"""
Preprint corpus study: bibliographies as authors actually write them.

Why this exists
---------------
The base-rate study measures references that *publishers deposited* — cleaned,
structured, DOI-bearing metadata produced by a production pipeline. It found
essentially perfect integrity: zero of 307 deposited reference DOIs failed to
resolve.

Nobody writes a bibliography that way.

A consulting report, a policy paper, a memo, a draft manuscript — these carry
references as a human (or a language model) typed them: inconsistent styles,
missing identifiers, abbreviated journals, transcription errors. That is the
corpus where fabrication has actually been found, and the deposited-metadata
base rate says nothing about it.

arXiv source packages contain the author's own `.bbl` or `.bib` file: the
bibliography exactly as written, before any publisher touched it. That makes
arXiv the closest public proxy available for author-written reference lists, at
a scale that can be sampled reproducibly.

What is and is not claimed
--------------------------
This measures how often a reference *as written* can be verified. A reference
that cannot be verified is not thereby fabricated — the far likelier
explanations are a thin citation, a non-indexed venue, or a transcription
error, and the base-rate study exists precisely to keep those from being
misread.

Results are reported in aggregate. Individual papers are not named, and no
claim is made about any author. The unit of analysis is the reference, not the
researcher.
"""

from __future__ import annotations

import io
import logging
import re
import tarfile
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from .extract import extract
from .http import Client, NotFound, Unreachable
from .models import Citation, Kind, Verdict
from .verify import Verifier

log = logging.getLogger(__name__)

ARXIV_QUERY = "https://export.arxiv.org/api/query"
ARXIV_SOURCE = "https://export.arxiv.org/e-print/"
ATOM = "{http://www.w3.org/2005/Atom}"


# ---------------------------------------------------------------------------
# Bibliography extraction from LaTeX sources
# ---------------------------------------------------------------------------

BIBITEM_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{[^}]*\}", re.S)

# LaTeX commands that wrap content we want to keep the argument of.
UNWRAP = re.compile(
    r"\\(?:emph|textit|textbf|texttt|mbox|text|href\{[^}]*\}|url|doi|newblock)"
    r"\s*\{([^{}]*)\}"
)
BARE_COMMAND = re.compile(r"\\[a-zA-Z@]+\s*")
BRACES = re.compile(r"[{}]")
WS = re.compile(r"\s+")


def delatex(text: str) -> str:
    """
    Reduce a LaTeX bibliography entry to the plain text a reader would see.

    Deliberately shallow. A full LaTeX parser is a project of its own, and the
    goal here is only to recover enough title and author text for verification.
    Entries that survive this badly are reported as unverifiable rather than
    guessed at.
    """
    out = text
    for _ in range(3):                      # resolve shallow nesting
        out = UNWRAP.sub(r"\1", out)
    out = re.sub(r"\\%", "%", out)
    out = re.sub(r"\\&", "&", out)
    out = re.sub(r"``|''", '"', out)
    out = re.sub(r"~", " ", out)
    out = BARE_COMMAND.sub(" ", out)
    out = BRACES.sub("", out)
    return WS.sub(" ", out).strip()


def split_bibitems(bbl: str) -> list[str]:
    """Split a .bbl body into one string per reference."""
    parts = BIBITEM_RE.split(bbl)
    if len(parts) <= 1:
        return []
    entries = []
    for raw in parts[1:]:
        # An entry ends at \end{thebibliography} if present.
        raw = raw.split(r"\end{thebibliography}")[0]
        text = delatex(raw)
        if 30 <= len(text) <= 1200:
            entries.append(text)
    return entries


