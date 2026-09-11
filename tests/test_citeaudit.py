"""
Offline tests.

Nothing here touches the network. Authority responses are represented by stub
clients whose payloads are shaped exactly like the real ones, so these tests
check logic, not connectivity.

Live verification against Crossref and arXiv runs separately in CI
(tests/test_live.py, marked `live`), and its results are committed as evidence.
Splitting them this way means a failing test always means the code is wrong,
never that an API was slow — which is the same distinction the tool itself
draws between NOT_FOUND and UNREACHABLE.
"""

from __future__ import annotations

import json

import pytest

from citeaudit import __version__
from citeaudit.extract import (
    extract, find_identifiers, normalise_doi, strip_trailing,
)
from citeaudit.http import Client, NotFound, Response, Unreachable
from citeaudit.match import (
    assess, author_overlap, is_plausible_search_hit, normalise,
    title_similarity,
)
from citeaudit.models import Citation, Finding, Kind, Report, Verdict
from citeaudit.report import to_html, to_json, to_markdown, to_terminal
from citeaudit.sources.arxiv import Arxiv, parse_feed
from citeaudit.sources.crossref import Crossref, to_work
from citeaudit.sources.openalex import OpenAlex, to_record
from citeaudit.verify import Verifier


# ===========================================================================
# Extraction
# ===========================================================================

class TestExtraction:

    def test_bare_doi(self):
        cits = find_identifiers("see 10.1038/nature12373 for detail")
        assert [c.identifier for c in cits] == ["10.1038/nature12373"]

    def test_doi_with_prefix_forms(self):
        for text in (
            "doi:10.1038/nature12373",
            "DOI: 10.1038/nature12373",
            "https://doi.org/10.1038/nature12373",
            "http://dx.doi.org/10.1038/nature12373",
        ):
            cits = find_identifiers(text)
            assert [c.identifier for c in cits] == ["10.1038/nature12373"], text

    def test_trailing_sentence_punctuation_stripped(self):
        cits = find_identifiers("as shown in 10.1038/nature12373.")
        assert cits[0].identifier == "10.1038/nature12373"

    def test_balanced_brackets_inside_doi_preserved(self):
        """Some real DOIs contain parentheses; only unmatched ones come off."""
        assert strip_trailing("10.1016/S0140(97)10015-1") == "10.1016/S0140(97)10015-1"
        assert strip_trailing("10.1000/xyz)") == "10.1000/xyz"
        assert strip_trailing("10.1000/x(y)") == "10.1000/x(y)"

    def test_doi_normalised_to_lowercase(self):
        assert normalise_doi("10.1038/NATURE12373") == "10.1038/nature12373"

    def test_modern_and_legacy_arxiv(self):
        modern = find_identifiers("arXiv:2301.12345v2")
        assert modern[0].identifier == "2301.12345v2"
        assert modern[0].kind is Kind.ARXIV
        legacy = find_identifiers("arXiv:math.GT/0309136")
        assert legacy[0].identifier == "math.GT/0309136"

    def test_doi_and_arxiv_urls_not_double_counted_as_links(self):
        """A doi.org URL is checked as a DOI, which is stronger than liveness."""
        cits = find_identifiers("https://doi.org/10.1038/nature12373")
        assert len(cits) == 1
        assert cits[0].kind is Kind.DOI

    def test_plain_urls_extracted(self):
        cits = find_identifiers("see https://example.com/paper.pdf here")
        assert cits[0].kind is Kind.URL
        assert cits[0].identifier == "https://example.com/paper.pdf"

    def test_reference_claims_attached_to_identifier(self):
        doc = (
            "## References\n\n"
            '[1] Smith, J. A. (2019). "Automated compliance frameworks". '
            "Journal of Public Administration, 45(3). doi:10.1016/j.test.2019.03.011\n"
        )
        cits = extract(doc)
        assert len(cits) == 1
        c = cits[0]
        assert c.identifier == "10.1016/j.test.2019.03.011"
        assert c.claimed_title == "Automated compliance frameworks"
        assert "Smith" in c.claimed_authors
        assert c.claimed_year == 2019

    def test_reference_without_identifier_still_captured(self):
        doc = (
            "References\n\n"
            '[4] Nguyen, T. (2022). "A study of imaginary compliance systems". '
            "Fictional Review, 1(1).\n"
        )
        cits = extract(doc)
        assert len(cits) == 1
        assert cits[0].kind is Kind.BIBLIOGRAPHIC
        assert cits[0].identifier is None
        assert cits[0].claimed_year == 2022

    def test_duplicate_identifiers_deduplicated(self):
        doc = "10.1038/nature12373 and again 10.1038/nature12373"
        assert len(extract(doc)) == 1

    def test_empty_document(self):
        assert extract("") == []
        assert extract("no citations here at all") == []

    def test_line_numbers_recorded(self):
        doc = "line one\nline two\n10.1038/nature12373\n"
        assert extract(doc)[0].line == 3


