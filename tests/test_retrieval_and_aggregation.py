"""
Tests for source-text retrieval and study aggregation.

`fulltext.retrieve` decides which coverage tier a quote gets checked against,
and the tier decides whether the tool is permitted to refute a quotation at
all. Preferring an abstract when full text was available would quietly downgrade
every refutable quote to inconclusive; preferring full text when none exists
would do the opposite and licence an accusation on thin evidence. The ordering
is a correctness property, not an optimisation.

The aggregation functions turn thousands of raw checks into the handful of
numbers that end up in the README. Every honesty rule in the project — that
inconclusive checks stay out of denominators, that a rate with no conclusive
checks is None rather than zero — lives or dies here.
"""

from __future__ import annotations

import json

import pytest

from citeaudit.corpus import (
    Check, StudyResult, estimate_is_usable, summarise as corpus_summarise,
    to_markdown as corpus_markdown, wilson_interval,
)
from citeaudit.fulltext import (
    Coverage, SourceText, clean_latex, clean_markup, reconstruct_abstract,
    retrieve,
)
from citeaudit.models import Verdict


# ===========================================================================
# Retrieval tiering
# ===========================================================================

class StubRetrieval:
    """Replaces the individual fetchers so ordering can be asserted."""

    def __init__(self, monkeypatch, *, arxiv_full=None, arxiv_abs=None,
                 openalex=None, crossref=None):
        import citeaudit.fulltext as ft
        self.calls: list[str] = []

        def make(name, result):
            def fn(client, ident):
                self.calls.append(name)
                return result or SourceText(Coverage.NONE, origin=name)
            return fn

        monkeypatch.setattr(ft, "arxiv_fulltext", make("arxiv_full", arxiv_full))
        monkeypatch.setattr(ft, "arxiv_abstract", make("arxiv_abs", arxiv_abs))
        monkeypatch.setattr(ft, "openalex_abstract", make("openalex", openalex))
        monkeypatch.setattr(ft, "crossref_abstract", make("crossref", crossref))


FULL = SourceText(Coverage.FULL, text="body " * 400, origin="arxiv-source")
ABS = SourceText(Coverage.ABSTRACT, text="abstract text " * 20, origin="x-abstract")


class TestRetrievalOrdering:

    def test_full_text_is_preferred_over_an_abstract(self, monkeypatch):
        """
        Only full text licenses refuting a quote. Settling for an abstract when
        the body was available would silently make every quotation
        inconclusive.
        """
        stub = StubRetrieval(monkeypatch, arxiv_full=FULL, arxiv_abs=ABS)
        got = retrieve(None, arxiv_id="1706.03762")
        assert got.coverage is Coverage.FULL
        assert stub.calls == ["arxiv_full"]

    def test_abstract_used_only_when_full_text_is_unavailable(self, monkeypatch):
        stub = StubRetrieval(monkeypatch, arxiv_full=None, arxiv_abs=ABS)
        got = retrieve(None, arxiv_id="1706.03762")
        assert got.coverage is Coverage.ABSTRACT
        assert stub.calls == ["arxiv_full", "arxiv_abs"]

    def test_doi_falls_back_through_both_abstract_sources(self, monkeypatch):
        stub = StubRetrieval(monkeypatch, openalex=None, crossref=ABS)
        got = retrieve(None, doi="10.1038/nature14539")
        assert got.coverage is Coverage.ABSTRACT
        assert stub.calls == ["openalex", "crossref"]

    def test_openalex_is_tried_before_crossref(self, monkeypatch):
        stub = StubRetrieval(monkeypatch, openalex=ABS, crossref=ABS)
        retrieve(None, doi="10.1/x")
        assert stub.calls == ["openalex"]

    def test_arxiv_doi_is_routed_to_arxiv_full_text(self, monkeypatch):
        """
        A 10.48550/arXiv.* DOI points at a preprint whose body is openly
        retrievable. Treating it as an ordinary DOI would settle for an
        abstract and lose the ability to refute.
        """
        stub = StubRetrieval(monkeypatch, arxiv_full=FULL, openalex=ABS)
        got = retrieve(None, doi="10.48550/arxiv.1706.03762")
        assert got.coverage is Coverage.FULL
        assert stub.calls[0] == "arxiv_full"

    def test_nothing_available_returns_no_coverage(self, monkeypatch):
        StubRetrieval(monkeypatch)
        got = retrieve(None, doi="10.1/x", arxiv_id="9999.99999")
        assert got.coverage is Coverage.NONE
        assert not got.coverage.can_refute

    def test_no_identifiers_makes_no_calls(self, monkeypatch):
        stub = StubRetrieval(monkeypatch, arxiv_full=FULL)
        assert retrieve(None).coverage is Coverage.NONE
        assert stub.calls == []


