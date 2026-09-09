"""
arXiv client.

arXiv is the authority for preprint identifiers. Its API returns Atom XML
rather than JSON, and — importantly for correctness — a query for a
non-existent identifier returns HTTP 200 with an empty or error feed rather
than a 404.

Treating "200 means it exists" would silently verify every fabricated arXiv
reference in a document, which is the precise failure this tool exists to
prevent. The entry contents determine the verdict here, never the status code.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from ..http import Client, NotFound

BASE = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"

VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)


@dataclass
class Preprint:
    arxiv_id: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None

    @property
    def evidence_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"


def _surname(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[-1] if parts else full_name.strip()


def parse_feed(body: str, arxiv_id: str) -> Preprint:
    """
    Parse an arXiv Atom response into a Preprint.

    Raises NotFound when the feed contains no real entry — including arXiv's
    convention of returning a single entry titled "Error" for an unknown id.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise NotFound(f"{arxiv_id}: unparseable response") from exc

    entries = root.findall(f"{ATOM}entry")
    if not entries:
        raise NotFound(arxiv_id)

    entry = entries[0]

    title_el = entry.find(f"{ATOM}title")
    title = " ".join((title_el.text or "").split()) if title_el is not None else ""
    id_el = entry.find(f"{ATOM}id")
    id_text = (id_el.text or "") if id_el is not None else ""

    if title.strip().lower() == "error" or "api/errors" in id_text:
        raise NotFound(arxiv_id)

    authors = []
    for a in entry.findall(f"{ATOM}author"):
        n = a.find(f"{ATOM}name")
        if n is not None and n.text:
            authors.append(_surname(n.text))

    year = None
    pub = entry.find(f"{ATOM}published")
    if pub is not None and pub.text and len(pub.text) >= 4:
        try:
            year = int(pub.text[:4])
        except ValueError:
            year = None

    doi = None
    doi_el = entry.find(f"{ARXIV_NS}doi")
    if doi_el is not None and doi_el.text:
        doi = doi_el.text.strip().lower()

    return Preprint(
        arxiv_id=VERSION_RE.sub("", arxiv_id.strip()),
        title=title or None, authors=authors, year=year, doi=doi,
    )


class Arxiv:
    name = "arxiv"

    def __init__(self, client: Client):
        self.client = client

    def resolve(self, arxiv_id: str) -> Preprint:
        base_id = VERSION_RE.sub("", arxiv_id.strip())
        url = f"{BASE}?{urllib.parse.urlencode({'id_list': base_id, 'max_results': 1})}"
        body = self.client.get(url, accept="application/atom+xml").text()
        return parse_feed(body, base_id)
