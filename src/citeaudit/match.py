"""
Claim matching.

Given what a document asserted about a reference and what the authority
actually holds under that identifier, decide whether they describe the same
work.

This is where MISMATCH gets detected, and it is the check that distinguishes
this tool from a link checker. A fabricated reference often carries a real DOI
belonging to an unrelated paper. The link resolves, a reviewer clicking it
lands on a real article, and the citation passes every check that stops at
"does this URL work".

Thresholds are conservative on purpose. A false MISMATCH accuses a real
citation of being wrong, which destroys trust in the tool faster than a missed
detection. Where the evidence is ambiguous the tool reports VERIFIED with a low
similarity score recorded, so a human can sort the borderline cases without
being told a conclusion the data does not support.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

# A resolved title this dissimilar to the claim indicates a different work.
#
# CALIBRATED, not asserted. See evidence/calibration/report.md: 2,501
# labelled pairs built from 260 real Crossref records, ground truth fixed by
# construction. Across the swept range, precision holds at 1.000 while recall
# climbs with the threshold — 60 catches 99.2% of genuine mismatches, 66
# catches 100% with zero false accusations across 1,721 genuine pairs.
#
# Chosen on a precision floor rather than by maximising F1. F1 treats the two
# errors as equally costly; here a false accusation is what makes a user
# switch the tool off, after which missed detections stop mattering because
# nobody is looking.
#
# Across independent sample draws the minimum threshold reaching full recall
# landed at 62 and at 66. The upper end is taken so the setting achieves full
# recall on BOTH draws rather than only on the one that produced it. The cost
# of that choice is bounded: precision holds at 1.000 across the entire swept
# range in every run, because the author-overlap corroboration rule in
# `assess` — not this threshold — is what protects genuine citations from
# being accused.
TITLE_MISMATCH_THRESHOLD = 66.0

# Above this, treat as the same work regardless of author noise.
TITLE_STRONG_MATCH = 85.0

# Publication year may differ from online-first or preprint year.
YEAR_TOLERANCE = 2

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

# Words carrying no discriminating power in a title comparison.
_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with",
    "from", "by", "at", "as", "is", "are", "be", "using", "via", "into",
}


def normalise(text: str | None) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT.sub(" ", text.casefold())
    return _WS.sub(" ", text).strip()


def content_tokens(text: str | None) -> set[str]:
    return {t for t in normalise(text).split() if t not in _STOPWORDS and len(t) > 2}


def title_similarity(claimed: str | None, resolved: str | None) -> float | None:
    """
    Similarity in 0-100, or None when there is nothing to compare.

    Uses token_set_ratio so that subtitle presence, word order, and truncation
    do not by themselves look like a different paper. A reference that gives
    only the main title should still match a record carrying "Main Title: A
    Longer Subtitle".
    """
    a, b = normalise(claimed), normalise(resolved)
    if not a or not b:
        return None
    return float(fuzz.token_set_ratio(a, b))


def author_overlap(claimed: list[str], resolved: list[str]) -> float | None:
    """
    Share of claimed author surnames that appear in the resolved record.

    Asymmetric by design. A document citing "Smith et al." for a twelve-author
    paper is correct, so the denominator is what the document claimed, not what
    the record holds.
    """
    if not claimed or not resolved:
        return None
    claimed_n = {normalise(a) for a in claimed if normalise(a)}
    resolved_n = {normalise(a) for a in resolved if normalise(a)}
    if not claimed_n or not resolved_n:
        return None

    hits = 0
    for c in claimed_n:
        if any(c == r or c in r.split() or r in c.split() for r in resolved_n):
            hits += 1
    return hits / len(claimed_n)


def year_consistent(claimed: int | None, resolved: int | None) -> bool | None:
    if claimed is None or resolved is None:
        return None
    return abs(claimed - resolved) <= YEAR_TOLERANCE


def assess(
    claimed_title: str | None,
    claimed_authors: list[str],
    claimed_year: int | None,
    resolved_title: str | None,
    resolved_authors: list[str],
    resolved_year: int | None,
) -> tuple[bool, float | None, float | None, str]:
    """
    Compare a claim to a resolved record.

    Returns (is_mismatch, title_similarity, author_overlap, explanation).

    The logic is deliberately reluctant to call MISMATCH. It requires positive
    evidence of a different work — a title that genuinely does not match — and
    will not infer one from author or year discrepancies alone, which have too
    many innocent explanations (corrigenda, online-first dates, "et al.",
    transliteration).
    """
    sim = title_similarity(claimed_title, resolved_title)
    overlap = author_overlap(claimed_authors, resolved_authors)
    yr_ok = year_consistent(claimed_year, resolved_year)

    notes: list[str] = []

    if sim is None:
        # No title asserted, so there is nothing to contradict. Record what
        # weak signals exist but do not accuse.
        if overlap is not None and overlap == 0.0:
            notes.append(
                f"no claimed author appears in the record "
                f"(claimed {', '.join(claimed_authors[:3])}; "
                f"record has {', '.join(resolved_authors[:3])})"
            )
        if yr_ok is False:
            notes.append(f"year {claimed_year} vs {resolved_year} in record")
        return False, sim, overlap, (
            "resolved; no title given in document to compare"
            + (" — " + "; ".join(notes) if notes else "")
        )

    if sim >= TITLE_STRONG_MATCH:
        return True is False, sim, overlap, f"title matches record ({sim:.0f}% similarity)"

    if sim < TITLE_MISMATCH_THRESHOLD:
        # Corroborate before accusing: strong author agreement suggests the
        # same work under a differently-recorded title.
        if overlap is not None and overlap >= 0.75:
            return False, sim, overlap, (
                f"title similarity low ({sim:.0f}%) but authors agree "
                f"({overlap:.0%}) — likely the same work recorded differently"
            )
        detail = (
            f"identifier resolves to a DIFFERENT work. "
            f"Document claims {claimed_title!r}; "
            f"record holds {resolved_title!r} ({sim:.0f}% similarity)"
        )
        if yr_ok is False:
            detail += f"; year {claimed_year} vs {resolved_year}"
        return True, sim, overlap, detail

    # Middle band: partial match. Report as verified, keep the score visible.
    notes.append(f"partial title match ({sim:.0f}%)")
    if overlap is not None:
        notes.append(f"author overlap {overlap:.0%}")
    if yr_ok is False:
        notes.append(f"year {claimed_year} vs {resolved_year}")
    return False, sim, overlap, "; ".join(notes)


def is_plausible_search_hit(
    claimed_title: str, candidate_title: str,
    claimed_authors: list[str], candidate_authors: list[str],
) -> tuple[bool, float]:
    """
    Decide whether a search result is the work a document described.

    Used for references with no identifier. Held to a higher bar than
    identifier resolution: with no DOI anchoring the claim, a loose match would
    let the tool "confirm" a fabricated reference by finding some vaguely
    similar real paper — manufacturing exactly the false assurance it exists to
    prevent.
    """
    sim = title_similarity(claimed_title, candidate_title) or 0.0
    if sim >= 90.0:
        return True, sim
    if sim >= 75.0:
        ov = author_overlap(claimed_authors, candidate_authors)
        if ov is not None and ov >= 0.5:
            return True, sim
    return False, sim