# ===========================================================================
# Matching
# ===========================================================================

class TestMatching:

    def test_normalise_strips_accents_and_punctuation(self):
        assert normalise("Étude, de l'ADN!") == "etude de l adn"

    def test_identical_titles_match(self):
        assert title_similarity("Machine Learning", "machine learning") == 100.0

    def test_subtitle_does_not_break_match(self):
        sim = title_similarity(
            "Attention Is All You Need",
            "Attention Is All You Need: Transformer Architectures",
        )
        assert sim is not None and sim >= 85

    def test_unrelated_titles_score_low(self):
        sim = title_similarity(
            "Automated compliance frameworks in social security",
            "Crystal structure of ribosomal protein L7",
        )
        assert sim is not None and sim < 60

    def test_missing_title_returns_none(self):
        assert title_similarity(None, "something") is None
        assert title_similarity("something", "") is None

    def test_author_overlap_is_asymmetric(self):
        """'Smith et al.' citing a twelve-author paper is correct."""
        ov = author_overlap(["Smith"], ["Smith", "Jones", "Patel", "Kim"])
        assert ov == 1.0

    def test_author_overlap_detects_no_shared_authors(self):
        assert author_overlap(["Smith"], ["Kowalski", "Petrov"]) == 0.0

    def test_mismatch_detected_on_divergent_title(self):
        mismatch, sim, _, detail = assess(
            "Automated compliance frameworks in social security", ["Smith"], 2019,
            "Crystal structure of ribosomal protein L7", ["Kowalski"], 1998,
        )
        assert mismatch is True
        assert "DIFFERENT work" in detail

    def test_no_mismatch_when_authors_corroborate(self):
        """Low title similarity plus strong author agreement is not an accusation."""
        mismatch, _, _, detail = assess(
            "Compliance frameworks", ["Smith", "Doe"], 2019,
            "A Study of Automated Decision Systems in Welfare", ["Smith", "Doe"], 2019,
        )
        assert mismatch is False
        assert "authors agree" in detail

    def test_no_accusation_without_a_claimed_title(self):
        """Author or year discrepancy alone never produces MISMATCH."""
        mismatch, sim, _, _ = assess(
            None, ["Smith"], 1999,
            "Some Real Paper", ["Kowalski"], 2020,
        )
        assert mismatch is False
        assert sim is None

    def test_year_tolerance_absorbs_online_first(self):
        mismatch, _, _, _ = assess(
            "Attention Is All You Need", ["Vaswani"], 2017,
            "Attention Is All You Need", ["Vaswani"], 2018,
        )
        assert mismatch is False

    def test_search_hit_requires_high_similarity(self):
        ok, _ = is_plausible_search_hit(
            "A study of imaginary compliance systems",
            "A study of real compliance systems in Denmark",
            ["Nguyen"], ["Andersen"],
        )
        assert ok is False

    def test_search_hit_accepts_near_identical_title(self):
        ok, sim = is_plausible_search_hit(
            "Attention Is All You Need", "Attention is all you need",
            ["Vaswani"], ["Vaswani"],
        )
        assert ok is True and sim >= 90


# ===========================================================================
# Verdict semantics — the integrity core
# ===========================================================================

