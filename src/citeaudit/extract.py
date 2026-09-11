"""
Citation extraction.

Finds three things in a document:

    1. Resolvable identifiers — DOIs, arXiv IDs, URLs.
    2. Bibliographic references with no identifier — author, title, year.
    3. The association between them, so that "Smith et al. (2019), 'Foo',
       doi:10.x/y" is checked as one claim rather than two unrelated facts.

Point 3 is what makes the tool useful. Checking that a DOI resolves is easy and
nearly worthless: a fabricated reference frequently carries a real DOI belonging
to some other paper. The claim under test is not "does this DOI exist" but "is
this DOI the paper you said it was", and answering that needs the surrounding
text, not just the identifier.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Citation, Kind

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# DOI syntax per the DOI Handbook: "10." then a registrant code, then a slash,
# then an opaque suffix. The suffix may contain almost anything, which is why
# trailing sentence punctuation has to be stripped afterwards rather than
# excluded here.
DOI_RE = re.compile(
    r"""(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?     # optional prefix
        (10\.\d{4,9}/[-._;()/:A-Za-z0-9<>\[\]+]+)     # the DOI itself
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Modern arXiv: 2301.12345 with optional version. Legacy: math.GT/0309136.
ARXIV_RE = re.compile(
    r"""arXiv:\s*
        (?:
            (\d{4}\.\d{4,5}(?:v\d+)?)              # modern
          | ([a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?) # legacy
        )
    """,
    re.VERBOSE | re.IGNORECASE,
)

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+", re.IGNORECASE)

# Trailing characters that belong to the sentence, not the identifier.
TRAILING = ".,;:)]}>\"'"

# A parenthesised year, or a bare year NOT adjacent to other digits.
#
# The negative lookarounds are load-bearing. Journal volume and issue numbers
# sit in the same range as years — "Proc. R. Soc. Lond. B, 271 (1547): 1443"
# has a volume of 1547 — and matching that as the publication year sent title
# extraction off into the page range, which then got compared against the real
# title and reported as a mismatch. Seven of eight mismatches in one live run
# were this bug.
YEAR_RE = re.compile(
    r"\((\d{4}[a-z]?)\)"
    r"|(?<![\d(,:\-])\b(19\d{2}|20\d{2})\b(?![\d)\-])"
)

# A quoted or italicised title inside a reference line.
TITLE_QUOTED_RE = re.compile(r'[""«"]([^""»"]{12,300})[""»"]|"([^"]{12,300})"')

# Heading that starts a bibliography.
BIB_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+\.?\s*)?"
    r"(references|bibliography|works cited|sources|citations|footnotes|endnotes)"
    r"\s*:?\s*$",
    re.IGNORECASE,
)

# Numbered or bracketed reference entry: "[12] ..." / "12. ..." / "(12) ..."
NUMBERED_ENTRY_RE = re.compile(r"^\s*(?:\[(\d{1,3})\]|\((\d{1,3})\)|(\d{1,3})\.)\s+(.{20,})$")

# "Surname, A." or "Surname AB" or "Surname et al."
AUTHOR_RE = re.compile(
    r"\b([A-Z][a-zA-Z'\-]{1,24})\s*,\s*(?:[A-Z]\.\s*){1,4}"     # Smith, J. A.
    r"|\b([A-Z][a-zA-Z'\-]{1,24})\s+(?:et\s+al\.?)"             # Smith et al.
)


def strip_trailing(s: str) -> str:
    """
    Remove sentence punctuation that regex greediness pulled into an identifier.

    Balanced brackets are kept: some real DOIs contain them, so a closing
    bracket only comes off when there is no matching opener to its left.
    """
    while s and s[-1] in TRAILING:
        if s[-1] == ")" and s.count(")") <= s.count("("):
            break
        if s[-1] == "]" and s.count("]") <= s.count("["):
            break
        s = s[:-1]
    return s


def normalise_doi(doi: str) -> str:
    return strip_trailing(doi.strip()).lower()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

