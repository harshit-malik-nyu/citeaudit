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

from .corpus import power_banner
from .extract import extract
from .http import Client, NotFound, Unreachable
from .models import Citation, Verdict
from .verify import Verifier

log = logging.getLogger(__name__)


class EmptyStudy(RuntimeError):
    """A run produced no checks. Never overwrite good evidence with it."""


class DegradedStudy(RuntimeError):
    """
    A run produced far fewer checks than the evidence it would replace.

    Emptiness was not the only way to destroy a measurement. A throttled run
    returning 87 checks overwrote one with 1,247 — the guard let it through
    because 87 is not zero. Fewer observations is a worse measurement, and
    replacing a good one with it needs to be a decision, not an accident.
    """


def _existing_check_count(directory) -> int:
    from pathlib import Path
    import json as _json
    f = Path(directory) / "summary.json"
    if not f.exists():
        return 0
    try:
        return int(_json.loads(f.read_text())["method"]["total_checks"])
    except (ValueError, KeyError, TypeError, OSError):
        return 0

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

def sample_via_openalex(client: Client, *, count: int, seed: int
                        ) -> list[tuple[str, str, str]]:
    """
    Draw arXiv preprint identifiers from OpenAlex instead of from arXiv.

    arXiv rate-limits by IP, and GitHub Actions runners share address space
    with every other project on the platform. Correct pacing on our side does
    not help when the quota is already spent by someone else: eleven of twelve
    category queries came back HTTP 429 across consecutive runs.

    OpenAlex indexes arXiv preprints and assigns them DOIs under the 10.48550
    prefix, from which the arXiv identifier reads directly. Sampling there
    halves the load on arXiv — only the source tarballs still need it — and
    moves the fragile step onto an API that publishes a polite pool and honours
    a contact address.

    Returns (arxiv_id, concept_or_type, title). Falls back to the arXiv API
    when OpenAlex yields nothing, so the study degrades rather than vanishing.
    """
    params = {
        "filter": "type:preprint,has_doi:true",
        "sample": str(min(count, 200)),
        "seed": str(seed),
        "per-page": str(min(count, 200)),
        "select": "id,doi,title,primary_location,publication_year",
    }
    if client.mailto:
        params["mailto"] = client.mailto

    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    try:
        data = client.get(url).json()
    except (NotFound, Unreachable) as exc:
        log.error("OpenAlex preprint sampling failed: %s", exc)
        return []

    out: list[tuple[str, str, str]] = []
    for item in data.get("results") or []:
        doi = (item.get("doi") or "").lower().replace("https://doi.org/", "")
        if not doi.startswith("10.48550/arxiv."):
            continue
        arxiv_id = doi.split("arxiv.", 1)[1]
        title = item.get("title") or ""
        venue = ((item.get("primary_location") or {}).get("source") or {}
                 ).get("display_name") or "preprint"
        out.append((arxiv_id, venue, title))

    log.info("OpenAlex yielded %s arXiv preprints", len(out))
    return out


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

    failed_categories: list[str] = []
    yielded = 0

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
            # Loud, not silent. A run that sampled nothing previously logged a
            # warning nobody read and reported "0 papers" as though that were a
            # result, then overwrote 1,247 good checks with it.
            log.error("arXiv sampling FAILED for %s: %s", cat, exc)
            failed_categories.append(cat)
            continue

        entries = root.findall(f"{ATOM}entry")
        if not entries:
            log.error("arXiv returned an EMPTY feed for %s — this is usually "
                      "throttling. Check request pacing.", cat)
            failed_categories.append(cat)
            continue

        for entry in entries:
            id_el = entry.find(f"{ATOM}id")
            title_el = entry.find(f"{ATOM}title")
            if id_el is None or not id_el.text:
                continue
            aid = id_el.text.rstrip("/").split("/abs/")[-1]
            title = " ".join((title_el.text or "").split()) if title_el is not None else ""
            yielded += 1
            yield aid, cat, title

    if failed_categories:
        log.error("arXiv sampling failed for %s of %s categories: %s",
                  len(failed_categories), len(categories),
                  ", ".join(failed_categories))
    if yielded == 0:
        log.error("arXiv yielded NO papers across every category. The study "
                  "cannot proceed and must not report zero as a result.")


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


