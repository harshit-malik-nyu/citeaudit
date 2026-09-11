"""
Base-rate study.

A document scores 62%. Is that bad? Nobody can say without knowing what normal
looks like, and that number does not exist anywhere in the literature. This
module measures it.

Design
------
The hard part of measuring a detector is obtaining ground truth. Here it comes
free, from a construction that makes it unarguable:

    Take real published papers. Take their deposited reference lists. Every
    reference in them describes a work that demonstrably exists — a publisher
    deposited it, and the cited DOI resolves.

    Now hide the DOI and hand citeaudit only what a bibliography shows: title,
    authors, year. Ask it whether the work exists.

Every NOT_FOUND in that setup is a **definite false positive**, because the
work provably exists. No labelling, no judgment calls, no annotator agreement
to worry about. The ground truth is established by the very deposit that
supplied the reference.

That yields the number the tool most needs and most lacks: how often does
citeaudit accuse a genuine reference of being fabricated.

Two measurements are taken:

    IDENTIFIED     References checked via their deposited DOI. Measures the
                   identifier path. Expected to be near-perfect; a failure here
                   is a client bug, not a coverage gap.

    DESCRIBED      The same references with the DOI withheld, checked by
                   description alone. Measures the search path, which is what
                   runs on the many real documents that cite without DOIs.
                   This is where the false-positive rate lives.

The gap between them is the cost of citing without identifiers, quantified.
"""

from __future__ import annotations

import json
import logging
import math
import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .http import Client, NotFound, Unreachable
from .models import Citation, Kind, Verdict
from .sources.crossref import BASE as CROSSREF_BASE
from .verify import Verifier

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson score interval for a binomial proportion.

    Used rather than the normal approximation because these rates sit near the
    boundaries, where the textbook interval produces bounds outside [0, 1] and
    understates uncertainty at small n. With per-stratum counts in the low
    hundreds, that difference is not cosmetic.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class Check:
    """One reference checked one way."""

    source_doi: str
    source_year: int | None
    source_type: str | None
    mode: str                      # "identified" | "described"
    reference_doi: str | None
    claimed_title: str | None
    claimed_authors: list[str] = field(default_factory=list)
    claimed_year: int | None = None
    verdict: str = ""
    authority: str = ""
    title_similarity: float | None = None
    detail: str = ""

    @property
    def is_false_positive(self) -> bool:
        """
        A genuine reference reported as non-existent.

        Only meaningful because ground truth is guaranteed by construction:
        these references carry DOIs deposited by publishers, so the works
        exist.
        """
        return self.verdict in (Verdict.NOT_FOUND.value, Verdict.MALFORMED.value)


@dataclass
class StudyResult:
    checks: list[Check] = field(default_factory=list)
    source_works: int = 0
    seed: int = 0
    started_utc: str = ""
    finished_utc: str = ""
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def sample_source_works(client: Client, *, per_year: int, years: list[int],
                        seed: int) -> Iterator[dict]:
    """
    Draw a stratified random sample of published works with reference lists.

    Stratified by publication year so that any trend over time can be read off
    directly, and because an unstratified draw from Crossref skews heavily to
    recent years and would confound coverage with recency.

    Crossref's `sample` parameter performs the randomisation server-side, which
    avoids downloading an index to draw from and is reproducible given the
    filter.
    """
    import urllib.parse

    for year in years:
        params = {
            "filter": (
                f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31,"
                "has-references:true,type:journal-article"
            ),
            "sample": str(min(per_year, 100)),
            "select": "DOI,title,reference,type,issued,publisher",
        }
        if client.mailto:
            params["mailto"] = client.mailto

        url = f"{CROSSREF_BASE}/works?{urllib.parse.urlencode(params)}"
        try:
            data = client.get(url).json()
        except (NotFound, Unreachable) as exc:
            log.warning("sampling failed for %s: %s", year, exc)
            continue

        for item in (data.get("message") or {}).get("items") or []:
            item["_stratum_year"] = year
            yield item


def references_of(work: dict, *, max_refs: int, rng: random.Random) -> list[dict]:
    """
    Usable references from a work's deposited list.

    Keeps only references that carry BOTH a DOI and a title. The DOI is what
    establishes ground truth; the title is what the described-mode check gets
    to work with. A reference lacking either cannot support the experiment.
    """
    usable = []
    for ref in work.get("reference") or []:
        doi = (ref.get("DOI") or "").strip().lower()
        title = (ref.get("article-title") or ref.get("volume-title") or "").strip()
        if not doi or len(title) < 15:
            continue
        usable.append(ref)

    if len(usable) > max_refs:
        usable = rng.sample(usable, max_refs)
    return usable


def _ref_year(ref: dict) -> int | None:
    raw = ref.get("year")
    if not raw:
        return None
    try:
        y = int(str(raw)[:4])
    except (TypeError, ValueError):
        return None
    return y if 1500 <= y <= 2100 else None


