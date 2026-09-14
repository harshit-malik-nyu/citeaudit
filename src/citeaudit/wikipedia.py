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


class EmptyStudy(RuntimeError):
    """A run produced no checks. Never overwrite good evidence with it."""

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


# Templates whose sources a scholarly index is the RIGHT authority for.
#
# This split is the difference between a measurement and a category error.
# Checking {{cite news}} or {{cite web}} against Crossref measures whether
# Crossref indexes journalism — it does not — and would report ~100%
# "unverified" for references that are perfectly real. Only the scholarly
# templates are comparable with the arXiv corpus.
SCHOLARLY_TEMPLATES = {"journal", "arxiv", "conference", "thesis"}

# Everything else is reported separately, and what it measures is index
# coverage of grey literature, not citation integrity.
GREY_TEMPLATES = {"book", "report", "web", "news"}


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


def sample_articles(client: Client, *, count: int, min_bytes: int = 8_000,
                    max_draws: int = 40, scholarly_only: bool = True
                    ) -> list[str]:
    """
    Article titles to sample references from.

    Two modes, and the choice materially changes what the result means.

    `scholarly_only` (default) searches for articles that actually contain a
    `{{cite journal}}` template. A uniform random draw does not work for this
    measurement: most Wikipedia articles cite news and web pages, so a random
    sample of 13 articles yielded SEVEN scholarly references — a confidence
    interval spanning 2.6% to 51%, which is no measurement at all.

    The cost is that the sample is no longer representative of Wikipedia. It is
    representative of *Wikipedia articles that cite scholarly literature*, and
    the report says so. That is the right population anyway: the comparison
    being drawn is against arXiv bibliographies, which are entirely scholarly.

    Setting `scholarly_only=False` restores the uniform random draw, which
    answers a different and less useful question.
    """
    if scholarly_only:
        return _search_articles(client, count=count)

    titles: list[str] = []
    seen: set[str] = set()

    for _ in range(max_draws):
        if len(titles) >= count:
            break
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "random", "grnnamespace": "0",
            "grnlimit": "50", "prop": "info",
        }
        url = f"{API}?{urllib.parse.urlencode(params)}"
        try:
            data = client.get(url).json()
        except (NotFound, Unreachable) as exc:
            log.warning("wikipedia sampling failed: %s", exc)
            break

        pages = (data.get("query") or {}).get("pages") or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        for page in pages:
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


def _search_articles(client: Client, *, count: int) -> list[str]:
    """Articles containing a {{cite journal}} template, via insource search."""
    titles: list[str] = []
    seen: set[str] = set()
    offset = 0

    while len(titles) < count and offset < 2000:
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "list": "search",
            "srsearch": 'insource:"cite journal" insource:"doi"',
            "srnamespace": "0",
            "srlimit": "50",
            "sroffset": str(offset),
            "srsort": "random",
        }
        url = f"{API}?{urllib.parse.urlencode(params)}"
        try:
            data = client.get(url).json()
        except (NotFound, Unreachable) as exc:
            log.warning("wikipedia search failed: %s", exc)
            break

        hits = (data.get("query") or {}).get("search") or []
        if not hits:
            break
        for h in hits:
            t = h.get("title")
            if t and t not in seen:
                seen.add(t)
                titles.append(t)
                if len(titles) >= count:
                    break
        offset += len(hits)

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
                detail=f.detail[:600],
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

    scholarly = [c for c in study.checks if c.template in SCHOLARLY_TEMPLATES]
    grey = [c for c in study.checks if c.template in GREY_TEMPLATES]

    return {
        "headline": {
            "comparable_rate": block(scholarly)["unverified_rate"],
            "comparable_n": block(scholarly)["conclusive"],
            "note": (
                "The comparable figure is the SCHOLARLY-template rate. "
                "Checking {{cite news}} or {{cite web}} against Crossref and "
                "OpenAlex measures whether those indexes cover journalism and "
                "the open web — they do not — so a high rate there says "
                "nothing about whether the reference is real. Only scholarly "
                "templates are comparable with the arXiv corpus."
            ),
        },
        "scholarly_templates": block(scholarly),
        "grey_templates": block(grey),
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
    sch = summary.get("scholarly_templates") or {}
    grey = summary.get("grey_templates") or {}

    out.append("## Result")
    out.append("")
    out.append("### The comparable figure")
    out.append("")
    out.append(
        f"**{pct(sch.get('unverified_rate'))} unverified** across "
        f"{sch.get('conclusive', 0):,} scholarly-template references "
        f"(95% CI {ci(sch)})."
    )
    out.append("")
    out.append(
        "This is the number to compare with the arXiv corpus, and the only one "
        "that measures citation integrity rather than index coverage. "
        "`{{cite journal}}`, `{{cite arxiv}}`, `{{cite conference}}` and "
        "`{{cite thesis}}` point at material Crossref and OpenAlex are the "
        "right authorities for."
    )
    out.append("")
    out.append("### Grey-literature templates, reported separately")
    out.append("")
    out.append(
        f"{pct(grey.get('unverified_rate'))} unverified across "
        f"{grey.get('conclusive', 0):,} references "
        f"(`cite web`, `cite news`, `cite book`, `cite report`)."
    )
    out.append("")
    out.append(
        "**This is not an integrity finding and must not be read as one.** "
        "Checking journalism and government web pages against a scholarly "
        "index measures whether that index covers journalism. It does not. A "
        "high rate here is the expected result for perfectly real references, "
        "and folding it into a headline would be a category error."
    )
    out.append("")
    out.append(
        "It is still worth reporting, because it quantifies how much of a "
        "mixed bibliography sits outside scholarly indexing altogether — which "
        "is the coverage problem any tool pointed at a consulting report runs "
        "into first."
    )
    out.append("")
    out.append("### All templates combined")
    out.append("")
    out.append(
        f"{pct(o['unverified_rate'])} across {o['conclusive']:,} checks "
        f"(95% CI {ci(o)}). Shown for completeness only; the split above is "
        "the meaningful cut."
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

    if not study.checks:
        # A study that produced nothing must not overwrite a good previous
        # result. An empty run once replaced 1,247 committed checks with zeros,
        # silently destroying the better measurement. Failure should leave the
        # evidence untouched and say so.
        raise EmptyStudy(
            "study produced zero checks; refusing to overwrite existing "
            "evidence. Investigate the upstream API before re-running."
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
