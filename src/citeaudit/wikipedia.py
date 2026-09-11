"""
Wikipedia corpus: bibliographies written by non-specialists.

Why a third corpus
------------------
The business case rests on an extrapolation, and it is the load-bearing
assumption in this whole project: that a rate measured on arXiv preprints tells
you something about consulting deliverables and government reports.

It might not. Physicists writing LaTeX bibliographies with reference managers
are not analysts assembling a client report under deadline. Stating that as a
limitation is necessary but not sufficient — a limitation you can bound is
worth far more than one you merely disclose.

Wikipedia bounds it. Its citations are written by non-specialists, in
inconsistent styles, mixing journal articles with news, government reports,
books and bare URLs, with no reference manager and no publisher pipeline
anywhere in the process. In character that is much closer to a consulting
report's bibliography than a physics preprint is.

So the three corpora span the plausible range:

    Publisher-deposited   machine pipeline, validated at source
    arXiv preprints       expert authors, reference managers, no publisher
    Wikipedia             non-expert authors, mixed sources, no pipeline

If the rate is stable across the second and third, the extrapolation is
defensible. If it moves a lot, the spread is the honest error bar on any claim
about a corpus none of us can sample.

What is not claimed
-------------------
This is not an audit of Wikipedia and nothing here is a judgment about its
reliability. The unit of analysis is the reference. Results are aggregate, no
article is named, and an unverifiable reference is not a false one — Wikipedia
cites a great deal of material that no scholarly index covers, which is exactly
the point of including it.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .extract import normalise_doi
from .http import Client, NotFound, Unreachable
from .models import Citation, Kind, Verdict
from .verify import Verifier

log = logging.getLogger(__name__)

API = "https://en.wikipedia.org/w/api.php"

# {{cite journal |title=... |doi=... }} and friends. Nested templates are
# skipped rather than parsed: a template this tool mangles produces an
# unverifiable reference, never a false one.
CITE_TEMPLATE_RE = re.compile(
    r"\{\{\s*[Cc]ite\s+(journal|book|report|web|news|conference|thesis|arxiv)\s*"
    r"\|(?P<body>[^{}]{0,2000}?)\}\}",
    re.S,
)

PARAM_RE = re.compile(r"\|\s*([A-Za-z0-9_\-]+)\s*=\s*([^|]*)")

# Wikilinks must be resolved BEFORE template parameters are split, because the
# pipe in [[target|label]] is the same character that separates parameters.
# Splitting first truncates every title that contains a link.
WIKILINK_RE = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
WIKI_MARKUP = re.compile(r"'''|''|<[^>]+>")
WS = re.compile(r"\s+")


def resolve_wikilinks(text: str) -> str:
    """[[target|label]] -> label, and [[page]] -> page."""
    return WIKILINK_RE.sub(r"\1", text or "")


def clean_wikitext(text: str) -> str:
    out = WIKI_MARKUP.sub("", resolve_wikilinks(text))
    return WS.sub(" ", out).strip()


@dataclass
class WikiReference:
    template: str
    title: str | None
    doi: str | None
    arxiv: str | None
    authors: list[str] = field(default_factory=list)
    year: int | None = None


def parse_citations(wikitext: str) -> list[WikiReference]:
    """Extract structured references from a page's citation templates."""
    refs: list[WikiReference] = []

    for m in CITE_TEMPLATE_RE.finditer(wikitext):
        kind = m.group(1).lower()
        # Resolve links first: their pipes would otherwise be read as parameter
        # separators and truncate any title containing one.
        body = resolve_wikilinks(m.group("body"))
        params = {k.lower(): clean_wikitext(v)
                  for k, v in PARAM_RE.findall("|" + body)}

        title = params.get("title") or params.get("chapter")
        doi = params.get("doi") or ""
        arxiv = params.get("arxiv") or params.get("eprint") or ""

        year = None
        for key in ("year", "date", "publication-date"):
            raw = params.get(key, "")
            ym = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", raw)
            if ym:
                year = int(ym.group(1))
                break

        authors = []
        for key in ("last", "last1", "author", "author1", "surname"):
            v = params.get(key)
            if v:
                authors.append(v.split(",")[0].strip().split()[-1]
                               if v.split() else v)
                break

        if not (title and len(title) >= 15):
            continue

        refs.append(WikiReference(
            template=kind,
            title=title,
            doi=normalise_doi(doi) if doi else None,
            arxiv=arxiv.strip() or None,
            authors=[a for a in authors if a],
            year=year,
        ))
    return refs