def load_existing_checks(directory) -> tuple[list[PreprintCheck], set[str]]:
    """
    Read checks already collected, and the arXiv ids they came from.

    Accumulation exists because a single run cannot reliably refresh this
    corpus. arXiv rate-limits by IP and GitHub runners share address space, so
    any given run may collect a hundred papers or none, and which one it is has
    nothing to do with this code.

    Rather than depend on a lucky run, each run contributes what it managed to
    fetch and skips papers already covered. An unreliable dependency becomes an
    eventually-sufficient one, and the sample only ever grows.
    """
    from pathlib import Path
    import csv as _csv

    path = Path(directory) / "checks.csv"
    if not path.exists():
        return [], set()

    rows: list[PreprintCheck] = []
    seen: set[str] = set()
    try:
        with path.open(newline="") as fh:
            for r in _csv.DictReader(fh):
                rows.append(PreprintCheck(
                    arxiv_id=r.get("arxiv_id", ""),
                    category=r.get("category", ""),
                    reference_text=r.get("reference_text", ""),
                    kind=r.get("kind", ""),
                    identifier=r.get("identifier") or None,
                    verdict=r.get("verdict", ""),
                    authority=r.get("authority", ""),
                    detail=r.get("detail", ""),
                ))
                if r.get("arxiv_id"):
                    seen.add(r["arxiv_id"])
    except (OSError, _csv.Error):
        return [], set()

    return rows, seen


@dataclass
class PreprintStudy:
    checks: list[PreprintCheck] = field(default_factory=list)
    papers_sampled: int = 0
    papers_with_bibliography: int = 0
    carried_checks: int = 0
    started_utc: str = ""
    finished_utc: str = ""


def run(client: Client, *, categories: list[str], per_category: int = 8,
        max_refs_per_paper: int = 12, max_checks: int = 1200,
        workers: int = 4, seed: int = 20260909,
        prefer_openalex: bool = True,
        accumulate_from=None) -> PreprintStudy:
    verifier = Verifier(client, check_urls=False, workers=workers)
    study = PreprintStudy(
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # Papers already covered by earlier runs are skipped, so a throttled run
    # spends its budget on new material rather than re-fetching what is done.
    already: set[str] = set()
    carried: list[PreprintCheck] = []
    if accumulate_from is not None:
        carried, already = load_existing_checks(accumulate_from)
        if carried:
            log.info("carrying %s checks from %s papers collected earlier",
                     len(carried), len(already))

    sampled: list[tuple[str, str, str]] = []
    if prefer_openalex:
        sampled = sample_via_openalex(
            client, count=per_category * len(categories), seed=seed)

    if not sampled:
        log.warning("falling back to the arXiv API for sampling")
        sampled = list(sample_preprints(
            client, categories=categories, per_category=per_category))

    sampled = [row for row in sampled if row[0] not in already]
    log.info("%s papers to fetch after skipping ones already collected",
             len(sampled))

    for aid, cat, _title in sampled:
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
                detail=f.detail[:600],
            ))
            if len(study.checks) >= max_checks:
                study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return study

    study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if carried:
        study.checks = carried + study.checks
        study.papers_with_bibliography += len(already)
        study.carried_checks = len(carried)

    return study


def summarise(study: PreprintStudy) -> dict:
    from collections import Counter
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
            "carried_from_earlier_runs": study.carried_checks,
            "collected_this_run": len(study.checks) - study.carried_checks,
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
        f"**{m['papers_with_bibliography']:,} arXiv preprints**, parsed from "
        "the authors' own `.bbl` and `.bib` source files."
    )
    out.append("")
    carried = m.get("carried_from_earlier_runs") or 0
    if carried:
        out.append(
            f"Accumulated across runs: {carried:,} references were collected "
            f"earlier and {m.get('collected_this_run', 0):,} were added by the "
            "most recent run."
        )
        out.append("")
        out.append(
            "arXiv rate-limits by IP and CI runners share address space, so "
            "any single run may collect a hundred papers or none for reasons "
            "unrelated to this code. Each run therefore contributes what it "
            "managed to fetch and skips papers already covered, rather than "
            "depending on one lucky execution. Stating the split matters: an "
            "accumulated total presented as a single run's output would "
            "overstate what any one execution achieved."
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
    out.extend(power_banner(o.get("conclusive", 0), o.get("unverified_ci95"),
                            "The unverified rate"))
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


# A run holding less than this share of the existing sample is a degradation,
# not an update.
DEGRADATION_RATIO = 0.5


def write_outputs(study: PreprintStudy, summary: dict, directory,
                  *, allow_smaller: bool = False) -> None:
    import csv, json
    from dataclasses import asdict
    from pathlib import Path

    if not study.checks:
        # A study that produced nothing must not overwrite a good previous
        # result. An empty run once replaced 1,247 committed checks with zeros,
        # silently destroying the better measurement. Failure should leave the
        # evidence untouched and say so.
        raise EmptyStudy(
            "study produced zero checks; refusing to overwrite existing "
            "evidence. Investigate the upstream API before re-running."
        )

    existing = _existing_check_count(directory)
    new_count = len(study.checks)
    if not allow_smaller and existing and new_count < existing * DEGRADATION_RATIO:
        raise DegradedStudy(
            f"run produced {new_count:,} checks against {existing:,} already "
            f"on record. Refusing to replace a larger sample with a smaller "
            f"one. Pass allow_smaller=True to override deliberately."
        )

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