# Virtually every citable work post-dates 1900. Anything earlier in a modern
# bibliography is far more likely to be a volume or issue number.
MODERN_YEAR = (1900, 2100)
ANY_YEAR = (1600, 2100)


def _year_from(text: str) -> int | None:
    """
    Publication year, preferring a plausible modern one.

    Every match is considered, not just the first. A parenthesised number is
    the strongest year signal in most citation styles, but issue numbers are
    parenthesised too — "Proc. R. Soc. Lond. B, 271 (1547): 1443--1450, 2004"
    has a volume of 271 and an issue of 1547, and taking the first parenthesised
    four-digit number returns 1547. That wrong year then sent title extraction
    into the page range, which was reported as a mismatch against the real
    title.
    """
    candidates: list[int] = []
    for m in YEAR_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        try:
            candidates.append(int(str(raw)[:4]))
        except (TypeError, ValueError):
            continue

    if not candidates:
        return None

    modern = [y for y in candidates if MODERN_YEAR[0] <= y <= MODERN_YEAR[1]]
    if modern:
        return modern[0]

    older = [y for y in candidates if ANY_YEAR[0] <= y <= ANY_YEAR[1]]
    return older[0] if older else None


def _authors_from(text: str) -> list[str]:
    out: list[str] = []
    for m in AUTHOR_RE.finditer(text):
        name = m.group(1) or m.group(2)
        if name and name.lower() not in {"the", "and", "in", "on", "of", "for"}:
            out.append(name)
    # preserve order, drop duplicates
    seen: set[str] = set()
    return [a for a in out if not (a.lower() in seen or seen.add(a.lower()))]


# Fragments that prove a candidate "title" is really an identifier, a page
# range, or other bibliographic debris.
_NOT_A_TITLE = re.compile(
    r"arxiv\s*:|doi\s*:|\b10\.\d{4,9}/|https?://|^\s*[\d\W]",
    re.IGNORECASE,
)


# "A. Author", "Smith, J.", "Yuhang Wu, and ..." — initials and comma-and
# constructions are what an author list is made of.
_INITIAL_RE = re.compile(r"\b[A-Z]\.")
_AUTHOR_SEP_RE = re.compile(r",\s*and\s|\sand\s|,\s*")


def looks_like_author_list(candidate: str) -> bool:
    """
    Detect an author list so it is not mistaken for a title.

    In LaTeX bibliographies the authors come first and are punctuated exactly
    like a sentence, so a naive "longest sentence-like segment" rule picks them
    every time. Comparing an author list against the record's real title scores
    low and produces the same false mismatch the title guard exists to prevent.
    """
    c = candidate.strip()
    words = c.split()
    if len(words) < 2:
        return False

    initials = len(_INITIAL_RE.findall(c))
    parts = [p for p in _AUTHOR_SEP_RE.split(c) if p.strip()]

    # Several initials relative to length is decisive on its own.
    if initials >= 2 and initials / len(words) > 0.20:
        return True

    def namelike(part: str) -> bool:
        toks = part.split()
        return (1 <= len(toks) <= 3
                and all(w[:1].isupper() or w[:1] == "-" for w in toks if w))

    hits = sum(1 for part in parts if namelike(part))

    # Three or more comma- or conjunction-separated name-shaped parts.
    if len(parts) >= 3 and hits / len(parts) >= 0.7:
        return True

    # Exactly two parts, both full personal names — "Holger Bast, Stefan Funke".
    # Held to a stricter bar than the three-part case: two capitalised phrases
    # can legitimately be a title, so every part must be name-shaped AND carry
    # a forename plus surname.
    if len(parts) == 2 and hits == 2 and all(
        2 <= len(part.split()) <= 3 for part in parts
    ):
        return True

    # "... and Surname" where what follows the conjunction is a bare name and
    # initials appear earlier. Requires BOTH, because plenty of real titles
    # contain "and" — "Random drift and culture change" was rejected by an
    # earlier version of this rule that only checked for the conjunction.
    if initials >= 2:
        tail = c.rsplit(" and ", 1)[-1].strip() if " and " in c else ""
        tail_words = tail.split()
        if 1 <= len(tail_words) <= 3 and all(
            w[:1].isupper() or w[:1] == "-" for w in tail_words if w
        ):
            return True

    return False