class TestVerdictSemantics:

    def test_failure_and_inconclusive_partition(self):
        for v in (Verdict.NOT_FOUND, Verdict.MISMATCH, Verdict.MALFORMED):
            assert v.is_failure and not v.is_inconclusive
        for v in (Verdict.UNREACHABLE, Verdict.UNVERIFIABLE):
            assert v.is_inconclusive and not v.is_failure
        assert not Verdict.VERIFIED.is_failure
        assert not Verdict.VERIFIED.is_inconclusive

    def test_unreachable_is_never_a_failure(self):
        """
        THE central invariant. A network problem must never be reported as a
        fabricated citation — that would make the tool commit the error it
        exists to detect.
        """
        r = Report(document="d", findings=[
            Finding(citation=Citation(raw="x", kind=Kind.DOI),
                    verdict=Verdict.UNREACHABLE, authority="-"),
        ])
        assert r.failures == []
        assert len(r.inconclusive) == 1

    def test_score_excludes_inconclusive_from_denominator(self):
        r = Report(document="d", findings=[
            Finding(citation=Citation(raw="a", kind=Kind.DOI),
                    verdict=Verdict.VERIFIED, authority="crossref"),
            Finding(citation=Citation(raw="b", kind=Kind.DOI),
                    verdict=Verdict.NOT_FOUND, authority="crossref"),
            Finding(citation=Citation(raw="c", kind=Kind.DOI),
                    verdict=Verdict.UNREACHABLE, authority="-"),
            Finding(citation=Citation(raw="d", kind=Kind.URL),
                    verdict=Verdict.UNVERIFIABLE, authority="-"),
        ])
        assert r.conclusive == 2
        assert r.integrity_score == pytest.approx(0.5)

    def test_score_is_none_when_nothing_conclusive(self):
        """Never report 0% or 100% when the answer is 'we could not check'."""
        r = Report(document="d", findings=[
            Finding(citation=Citation(raw="a", kind=Kind.DOI),
                    verdict=Verdict.UNREACHABLE, authority="-"),
        ])
        assert r.integrity_score is None

    def test_empty_report_scores_none(self):
        assert Report(document="d").integrity_score is None


# ===========================================================================
# Authority clients, against stub transports
# ===========================================================================

class StubClient(Client):
    """Client with a scripted response table instead of a network."""

    def __init__(self, table: dict[str, tuple[int, str]]):
        super().__init__(cache_dir=None, use_cache=False, retries=1)
        self.table = table
        self.calls: list[str] = []

    def get(self, url, *, accept="application/json", allow_404=True, method="GET"):
        self.calls.append(url)
        for pattern, (status, body) in self.table.items():
            if pattern in url:
                if status == 404 and allow_404:
                    raise NotFound(url)
                if status >= 500:
                    raise Unreachable(f"{url}: HTTP {status}")
                return Response(url=url, status=status, body=body.encode())
        raise NotFound(url)


CROSSREF_HIT = json.dumps({
    "message": {
        "DOI": "10.1038/nature12373",
        "title": ["A real paper about real things"],
        "author": [{"family": "Kowalski", "given": "A"},
                   {"family": "Petrov", "given": "B"}],
        "issued": {"date-parts": [[2013]]},
        "container-title": ["Nature"],
        "publisher": "Springer",
        "type": "journal-article",
    }
})

ARXIV_HIT = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
  </entry>
</feed>"""

ARXIV_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>ArXiv Query</title></feed>"""

ARXIV_ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/api/errors#incorrect_id_format</id>
    <title>Error</title>
  </entry>
