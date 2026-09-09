"""
Crossref client.

Crossref is the DOI registration agency for scholarly publishing and holds
metadata for well over a hundred million works. It is the correct authority for
"does this DOI exist and what is it": free, no key required, and definitive for
the question asked.

Two operations:

    resolve(doi)     Look up a specific DOI. A 404 here is meaningful — it
                     means no registrant has ever deposited that identifier.

    search(title)    Find works matching a title. Used for references carrying
                     no identifier, where the question becomes "was this paper
                     ever written" rather than "does this DOI point at it".
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

from ..http import Client, NotFound

BASE = "https://api.crossref.org"


@dataclass
class Work:
    """A bibliographic record as Crossref holds it."""

    doi: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    container: str | None = None
    publisher: str | None = None
    type: str | None = None
    url: str | None = None

    @property
    def evidence_url(self) -> str:
        return f"https://doi.org/{self.doi}"


def _first_title(item: dict) -> str | None:
    titles = item.get("title") or []
    return titles[0].strip() if titles and titles[0] else None


def _authors(item: dict) -> list[str]:
    out: list[str] = []
    for a in item.get("author") or []:
        surname = (a.get("family") or "").strip()
        if surname:
            out.append(surname)
        elif a.get("name"):
            out.append(a["name"].strip())
    return out


def _year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def to_work(item: dict) -> Work:
    container = item.get("container-title") or []
    return Work(
        doi=(item.get("DOI") or "").lower(),
        title=_first_title(item),
        authors=_authors(item),
        year=_year(item),
        container=container[0] if container else None,
        publisher=item.get("publisher"),
        type=item.get("type"),
        url=item.get("URL"),
    )


class Crossref:
    name = "crossref"

    def __init__(self, client: Client):
        self.client = client

    def resolve(self, doi: str) -> Work:
        """Raises NotFound if Crossref holds no such DOI, Unreachable on error."""
        url = f"{BASE}/works/{urllib.parse.quote(doi, safe='')}"
        if self.client.mailto:
            url += f"?mailto={urllib.parse.quote(self.client.mailto)}"
        data = self.client.get(url).json()
        item = data.get("message")
        if not item:
            raise NotFound(doi)
        return to_work(item)

    def search(self, title: str, *, rows: int = 5,
               author: str | None = None) -> list[Work]:
        """Search by bibliographic string, optionally biased by author surname."""
        params = {
            "query.bibliographic": title[:300],
            "rows": str(rows),
            "select": ("DOI,title,author,issued,published-print,"
                       "published-online,container-title,publisher,type,URL"),
        }
        if author:
            params["query.author"] = author
        if self.client.mailto:
            params["mailto"] = self.client.mailto

        url = f"{BASE}/works?{urllib.parse.urlencode(params)}"
        try:
            data = self.client.get(url).json()
        except NotFound:
            return []
        items = (data.get("message") or {}).get("items") or []
        return [to_work(i) for i in items]
