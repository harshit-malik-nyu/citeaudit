"""
Tests for the base-rate and calibration machinery.

The statistics and the labelling construction are tested offline; the studies
themselves run against live authorities in CI.
"""

from __future__ import annotations

import random

import pytest

from citeaudit.calibrate import (
    Pair, build_pairs, choose_operating_point, drop_subtitle, evaluate_at,
    introduce_typo, sweep, truncate,
)
from citeaudit.corpus import Check, references_of, wilson_interval
from citeaudit.models import Verdict
from citeaudit.sources.crossref import Work


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestWilson:

    def test_zero_n_is_degenerate_not_an_error(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)

    def test_interval_brackets_the_point_estimate(self):
        lo, hi = wilson_interval(20, 100)
        assert lo < 0.20 < hi

    def test_bounds_stay_inside_zero_one_at_the_extremes(self):
        """
        The normal approximation produces bounds outside [0,1] here, which is
        why Wilson is used.
        """
        lo, hi = wilson_interval(0, 30)
        assert lo == 0.0 and 0 < hi < 1
        lo, hi = wilson_interval(30, 30)
        assert hi == 1.0 and 0 < lo < 1

    def test_interval_narrows_as_n_grows(self):
        narrow = wilson_interval(500, 1000)
        wide = wilson_interval(5, 10)
        assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


# ---------------------------------------------------------------------------
# Ground truth by construction
# ---------------------------------------------------------------------------

def _work(doi: str, title: str, authors: list[str], year: int = 2020) -> Work:
    return Work(doi=doi, title=title, authors=authors, year=year)


class TestLabelledSet:

    @pytest.fixture
    def works(self) -> list[Work]:
        """
        A topically clustered sample, as a real random draw from a field would
        be. Unrelated titles make the calibration look perfect without testing
        anything, so the fixture deliberately contains confusable neighbours.
        """
        return [
            _work("10.1/a", "Deep learning methods for image recognition tasks",
                  ["Smith", "Jones"]),
            _work("10.1/b", "Deep learning methods for speech recognition tasks",
                  ["Alvarez"]),
            _work("10.1/c", "Monetary policy transmission in emerging markets: evidence from Asia",
                  ["Patel", "Chen"]),
            _work("10.1/d", "Monetary policy transmission in developed markets: evidence from Europe",
                  ["Novak"]),
            _work("10.1/e", "Crystal structure of ribosomal protein L7 in yeast",
                  ["Kowalski"]),
            _work("10.1/f", "A longitudinal study of urban air quality and childhood asthma",
                  ["Okafor"]),
        ]

    def test_same_work_pairs_are_labelled_same(self, works):
        pairs = build_pairs(works, seed=1)
        same = [p for p in pairs if p.label == "same_work"]
        assert same
        for p in same:
            assert not p.is_truly_different

    def test_different_work_pairs_use_another_works_title(self, works):
        pairs = build_pairs(works, seed=1)
        diff = [p for p in pairs if p.label == "different_work"]
        assert diff
        for p in diff:
            assert p.claimed_title != p.resolved_title
            assert p.is_truly_different

    def test_same_work_deposited_twice_excluded_from_positives(self):
        """
        Identical title AND the same authors: plausibly one work deposited
        twice. Labelling that 'different' would corrupt precision.
        """
        works = [
            _work("10.1/a", "Deep learning for image recognition", ["Smith", "Jones"]),
            _work("10.1/b", "Deep learning for image recognition", ["Smith", "Jones"]),
        ]
        pairs = build_pairs(works, seed=1)
        assert [p for p in pairs if p.label == "different_work"] == []

    def test_similar_title_different_authors_kept_as_hard_positive(self):
        """
        Near-identical titles from different research groups are two papers,
        and they are the hardest and most valuable positives in the set.
        """
        works = [
            _work("10.1/a", "Deep learning for image recognition", ["Smith", "Jones"]),
            _work("10.1/b", "Deep learning for image recognition", ["Kowalski", "Petrov"]),
        ]
        pairs = build_pairs(works, seed=1)
        assert [p for p in pairs if p.label == "different_work"]

    def test_similarity_computed_for_every_pair(self, works):
        for p in build_pairs(works, seed=1):
            assert p.similarity is not None

    def test_labelled_classes_are_not_trivially_separable(self, works):
        """
        REGRESSION. The first version of this test asserted the classes were
        perfectly separable, which is precisely the defect it should have
        caught: pairing random titles from unrelated fields produced precision
        and recall of 1.000 at every threshold from 54 to 90. A threshold that
        makes no difference anywhere has not been calibrated — the labelled set
        just never posed a hard case.

        A useful set must contain contested pairs. This asserts the ranges
        overlap, so the sweep has something to discriminate.
        """
        pairs = build_pairs(works, seed=1)
        same = [p.similarity for p in pairs if p.label == "same_work"]
        diff = [p.similarity for p in pairs if p.label == "different_work"]
        assert same and diff
        # The hardest same-work case must score no higher than the hardest
        # different-work case, or the two classes never meet.
        assert min(same) <= max(diff), (
            "labelled set is trivially separable; the threshold sweep would "
            "report a perfect score without measuring anything"
        )

    def test_hard_positives_use_the_nearest_available_title(self):
        """Positives should be the most confusable pairing, not a random one."""
        works = [
            _work("10.1/a", "Monetary policy transmission in emerging markets", ["Patel"]),
            _work("10.1/b", "Monetary policy transmission in developed markets", ["Novak"]),
            _work("10.1/c", "Crystal structure of ribosomal protein L7 in yeast", ["Kowalski"]),
        ]
        pairs = build_pairs(works, seed=1)
        hard = [p for p in pairs
                if p.label == "different_work" and p.doi == "10.1/a"]
        assert hard
        best = max(hard, key=lambda p: p.similarity or 0)
        assert "developed markets" in best.claimed_title