</feed>"""


class TestAuthorities:

    def test_crossref_parses_record(self):
        cr = Crossref(StubClient({"/works/": (200, CROSSREF_HIT)}))
        w = cr.resolve("10.1038/nature12373")
        assert w.title == "A real paper about real things"
        assert w.authors == ["Kowalski", "Petrov"]
        assert w.year == 2013
        assert w.evidence_url == "https://doi.org/10.1038/nature12373"

    def test_crossref_404_raises_not_found(self):
        cr = Crossref(StubClient({"/works/": (404, "")}))
        with pytest.raises(NotFound):
            cr.resolve("10.9999/does-not-exist")

    def test_crossref_year_falls_back_across_date_fields(self):
        item = {"DOI": "10.1/x", "title": ["T"],
                "published-online": {"date-parts": [[2021, 4]]}}
        assert to_work(item).year == 2021

    def test_arxiv_parses_entry(self):
        p = parse_feed(ARXIV_HIT, "1706.03762")
        assert p.title == "Attention Is All You Need"
        assert p.authors == ["Vaswani", "Shazeer"]
        assert p.year == 2017

    def test_arxiv_empty_feed_is_not_found_despite_http_200(self):
        """
        REGRESSION GUARD. arXiv answers unknown ids with HTTP 200 and an empty
        feed. Trusting the status code would verify every fabricated arXiv
        reference in a document.
        """
        with pytest.raises(NotFound):
            parse_feed(ARXIV_EMPTY, "9999.99999")

    def test_arxiv_error_entry_is_not_found(self):
        with pytest.raises(NotFound):
            parse_feed(ARXIV_ERROR, "not-an-id")

    def test_arxiv_version_suffix_stripped(self):
        p = parse_feed(ARXIV_HIT, "1706.03762v5")
        assert p.arxiv_id == "1706.03762"


# ===========================================================================
# End-to-end verification against stubs
# ===========================================================================

class TestVerifier:

    def test_matching_doi_verifies(self):
        v = Verifier(StubClient({"/works/": (200, CROSSREF_HIT)}), workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.1038/nature12373",
                     claimed_title="A real paper about real things",
                     claimed_authors=["Kowalski"], claimed_year=2013)
        assert v.check(c).verdict is Verdict.VERIFIED

    def test_nonexistent_doi_is_not_found_after_both_authorities_miss(self):
        """Both Crossref and the OpenAlex fallback must miss before accusing."""
        stub = StubClient({"/works/": (404, "")})
        v = Verifier(stub, workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.9999/nope")
        f = v.check(c)
        assert f.verdict is Verdict.NOT_FOUND
        assert f.authority == "crossref+openalex"
        assert "no registration" in f.detail.lower()
        # both authorities were actually consulted
        assert any("api.crossref.org" in u for u in stub.calls)
        assert any("api.openalex.org" in u for u in stub.calls)

    def test_real_doi_wrong_paper_is_mismatch(self):
        """The dangerous case: link resolves, but to something else entirely."""
        v = Verifier(StubClient({"/works/": (200, CROSSREF_HIT)}), workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.1038/nature12373",
                     claimed_title="Automated compliance frameworks in welfare",
                     claimed_authors=["Smith"], claimed_year=2019)
        f = v.check(c)
        assert f.verdict is Verdict.MISMATCH
        assert f.resolved_title == "A real paper about real things"

    def test_server_error_is_unreachable_not_not_found(self):
        v = Verifier(StubClient({"/works/": (503, "")}), workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.1038/nature12373")
        assert v.check(c).verdict is Verdict.UNREACHABLE

    def test_malformed_doi_short_circuits_without_network(self):
        stub = StubClient({})
        v = Verifier(stub, workers=1)
        c = Citation(raw="10.abc/xyz", kind=Kind.DOI, identifier="10.abc/xyz")
        assert v.check(c).verdict is Verdict.MALFORMED
        assert stub.calls == []

    def test_unidentified_reference_with_no_match_is_not_found(self):
        empty = json.dumps({"message": {"items": []}})
        v = Verifier(StubClient({"/works?": (200, empty)}), workers=1)
        c = Citation(raw="x", kind=Kind.BIBLIOGRAPHIC,
                     claimed_title="A study of imaginary compliance systems",
                     claimed_authors=["Nguyen"], claimed_year=2022)
        f = v.check(c)
        assert f.verdict is Verdict.NOT_FOUND
        assert f.evidence_url and "search.crossref.org" in f.evidence_url

    def test_short_title_without_identifier_is_unverifiable(self):
        v = Verifier(StubClient({}), workers=1)
        c = Citation(raw="x", kind=Kind.BIBLIOGRAPHIC, claimed_title="Short")
        assert v.check(c).verdict is Verdict.UNVERIFIABLE

    def test_unexpected_exception_becomes_inconclusive_not_failure(self):
        class Exploding(StubClient):
            def get(self, *a, **k):
                raise ValueError("boom")

        v = Verifier(Exploding({}), workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.1038/nature12373")
        f = v.check(c)
        assert f.verdict is Verdict.UNREACHABLE
        assert not f.verdict.is_failure


# ===========================================================================
# Reporting
# ===========================================================================

@pytest.fixture
def mixed_report() -> Report:
    return Report(document="doc.md", tool_version=__version__, findings=[
        Finding(citation=Citation(raw="a", kind=Kind.DOI, line=1,
                                  identifier="10.1/ok"),
                verdict=Verdict.VERIFIED, authority="crossref",
                evidence_url="https://doi.org/10.1/ok"),
        Finding(citation=Citation(raw="b", kind=Kind.DOI, line=2,
                                  identifier="10.9/nope",
                                  claimed_title="Invented Paper"),
                verdict=Verdict.NOT_FOUND, authority="crossref",
                detail="Crossref holds no record for this DOI.",
                evidence_url="https://api.crossref.org/works/10.9/nope"),
        Finding(citation=Citation(raw="c", kind=Kind.DOI, line=3,
                                  identifier="10.1/other",
                                  claimed_title="Claimed Title"),
                verdict=Verdict.MISMATCH, authority="crossref",
                resolved_title="Actual Different Title", title_similarity=12.0),
        Finding(citation=Citation(raw="d", kind=Kind.URL, line=4,
                                  identifier="https://x.invalid"),
                verdict=Verdict.UNREACHABLE, authority="-"),
    ])

class TestReporting:

    def test_json_roundtrips(self, mixed_report):
        d = json.loads(to_json(mixed_report))
        assert d["summary"]["total_citations"] == 4
        assert d["summary"]["not_found"] == 1
        assert d["summary"]["conclusive_checks"] == 3
        assert len(d["findings"]) == 4

    def test_markdown_lists_failures_with_evidence(self, mixed_report):
        md = to_markdown(mixed_report)
        assert "10.9/nope" in md
        assert "api.crossref.org" in md
        assert "did not hold up" in md

    def test_markdown_separates_inconclusive(self, mixed_report):
        md = to_markdown(mixed_report)
        assert "inconclusive" in md.lower()
        assert "not counted as failures" in md

    def test_terminal_output_is_plain_without_colour(self, mixed_report):
        out = to_terminal(mixed_report, colour=False)
        assert "\033[" not in out
        assert "No such record" in out

    def test_html_is_self_contained(self, mixed_report):
        h = to_html(mixed_report)
        assert h.startswith("<!doctype html>")
        assert "<style>" in h
        assert "src=" not in h          # no external assets
        assert "Actual Different Title" in h

    def test_html_escapes_injected_markup(self):
        r = Report(document="d", findings=[
            Finding(citation=Citation(raw="<script>alert(1)</script>",
                                      kind=Kind.BIBLIOGRAPHIC, line=1,
                                      claimed_title="<img onerror=x>"),
                    verdict=Verdict.NOT_FOUND, authority="crossref"),
        ])
        h = to_html(r)
        assert "<script>alert(1)</script>" not in h
        assert "&lt;" in h

    def test_empty_report_renders_in_every_format(self):
        r = Report(document="empty.md", tool_version=__version__)
        assert "No citations found." in to_terminal(r, colour=False)
        assert "No citations found." in to_markdown(r)
        assert to_html(r).startswith("<!doctype html>")
        assert json.loads(to_json(r))["summary"]["total_citations"] == 0


# ===========================================================================
# Deduplication semantics
# ===========================================================================

class TestDeduplication:

    def test_same_identifier_same_claim_is_one_citation(self):
        doc = (
            "References\n\n"
            '[1] Lee, K. (2015). "Deep learning". Nature. doi:10.1038/nature14539\n'
            '[2] Lee, K. (2015). "Deep learning". Nature. doi:10.1038/nature14539\n'
        )
        assert len(extract(doc)) == 1

    def test_same_identifier_different_claims_kept_separately(self):
        """
        REGRESSION. Keying duplicates on the identifier alone dropped the
        second assertion — discarding the exact signal that reveals a DOI
        attached to the wrong paper. At most one of these two claims can be
        true, so both must be checked.
        """
        doc = (
            "References\n\n"
            '[1] LeCun, Y. (2015). "Deep learning". Nature. doi:10.1038/nature14539\n'
            '[2] Harper, S. J. (2016). "Procedural baselines for administrative '
            'automation". Admin Law Quarterly. doi:10.1038/nature14539\n'
        )
        cits = extract(doc)
        assert len(cits) == 2
        titles = {c.claimed_title for c in cits}
        assert "Deep learning" in titles
        assert any("Procedural baselines" in (t or "") for t in titles)

    def test_bare_repeated_identifier_still_deduplicates(self):
        assert len(extract("10.1038/nature14539 and 10.1038/nature14539")) == 1


# ===========================================================================
# Fallback authority
# ===========================================================================

OPENALEX_HIT = json.dumps({
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.5555/lawreview.2022.33.1",
    "title": "The reasoned decision requirement and automated administrative action",
    "authorships": [{"author": {"display_name": "Lisa Burton Crawford"}}],
    "publication_year": 2022,
    "type": "article",
    "primary_location": {"source": {"display_name": "Public Law Review"}},
})

OPENALEX_SEARCH = json.dumps({"results": [json.loads(OPENALEX_HIT)]})
OPENALEX_EMPTY = json.dumps({"results": []})


class TestFallbackAuthority:

    def test_doi_missing_from_crossref_but_held_by_openalex_verifies(self):
        """
        The false-positive guard. Crossref does not cover law reviews, books,
        reports or theses; flagging those as fabricated would make the tool
        untrustworthy on exactly the documents it is meant to check.
        """
        stub = StubClient({
            "api.crossref.org": (404, ""),
            "api.openalex.org/works/doi:": (200, OPENALEX_HIT),
        })
        v = Verifier(stub, workers=1)
        c = Citation(
            raw="x", kind=Kind.DOI, identifier="10.5555/lawreview.2022.33.1",
            claimed_title="The reasoned decision requirement and automated administrative action",
            claimed_authors=["Crawford"], claimed_year=2022,
        )
        f = v.check(c)
        assert f.verdict is Verdict.VERIFIED
        assert f.authority == "openalex"
        assert "not in Crossref" in f.detail

    def test_fallback_still_detects_mismatch(self):
        """Broader coverage must not become laxer checking."""
        stub = StubClient({
            "api.crossref.org": (404, ""),
            "api.openalex.org/works/doi:": (200, OPENALEX_HIT),
        })
        v = Verifier(stub, workers=1)
        c = Citation(
            raw="x", kind=Kind.DOI, identifier="10.5555/lawreview.2022.33.1",
            claimed_title="Crystal structure of ribosomal protein L7",
            claimed_authors=["Kowalski"], claimed_year=1998,
        )
        assert v.check(c).verdict is Verdict.MISMATCH

    def test_unreachable_fallback_does_not_mask_the_crossref_miss(self):
        """A failed second opinion is not evidence; the first verdict stands."""
        stub = StubClient({
            "api.crossref.org": (404, ""),
            "api.openalex.org": (503, ""),
        })
        v = Verifier(stub, workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.9999/nope")
        assert v.check(c).verdict is Verdict.NOT_FOUND

    def test_fallback_can_be_disabled(self):
        stub = StubClient({"api.crossref.org": (404, "")})
        v = Verifier(stub, use_fallback=False, workers=1)
        c = Citation(raw="x", kind=Kind.DOI, identifier="10.9999/nope")
        f = v.check(c)
        assert f.verdict is Verdict.NOT_FOUND
        assert not any("openalex" in u for u in stub.calls)

    def test_bibliographic_reference_found_only_in_openalex(self):
        stub = StubClient({
            "api.crossref.org": (200, json.dumps({"message": {"items": []}})),
            "api.openalex.org/works?": (200, OPENALEX_SEARCH),
        })
        v = Verifier(stub, workers=1)
        c = Citation(
            raw="x", kind=Kind.BIBLIOGRAPHIC,
            claimed_title="The reasoned decision requirement and automated administrative action",
            claimed_authors=["Crawford"], claimed_year=2022,
        )
        f = v.check(c)
        assert f.verdict is Verdict.VERIFIED
        assert f.authority == "openalex"

    def test_bibliographic_missing_everywhere_is_not_found(self):
        stub = StubClient({
            "api.crossref.org": (200, json.dumps({"message": {"items": []}})),
            "api.openalex.org/works?": (200, OPENALEX_EMPTY),
        })
        v = Verifier(stub, workers=1)
        c = Citation(
            raw="x", kind=Kind.BIBLIOGRAPHIC,
            claimed_title="A study of imaginary compliance systems in nowhere",
            claimed_authors=["Nguyen"], claimed_year=2022,
        )
        f = v.check(c)
        assert f.verdict is Verdict.NOT_FOUND
        assert "evidence, not proof" in f.detail


# ===========================================================================
# False-accusation guards
# ===========================================================================

class TestTitleExtractionGuards:
    """
    REGRESSION SUITE. In one live run over real arXiv bibliographies the tool
    reported 8 mismatches. Seven were its own fault: title extraction produced
    debris, `assess` compared debris against the record's real title, scored
    13-20%, and accused the author of citing the wrong paper.

    Every string below is taken verbatim from that run. A false accusation is
    the worst output this tool can produce, so these are the tests that matter
    most in the file.
    """

    REAL_REFERENCES = [
        ("Holger Bast, Stefan Funke. Fast routing in road networks with transit "
         "nodes. Science, 316 0 (5824): 0 566, 2007. 10.1126/science.1137521",
         "fast routing in road networks"),
        ("Mitchell G. Newberry, Christopher A. Ahern. Detecting evolutionary "
         "forces in language change. Nature, 551 0 (7679): 0 223--226, 2017. "
         "10.1038/nature24455",
         "detecting evolutionary forces"),
        ("R. Alexander Bentley, Matthew W. Hahn, and Stephen J. Shennan. Random "
         "drift and culture change. Proc. R. Soc. Lond. B Biol. Sci., 271 0 "
         "(1547): 0 1443--1450, 2004. 10.1098/rspb.2004.2746",
         "random drift and culture change"),
        ("Ryan Dew, Nicolas Padilla, and Anya Shchetkina. Your mmm is broken: "
         "Identification of nonlinear and time-varying effects in marketing mix "
         "models, 2024",
         "your mmm is broken"),
    ]

    @pytest.mark.parametrize("text,expected", REAL_REFERENCES)
    def test_real_titles_are_recovered_not_replaced_by_debris(self, text, expected):
        from citeaudit.extract import _title_from
        title = _title_from(text)
        assert title is not None, f"no title recovered from {text[:60]!r}"
        assert expected in title.lower()

    DEBRIS = [
        ": 0 1443--1450, 2004. 10.1098/rspb.2004.2746",
        "arXiv: 2511.20867",
        "LC-PFN. arXiv:2310.20447",
        "271 0 (1547): 0 1443",
        "https://doi.org/10.1016/j.energy.2023.128204",
        ": 0 566, 2007. 10.1126/science.1137521",
    ]

    @pytest.mark.parametrize("junk", DEBRIS)
    def test_debris_is_never_accepted_as_a_title(self, junk):
        from citeaudit.extract import looks_like_a_title
        assert not looks_like_a_title(junk)

    AUTHOR_LISTS = [
        "Holger Bast, Stefan Funke",
        "R. Alexander Bentley, Matthew W. Hahn, and Stephen J. Shennan",
        "Puneet S. Bagga, Vivek F. Farias, Tamar Korkotashvili, and Yuhang Wu",
        "Mitchell G. Newberry, Christopher A. Ahern",
    ]

    @pytest.mark.parametrize("names", AUTHOR_LISTS)
    def test_author_lists_are_not_mistaken_for_titles(self, names):
        """
        In LaTeX bibliographies the authors come first and are punctuated like
        a sentence, so a naive longest-segment rule picks them every time.
        Comparing an author list against the real title produces the same false
        mismatch.
        """
        from citeaudit.extract import looks_like_author_list
        assert looks_like_author_list(names)

    REAL_TITLES_THAT_LOOK_RISKY = [
        "Random drift and culture change",
        "Attention Is All You Need",
        "Deep learning",
        "Fast routing in road networks with transit nodes",
        "Monetary policy transmission in emerging markets",
    ]

    @pytest.mark.parametrize("title", REAL_TITLES_THAT_LOOK_RISKY)
    def test_genuine_titles_survive_the_guards(self, title):
        """
        Over-correcting is its own failure. An earlier version rejected
        'Deep learning' for having under three words, and 'Random drift and
        culture change' for containing the word 'and'.
        """
        from citeaudit.extract import looks_like_a_title, looks_like_author_list
        assert looks_like_a_title(title)
        assert not looks_like_author_list(title)

    def test_volume_number_is_not_read_as_a_year(self):
        """
        The root cause. 'Proc. R. Soc. Lond. B, 271 (1547): 1443' has a volume
        of 1547, which matched as a publication year and sent title extraction
        into the page range.
        """
        from citeaudit.extract import _year_from
        assert _year_from("Proc. R. Soc. Lond. B, 271 0 (1547): 0 1443--1450, 2004") == 2004
        assert _year_from("Nature, 551 0 (7679): 0 223--226, 2017") == 2017

    def test_unrecoverable_title_yields_none_not_a_guess(self):
        """
        The safe failure. No title means `assess` declines to compare, so the
        citation is reported VERIFIED with no title comparison rather than
        accused on the strength of a parsing error.
        """
        from citeaudit.extract import _title_from
        assert _title_from("10.1234/x, 2019, pp. 1-10") is None
