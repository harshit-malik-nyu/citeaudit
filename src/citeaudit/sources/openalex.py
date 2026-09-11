"""
OpenAlex client.

Crossref is authoritative for DOIs but covers scholarly publishing only. Law
reviews, books, government reports, dissertations, working papers, and most
grey literature are outside it. A reference to any of those is real and will
still come back NOT_FOUND from Crossref alone.

That matters more than it sounds. A tool that flags legitimate references as
fabricated is worse than no tool: it trains its users to ignore it, and the one
time it is right, nobody looks. False accusations are the failure mode that
kills adoption, so coverage breadth is a correctness requirement, not a
nice-to-have.

OpenAlex indexes roughly 250 million works from Crossref, PubMed, DOAJ,
institutional repositories, and others. It is consulted as a fallback: only
after Crossref has already said no. Two independent authorities missing a work
is materially stronger evidence than one missing it.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

from ..http import Client, NotFound

BASE = "https://api.openalex.org"


@dataclass
class Record:
    openalex_id: str
    doi: str | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    type: str | None = None
    venue: str | None = None

    @property
    def evidence_url(self) -> str:
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return self.openalex_id or f"{BASE}/works"


def _surname(display_name: str) -> str:
    parts = (display_name or "").strip().split()
    return parts[-1] if parts else ""


def to_record(item: dict) -> Record:
    doi = item.get("doi") or ""
    doi = doi.replace("https://doi.org/", "").lower() or None

    authors = []
    for a in item.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name")
        if name:
            s = _surname(name)
            if s:
                authors.append(s)

    venue = None
    pl = item.get("primary_location") or {}
    src = pl.get("source") or {}
    if src.get("display_name"):
        venue = src["display_name"]

    return Record(
        openalex_id=item.get("id") or "",
        doi=doi,
        title=(item.get("title") or item.get("display_name") or None),
        authors=authors,
        year=item.get("publication_year"),
        type=item.get("type"),
        venue=venue,
    )


SELECT = "id,doi,title,display_name,authorships,publication_year,type,primary_location"


class OpenAlex:
    name = "openalex"

    def __init__(self, client: Client):
        self.client = client

    def _mailto(self, params: dict) -> dict:
        if self.client.mailto:
            params["mailto"] = self.client.mailto
        return params

    def resolve_doi(self, doi: str) -> Record:
        url = f"{BASE}/works/doi:{urllib.parse.quote(doi, safe='')}"
        params = self._mailto({"select": SELECT})
        url = f"{url}?{urllib.parse.urlencode(params)}"
        item = self.client.get(url).json()
        if not item or not item.get("id"):
            raise NotFound(doi)
        return to_record(item)

    def search_title(self, title: str, *, rows: int = 5) -> list[Record]:
        """
        Title search.

        Uses OpenAlex's title.search filter rather than free-text `search`,
        which also matches abstracts and would return topically-similar work
        for a title that does not exist — manufacturing the false assurance
        this tool exists to prevent.
        """
        cleaned = title.replace(",", " ").strip()[:250]
        params = self._mailto({
            "filter": f"title.search:{cleaned}",
            "per-page": str(rows),
            "select": SELECT,
        })
        url = f"{BASE}/works?{urllib.parse.urlencode(params)}"
        try:
            data = self.client.get(url).json()
        except NotFound:
            return []
        return [to_record(i) for i in (data.get("results") or [])]

    def sample_works(self, *, count: int = 50, seed: int = 42,
                     from_year: int | None = None,
                     to_year: int | None = None,
                     extra_filter: str | None = None) -> list[dict]:
        """
        Random sample of works, used by the base-rate study.

        OpenAlex supports seeded random sampling server-side, which gives a
        reproducible draw without downloading the index. The seed is recorded
        in the study manifest so the sample can be redrawn exactly.
        """
        filters = ["has_doi:true"]
        if from_year:
            filters.append(f"from_publication_date:{from_year}-01-01")
        if to_year:
            filters.append(f"to_publication_date:{to_year}-12-31")
        if extra_filter:
            filters.append(extra_filter)

        params = self._mailto({
            "filter": ",".join(filters),
            "sample": str(min(count, 200)),
            "seed": str(seed),
            "per-page": str(min(count, 200)),
            "select": SELECT,
        })
        url = f"{BASE}/works?{urllib.parse.urlencode(params)}"
        try:
            data = self.client.get(url).json()
        except NotFound:
            return []
        return data.get("results") or []