def sample_articles(client: Client, *, count: int, min_bytes: int = 30_000
                    ) -> list[str]:
    """
    Random article titles, biased toward substantial pages.

    Wikipedia's `random` generator is uniform over all articles, and most
    articles are stubs with no references at all. Filtering by size keeps the
    sample to pages that actually carry a bibliography, which is what is being
    measured.
    """
    titles: list[str] = []
    seen: set[str] = set()

    for _ in range(max(1, count // 20 + 2)):
        params = {
            "action": "query", "format": "json",
            "generator": "random", "grnnamespace": "0",
            "grnlimit": "50", "prop": "info",
        }
        url = f"{API}?{urllib.parse.urlencode(params)}"
        try:
            data = client.get(url).json()
        except (NotFound, Unreachable) as exc:
            log.warning("wikipedia sampling failed: %s", exc)
            break

        for page in (data.get("query") or {}).get("pages", {}).values():
            t = page.get("title")
            if not t or t in seen:
                continue
            if (page.get("length") or 0) < min_bytes:
                continue
            seen.add(t)
            titles.append(t)
            if len(titles) >= count:
                return titles
    return titles


def fetch_wikitext(client: Client, title: str) -> str:
    params = {
        "action": "query", "format": "json", "prop": "revisions",
        "rvprop": "content", "rvslots": "main",
        "titles": title, "formatversion": "2",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    try:
        data = client.get(url).json()
    except (NotFound, Unreachable):
        return ""
    for page in (data.get("query") or {}).get("pages", []):
        for slot in (page.get("revisions") or [{}])[0].get("slots", {}).values():
            return slot.get("content") or ""
    return ""


@dataclass
class WikiCheck:
    article: str
    template: str
    kind: str
    identifier: str | None
    claimed_title: str | None
    verdict: str
    authority: str
    detail: str = ""


@dataclass
class WikiStudy:
    checks: list[WikiCheck] = field(default_factory=list)
    articles_sampled: int = 0
    articles_with_citations: int = 0
    started_utc: str = ""
    finished_utc: str = ""


def run(client: Client, *, articles: int = 120, max_refs_per_article: int = 8,
        max_checks: int = 900, workers: int = 4) -> WikiStudy:
    verifier = Verifier(client, check_urls=False, workers=workers)
    study = WikiStudy(
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    for title in sample_articles(client, count=articles):
        study.articles_sampled += 1
        wikitext = fetch_wikitext(client, title)
        if not wikitext:
            continue

        refs = parse_citations(wikitext)[:max_refs_per_article]
        if not refs:
            continue
        study.articles_with_citations += 1

        for ref in refs:
            if ref.doi:
                cit = Citation(raw=ref.doi, kind=Kind.DOI, identifier=ref.doi,
                               claimed_title=ref.title,
                               claimed_authors=ref.authors, claimed_year=ref.year)
            elif ref.arxiv:
                cit = Citation(raw=ref.arxiv, kind=Kind.ARXIV,
                               identifier=ref.arxiv, claimed_title=ref.title,
                               claimed_authors=ref.authors, claimed_year=ref.year)
            else:
                cit = Citation(raw=ref.title or "", kind=Kind.BIBLIOGRAPHIC,
                               claimed_title=ref.title,
                               claimed_authors=ref.authors, claimed_year=ref.year)

            f = verifier.check(cit)
            study.checks.append(WikiCheck(
                article=title, template=ref.template, kind=cit.kind.value,
                identifier=cit.identifier, claimed_title=ref.title,
                verdict=f.verdict.value, authority=f.authority,
                detail=f.detail[:200],
            ))
            if len(study.checks) >= max_checks:
                study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return study

    study.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return study


def summarise(study: WikiStudy) -> dict:
    from collections import Counter
    from .corpus import wilson_interval

    def block(checks: list[WikiCheck]) -> dict:
        counts = Counter(c.verdict for c in checks)
        conclusive = [c for c in checks if not Verdict(c.verdict).is_inconclusive]
        failed = [c for c in conclusive if Verdict(c.verdict).is_failure]
        lo, hi = wilson_interval(len(failed), len(conclusive)) if conclusive else (None, None)
        return {
            "checks": len(checks), "conclusive": len(conclusive),
            "verified": counts.get(Verdict.VERIFIED.value, 0),
            "not_found": counts.get(Verdict.NOT_FOUND.value, 0),
            "mismatch": counts.get(Verdict.MISMATCH.value, 0),
            "unverified_rate": len(failed) / len(conclusive) if conclusive else None,
            "unverified_ci95": [lo, hi],
        }

    return {
        "method": {
            "corpus": "English Wikipedia citation templates",
            "articles_sampled": study.articles_sampled,
            "articles_with_citations": study.articles_with_citations,
            "total_checks": len(study.checks),
            "started_utc": study.started_utc,
            "finished_utc": study.finished_utc,
            "claim_boundary": (
                "Not an audit of Wikipedia and not a judgment about its "
                "reliability. The unit is the reference; results are aggregate "
                "and no article is named. Wikipedia cites a great deal of "
                "material no scholarly index covers, so an unverifiable "
                "reference here is expected, not an error."
            ),
        },
        "overall": block(study.checks),
        "by_template": {
            t: block([c for c in study.checks if c.template == t])
            for t in sorted({c.template for c in study.checks})
        },
        "by_reference_kind": {
            k: block([c for c in study.checks if c.kind == k])
            for k in sorted({c.kind for c in study.checks})
        },
    }


def to_markdown(summary: dict) -> str:
    m, o = summary["method"], summary["overall"]

    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"

    def ci(b):
        c = b.get("unverified_ci95") or [None, None]
        return "-" if c[0] is None else f"{c[0]:.1%}-{c[1]:.1%}"

    out = []
    out.append("# Non-expert bibliographies: bounding the extrapolation")
    out.append("")
    out.append(
        f"**{m['total_checks']:,} references** from "
        f"**{m['articles_with_citations']:,} randomly sampled Wikipedia "
        f"articles** ({m['articles_sampled']:,} drawn)."
    )
    out.append("")
    out.append("## Why this corpus")
    out.append("")
    out.append(
        "The business case rests on an extrapolation from arXiv preprints to "
        "consulting deliverables, and that is the load-bearing assumption in "
        "the whole project. Physicists using reference managers are not "
        "analysts assembling a client report under deadline."
    )
    out.append("")
    out.append(
        "Wikipedia bounds it. Citations there are written by non-specialists "
        "in inconsistent styles, mixing journal articles with news, government "
        "reports, books and bare URLs, with no reference manager and no "
        "publisher pipeline. In character that is much closer to a consulting "
        "bibliography than a physics preprint is."
    )
    out.append("")
    out.append("## What is not claimed")
    out.append("")
    out.append(m["claim_boundary"])
    out.append("")
    out.append("## Result")
    out.append("")
    out.append(
        f"**Unverified rate {pct(o['unverified_rate'])}** of "
        f"{o['conclusive']:,} conclusive checks (95% CI {ci(o)})."
    )
    out.append("")
    out.append("| | count |")
    out.append("|---|---:|")
    out.append(f"| Verified | {o['verified']:,} |")
    out.append(f"| Not found | {o['not_found']:,} |")
    out.append(f"| Resolves to a different work | {o['mismatch']:,} |")
    out.append("")

    if summary.get("by_reference_kind"):
        out.append("### By how the reference was given")
        out.append("")
        out.append("| Form | Conclusive | Unverified |")
        out.append("|---|---:|---:|")
        for k, b in sorted(summary["by_reference_kind"].items()):
            out.append(f"| {k} | {b['conclusive']:,} | {pct(b['unverified_rate'])} |")
        out.append("")

    if summary.get("by_template"):
        out.append("### By source type")
        out.append("")
        out.append("| Template | Conclusive | Unverified |")
        out.append("|---|---:|---:|")
        for t, b in sorted(summary["by_template"].items()):
            out.append(f"| cite {t} | {b['conclusive']:,} | {pct(b['unverified_rate'])} |")
        out.append("")
        out.append(
            "The split by source type is the useful part. `cite journal` sits "
            "inside scholarly indexing; `cite report`, `cite book` and `cite "
            "news` largely do not, and a consulting bibliography is full of "
            "the latter. Their rate is the better guide to what a grey-"
            "literature document would score."
        )
        out.append("")

    out.append("## Limits")
    out.append("")
    out.append(
        "- Sampling is biased toward substantial articles. Stubs carry no "
        "bibliography, so including them would measure nothing."
    )
    out.append(
        "- Wikipedia is community-audited, with a culture of challenging "
        "unsourced claims. That plausibly makes it CLEANER than an unreviewed "
        "consulting report, so this is a lower bound on the target corpus, not "
        "an estimate of it."
    )
    out.append(
        "- Citation templates are parsed structurally. References written as "
        "free text outside a template are not captured at all."
    )
    return "\n".join(out)


def write_outputs(study: WikiStudy, summary: dict, directory) -> None:
    import csv
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