class TestSourceText:

    def test_word_count(self):
        assert SourceText(Coverage.FULL, text="one two three").words == 3

    def test_only_full_coverage_can_refute(self):
        assert Coverage.FULL.can_refute
        assert not Coverage.ABSTRACT.can_refute
        assert not Coverage.NONE.can_refute


class TestTextCleaning:

    def test_latex_environments_dropped_wholesale(self):
        out = clean_latex(r"Before \begin{figure} caption junk \end{figure} after")
        assert "Before" in out and "after" in out
        assert "caption junk" not in out

    def test_bibliography_environment_dropped(self):
        """A quote must not be 'found' inside the reference list."""
        out = clean_latex(
            r"Body text. \begin{thebibliography}{9} \bibitem{a} X \end{thebibliography}")
        assert "Body text" in out
        assert "bibitem" not in out

    def test_nested_formatting_resolved(self):
        assert "inner" in clean_latex(r"\textbf{\emph{inner}}")

    def test_markup_stripped_from_jats_abstracts(self):
        assert clean_markup("<jats:p>Some <b>text</b></jats:p>") == "Some text"

    def test_inverted_index_roundtrip_preserves_order(self):
        text = "the quick brown fox jumps"
        inverted: dict[str, list[int]] = {}
        for i, w in enumerate(text.split()):
            inverted.setdefault(w, []).append(i)
        assert reconstruct_abstract(inverted) == text


# ===========================================================================
# Aggregation
# ===========================================================================

def _check(mode: str, verdict: str, year: int = 2020) -> Check:
    return Check(
        source_doi="10.1/src", source_year=year, source_type="journal-article",
        mode=mode, reference_doi="10.1/ref", claimed_title="A title",
        verdict=verdict,
    )


class TestCorpusAggregation:

    def test_inconclusive_checks_stay_out_of_the_denominator(self):
        result = StudyResult(source_works=1, checks=[
            _check("described", Verdict.VERIFIED.value),
            _check("described", Verdict.NOT_FOUND.value),
            _check("described", Verdict.UNREACHABLE.value),
            _check("described", Verdict.UNVERIFIABLE.value),
        ])
        block = corpus_summarise(result)["described_mode"]
        assert block["conclusive"] == 2
        assert block["false_positive_rate"] == pytest.approx(0.5)

    def test_rate_is_none_when_nothing_conclusive(self):
        result = StudyResult(source_works=1, checks=[
            _check("described", Verdict.UNREACHABLE.value),
        ])
        assert corpus_summarise(result)["described_mode"]["false_positive_rate"] is None

    def test_modes_are_reported_separately(self):
        result = StudyResult(source_works=1, checks=[
            _check("identified", Verdict.VERIFIED.value),
            _check("described", Verdict.NOT_FOUND.value),
        ])
        s = corpus_summarise(result)
        assert s["identified_mode"]["false_positive_rate"] == 0.0
        assert s["described_mode"]["false_positive_rate"] == 1.0

    def test_stratification_by_year_is_preserved(self):
        result = StudyResult(source_works=2, checks=[
            _check("described", Verdict.VERIFIED.value, year=2020),
            _check("described", Verdict.NOT_FOUND.value, year=2024),
        ])
        by_year = corpus_summarise(result)["described_by_year"]
        assert by_year["2020"]["false_positive_rate"] == 0.0
        assert by_year["2024"]["false_positive_rate"] == 1.0

    def test_false_positive_examples_are_surfaced(self):
        """A bare rate is not auditable; the failing references must be listed."""
        result = StudyResult(source_works=1, checks=[
            _check("described", Verdict.NOT_FOUND.value),
        ])
        examples = corpus_summarise(result)["false_positive_examples"]
        assert len(examples) == 1
        assert examples[0]["reference_doi"] == "10.1/ref"

    def test_fallback_rescues_are_counted(self):
        c = _check("described", Verdict.VERIFIED.value)
        c.authority = "openalex"
        result = StudyResult(source_works=1, checks=[c])
        assert corpus_summarise(result)["fallback_rescues"] == 1

    def test_markdown_renders_without_error_on_a_minimal_study(self):
        result = StudyResult(source_works=1, checks=[
            _check("identified", Verdict.VERIFIED.value),
            _check("described", Verdict.NOT_FOUND.value),
        ])
        md = corpus_markdown(corpus_summarise(result))
        assert "Base rate" in md
        assert "Limits" in md

    def test_markdown_carries_the_power_banner_when_underpowered(self):
        result = StudyResult(source_works=1, checks=[
            _check("described", Verdict.NOT_FOUND.value),
        ])
        md = corpus_markdown(corpus_summarise(result))
        assert "Limits" in md