def parse_bibtex(bib: str) -> list[str]:
    """Recover reference strings from a .bib file."""
    entries = []
    for block in re.split(r"@\w+\s*\{", bib)[1:]:
        fields = dict(re.findall(
            r"(\w+)\s*=\s*[{\"]([^{}\"]{2,400})[}\"]", block
        ))
        title = fields.get("title", "").strip()
        if len(title) < 15:
            continue
        author = fields.get("author", "").split(" and ")[0].strip()
        year = fields.get("year", "").strip()
        doi = fields.get("doi", "").strip()
        parts = [p for p in (author, f"({year})" if year else "",
                             f'"{title}"', fields.get("journal", ""),
                             f"doi:{doi}" if doi else "") if p]
        entries.append(delatex(" ".join(parts)))
    return entries


def bibliography_from_source(blob: bytes) -> list[str]:
    """
    Pull reference strings out of an arXiv source package.

    Sources arrive as a gzipped tar of the LaTeX project, or occasionally a
    bare gzipped .tex file. Both are handled; anything else is skipped rather
    than guessed at.
    """
    entries: list[str] = []

    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            members = [m for m in tar.getmembers() if m.isfile()]
            # .bbl first: it is the rendered bibliography, closest to what a
            # reader sees. .bib is the source database and may contain entries
            # the paper never cites.
            for suffix, parser in ((".bbl", split_bibitems),
                                   (".bib", parse_bibtex)):
                for m in members:
                    if not m.name.lower().endswith(suffix):
                        continue
                    fh = tar.extractfile(m)
                    if not fh:
                        continue
                    text = fh.read().decode("utf-8", errors="replace")
                    entries.extend(parser(text))
                if entries:
                    return entries

            # Fall back to an embedded thebibliography environment in the .tex
            for m in members:
                if not m.name.lower().endswith(".tex"):
                    continue
                fh = tar.extractfile(m)
                if not fh:
                    continue
                text = fh.read().decode("utf-8", errors="replace")
                if r"\begin{thebibliography}" in text:
                    body = text.split(r"\begin{thebibliography}", 1)[1]
                    entries.extend(split_bibitems(body))
            return entries

    except (tarfile.TarError, EOFError, OSError):
        return []


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def sample_preprints(client: Client, *, categories: list[str],
                     per_category: int) -> Iterator[tuple[str, str, str]]:
    """
    Yield (arxiv_id, primary_category, title) for recent preprints.

    Sampled across categories so the result is not a statement about one
    field's citation habits. arXiv's API orders by submission date; this takes
    a recent window rather than a uniform random draw, which is a real
    limitation and is reported as one.
    """
    import xml.etree.ElementTree as ET

    for cat in categories:
        params = {
            "search_query": f"cat:{cat}",
            "start": "0",
            "max_results": str(per_category),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_QUERY}?{urllib.parse.urlencode(params)}"
        try:
            body = client.get(url, accept="application/atom+xml").text()
            root = ET.fromstring(body)
        except (NotFound, Unreachable, ET.ParseError) as exc:
            log.warning("arXiv sampling failed for %s: %s", cat, exc)
            continue

        for entry in root.findall(f"{ATOM}entry"):
            id_el = entry.find(f"{ATOM}id")
            title_el = entry.find(f"{ATOM}title")
            if id_el is None or not id_el.text:
                continue
            aid = id_el.text.rstrip("/").split("/abs/")[-1]
            title = " ".join((title_el.text or "").split()) if title_el is not None else ""
            yield aid, cat, title


def fetch_source(client: Client, arxiv_id: str) -> bytes | None:
    try:
        resp = client.get(f"{ARXIV_SOURCE}{arxiv_id}", accept="*/*")
    except (NotFound, Unreachable):
        return None
    return resp.body if resp.body else None


# ---------------------------------------------------------------------------
# Study
# ---------------------------------------------------------------------------

@dataclass
class PreprintCheck:
    arxiv_id: str
    category: str
    reference_text: str
    kind: str
    identifier: str | None
    verdict: str
    authority: str
    detail: str = ""


@dataclass
class PreprintStudy:
    checks: list[PreprintCheck] = field(default_factory=list)
    papers_sampled: int = 0
    papers_with_bibliography: int = 0
    started_utc: str = ""
    finished_utc: str = ""


