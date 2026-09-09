"""
Verification orchestration.

Routes each extracted citation to the authority that can answer for it, then
converts the answer into a verdict.

The control flow is deliberately boring. Every path that fails to reach a
conclusion returns UNREACHABLE and says why; no path guesses. The one piece of
real judgment is in match.assess, which is kept in its own module so that the
question "when do we accuse a citation of being wrong" can be reviewed in
isolation from the plumbing.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, match
from .extract import extract, extract_from_file
from .http import Client, NotFound, Unreachable
from .models import Citation, Finding, Kind, Report, Verdict
from .sources.arxiv import Arxiv
from .sources.crossref import Crossref

log = logging.getLogger(__name__)

# A DOI prefix is 10.NNNN where NNNN is a registrant assigned by a registration
# agency. Syntactically valid but obviously impossible prefixes are rejected
# before spending a network call.
DOI_SYNTAX_RE = re.compile(r"^10\.\d{4,9}/\S+$")


class Verifier:
    def __init__(
        self,
        client: Client | None = None,
        *,
        check_urls: bool = True,
        search_unidentified: bool = True,
        workers: int = 4,
    ):
        self.client = client or Client(version=__version__)
        self.crossref = Crossref(self.client)
        self.arxiv = Arxiv(self.client)
        self.check_urls = check_urls
        self.search_unidentified = search_unidentified
        self.workers = max(1, workers)

    # -- per-citation routing ---------------------------------------------

    def check(self, c: Citation) -> Finding:
        try:
            if c.kind is Kind.DOI:
                return self._check_doi(c)
            if c.kind is Kind.ARXIV:
                return self._check_arxiv(c)
            if c.kind is Kind.URL:
                return self._check_url(c)
            return self._check_bibliographic(c)
        except Unreachable as exc:
            return Finding(
                citation=c, verdict=Verdict.UNREACHABLE, authority="-",
                detail=f"check could not be completed: {exc}",
            )
        except Exception as exc:                       # never crash a run
            log.exception("unexpected error checking %s", c.raw)
            return Finding(
                citation=c, verdict=Verdict.UNREACHABLE, authority="-",
                detail=f"internal error, treated as inconclusive: {exc!r}",
            )

    def _check_doi(self, c: Citation) -> Finding:
        doi = (c.identifier or "").strip()
        if not DOI_SYNTAX_RE.match(doi):
            return Finding(
                citation=c, verdict=Verdict.MALFORMED, authority="crossref",
                detail=f"{doi!r} is not a syntactically valid DOI",
            )

        try:
            work = self.crossref.resolve(doi)
        except NotFound:
            return Finding(
                citation=c, verdict=Verdict.NOT_FOUND, authority="crossref",
                detail=("Crossref holds no record for this DOI. No registrant "
                        "has ever deposited it."),
                evidence_url=f"https://api.crossref.org/works/{doi}",
            )

        mismatch, sim, overlap, detail = match.assess(
            c.claimed_title, c.claimed_authors, c.claimed_year,
            work.title, work.authors, work.year,
        )
        return Finding(
            citation=c,
            verdict=Verdict.MISMATCH if mismatch else Verdict.VERIFIED,
            authority="crossref", detail=detail,
            resolved_title=work.title, resolved_authors=work.authors,
            resolved_year=work.year, title_similarity=sim,
            author_overlap=overlap, evidence_url=work.evidence_url,
        )

    def _check_arxiv(self, c: Citation) -> Finding:
        aid = (c.identifier or "").strip()
        try:
            pre = self.arxiv.resolve(aid)
        except NotFound:
            return Finding(
                citation=c, verdict=Verdict.NOT_FOUND, authority="arxiv",
                detail="arXiv holds no preprint with this identifier.",
                evidence_url=f"https://arxiv.org/abs/{aid}",
            )

        mismatch, sim, overlap, detail = match.assess(
            c.claimed_title, c.claimed_authors, c.claimed_year,
            pre.title, pre.authors, pre.year,
        )
        return Finding(
            citation=c,
            verdict=Verdict.MISMATCH if mismatch else Verdict.VERIFIED,
            authority="arxiv", detail=detail,
            resolved_title=pre.title, resolved_authors=pre.authors,
            resolved_year=pre.year, title_similarity=sim,
            author_overlap=overlap, evidence_url=pre.evidence_url,
        )

    def _check_url(self, c: Citation) -> Finding:
        url = c.identifier or c.raw
        if not self.check_urls:
            return Finding(
                citation=c, verdict=Verdict.UNVERIFIABLE, authority="-",
                detail="URL checking disabled for this run",
            )
        alive, status = self.client.head_ok(url)
        if alive:
            return Finding(
                citation=c, verdict=Verdict.VERIFIED, authority="http",
                detail=f"link responded HTTP {status}", evidence_url=url,
            )
        return Finding(
            citation=c, verdict=Verdict.NOT_FOUND, authority="http",
            detail=(f"link returned HTTP {status}. Note this proves the URL is "
                    "dead, not that the content it described never existed."),
            evidence_url=url,
        )

    def _check_bibliographic(self, c: Citation) -> Finding:
        """
        A reference with no identifier.

        Searching an authority for the described work is the only way to test
        it, and the bar for declaring a match is set high in match.py: with no
        DOI anchoring the claim, a loose match would let the tool "confirm" a
        fabricated reference by finding some vaguely similar real paper.
        """
        title = (c.claimed_title or "").strip()
        if not self.search_unidentified or len(title) < 15:
            return Finding(
                citation=c, verdict=Verdict.UNVERIFIABLE, authority="-",
                detail=("no identifier and no title specific enough to search; "
                        "requires manual checking"),
            )

        author = c.claimed_authors[0] if c.claimed_authors else None
        candidates = self.crossref.search(title, author=author)
        if not candidates:
            return Finding(
                citation=c, verdict=Verdict.NOT_FOUND, authority="crossref",
                detail=("no work matching this title appears in Crossref. "
                        "Either the reference is to something outside Crossref's "
                        "coverage (books, reports, grey literature) or it "
                        "describes a work that does not exist."),
                evidence_url=(
                    "https://search.crossref.org/?q="
                    + title[:120].replace(" ", "+")
                ),
            )

        best = None
        best_sim = 0.0
        for cand in candidates:
            ok, sim = match.is_plausible_search_hit(
                title, cand.title or "", c.claimed_authors, cand.authors
            )
            if sim > best_sim:
                best, best_sim = cand, sim
            if ok:
                return Finding(
                    citation=c, verdict=Verdict.VERIFIED, authority="crossref",
                    detail=(f"matched a Crossref record by title search "
                            f"({sim:.0f}% similarity); no DOI given in document"),
                    resolved_title=cand.title, resolved_authors=cand.authors,
                    resolved_year=cand.year, title_similarity=sim,
                    evidence_url=cand.evidence_url,
                )

        return Finding(
            citation=c, verdict=Verdict.NOT_FOUND, authority="crossref",
            detail=(f"no Crossref record matches this description. Closest was "
                    f"{(best.title if best else 'nothing')!r} at {best_sim:.0f}% "
                    "similarity, below the threshold for a match."),
            resolved_title=best.title if best else None,
            title_similarity=best_sim or None,
            evidence_url=best.evidence_url if best else None,
        )

    # -- document level ----------------------------------------------------

    def verify_citations(self, citations: list[Citation],
                         document: str = "-") -> Report:
        if self.workers == 1:
            findings = [self.check(c) for c in citations]
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                findings = list(pool.map(self.check, citations))

        findings.sort(key=lambda f: (f.citation.line, f.citation.raw))
        return Report(document=document, findings=findings,
                      tool_version=__version__)

    def verify_text(self, text: str, document: str = "-") -> Report:
        return self.verify_citations(extract(text), document)

    def verify_file(self, path: str | Path) -> Report:
        return self.verify_citations(extract_from_file(path), str(path))
