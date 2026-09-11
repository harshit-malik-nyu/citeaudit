"""
Retrieval of source text for quote checking.

The hard constraint
-------------------
Most scholarly text is paywalled. Any tool claiming to verify quotations has to
be honest about how little of the literature it can actually read, because the
alternative is catastrophic: reporting "this quote does not appear in the
source" when the truth is "I could not read the source" would manufacture an
accusation of fabrication out of a licensing restriction.

So retrieval returns a COVERAGE TIER alongside the text, and the tier governs
what conclusion is permitted:

    FULL       Complete body text retrieved. A quote absent from this is
               genuinely absent — the only tier that licenses NOT_FOUND.

    ABSTRACT   Only the abstract was available. A quote absent from an
               abstract says nothing; it may sit in the body. This tier can
               confirm a quote, never refute one.

    NONE       No open text. No conclusion of any kind.

The asymmetry is deliberate and runs one way: every tier can VERIFY a quote,
only FULL can refute one.
"""

from __future__ import annotations

import io
import logging
import re
import tarfile
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum

from .http import Client, NotFound, Unreachable

log = logging.getLogger(__name__)

ARXIV_QUERY = "https://export.arxiv.org/api/query"
ARXIV_SOURCE = "https://export.arxiv.org/e-print/"
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
ATOM = "{http://www.w3.org/2005/Atom}"


class Coverage(str, Enum):
    FULL = "full"
    ABSTRACT = "abstract"
    NONE = "none"

    @property
    def can_refute(self) -> bool:
        """Only complete text licenses the claim that a quote is absent."""
        return self is Coverage.FULL


@dataclass
class SourceText:
    coverage: Coverage
    text: str = ""
    origin: str = ""
    url: str | None = None

    @property
    def words(self) -> int:
        return len(self.text.split())


# ---------------------------------------------------------------------------
# LaTeX / markup cleanup
# ---------------------------------------------------------------------------

_TEX_COMMENT = re.compile(r"(?<!\\)%.*$", re.M)
_TEX_ENV_DROP = re.compile(
    r"\\begin\{(equation|align|figure|table|tabular|thebibliography|lstlisting|verbatim)\*?\}"
    r".*?\\end\{\1\*?\}", re.S)
_TEX_CMD_ARG = re.compile(r"\\(?:emph|textit|textbf|texttt|text|section|subsection|"
                          r"subsubsection|title|caption|footnote)\*?\s*\{([^{}]*)\}")
_TEX_BARE = re.compile(r"\\[a-zA-Z@]+\*?\s*(\[[^\]]*\])?")
_BRACES = re.compile(r"[{}]")
_JATS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_latex(text: str) -> str:
    out = _TEX_COMMENT.sub(" ", text)
    out = _TEX_ENV_DROP.sub(" ", out)
    for _ in range(3):
        out = _TEX_CMD_ARG.sub(r"\1", out)
    out = _TEX_BARE.sub(" ", out)
    out = _BRACES.sub(" ", out)
    out = out.replace("``", '"').replace("''", '"').replace("~", " ")
    return _WS.sub(" ", out).strip()


def clean_markup(text: str) -> str:
    return _WS.sub(" ", _JATS.sub(" ", text)).strip()


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def arxiv_fulltext(client: Client, arxiv_id: str) -> SourceText:
    """
    Body text from an arXiv source package.

    arXiv is the largest corpus whose full text is openly retrievable at scale,
    which makes it the only place quote refutation is broadly possible today.
    """
    base = re.sub(r"v\d+$", "", arxiv_id.strip())
    try:
        resp = client.get(f"{ARXIV_SOURCE}{base}", accept="*/*")
    except (NotFound, Unreachable):
        return SourceText(Coverage.NONE, origin="arxiv")

    blob = resp.body
    if not blob:
        return SourceText(Coverage.NONE, origin="arxiv")

    chunks: list[str] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            for m in tar.getmembers():
                if not (m.isfile() and m.name.lower().endswith(".tex")):
                    continue
                fh = tar.extractfile(m)
                if fh:
                    chunks.append(fh.read().decode("utf-8", errors="replace"))
    except (tarfile.TarError, EOFError, OSError):
        # Some submissions are a bare gzipped .tex rather than a tarball.
        try:
            import gzip
            chunks.append(gzip.decompress(blob).decode("utf-8", errors="replace"))
        except Exception:
            return SourceText(Coverage.NONE, origin="arxiv")

    if not chunks:
        return SourceText(Coverage.NONE, origin="arxiv")

    text = clean_latex("\n".join(chunks))
    if len(text.split()) < 200:
        # Too short to be a body; treat as unusable rather than claim coverage.
        return SourceText(Coverage.NONE, origin="arxiv")

    return SourceText(Coverage.FULL, text=text, origin="arxiv-source",
                      url=f"https://arxiv.org/abs/{base}")