def run(client: Client, *, categories: list[str], per_category: int = 8,
        max_refs_per_paper: int = 12, max_checks: int = 1200,
        workers: int = 4) -> PreprintStudy:
    verifier = Verifier(client, check_urls=False, workers=workers)
    study = PreprintStudy(
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    for aid, cat, _title in sample_preprints(
        client, categories=categories, per_category=per_category
    ):
        study.papers_sampled += 1
        blob = fetch_source(client, aid)
        if not blob:
            continue

        entries = bibliography_from_source(blob)
        if not entries:
            continue
        study.papers_with_bibliography += 1

        citations: list[Citation] = []
        for entry in entries[:max_refs_per_paper]:
            found = extract("References\n\n[1] " + entry)
            citations.extend(found)

        for c in citations:
            f = verifier.check(c)
            study.checks.append(PreprintCheck(
                arxiv_id=aid, category=cat,
                reference_text=c.context[:300],
                kind=c.kind.value, identifier=c.identifier,
                verdict=f.verdict.value, authority=f.authority,
                detail=f.detail[:200],
            ))
            if len(study.checks) >= max_checks:
                study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return study

    study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return study


def summarise(study: PreprintStudy) -> dict:
    from collections import Counter, defaultdict
    from .corpus import wilson_interval

    def block(checks: list[PreprintCheck]) -> dict:
        counts = Counter(c.verdict for c in checks)
        conclusive = [c for c in checks if not Verdict(c.verdict).is_inconclusive]
        failed = [c for c in conclusive if Verdict(c.verdict).is_failure]
        lo, hi = wilson_interval(len(failed), len(conclusive)) if conclusive else (None, None)
        return {
            "checks": len(checks),
            "conclusive": len(conclusive),
            "verified": counts.get(Verdict.VERIFIED.value, 0),
            "not_found": counts.get(Verdict.NOT_FOUND.value, 0),
            "mismatch": counts.get(Verdict.MISMATCH.value, 0),
            "unverifiable": counts.get(Verdict.UNVERIFIABLE.value, 0),
            "unreachable": counts.get(Verdict.UNREACHABLE.value, 0),
            "unverified_rate": len(failed) / len(conclusive) if conclusive else None,
            "unverified_ci95": [lo, hi],
        }

    by_kind: dict[str, dict] = {}
    for kind in {c.kind for c in study.checks}:
        by_kind[kind] = block([c for c in study.checks if c.kind == kind])

    by_cat: dict[str, dict] = {}
    for cat in {c.category for c in study.checks}:
        by_cat[cat] = block([c for c in study.checks if c.category == cat])

    return {
        "method": {
            "corpus": "arXiv author-written bibliographies (.bbl / .bib source)",
            "papers_sampled": study.papers_sampled,
            "papers_with_bibliography": study.papers_with_bibliography,
            "total_checks": len(study.checks),
            "started_utc": study.started_utc,
            "finished_utc": study.finished_utc,
            "claim_boundary": (
                "Measures whether a reference as written can be verified. An "
                "unverified reference is NOT thereby fabricated. Reported in "
                "aggregate; no paper is named and no claim is made about any "
                "author."
            ),
        },
        "overall": block(study.checks),
        "by_reference_kind": by_kind,
        "by_category": by_cat,
    }


def to_markdown(summary: dict) -> str:
    m = summary["method"]
    o = summary["overall"]

    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"

    def ci(b):
        c = b.get("unverified_ci95") or [None, None]
        return "—" if c[0] is None else f"{c[0]:.1%}–{c[1]:.1%}"

    out: list[str] = []
    out.append("# Author-written bibliographies: what happens outside the pipeline")
    out.append("")
    out.append(
        f"**{m['total_checks']:,} references** from "
        f"**{m['papers_with_bibliography']:,} arXiv preprints** "
        f"({m['papers_sampled']:,} sampled), parsed from the authors' own "
        "`.bbl` and `.bib` source files."
    )
    out.append("")
    out.append("## Why a second corpus")
    out.append("")
    out.append(
        "The base-rate study measured references that *publishers deposited* — "
        "cleaned, structured, DOI-bearing metadata from a production pipeline. "
        "It found essentially perfect integrity: zero of 307 deposited "
        "reference DOIs failed to resolve."
    )
    out.append("")
    out.append(
        "Nobody writes a bibliography that way. A consulting report, a policy "
        "paper or a draft manuscript carries references as a human or a "
        "language model typed them. arXiv source packages contain the author's "
        "bibliography before any publisher touched it, which makes them the "
        "closest public proxy for that corpus."
    )
    out.append("")
    out.append("## What this does and does not claim")
    out.append("")
    out.append(m["claim_boundary"])
    out.append("")
    out.append("## Headline")
    out.append("")
    out.append("| | count |")
    out.append("|---|---:|")
    out.append(f"| References checked | {o['checks']:,} |")
    out.append(f"| Verified | {o['verified']:,} |")
    out.append(f"| Not found | {o['not_found']:,} |")
    out.append(f"| Resolves to a different work | {o['mismatch']:,} |")
    out.append(f"| Not machine-checkable | {o['unverifiable']:,} |")
    out.append(f"| Could not check | {o['unreachable']:,} |")
    out.append("")
    out.append(
        f"**Unverified rate: {pct(o['unverified_rate'])}** of "
        f"{o['conclusive']:,} conclusive checks (95% CI {ci(o)})."
    )
    out.append("")

    if summary.get("by_reference_kind"):
        out.append("## By how the reference was written")
        out.append("")
        out.append("| Form | Conclusive | Unverified | 95% CI |")
        out.append("|---|---:|---:|---|")
        for kind, b in sorted(summary["by_reference_kind"].items()):
            out.append(
                f"| {kind} | {b['conclusive']:,} | "
                f"{pct(b['unverified_rate'])} | {ci(b)} |"
            )
        out.append("")
        out.append(
            "The gap between identifier-bearing and description-only "
            "references is the cost of omitting a DOI, measured rather than "
            "asserted."
        )
        out.append("")

    if summary.get("by_category"):
        out.append("## By field")
        out.append("")
        out.append("| Category | Conclusive | Unverified |")
        out.append("|---|---:|---:|")
        for cat, b in sorted(summary["by_category"].items()):
            out.append(f"| {cat} | {b['conclusive']:,} | {pct(b['unverified_rate'])} |")
        out.append("")

    out.append("## Limits")
    out.append("")
    out.append(
        "- Preprints are a *proxy* for author-written bibliographies, not the "
        "target corpus. Consulting deliverables and government reports are not "
        "publicly samplable at scale, which is why no base rate for them "
        "exists and why this stands in."
    )
    out.append(
        "- Sampling takes a recent window per category by submission date, not "
        "a uniform random draw, so the result reflects current practice rather "
        "than the historical corpus."
    )
    out.append(
        "- LaTeX parsing is shallow. Entries it mangles are reported as "
        "unverifiable rather than guessed at, so parsing failure inflates the "
        "inconclusive count, never the unverified rate."
    )
    out.append(
        "- An unverified reference is not a fabricated one. Thin citations, "
        "non-indexed venues and transcription errors all land here, and the "
        "base-rate study exists to keep those from being misread."
    )
    return "\n".join(out)


def write_outputs(study: PreprintStudy, summary: dict, directory) -> None:
    import csv, json
    from dataclasses import asdict
    from pathlib import Path

    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    (d / "report.md").write_text(to_markdown(summary))

    if study.checks:
        with (d / "checks.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(asdict(study.checks[0]).keys()))
            w.writeheader()
            for c in study.checks:
                w.writerow(asdict(c))