class TestWilsonEdgeCases:

    def test_all_failures_gives_upper_bound_of_one(self):
        lo, hi = wilson_interval(10, 10)
        assert hi == 1.0 and lo > 0

    def test_single_observation_is_extremely_wide(self):
        lo, hi = wilson_interval(0, 1)
        assert (hi - lo) > 0.5
        assert not estimate_is_usable(1, [lo, hi])[0]

    def test_interval_is_symmetric_under_complement(self):
        lo_a, hi_a = wilson_interval(3, 10)
        lo_b, hi_b = wilson_interval(7, 10)
        assert lo_a == pytest.approx(1 - hi_b, abs=1e-9)
        assert hi_a == pytest.approx(1 - lo_b, abs=1e-9)


# ===========================================================================
# Report rendering — what a reader actually sees
# ===========================================================================

class TestCalibrationReport:

    def _pairs(self):
        from citeaudit.calibrate import Pair
        same = [Pair(label="same_work", perturbation="typo", doi="10.1/x",
                     claimed_title="A degraded title", resolved_title="A title",
                     similarity=s) for s in (96.0, 91.0, 72.0, 58.0)]
        diff = [Pair(label="different_work", perturbation="nearest_title",
                     doi="10.1/y", claimed_title="Another paper entirely",
                     resolved_title="A title", similarity=s)
                for s in (12.0, 30.0, 48.0, 63.0)]
        return same + diff

    def test_report_states_whether_the_classes_overlap(self):
        """
        The guard against a meaningless perfect score. If the two classes never
        meet, every threshold separates them and the curve measures nothing.
        """
        from citeaudit.calibrate import (
            choose_operating_point, sweep, to_markdown,
        )
        pairs = self._pairs()
        curve = sweep(pairs)
        md = to_markdown(pairs, curve,
                         choose_operating_point(curve, min_precision=0.99),
                         {"works": 10, "seed": 1, "pairs": len(pairs)})
        assert "Is this set actually hard?" in md
        assert "overlap" in md.lower()

    def test_report_names_the_selection_rule(self):
        from citeaudit.calibrate import (
            choose_operating_point, sweep, to_markdown,
        )
        pairs = self._pairs()
        curve = sweep(pairs)
        md = to_markdown(pairs, curve,
                         choose_operating_point(curve, min_precision=0.99),
                         {"works": 10, "seed": 1, "pairs": len(pairs)})
        assert "precision floor" in md
        assert "F1" in md

    def test_report_handles_no_viable_operating_point(self):
        """An unmeetable precision floor must be reported, not papered over."""
        from citeaudit.calibrate import Pair, sweep, to_markdown
        pairs = [
            Pair(label="same_work", perturbation="p", doi="10.1/x",
                 claimed_title="a", resolved_title="b", similarity=20.0),
            Pair(label="different_work", perturbation="s", doi="10.1/y",
                 claimed_title="c", resolved_title="d", similarity=20.0),
        ]
        md = to_markdown(pairs, sweep(pairs), None,
                         {"works": 2, "seed": 1, "pairs": 2})
        assert "No threshold" in md
        # The failure is reported as a failure, not worked around by quietly
        # relaxing the floor until something passes.
        assert "not usable on this labelled set" in md
        assert "reported rather than worked around" in md

    def test_write_outputs_produces_all_three_artifacts(self, tmp_path):
        from citeaudit.calibrate import (
            choose_operating_point, sweep, write_outputs,
        )
        pairs = self._pairs()
        curve = sweep(pairs)
        write_outputs(pairs, curve,
                      choose_operating_point(curve, min_precision=0.99),
                      {"works": 10, "seed": 1, "pairs": len(pairs)}, tmp_path)
        assert (tmp_path / "curve.json").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "pairs.csv").exists()
        data = json.loads((tmp_path / "curve.json").read_text())
        assert "curve" in data and "meta" in data