def looks_like_a_title(candidate: str, *, quoted: bool = False) -> bool:
    """
    Reject bibliographic debris masquerading as a title.

    This guard exists because the alternative is the worst failure this tool
    can produce. A garbage "claimed title" gets compared against the real
    record, scores low, and the document is told it cited the wrong paper — an
    accusation manufactured entirely from a parsing error. Seven of eight
    mismatches in one live run were exactly that.

    Validation is graded by how strong the signal was. A string the author put
    in quotation marks inside a reference entry is almost certainly a title, so
    it only has to clear the debris check. A span recovered by splitting on
    sentence punctuation is a guess, and has to clear everything.

    When a title cannot be recovered confidently the answer is None, which makes
    `assess` decline to compare rather than guess. Missing a mismatch costs far
    less than inventing one.
    """
    c = candidate.strip()
    if not (8 <= len(c) <= 300):
        return False
    if _NOT_A_TITLE.search(c):
        return False

    words = c.split()
    if len(words) < 2:
        return False

    if quoted:
        # Explicitly delimited by the author. Debris check is enough.
        return True

    # A title is mostly words. Page ranges, volume/issue strings and
    # identifiers are mostly not.
    alpha_words = [w for w in words if sum(ch.isalpha() for ch in w) >= 2]
    if len(alpha_words) / len(words) < 0.6:
        return False

    letters = sum(ch.isalpha() for ch in c)
    if letters / len(c) < 0.55:
        return False

    if looks_like_author_list(c):
        return False

    return True


def _title_from(text: str) -> str | None:
    m = TITLE_QUOTED_RE.search(text)
    if m:
        cand = (m.group(1) or m.group(2) or "").strip()
        return cand if cand and looks_like_a_title(cand, quoted=True) else None

    # Unquoted style: "Authors (Year). Title. Journal, vol(issue), pages."
    # Take the sentence-like span after the year marker.
    ym = YEAR_RE.search(text)
    if ym:
        tail = text[ym.end():].lstrip(" .),")
        parts = re.split(r"(?<=[a-z0-9])\.\s+(?=[A-Z])", tail)
        if parts:
            cand = parts[0].strip().rstrip(".")
            if looks_like_a_title(cand):
                return cand

    # Author-first LaTeX style with no year marker and no quotes:
    # "A. Author, B. Writer. The Real Title Here. Venue, 2024."
    #
    # The title is the first title-like segment AFTER the authors, not the
    # longest one — venue strings and author lists are both long, and taking
    # the maximum picks them.
    segments = [seg.strip().rstrip(".")
                for seg in re.split(r"(?<=[a-z0-9\)])\.\s+", text)]
    for seg in segments:
        if looks_like_a_title(seg):
            return seg

    return None


def find_identifiers(text: str, line_no: int = 0) -> list[Citation]:
    """Extract every resolvable identifier from a span of text."""
    out: list[Citation] = []
    seen: set[str] = set()

    for m in DOI_RE.finditer(text):
        doi = normalise_doi(m.group(1))
        if len(doi) < 8 or doi in seen:
            continue
        seen.add(doi)
        out.append(Citation(
            raw=m.group(0).strip(), kind=Kind.DOI, line=line_no,
            identifier=doi, context=text.strip()[:400],
        ))

    for m in ARXIV_RE.finditer(text):
        aid = strip_trailing((m.group(1) or m.group(2) or "").strip())
        if not aid or aid in seen:
            continue
        seen.add(aid)
        out.append(Citation(
            raw=m.group(0).strip(), kind=Kind.ARXIV, line=line_no,
            identifier=aid, context=text.strip()[:400],
        ))

    for m in URL_RE.finditer(text):
        url = strip_trailing(m.group(0))
        # A doi.org or arxiv.org URL is already captured above as its
        # identifier, which is a stronger check than HTTP liveness.
        low = url.lower()
        if "doi.org/" in low or "arxiv.org/abs" in low:
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(Citation(
            raw=url, kind=Kind.URL, line=line_no,
            identifier=url, context=text.strip()[:400],
        ))

    return out