class TestPerturbations:

    def test_drop_subtitle(self):
        rng = random.Random(0)
        assert drop_subtitle("Main Title Here: A Subtitle", rng) == "Main Title Here"

    def test_drop_subtitle_declines_when_head_too_short(self):
        assert drop_subtitle("Short: Something", random.Random(0)) is None

    def test_truncate_shortens_long_titles_only(self):
        rng = random.Random(0)
        long_title = " ".join(f"word{i}" for i in range(12))
        out = truncate(long_title, rng)
        assert out and len(out.split()) < 12
        assert truncate("three word title", rng) is None

    def test_typo_changes_exactly_the_length_preserved(self):
        out = introduce_typo("A reasonably long title for testing", random.Random(3))
        assert out is not None
        assert len(out) == len("A reasonably long title for testing")
        assert out != "A reasonably long title for testing"


# ---------------------------------------------------------------------------
# Sweep mechanics
# ---------------------------------------------------------------------------

class TestSweep:

    @pytest.fixture
    def pairs(self) -> list[Pair]:
        out = []
        for sim in (98, 95, 92, 88, 84):
            out.append(Pair(label="same_work", perturbation="p", doi="10.1/x",
                            claimed_title="t", resolved_title="t",
                            similarity=float(sim)))
        for sim in (10, 18, 25, 33, 41):
            out.append(Pair(label="different_work", perturbation="swapped_title",
                            doi="10.1/x", claimed_title="a", resolved_title="b",
                            similarity=float(sim)))
        return out

    def test_perfect_separation_at_a_middle_threshold(self, pairs):
        r = evaluate_at(pairs, 60.0)
        assert r["precision"] == 1.0
        assert r["recall"] == 1.0
        assert r["false_positive"] == 0

    def test_threshold_too_low_misses_detections(self, pairs):
        r = evaluate_at(pairs, 5.0)
        assert r["recall"] == 0.0
        assert r["false_negative"] == 5

    def test_sweep_is_monotonic_in_recall(self, pairs):
        """Raising the threshold can only flag more, never fewer."""
        curve = sweep(pairs, [20.0, 40.0, 60.0, 80.0])
        recalls = [r["recall"] for r in curve]
        assert recalls == sorted(recalls)

    def test_operating_point_respects_precision_floor(self, pairs):
        chosen = choose_operating_point(sweep(pairs), min_precision=0.99)
        assert chosen is not None
        assert chosen["precision"] >= 0.99

    def test_no_operating_point_when_floor_unreachable(self):
        """An unmeetable floor must return None, not silently relax."""
        pairs = [
            Pair(label="same_work", perturbation="p", doi="10.1/x",
                 claimed_title="t", resolved_title="t", similarity=10.0),
            Pair(label="different_work", perturbation="s", doi="10.1/y",
                 claimed_title="a", resolved_title="b", similarity=10.0),
        ]
        assert choose_operating_point(sweep(pairs), min_precision=0.99) is None

    def test_sweep_does_not_mutate_module_state(self, pairs):
        """The sweep must be order-independent and reproducible."""
        from citeaudit import match
        before = match.TITLE_MISMATCH_THRESHOLD
        sweep(pairs)
        assert match.TITLE_MISMATCH_THRESHOLD == before


# ---------------------------------------------------------------------------
# Corpus helpers
# ---------------------------------------------------------------------------

class TestCorpus:

    def test_references_require_both_doi_and_title(self):
        work = {"reference": [
            {"DOI": "10.1/a", "article-title": "A sufficiently long real title"},
            {"DOI": "10.1/b"},                              # no title
            {"article-title": "A title with no identifier at all"},  # no DOI
            {"DOI": "10.1/c", "article-title": "short"},    # title too short
        ]}
        refs = references_of(work, max_refs=10, rng=random.Random(0))
        assert len(refs) == 1
        assert refs[0]["DOI"] == "10.1/a"

    def test_references_capped_and_sampled(self):
        work = {"reference": [
            {"DOI": f"10.1/{i}", "article-title": f"A long enough title number {i}"}
            for i in range(30)
        ]}
        refs = references_of(work, max_refs=5, rng=random.Random(0))
        assert len(refs) == 5

    def test_false_positive_flags_only_definite_failures(self):
        def chk(v): return Check(source_doi="10.1/s", source_year=2020,
                                 source_type="journal-article", mode="described",
                                 reference_doi="10.1/r", claimed_title="t",
                                 verdict=v)
        assert chk(Verdict.NOT_FOUND.value).is_false_positive
        assert chk(Verdict.MALFORMED.value).is_false_positive
        assert not chk(Verdict.VERIFIED.value).is_false_positive
        assert not chk(Verdict.UNREACHABLE.value).is_false_positive
        assert not chk(Verdict.UNVERIFIABLE.value).is_false_positive
