"""
Live tests.

These hit Crossref and arXiv for real. They are excluded from the default test
run (`-m 'not live'` in pyproject) and execute in CI, where their results are
committed to `evidence/` as a record of what the authorities actually returned.

Each test states the invariant it is protecting rather than asserting a
specific record's contents, because published metadata is not under this
project's control and a test that breaks when a publisher fixes a typo is a
liability.

Network flakiness must not produce a red build here for the same reason it must
not produce a NOT_FOUND verdict in the tool: an inconclusive check is not
evidence of anything. Tests that cannot reach an authority skip.
"""

from __future__ import annotations

import pytest

from citeaudit.http import Client, NotFound, Unreachable
from citeaudit.models import Citation, Kind, Verdict
from citeaudit.sources.arxiv import Arxiv
from citeaudit.sources.crossref import Crossref
from citeaudit.verify import Verifier

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(mailto="citeaudit-ci@example.com", cache_dir=None,
                  use_cache=False, timeout=30)


@pytest.fixture(scope="module")
def verifier(client: Client) -> Verifier:
    return Verifier(client, workers=2)


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------

def test_crossref_resolves_a_known_doi(client):
    """
    Nature's DOI for the 2015 deep learning review. If this ever fails, either
    Crossref is down or something is very wrong with the client.
    """
    try:
        work = Crossref(client).resolve("10.1038/nature14539")
    except Unreachable:
        pytest.skip("Crossref unreachable")
    assert work.doi == "10.1038/nature14539"
    assert work.title and len(work.title) > 5
    assert work.authors
    assert work.year


def test_crossref_rejects_a_wellformed_but_unregistered_doi(client):
    """
    THE core capability. This DOI is syntactically perfect and belongs to a
    registrant prefix that does not exist. Crossref must answer 'no such
    record', which is what makes fabrication detectable at all.
    """
    try:
        with pytest.raises(NotFound):
            Crossref(client).resolve("10.9911/erla.2020.13.4.055")
    except Unreachable:
        pytest.skip("Crossref unreachable")


def test_crossref_search_finds_a_real_paper(client):
    try:
        hits = Crossref(client).search("Attention is all you need", rows=5)
    except Unreachable:
        pytest.skip("Crossref unreachable")
    assert hits, "expected at least one result for a heavily cited title"
    assert any(h.title for h in hits)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def test_arxiv_resolves_a_known_preprint(client):
    try:
        pre = Arxiv(client).resolve("1706.03762")
    except Unreachable:
        pytest.skip("arXiv unreachable")
    assert pre.title and "attention" in pre.title.lower()
    assert pre.authors


def test_arxiv_rejects_a_nonexistent_id_despite_http_200(client):
    """
    arXiv answers unknown identifiers with HTTP 200 and an empty feed. The
    client must not read that as success — see sources/arxiv.py.
    """
    try:
        with pytest.raises(NotFound):
            Arxiv(client).resolve("2499.99999")
    except Unreachable:
        pytest.skip("arXiv unreachable")


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def test_real_doi_with_wrong_title_is_flagged_as_mismatch(verifier):
    """
    A real, resolvable DOI paired with a title from a different field. This is
    the failure mode a link checker cannot see: the link works, so the citation
    looks fine to anyone who clicks it.
    """
    c = Citation(
        raw="test", kind=Kind.DOI, identifier="10.1038/nature14539",
        claimed_title="Procedural fairness in machine-assisted eligibility determination",
        claimed_authors=["Ashworth"], claimed_year=2023,
    )
    f = verifier.check(c)
    if f.verdict is Verdict.UNREACHABLE:
        pytest.skip("Crossref unreachable")
    assert f.verdict is Verdict.MISMATCH
    assert f.resolved_title
    assert f.title_similarity is not None and f.title_similarity < 60


def test_real_doi_with_correct_title_verifies(verifier):
    c = Citation(
        raw="test", kind=Kind.DOI, identifier="10.1038/nature14539",
        claimed_title="Deep learning",
        claimed_authors=["LeCun", "Bengio", "Hinton"], claimed_year=2015,
    )
    f = verifier.check(c)
    if f.verdict is Verdict.UNREACHABLE:
        pytest.skip("Crossref unreachable")
    assert f.verdict is Verdict.VERIFIED


def test_demo_document_produces_both_passes_and_failures(verifier):
    """
    The demo must exercise both outcomes. A demo where everything passes proves
    the tool cannot detect anything; one where everything fails proves it
    cannot distinguish. Either would be worthless as evidence.
    """
    report = verifier.verify_file("examples/demo.md")
    if report.conclusive == 0:
        pytest.skip("no authority reachable")

    assert report.count(Verdict.VERIFIED) > 0, "demo detected nothing valid"
    assert len(report.failures) > 0, "demo detected nothing broken"
    assert report.integrity_score is not None
    assert 0.0 < report.integrity_score < 1.0


def test_inconclusive_never_counted_as_failure_on_real_data(verifier):
    """The tool's central promise, asserted against a live run."""
    report = verifier.verify_file("examples/demo.md")
    for f in report.inconclusive:
        assert not f.verdict.is_failure
    assert all(f.verdict.is_failure for f in report.failures)