def _attach_claims(cit: Citation, entry_text: str) -> Citation:
    """Attach the title/author/year asserted around an identifier."""
    cit.claimed_title = _title_from(entry_text)
    cit.claimed_authors = _authors_from(entry_text)
    cit.claimed_year = _year_from(entry_text)
    cit.context = entry_text.strip()[:400]
    return cit


def extract(text: str) -> list[Citation]:
    """
    Extract citations from document text.

    Bibliography entries are treated as units so that an identifier inherits
    the claims made about it on the same line.
    """
    lines = text.splitlines()
    citations: list[Citation] = []
    in_bibliography = False
    seen_keys: set[str] = set()

    def add(c: Citation) -> None:
        k = c.key()
        if k not in seen_keys:
            seen_keys.add(k)
            citations.append(c)

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue

        if BIB_HEADING_RE.match(stripped):
            in_bibliography = True
            continue

        entry = NUMBERED_ENTRY_RE.match(stripped)
        is_entry = bool(entry) or (in_bibliography and len(stripped) > 40)
        body = entry.group(4) if entry else stripped

        ref_no = None
        if entry:
            raw_no = entry.group(1) or entry.group(2) or entry.group(3)
            try:
                ref_no = int(raw_no) if raw_no else None
            except (TypeError, ValueError):
                ref_no = None

        ids = find_identifiers(body, line_no=i)

        if ids:
            for c in ids:
                if is_entry:
                    _attach_claims(c, body)
                    c.ref_number = ref_no
                add(c)
            continue

        # A reference entry with no identifier at all. Still checkable by
        # searching the authority for the claimed work — this is the path that
        # catches a confident reference to a paper that does not exist.
        if is_entry:
            title = _title_from(body)
            authors = _authors_from(body)
            year = _year_from(body)
            if title and (authors or year):
                add(Citation(
                    raw=body[:300], kind=Kind.BIBLIOGRAPHIC, line=i,
                    claimed_title=title, claimed_authors=authors,
                    claimed_year=year, context=body.strip()[:400],
                    ref_number=ref_no,
                ))

    return citations


# ---------------------------------------------------------------------------
# Document loading
# ---------------------------------------------------------------------------

class UnsupportedDocument(RuntimeError):
    pass


def read_document(path: str | Path) -> str:
    """Load text from md, txt, html, pdf, or docx."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    suffix = p.suffix.lower()

    if suffix in {".md", ".txt", ".rst", ".tex", ".csv", ".json"}:
        return p.read_text(encoding="utf-8", errors="replace")

    if suffix in {".html", ".htm"}:
        raw = p.read_text(encoding="utf-8", errors="replace")
        raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", raw, flags=re.I)
        return re.sub(r"<[^>]+>", " ", raw)

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise UnsupportedDocument(
                "PDF support needs pypdf: pip install 'citeaudit[pdf]'"
            ) from exc
        reader = PdfReader(str(p))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if suffix == ".docx":
        try:
            import docx
        except ImportError as exc:
            raise UnsupportedDocument(
                "DOCX support needs python-docx: pip install 'citeaudit[docx]'"
            ) from exc
        d = docx.Document(str(p))
        parts = [para.text for para in d.paragraphs]
        for table in d.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)

    raise UnsupportedDocument(
        f"Cannot read {suffix or 'file with no extension'}. "
        "Supported: .md .txt .rst .tex .html .pdf .docx"
    )


def extract_from_file(path: str | Path) -> list[Citation]:
    return extract(read_document(path))