def arxiv_abstract(client: Client, arxiv_id: str) -> SourceText:
    base = re.sub(r"v\d+$", "", arxiv_id.strip())
    params = {"id_list": base, "max_results": "1"}
    try:
        body = client.get(f"{ARXIV_QUERY}?{urllib.parse.urlencode(params)}",
                          accept="application/atom+xml").text()
        root = ET.fromstring(body)
    except (NotFound, Unreachable, ET.ParseError):
        return SourceText(Coverage.NONE, origin="arxiv")

    for entry in root.findall(f"{ATOM}entry"):
        el = entry.find(f"{ATOM}summary")
        if el is not None and el.text and len(el.text.split()) > 20:
            return SourceText(Coverage.ABSTRACT, text=_WS.sub(" ", el.text).strip(),
                              origin="arxiv-abstract",
                              url=f"https://arxiv.org/abs/{base}")
    return SourceText(Coverage.NONE, origin="arxiv")


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def reconstruct_abstract(inverted: dict[str, list[int]]) -> str:
    """
    Rebuild an abstract from OpenAlex's inverted index.

    OpenAlex stores abstracts as {word: [positions]} rather than as prose, for
    licensing reasons. Reconstruction is exact.
    """
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions))


def openalex_abstract(client: Client, doi: str) -> SourceText:
    url = (f"{OPENALEX}/works/doi:{urllib.parse.quote(doi, safe='')}"
           f"?select=abstract_inverted_index,doi,id")
    if client.mailto:
        url += f"&mailto={urllib.parse.quote(client.mailto)}"
    try:
        item = client.get(url).json()
    except (NotFound, Unreachable):
        return SourceText(Coverage.NONE, origin="openalex")

    text = reconstruct_abstract(item.get("abstract_inverted_index") or {})
    if len(text.split()) < 20:
        return SourceText(Coverage.NONE, origin="openalex")
    return SourceText(Coverage.ABSTRACT, text=text, origin="openalex-abstract",
                      url=f"https://doi.org/{doi}")


def crossref_abstract(client: Client, doi: str) -> SourceText:
    url = f"{CROSSREF}/works/{urllib.parse.quote(doi, safe='')}?select=abstract"
    if client.mailto:
        url += f"&mailto={urllib.parse.quote(client.mailto)}"
    try:
        data = client.get(url).json()
    except (NotFound, Unreachable):
        return SourceText(Coverage.NONE, origin="crossref")

    raw = (data.get("message") or {}).get("abstract") or ""
    text = clean_markup(raw)
    if len(text.split()) < 20:
        return SourceText(Coverage.NONE, origin="crossref")
    return SourceText(Coverage.ABSTRACT, text=text, origin="crossref-abstract",
                      url=f"https://doi.org/{doi}")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def retrieve(client: Client, *, doi: str | None = None,
             arxiv_id: str | None = None) -> SourceText:
    """
    Best available open text for a source, preferring full text.

    Order matters: full text first, because only full text permits refuting a
    quote. Falling back to an abstract is a real downgrade in what can be
    concluded, not merely in quality, and the returned tier records that.
    """
    if arxiv_id:
        full = arxiv_fulltext(client, arxiv_id)
        if full.coverage is Coverage.FULL:
            return full
        abs_ = arxiv_abstract(client, arxiv_id)
        if abs_.coverage is not Coverage.NONE:
            return abs_

    if doi:
        # A DOI may point at an arXiv preprint with retrievable source.
        if doi.startswith("10.48550/arxiv."):
            aid = doi.split("arxiv.", 1)[1]
            full = arxiv_fulltext(client, aid)
            if full.coverage is Coverage.FULL:
                return full

        for fn in (openalex_abstract, crossref_abstract):
            got = fn(client, doi)
            if got.coverage is not Coverage.NONE:
                return got

    return SourceText(Coverage.NONE, origin="none")