class TestWikipediaReport:

    def _study(self, scholarly: int, grey: int):
        from citeaudit.wikipedia import WikiCheck, WikiStudy
        checks = []
        for i in range(scholarly):
            checks.append(WikiCheck(
                article="A", template="journal", kind="doi",
                identifier=f"10.1/{i}", claimed_title="t",
                verdict="verified" if i % 4 else "not_found",
                authority="crossref"))
        for i in range(grey):
            checks.append(WikiCheck(
                article="A", template="news", kind="bibliographic",
                identifier=None, claimed_title="t",
                verdict="not_found", authority="crossref"))
        return WikiStudy(articles_sampled=50, articles_with_citations=50,
                         checks=checks)

    def test_grey_rate_is_labelled_as_index_coverage(self):
        """
        The category error this split exists to prevent. Checking journalism
        against a scholarly index measures whether that index covers
        journalism.
        """
        from citeaudit.wikipedia import summarise, to_markdown
        md = to_markdown(summarise(self._study(60, 60)))
        assert "not an integrity finding" in md
        assert "category error" in md

    def test_comparable_figure_is_presented_first(self):
        from citeaudit.wikipedia import summarise, to_markdown
        md = to_markdown(summarise(self._study(60, 60)))
        assert md.index("The comparable figure") < md.index("Grey-literature")

    def test_pooled_figure_is_marked_for_completeness_only(self):
        from citeaudit.wikipedia import summarise, to_markdown
        md = to_markdown(summarise(self._study(60, 60)))
        assert "completeness only" in md

    def test_underpowered_scholarly_rate_is_banner_flagged(self):
        from citeaudit.wikipedia import summarise, to_markdown
        md = to_markdown(summarise(self._study(5, 60)))
        assert "not usable" in md

    def test_write_outputs_round_trips(self, tmp_path):
        from citeaudit.wikipedia import summarise, write_outputs
        study = self._study(60, 20)
        write_outputs(study, summarise(study), tmp_path)
        assert (tmp_path / "summary.json").exists()
        assert (tmp_path / "report.md").exists()
        assert (tmp_path / "checks.csv").exists()


class TestPreprintReport:

    def _study(self, n: int):
        from citeaudit.preprints import PreprintCheck, PreprintStudy
        return PreprintStudy(
            papers_sampled=20, papers_with_bibliography=18,
            checks=[PreprintCheck(
                arxiv_id=f"24{i:02d}.0001", category="cs.LG",
                reference_text="t", kind="doi", identifier=f"10.1/{i}",
                verdict="verified" if i % 5 else "not_found",
                authority="crossref") for i in range(n)])

    def test_claim_boundary_is_stated_in_the_report(self):
        """An unverified reference is not a fabricated one, and it must say so."""
        from citeaudit.preprints import summarise, to_markdown
        md = to_markdown(summarise(self._study(80)))
        assert "not thereby fabricated" in md.lower() or "NOT thereby fabricated" in md
        assert "no paper is named" in md

    def test_breakdown_by_reference_form_is_present(self):
        from citeaudit.preprints import summarise, to_markdown
        md = to_markdown(summarise(self._study(80)))
        assert "By how the reference was written" in md

    def test_underpowered_run_is_banner_flagged(self):
        from citeaudit.preprints import summarise, to_markdown
        assert "not usable" in to_markdown(summarise(self._study(10)))
