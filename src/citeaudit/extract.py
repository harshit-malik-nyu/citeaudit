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

YEAR_RE = re.compile(r"\((\d{4}[a-z]?)\)|\b(19\d{2}|20\d{2})\b")

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

def _year_from(text: str) -> int | None:
    m = YEAR_RE.search(text)
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    try:
        y = int(str(raw)[:4])
    except (TypeError, ValueError):
        return None
    return y if 1500 <= y <= 2100 else None


def _authors_from(text: str) -> list[str]:
    out: list[str] = []
    for m in AUTHOR_RE.finditer(text):
        name = m.group(1) or m.group(2)
        if name and name.lower() not in {"the", "and", "in", "on", "of", "for"}:
            out.append(name)
    # preserve order, drop duplicates
    seen: set[str] = set()
    return [a for a in out if not (a.lower() in seen or seen.add(a.lower()))]


def _title_from(text: str) -> str | None:
    m = TITLE_QUOTED_RE.search(text)
    if m:
        return (m.group(1) or m.group(2) or "").strip() or None

    # Unquoted style: "Authors (Year). Title. Journal, vol(issue), pages."
    # Take the sentence-like span after the year marker.
    ym = YEAR_RE.search(text)
    if ym:
        tail = text[ym.end():].lstrip(" .),")
        parts = re.split(r"(?<=[a-z0-9])\.\s+(?=[A-Z])", tail)
        if parts:
            cand = parts[0].strip().rstrip(".")
            if 12 <= len(cand) <= 300 and " " in cand:
                return cand
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

        ids = find_identifiers(body, line_no=i)

        if ids:
            for c in ids:
                add(_attach_claims(c, body) if is_entry else c)
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