def _ref_authors(ref: dict) -> list[str]:
    a = (ref.get("author") or "").strip()
    return [a.split()[-1]] if a else []


# ---------------------------------------------------------------------------
# The study
# ---------------------------------------------------------------------------

def run_study(
    *,
    client: Client,
    years: list[int],
    per_year: int = 25,
    max_refs_per_work: int = 8,
    seed: int = 20260909,
    workers: int = 4,
    max_checks: int | None = None,
) -> StudyResult:
    """Execute the study and return every individual check."""
    rng = random.Random(seed)
    verifier = Verifier(client, check_urls=False, workers=workers)

    result = StudyResult(
        seed=seed,
        started_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    for work in sample_source_works(client, per_year=per_year, years=years, seed=seed):
        source_doi = (work.get("DOI") or "").lower()
        source_year = work.get("_stratum_year")
        refs = references_of(work, max_refs=max_refs_per_work, rng=rng)
        if not refs:
            continue
        result.source_works += 1

        for ref in refs:
            ref_doi = (ref.get("DOI") or "").strip().lower()
            title = (ref.get("article-title") or ref.get("volume-title") or "").strip()
            authors = _ref_authors(ref)
            year = _ref_year(ref)

            # --- identified: check via the deposited DOI --------------------
            cit_id = Citation(
                raw=ref_doi, kind=Kind.DOI, identifier=ref_doi,
                claimed_title=title, claimed_authors=authors, claimed_year=year,
            )
            f_id = verifier.check(cit_id)
            result.checks.append(Check(
                source_doi=source_doi, source_year=source_year,
                source_type=work.get("type"), mode="identified",
                reference_doi=ref_doi, claimed_title=title,
                claimed_authors=authors, claimed_year=year,
                verdict=f_id.verdict.value, authority=f_id.authority,
                title_similarity=f_id.title_similarity, detail=f_id.detail[:200],
            ))

            # --- described: same reference, DOI withheld --------------------
            cit_desc = Citation(
                raw=title, kind=Kind.BIBLIOGRAPHIC, identifier=None,
                claimed_title=title, claimed_authors=authors, claimed_year=year,
            )
            f_desc = verifier.check(cit_desc)
            result.checks.append(Check(
                source_doi=source_doi, source_year=source_year,
                source_type=work.get("type"), mode="described",
                reference_doi=ref_doi, claimed_title=title,
                claimed_authors=authors, claimed_year=year,
                verdict=f_desc.verdict.value, authority=f_desc.authority,
                title_similarity=f_desc.title_similarity,
                detail=f_desc.detail[:200],
            ))

            if max_checks and len(result.checks) >= max_checks:
                result.notes.append(
                    f"stopped at max_checks={max_checks}; sample is truncated "
                    "and later strata are under-represented"
                )
                result.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                return result

    result.finished_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def summarise(result: StudyResult) -> dict[str, Any]:
    """Aggregate a study into the numbers that go in the report."""

    def block(checks: list[Check]) -> dict[str, Any]:
        n = len(checks)
        counts = Counter(c.verdict for c in checks)
        conclusive = [c for c in checks if not Verdict(c.verdict).is_inconclusive]
        fp = [c for c in checks if c.is_false_positive]
        verified = counts.get(Verdict.VERIFIED.value, 0)

        fp_rate = len(fp) / len(conclusive) if conclusive else None
        lo, hi = wilson_interval(len(fp), len(conclusive)) if conclusive else (None, None)

        return {
            "checks": n,
            "conclusive": len(conclusive),
            "verified": verified,
            "not_found": counts.get(Verdict.NOT_FOUND.value, 0),
            "mismatch": counts.get(Verdict.MISMATCH.value, 0),
            "malformed": counts.get(Verdict.MALFORMED.value, 0),
            "unreachable": counts.get(Verdict.UNREACHABLE.value, 0),
            "unverifiable": counts.get(Verdict.UNVERIFIABLE.value, 0),
            "false_positive_rate": fp_rate,
            "false_positive_ci95": [lo, hi],
            "verified_rate_of_conclusive": (
                verified / len(conclusive) if conclusive else None
            ),
        }

    identified = [c for c in result.checks if c.mode == "identified"]
    described = [c for c in result.checks if c.mode == "described"]

    by_year: dict[str, dict] = {}
    years = sorted({c.source_year for c in described if c.source_year})
    for y in years:
        by_year[str(y)] = block([c for c in described if c.source_year == y])

    # Authority attribution: how much work is the fallback actually doing?
    fallback_rescues = sum(
        1 for c in result.checks
        if c.verdict == Verdict.VERIFIED.value and "openalex" in (c.authority or "")
    )

    return {
        "method": {
            "design": (
                "References deposited by publishers in real published papers. "
                "Ground truth is guaranteed by construction: every reference "
                "carries a DOI, so the cited work exists. Any NOT_FOUND is "
                "therefore a definite false positive."
            ),
            "source_works": result.source_works,
            "total_checks": len(result.checks),
            "seed": result.seed,
            "started_utc": result.started_utc,
            "finished_utc": result.finished_utc,
            "strata": years,
            "notes": result.notes,
        },
        "identified_mode": identified and block(identified) or None,
        "described_mode": described and block(described) or None,
        "described_by_year": by_year,
        "fallback_rescues": fallback_rescues,
    }


def to_markdown(summary: dict[str, Any]) -> str:
    """Render the study as a readable brief."""
    m = summary["method"]
    idt = summary.get("identified_mode") or {}
    dsc = summary.get("described_mode") or {}

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x:.1%}"

    def ci(block: dict) -> str:
        c = block.get("false_positive_ci95") or [None, None]
        if c[0] is None:
            return ""
        return f" (95% CI {c[0]:.1%}–{c[1]:.1%})"

    out: list[str] = []
    out.append("# Base rate: how often does citeaudit flag a genuine reference?")
    out.append("")
    out.append(
        f"**{m['total_checks']:,} checks** across **{m['source_works']:,} "
        f"published papers**, sampled at random from Crossref and stratified by "
        f"publication year ({min(m['strata']) if m['strata'] else '?'}–"
        f"{max(m['strata']) if m['strata'] else '?'}). Seed {m['seed']}."
    )
    out.append("")
    out.append("## Why these references are known to be genuine")
    out.append("")
    out.append(m["design"])
    out.append("")
    out.append("## Headline")
    out.append("")
    out.append("| Mode | Checks | Verified | False positives | FP rate |")
    out.append("|---|---:|---:|---:|---:|")
    if idt:
        out.append(
            f"| Identified (DOI given) | {idt['checks']:,} | {idt['verified']:,} | "
            f"{idt['not_found'] + idt['malformed']:,} | "
            f"{pct(idt['false_positive_rate'])}{ci(idt)} |"
        )
    if dsc:
        out.append(
            f"| Described (DOI withheld) | {dsc['checks']:,} | {dsc['verified']:,} | "
            f"{dsc['not_found'] + dsc['malformed']:,} | "
            f"{pct(dsc['false_positive_rate'])}{ci(dsc)} |"
        )
    out.append("")

    if summary.get("fallback_rescues"):
        out.append(
            f"The OpenAlex fallback rescued **{summary['fallback_rescues']:,}** "
            "references that Crossref alone would have reported as non-existent."
        )
        out.append("")

    if summary.get("described_by_year"):
        out.append("## By publication year of the citing paper")
        out.append("")
        out.append("| Year | Checks | FP rate | 95% CI |")
        out.append("|---:|---:|---:|---|")
        for year, b in sorted(summary["described_by_year"].items()):
            c = b.get("false_positive_ci95") or [None, None]
            ci_s = "—" if c[0] is None else f"{c[0]:.1%}–{c[1]:.1%}"
            out.append(
                f"| {year} | {b['conclusive']:,} | "
                f"{pct(b['false_positive_rate'])} | {ci_s} |"
            )
        out.append("")

    out.append("## How to read a document score against this")
    out.append("")
    if dsc and dsc.get("false_positive_rate") is not None:
        fp = dsc["false_positive_rate"]
        out.append(
            f"On references that are genuine, citeaudit reports NOT_FOUND about "
            f"**{fp:.1%}** of the time when no identifier is supplied. A "
            f"document whose references carry no DOIs should therefore be "
            f"expected to show roughly that failure rate before any real "
            f"problem is present."
        )
        out.append("")
        out.append(
            f"A NOT_FOUND rate materially above {fp:.1%} is the signal worth "
            "investigating. A rate at or below it is consistent with normal "
            "coverage gaps and says nothing about fabrication."
        )
    out.append("")
    out.append("## Limits")
    out.append("")
    out.append(
        "- The sample is drawn from `type:journal-article` with deposited "
        "references. It is representative of the indexed scholarly literature, "
        "not of consulting reports, government documents, or grey literature — "
        "the very corpora where fabrication has actually been found."
    )
    out.append(
        "- References were required to carry both a DOI and a title, which "
        "biases toward well-deposited records. The true false-positive rate on "
        "messier bibliographies is likely higher."
    )
    out.append(
        "- This measures whether a genuine work can be *found*. It does not "
        "measure whether a fabricated work is correctly *rejected*; that is "
        "what the calibration study covers."
    )
    return "\n".join(out)


def write_outputs(result: StudyResult, summary: dict, directory: str | Path) -> None:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)

    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    (d / "report.md").write_text(to_markdown(summary))

    import csv
    with (d / "checks.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(result.checks[0]).keys())
                           if result.checks else ["source_doi"])
        w.writeheader()
        for c in result.checks:
            row = asdict(c)
            row["claimed_authors"] = "; ".join(row["claimed_authors"])
            w.writerow(row)
