"""
Quote verification.

The failure this addresses
--------------------------
Deloitte's retracted report contained a fabricated quote attributed to a real
federal court judge. Every citation check in this tool would have passed it: the
case was real, the judge was real, the reference resolved. The quote was simply
never said.

Checking that a cited work *exists* and checking that it *says what you claim*
are different questions. This module asks the second one.

What makes it hard, and what makes it honest
--------------------------------------------
Most scholarly text is paywalled, so most quotes cannot be checked at all. The
temptation is to report an unchecked quote as suspicious. That would be the
same error the tool exists to catch — an accusation the evidence does not
support — with worse consequences, because it accuses a person of fabrication
rather than a reference of being wrong.

The verdict set is therefore built around what the retrieved text entitles us
to say:

    FOUND            The quote appears in the retrieved source.
    NOT_FOUND        Complete body text was retrieved and the quote is absent.
                     The only verdict that suggests fabrication, and it
                     requires FULL coverage.
    ABSENT_FROM_ABSTRACT
                     Only an abstract was available and the quote is not in it.
                     INCONCLUSIVE — the quote may sit in the body. Never
                     reported as a failure.
    SOURCE_UNAVAILABLE
                     No open text. No conclusion.
    NOT_ATTRIBUTED   The quote has no citation attached to check against.

Every tier can confirm a quote. Only full text can refute one.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

from rapidfuzz import fuzz

from .fulltext import Coverage, SourceText, retrieve
from .http import Client
from .models import Citation, Kind

# A quotation shorter than this is not distinctive enough to check: common
# phrases appear everywhere, and a false "not found" on six words would be
# noise.
MIN_QUOTE_WORDS = 8

# Similarity at which a passage counts as present. Below 100 because quoting
# practice legitimately alters text — ellipsis, bracketed insertions, British
# to American spelling, a dropped subordinate clause.
QUOTE_MATCH_THRESHOLD = 88.0

# Window used when scanning a long body for the best matching passage.
WINDOW_SLACK = 1.6


class QuoteVerdict(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ABSENT_FROM_ABSTRACT = "absent_from_abstract"
    SOURCE_UNAVAILABLE = "source_unavailable"
    NOT_ATTRIBUTED = "not_attributed"

    @property
    def is_failure(self) -> bool:
        """Only a refutation backed by complete text counts against a document."""
        return self is QuoteVerdict.NOT_FOUND

    @property
    def is_inconclusive(self) -> bool:
        return self in (QuoteVerdict.ABSENT_FROM_ABSTRACT,
                        QuoteVerdict.SOURCE_UNAVAILABLE,
                        QuoteVerdict.NOT_ATTRIBUTED)


@dataclass
class Quote:
    text: str
    line: int = 0
    attributed_to: Citation | None = None
    context: str = ""


@dataclass
class QuoteFinding:
    quote: Quote
    verdict: QuoteVerdict
    coverage: str = Coverage.NONE.value
    similarity: float | None = None
    best_passage: str | None = None
    source_origin: str = ""
    evidence_url: str | None = None
    detail: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        if self.quote.attributed_to:
            d["quote"]["attributed_to"]["kind"] = self.quote.attributed_to.kind.value
        return d


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Straight and curly double quotes, and guillemets. Single quotes are excluded
# deliberately: apostrophes make them ambiguous and the false-extraction rate is
# far too high to be worth the extra coverage.
# Newlines are permitted inside a quotation. Prose wraps, and a line-anchored
# pattern silently misses every quote long enough to matter — which is most of
# the ones worth checking.
QUOTE_RE = re.compile(
    r'"([^"]{40,600})"'
    r"|\u201c([^\u201d]{40,600})\u201d"
    r"|\u00ab([^\u00bb]{40,600})\u00bb",
    re.S,
)

# A numbered citation marker following a quotation: [3], (3), or a superscript
# style rendered as ^3 in plain text.
MARKER_RE = re.compile(r"^[\s.,;:]*(?:\[(\d{1,3})\]|\((\d{1,3})\)|\^(\d{1,3}))")

BIB_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+\.?\s*)?"
    r"(references|bibliography|works cited|sources|citations)\s*:?\s*$",
    re.IGNORECASE,
)


def body_of(text: str) -> str:
    """
    The document up to its bibliography.

    Reference entries put titles in quotation marks. Treating those as
    quotations would produce a flood of unverifiable findings that bury the
    real ones, so everything from the references heading onward is dropped.
    """
    out_lines: list[str] = []
    for line in text.splitlines():
        if BIB_HEADING_RE.match(line.strip()):
            break
        out_lines.append(line)
    return "\n".join(out_lines)


def extract_quotes(text: str, citations: list[Citation]) -> list[Quote]:
    """
    Find quoted passages in the body and attach the citation they rely on.

    Scanning runs over the whole body rather than line by line, because prose
    wraps and a quotation long enough to be worth checking almost never fits on
    one line. Line numbers are recovered from the match offset so findings
    still point somewhere useful.

    Attribution takes the nearest citation at or before the quote's closing
    mark, which matches how citations are actually placed: the marker follows
    the claim it supports.
    """
    body = body_of(text)

    # offset -> line number, computed once
    line_starts = [0]
    for i, ch in enumerate(body):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_of(offset: int) -> int:
        import bisect
        return bisect.bisect_right(line_starts, offset)

    by_line: dict[int, list[Citation]] = {}
    by_marker: dict[int, Citation] = {}
    for c in citations:
        by_line.setdefault(c.line, []).append(c)
        if c.ref_number is not None and c.ref_number not in by_marker:
            by_marker[c.ref_number] = c

    quotes: list[Quote] = []
    for m in QUOTE_RE.finditer(body):
        raw = (m.group(1) or m.group(2) or m.group(3) or "")
        passage = _WS.sub(" ", raw).strip()
        if len(passage.split()) < MIN_QUOTE_WORDS:
            continue

        end_line = line_of(m.end())
        nearest = None

        # A numbered marker immediately after the closing quotation mark is the
        # strongest available signal, and the dominant pattern in real
        # documents: the body says [3] and the source sits in the bibliography
        # at the end. Proximity alone never connects those, because they are
        # nowhere near each other.
        tail = body[m.end():m.end() + 40]
        marker = MARKER_RE.search(tail)
        if marker:
            raw = marker.group(1) or marker.group(2) or marker.group(3)
            try:
                num = int(raw) if raw else None
            except (TypeError, ValueError):
                num = None
            if num is not None and num in by_marker:
                nearest = by_marker[num]

        # Otherwise fall back to the nearest citation by line, which covers
        # inline styles that put the DOI or URL beside the claim.
        if nearest is None:
            for ln in list(range(end_line, end_line + 2)) + \
                      list(range(end_line - 1, max(0, end_line - 4), -1)):
                if by_line.get(ln):
                    nearest = by_line[ln][0]
                    break

        ctx_start = max(0, m.start() - 80)
        quotes.append(Quote(
            text=passage, line=line_of(m.start()), attributed_to=nearest,
            context=_WS.sub(" ", body[ctx_start:m.end() + 80]).strip()[:300],
        ))
    return quotes


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_NORM = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WS.sub(" ", _NORM.sub(" ", text.casefold())).strip()


def find_passage(quote: str, source: str) -> tuple[float, str | None]:
    """
    Best matching passage for a quote within a source text.

    Uses partial_ratio, which finds the best-matching substring rather than
    comparing whole strings — the right operation when looking for a sentence
    inside a paper. A sliding window then recovers the matched passage itself,
    so a reader can see what was compared instead of being handed a bare score.
    """
    q, s = normalise(quote), normalise(source)
    if not q or not s:
        return 0.0, None

    score = float(fuzz.partial_ratio(q, s))

    words = s.split()
    qlen = len(q.split())
    if qlen == 0 or not words:
        return score, None

    win = max(qlen, int(qlen * WINDOW_SLACK))
    step = max(1, win // 3)
    best, best_text = 0.0, None
    for start in range(0, max(1, len(words) - win + 1), step):
        chunk = " ".join(words[start:start + win])
        sc = float(fuzz.ratio(q, chunk))
        if sc > best:
            best, best_text = sc, chunk

    return max(score, best), best_text


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class QuoteVerifier:
    def __init__(self, client: Client, *, threshold: float = QUOTE_MATCH_THRESHOLD):
        self.client = client
        self.threshold = threshold
        self._cache: dict[str, SourceText] = {}

    def _source_for(self, c: Citation) -> SourceText:
        key = f"{c.kind.value}:{c.identifier}"
        if key in self._cache:
            return self._cache[key]

        if c.kind is Kind.ARXIV:
            got = retrieve(self.client, arxiv_id=c.identifier)
        elif c.kind is Kind.DOI:
            got = retrieve(self.client, doi=c.identifier)
        else:
            got = SourceText(Coverage.NONE, origin="no-identifier")

        self._cache[key] = got
        return got

    def check(self, quote: Quote) -> QuoteFinding:
        cit = quote.attributed_to
        if cit is None or cit.identifier is None:
            return QuoteFinding(
                quote=quote, verdict=QuoteVerdict.NOT_ATTRIBUTED,
                detail=("no citation with a resolvable identifier is attached "
                        "to this quotation, so there is nothing to check it "
                        "against"),
            )

        src = self._source_for(cit)
        if src.coverage is Coverage.NONE:
            return QuoteFinding(
                quote=quote, verdict=QuoteVerdict.SOURCE_UNAVAILABLE,
                coverage=src.coverage.value, source_origin=src.origin,
                evidence_url=src.url,
                detail=("no openly available text for this source. Most "
                        "scholarly content is paywalled; this is a licensing "
                        "limit, not a finding about the quotation."),
            )

        score, passage = find_passage(quote.text, src.text)

        if score >= self.threshold:
            return QuoteFinding(
                quote=quote, verdict=QuoteVerdict.FOUND,
                coverage=src.coverage.value, similarity=score,
                best_passage=passage, source_origin=src.origin,
                evidence_url=src.url,
                detail=(f"passage located in the {src.coverage.value} text "
                        f"({score:.0f}% match)"),
            )

        if src.coverage.can_refute:
            return QuoteFinding(
                quote=quote, verdict=QuoteVerdict.NOT_FOUND,
                coverage=src.coverage.value, similarity=score,
                best_passage=passage, source_origin=src.origin,
                evidence_url=src.url,
                detail=(f"complete text of the source was retrieved "
                        f"({src.words:,} words) and this passage does not "
                        f"appear in it. Closest match scored {score:.0f}%."),
            )

        return QuoteFinding(
            quote=quote, verdict=QuoteVerdict.ABSENT_FROM_ABSTRACT,
            coverage=src.coverage.value, similarity=score,
            best_passage=passage, source_origin=src.origin,
            evidence_url=src.url,
            detail=("not present in the abstract, which is all that was "
                    "openly available. The passage may well appear in the "
                    "body. INCONCLUSIVE, not a failure."),
        )

    def verify(self, quotes: list[Quote]) -> list[QuoteFinding]:
        return [self.check(q) for q in quotes]


def summarise(findings: list[QuoteFinding]) -> dict:
    from collections import Counter

    counts = Counter(f.verdict.value for f in findings)
    checkable = [f for f in findings if not f.verdict.is_inconclusive]
    return {
        "total_quotes": len(findings),
        "found": counts.get(QuoteVerdict.FOUND.value, 0),
        "not_found": counts.get(QuoteVerdict.NOT_FOUND.value, 0),
        "absent_from_abstract": counts.get(QuoteVerdict.ABSENT_FROM_ABSTRACT.value, 0),
        "source_unavailable": counts.get(QuoteVerdict.SOURCE_UNAVAILABLE.value, 0),
        "not_attributed": counts.get(QuoteVerdict.NOT_ATTRIBUTED.value, 0),
        "conclusive_checks": len(checkable),
        "coverage_rate": (len(checkable) / len(findings)) if findings else None,
    }
