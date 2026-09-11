"""
Quote verification tests.

The load-bearing assertions here are about what the tool is *not* allowed to
conclude. Refuting a quotation accuses a person of fabrication, which is a far
graver claim than saying a reference is unresolvable, so the evidence bar is
correspondingly higher: only complete source text may refute, and everything
else is inconclusive.
"""

from __future__ import annotations

import pytest

from citeaudit.extract import extract
from citeaudit.fulltext import Coverage, SourceText, clean_latex, reconstruct_abstract
from citeaudit.models import Citation, Kind
from citeaudit.quotes import (
    MIN_QUOTE_WORDS, Quote, QuoteVerdict, QuoteVerifier, body_of,
    extract_quotes, find_passage, normalise, summarise,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

BODY = '''The court was unambiguous. As Justice Reeve put it, "the algorithm cannot
substitute for the exercise of discretion that the statute requires of a
decision-maker" [1].

A second claim quoting "a passage that wraps across the line boundary and
should still be detected correctly here" [2].

## References

[1] Reeve, J. (2019). "Administrative discretion". doi:10.1016/j.test.2019.03.011
[2] Other, A. (2020). "Another title entirely". arXiv:1706.03762
'''


class TestQuoteExtraction:

    @pytest.fixture
    def quotes(self):
        return extract_quotes(BODY, extract(BODY))

    def test_finds_quotes_spanning_multiple_lines(self, quotes):
        """
        REGRESSION. A line-anchored pattern found nothing here: prose wraps,
        and a quotation long enough to be worth checking rarely fits on one
        line.
        """
        assert len(quotes) == 2
        assert "exercise of discretion" in quotes[0].text
        assert "wraps across the line boundary" in quotes[1].text

    def test_wrapped_whitespace_is_normalised(self, quotes):
        assert "\n" not in quotes[0].text
        assert "  " not in quotes[0].text

    def test_numbered_marker_resolves_to_the_bibliography_entry(self, quotes):
        """
        REGRESSION. Proximity alone cannot connect a body marker to a reference
        list at the end of the document — they are nowhere near each other,
        which is the dominant citation pattern in real writing.
        """
        assert quotes[0].attributed_to is not None
        assert quotes[0].attributed_to.identifier == "10.1016/j.test.2019.03.011"
        assert quotes[1].attributed_to.identifier == "1706.03762"

    def test_bibliography_titles_are_not_treated_as_quotes(self, quotes):
        """Reference entries quote titles; counting those would bury real findings."""
        assert all("Administrative discretion" not in q.text for q in quotes)
        assert all("Another title entirely" not in q.text for q in quotes)

    def test_body_stops_at_the_references_heading(self):
        assert "Reeve, J. (2019)" not in body_of(BODY)
        assert "Justice Reeve put it" in body_of(BODY)

    def test_short_quotations_are_ignored(self):
        doc = 'He said "too short to check" [1].\n\n## References\n\n[1] A. doi:10.1/x'
        assert extract_quotes(doc, extract(doc)) == []

    def test_minimum_length_is_in_words_not_characters(self):
        long_but_few_words = '"' + ("supercalifragilistic " * 4).strip() + '"'
        assert len(long_but_few_words) > 40
        assert extract_quotes(long_but_few_words, []) == []

    def test_curly_quotes_supported(self):
        doc = ('She wrote \u201ca sufficiently long passage here that should be '
               'detected without trouble\u201d in the report.')
        assert len(extract_quotes(doc, [])) == 1

    def test_quote_without_attribution_is_kept_but_unattributed(self):
        doc = 'Someone claimed "a sufficiently long passage with no citation at all nearby".'
        qs = extract_quotes(doc, [])
        assert len(qs) == 1 and qs[0].attributed_to is None


# ---------------------------------------------------------------------------
# Passage matching
# ---------------------------------------------------------------------------

SOURCE = ("We begin with background material. We hold that the algorithm cannot "
          "substitute for the exercise of discretion that the statute requires "
          "of a decision-maker. Further analysis follows in section four.")


class TestPassageMatching:

    def test_exact_quote_scores_full(self):
        score, _ = find_passage(
            "the algorithm cannot substitute for the exercise of discretion", SOURCE)
        assert score >= 99

    def test_fabricated_quote_scores_low(self):
        score, _ = find_passage(
            "the model achieves results that were never stated anywhere", SOURCE)
        assert score < 60

    def test_punctuation_and_case_do_not_matter(self):
        score, _ = find_passage(
            "THE ALGORITHM, CANNOT SUBSTITUTE -- for the exercise of discretion!", SOURCE)
        assert score >= 88

    def test_returns_the_matched_passage_for_inspection(self):
        _, passage = find_passage("the exercise of discretion that the statute requires",
                                  SOURCE)
        assert passage and "discretion" in passage

    def test_empty_inputs_are_safe(self):
        assert find_passage("", SOURCE) == (0.0, None)
        assert find_passage("anything", "") == (0.0, None)

    def test_normalise_strips_punctuation_and_case(self):
        assert normalise("The, Quick-Brown FOX!") == "the quick brown fox"


# ---------------------------------------------------------------------------
# Verdict discipline — the part that matters
# ---------------------------------------------------------------------------

class StubVerifier(QuoteVerifier):
    """QuoteVerifier with retrieval replaced by a fixed source."""

    def __init__(self, source: SourceText):
        super().__init__(client=None)  # type: ignore[arg-type]
        self._source = source

    def _source_for(self, c):
        return self._source


def _quote(text: str, with_citation: bool = True) -> Quote:
    cit = Citation(raw="x", kind=Kind.DOI, identifier="10.1/x") if with_citation else None
    return Quote(text=text, line=1, attributed_to=cit)


class TestVerdictDiscipline:

    def test_full_text_plus_present_quote_is_found(self):
        v = StubVerifier(SourceText(Coverage.FULL, text=SOURCE, origin="t"))
        f = v.check(_quote("the algorithm cannot substitute for the exercise of discretion"))
        assert f.verdict is QuoteVerdict.FOUND

    def test_full_text_plus_absent_quote_is_the_only_refutation(self):
        v = StubVerifier(SourceText(Coverage.FULL, text=SOURCE, origin="t"))
        f = v.check(_quote("the tribunal endorsed fully automated determination without review"))
        assert f.verdict is QuoteVerdict.NOT_FOUND
        assert f.verdict.is_failure

    def test_abstract_only_can_confirm_a_quote(self):
        v = StubVerifier(SourceText(Coverage.ABSTRACT, text=SOURCE, origin="t"))
        f = v.check(_quote("the algorithm cannot substitute for the exercise of discretion"))
        assert f.verdict is QuoteVerdict.FOUND

    def test_abstract_only_can_never_refute_a_quote(self):
        """
        THE central invariant of this module. A quote absent from an abstract
        may sit in the body. Reporting that as fabrication would accuse a
        person on the strength of a paywall.
        """
        v = StubVerifier(SourceText(Coverage.ABSTRACT, text=SOURCE, origin="t"))
        f = v.check(_quote("the tribunal endorsed fully automated determination without review"))
        assert f.verdict is QuoteVerdict.ABSENT_FROM_ABSTRACT
        assert not f.verdict.is_failure
        assert f.verdict.is_inconclusive

    def test_no_open_text_yields_no_conclusion(self):
        v = StubVerifier(SourceText(Coverage.NONE, origin="t"))
        f = v.check(_quote("anything at all that is long enough to be checked here"))
        assert f.verdict is QuoteVerdict.SOURCE_UNAVAILABLE
        assert not f.verdict.is_failure
        assert "paywalled" in f.detail

    def test_unattributed_quote_is_not_a_failure(self):
        v = StubVerifier(SourceText(Coverage.FULL, text=SOURCE, origin="t"))
        f = v.check(_quote("a passage long enough to check but with no source", with_citation=False))
        assert f.verdict is QuoteVerdict.NOT_ATTRIBUTED
        assert not f.verdict.is_failure

    def test_only_full_coverage_can_refute(self):
        assert Coverage.FULL.can_refute
        assert not Coverage.ABSTRACT.can_refute
        assert not Coverage.NONE.can_refute

    def test_refutation_reports_the_closest_passage_found(self):
        """A bare accusation is not evidence; show what was compared."""
        v = StubVerifier(SourceText(Coverage.FULL, text=SOURCE, origin="t"))
        f = v.check(_quote("the tribunal endorsed fully automated determination without review"))
        assert f.best_passage is not None
        assert f.similarity is not None


# ---------------------------------------------------------------------------
# Source retrieval helpers
# ---------------------------------------------------------------------------

class TestFullText:

    def test_reconstruct_abstract_from_inverted_index(self):
        inverted = {"The": [0], "study": [1], "found": [2], "nothing": [3]}
        assert reconstruct_abstract(inverted) == "The study found nothing"

    def test_reconstruct_handles_repeated_words(self):
        inverted = {"very": [0, 1], "good": [2]}
        assert reconstruct_abstract(inverted) == "very very good"

    def test_reconstruct_empty_is_empty(self):
        assert reconstruct_abstract({}) == ""

    def test_clean_latex_drops_equations_and_commands(self):
        tex = (r"Some prose here. \begin{equation} E = mc^2 \end{equation} "
               r"More \emph{emphasised} prose.")
        out = clean_latex(tex)
        assert "mc^2" not in out
        assert "emphasised" in out
        assert "\\emph" not in out

    def test_clean_latex_drops_comments(self):
        assert "hidden" not in clean_latex("visible text % hidden comment")


class TestSummary:

    def test_coverage_rate_counts_only_conclusive_checks(self):
        from citeaudit.quotes import QuoteFinding
        fs = [
            QuoteFinding(quote=_quote("a"), verdict=QuoteVerdict.FOUND),
            QuoteFinding(quote=_quote("b"), verdict=QuoteVerdict.NOT_FOUND),
            QuoteFinding(quote=_quote("c"), verdict=QuoteVerdict.SOURCE_UNAVAILABLE),
            QuoteFinding(quote=_quote("d"), verdict=QuoteVerdict.ABSENT_FROM_ABSTRACT),
        ]
        s = summarise(fs)
        assert s["total_quotes"] == 4
        assert s["conclusive_checks"] == 2
        assert s["coverage_rate"] == pytest.approx(0.5)
