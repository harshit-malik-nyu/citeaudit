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


class TestStudyNormalisation:

    def test_deposited_dois_are_normalised_like_extracted_ones(self):
        """
        REGRESSION. Publishers deposit DOIs with trailing punctuation —
        '10.1016/s0140-6736(18)32594-7.' appeared in a real sample. The study
        passed those through raw while the extractor normalised them, so it was
        measuring a bypass of citeaudit rather than citeaudit, and reporting the
        study's own bug as the tool's false-positive rate.
        """
        from citeaudit.extract import normalise_doi

        work = {"reference": [
            {"DOI": "10.1016/s0140-6736(18)32594-7.",
             "article-title": "A sufficiently long genuine title here"},
        ]}
        refs = references_of(work, max_refs=5, rng=random.Random(0))
        assert len(refs) == 1
        assert normalise_doi(refs[0]["DOI"]) == "10.1016/s0140-6736(18)32594-7"

    def test_balanced_parens_survive_normalisation(self):
        """Elsevier DOIs legitimately contain them; stripping breaks real ones."""
        from citeaudit.extract import normalise_doi
        assert normalise_doi("10.1016/s2542-5196(17)30162-6.") == \
            "10.1016/s2542-5196(17)30162-6"


# ===========================================================================
# Preprint corpus: author-written bibliographies
# ===========================================================================

from citeaudit.preprints import (
    bibliography_from_source, delatex, parse_bibtex, split_bibitems,
)


class TestLatexBibliography:

    def test_delatex_unwraps_formatting_commands(self):
        raw = r"J.~Smith, \emph{A Study of Things}, \textbf{Nature} 521 (2015)"
        out = delatex(raw)
        assert "emph" not in out and "textbf" not in out
        assert "A Study of Things" in out
        assert "Nature" in out

    def test_delatex_normalises_latex_quotes(self):
        assert '"' in delatex(r"``A Quoted Title''")

    def test_delatex_strips_braces_and_tildes(self):
        assert delatex(r"{Smith}, J.~A.") == "Smith, J. A."

    def test_split_bibitems_separates_entries(self):
        bbl = r"""
\begin{thebibliography}{9}
\bibitem{a} A.~Author, \emph{First paper about something interesting}, Journal of Things, 2019. doi:10.1/aaa
\bibitem{b} B.~Writer, \emph{Second paper about other interesting matters}, Review of Stuff, 2020.
\end{thebibliography}
"""
        entries = split_bibitems(bbl)
        assert len(entries) == 2
        assert "First paper" in entries[0]
        assert "Second paper" in entries[1]
        assert r"\end{thebibliography}" not in entries[1]

    def test_split_bibitems_handles_optional_label(self):
        bbl = r"\bibitem[Smith et al.(2019)]{smith19} Smith, J., Title of the work here, 2019."
        assert len(split_bibitems(bbl)) == 1

    def test_split_bibitems_returns_nothing_without_bibitems(self):
        assert split_bibitems("just some prose with no bibliography at all") == []

    def test_parse_bibtex_reconstructs_a_reference_string(self):
        bib = """
@article{smith2019,
  author = {Smith, John and Doe, Jane},
  title = {A sufficiently long and genuine sounding title},
  journal = {Journal of Testing},
  year = {2019},
  doi = {10.1234/jot.2019.001}
}
"""
        out = parse_bibtex(bib)
        assert len(out) == 1
        assert "A sufficiently long and genuine sounding title" in out[0]
        assert "10.1234/jot.2019.001" in out[0]

    def test_parse_bibtex_skips_entries_without_a_usable_title(self):
        assert parse_bibtex("@misc{x, author={A}, year={2020}}") == []

    def test_malformed_archive_returns_empty_not_an_exception(self):
        """A bad source package must skip the paper, never abort the study."""
        assert bibliography_from_source(b"not a tarball at all") == []
        assert bibliography_from_source(b"") == []

    def test_real_tarball_is_parsed(self):
        import io, tarfile

        bbl = (r"\bibitem{a} A.~Author, \emph{A genuine looking title of "
               r"sufficient length}, Journal, 2019.")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            data = bbl.encode()
            info = tarfile.TarInfo(name="main.bbl")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        entries = bibliography_from_source(buf.getvalue())
        assert len(entries) == 1
        assert "genuine looking title" in entries[0]

    def test_bbl_preferred_over_bib(self):
        """
        .bbl is the rendered bibliography. .bib is a source database that may
        list works the paper never cites, which would inflate the sample with
        references no author actually made.
        """
        import io, tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, content in (
                ("refs.bib", "@article{x, title={A bibtex only entry title here}, "
                             "author={A}, year={2020}}"),
                ("main.bbl", r"\bibitem{a} Author, \emph{The rendered bbl title "
                             r"which should win}, 2019."),
            ):
                data = content.encode()
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        entries = bibliography_from_source(buf.getvalue())
        joined = " ".join(entries)
        assert "rendered bbl title" in joined
        assert "bibtex only entry" not in joined


# ===========================================================================
# Wikipedia corpus
# ===========================================================================

from citeaudit.wikipedia import clean_wikitext, parse_citations


class TestWikipediaParsing:

    WIKITEXT = """
Some article prose with a claim.<ref>{{cite journal |last=Smith |first=John
|title=A sufficiently long journal article title |journal=Nature |year=2015
|doi=10.1038/nature14539 }}</ref>

Another claim.<ref>{{cite report |author=Department of Health
|title=Annual statistical report on communicable disease |year=2021
|publisher=HMSO }}</ref>

A preprint.<ref>{{cite arxiv |last=Vaswani |title=Attention Is All You Need
|eprint=1706.03762 |year=2017 }}</ref>

A stub with no usable title.<ref>{{cite web |url=http://example.com |title=x }}</ref>
"""

    def test_extracts_structured_references(self):
        refs = parse_citations(self.WIKITEXT)
        assert len(refs) == 3          # the 'x' title is too short to use
        titles = [r.title for r in refs]
        assert any("journal article title" in t for t in titles)

    def test_doi_is_normalised(self):
        refs = parse_citations(self.WIKITEXT)
        journal = next(r for r in refs if r.template == "journal")
        assert journal.doi == "10.1038/nature14539"
        assert journal.year == 2015
        assert journal.authors == ["Smith"]

    def test_arxiv_eprint_parameter_recognised(self):
        refs = parse_citations(self.WIKITEXT)
        pre = next(r for r in refs if r.template == "arxiv")
        assert pre.arxiv == "1706.03762"

    def test_non_journal_templates_are_kept(self):
        """
        Reports and books are precisely why this corpus is here: they are the
        grey literature a scholarly index does not cover, and a consulting
        bibliography is full of them.
        """
        refs = parse_citations(self.WIKITEXT)
        assert any(r.template == "report" for r in refs)

    def test_short_titles_are_skipped(self):
        assert all(len(r.title or "") >= 15 for r in parse_citations(self.WIKITEXT))

    def test_year_parsed_from_a_full_date(self):
        wt = ('{{cite journal |title=A long enough title for the parser '
              '|date=14 March 2019 }}')
        assert parse_citations(wt)[0].year == 2019

    def test_wiki_markup_stripped_from_titles(self):
        wt = ("{{cite journal |title=A study of [[quantum mechanics|quantum]] "
              "effects in solids }}")
        title = parse_citations(wt)[0].title
        assert "[[" not in title and "|" not in title
        assert "quantum" in title

    def test_clean_wikitext_handles_bold_italic_and_html(self):
        assert clean_wikitext("'''bold''' and ''italic'' <br/>text") == \
            "bold and italic text"

    def test_no_citations_returns_empty(self):
        assert parse_citations("Plain prose with no templates at all.") == []

    def test_malformed_template_is_skipped_not_crashed(self):
        assert parse_citations("{{cite journal |title=unterminated") == []


class TestWikipediaTemplateSplit:
    """
    The split between scholarly and grey templates is the difference between a
    measurement and a category error. An earlier run reported 75% unverified by
    pooling them, which measured whether Crossref indexes journalism rather
    than whether references were real.
    """

    def test_scholarly_and_grey_sets_are_disjoint(self):
        from citeaudit.wikipedia import GREY_TEMPLATES, SCHOLARLY_TEMPLATES
        assert not (SCHOLARLY_TEMPLATES & GREY_TEMPLATES)

    def test_journal_and_arxiv_are_scholarly(self):
        from citeaudit.wikipedia import SCHOLARLY_TEMPLATES
        assert {"journal", "arxiv"} <= SCHOLARLY_TEMPLATES

    def test_news_and_web_are_not_scholarly(self):
        from citeaudit.wikipedia import SCHOLARLY_TEMPLATES
        assert "news" not in SCHOLARLY_TEMPLATES
        assert "web" not in SCHOLARLY_TEMPLATES

    def test_summary_reports_the_comparable_rate_separately(self):
        from citeaudit.wikipedia import WikiCheck, WikiStudy, summarise

        study = WikiStudy(checks=[
            WikiCheck(article="A", template="journal", kind="doi",
                      identifier="10.1/a", claimed_title="t",
                      verdict="verified", authority="crossref"),
            WikiCheck(article="A", template="journal", kind="doi",
                      identifier="10.1/b", claimed_title="t",
                      verdict="not_found", authority="crossref"),
            WikiCheck(article="A", template="news", kind="bibliographic",
                      identifier=None, claimed_title="t",
                      verdict="not_found", authority="crossref"),
            WikiCheck(article="A", template="web", kind="bibliographic",
                      identifier=None, claimed_title="t",
                      verdict="not_found", authority="crossref"),
        ])
        s = summarise(study)
        assert s["scholarly_templates"]["unverified_rate"] == pytest.approx(0.5)
        assert s["grey_templates"]["unverified_rate"] == pytest.approx(1.0)
        # Pooling would report 75% and call it an integrity finding.
        assert s["overall"]["unverified_rate"] == pytest.approx(0.75)
        assert s["headline"]["comparable_rate"] == pytest.approx(0.5)


class TestEmptyStudyGuard:
    """
    REGRESSION. An arXiv run returned zero papers — the client was pacing
    requests at 0.12s against an API that asks for three seconds, so every
    query came back empty. The empty result was then written over 1,247
    committed checks, destroying the better measurement silently.

    A failed run must leave good evidence alone and fail loudly.
    """

    def test_empty_preprint_study_refuses_to_write(self, tmp_path):
        from citeaudit.preprints import EmptyStudy, PreprintStudy, summarise, write_outputs

        study = PreprintStudy()
        with pytest.raises(EmptyStudy):
            write_outputs(study, summarise(study), tmp_path)
        assert not (tmp_path / "summary.json").exists()

    def test_empty_wikipedia_study_refuses_to_write(self, tmp_path):
        from citeaudit.wikipedia import EmptyStudy, WikiStudy, summarise, write_outputs

        study = WikiStudy()
        with pytest.raises(EmptyStudy):
            write_outputs(study, summarise(study), tmp_path)
        assert not (tmp_path / "summary.json").exists()

    def test_existing_evidence_survives_a_failed_run(self, tmp_path):
        from citeaudit.preprints import EmptyStudy, PreprintStudy, summarise, write_outputs

        good = tmp_path / "summary.json"
        good.write_text('{"real": "data"}')
        study = PreprintStudy()
        with pytest.raises(EmptyStudy):
            write_outputs(study, summarise(study), tmp_path)
        assert good.read_text() == '{"real": "data"}'


class TestHostPacing:

    def test_arxiv_is_paced_far_slower_than_the_default(self):
        """arXiv's API guidelines ask for roughly three seconds between calls."""
        from citeaudit.http import DEFAULT_MIN_INTERVAL, HOST_MIN_INTERVAL
        assert HOST_MIN_INTERVAL["export.arxiv.org"] >= 3.0
        assert HOST_MIN_INTERVAL["export.arxiv.org"] > DEFAULT_MIN_INTERVAL * 10

    def test_unknown_hosts_fall_back_to_the_default(self):
        from citeaudit.http import Client, DEFAULT_MIN_INTERVAL, HOST_MIN_INTERVAL
        assert "api.crossref.org" not in HOST_MIN_INTERVAL
        c = Client(cache_dir=None, use_cache=False)
        assert c.min_interval == DEFAULT_MIN_INTERVAL


class TestMismatchAudit:
    """
    The audit script exists because twice a plausible-looking rate concealed
    mostly false accusations, and both times only reading individual findings
    caught it. These tests pin the behaviour that matters: it must never
    conclude on evidence it cannot see.
    """

    def _write(self, tmp_path, rows):
        import csv
        p = tmp_path / "checks.csv"
        with p.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "identifier", "verdict", "reference_text", "detail"])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        return p

    def _run(self, path):
        import subprocess, sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / "scripts" / "audit_mismatches.py"
        return subprocess.run([sys.executable, str(script), str(path)],
                              capture_output=True, text=True)

    def test_resolved_false_accusation_is_reported_as_resolved(self, tmp_path):
        p = self._write(tmp_path, [{
            "identifier": "10.1007/bf01386390",
            "verdict": "mismatch",
            "reference_text": ("Edsger W. Dijkstra. A note on two problems in "
                               "connexion with graphs. Numer. Math., 1959."),
            "detail": ("identifier resolves to a DIFFERENT work. Document "
                       "claims 'Edsger W. Dijkstra'; record holds 'A note on "
                       "two problems in connexion with graphs' (25% similarity)"),
        }])
        out = self._run(p).stdout
        assert "were false accusations, now resolved" in out
        assert "1/1 were false accusations" in out

    def test_genuine_mismatch_survives(self, tmp_path):
        p = self._write(tmp_path, [{
            "identifier": "10.1/x",
            "verdict": "mismatch",
            "reference_text": ('Someone, A. (2023) "Oklo Inc. Fission '
                               'Impossible" Energy doi:10.1/x'),
            "detail": ("identifier resolves to a DIFFERENT work. Document "
                       "claims 'Oklo Inc. Fission Impossible'; record holds "
                       "'Uncertainties in estimating production costs of "
                       "future nuclear technologies' (8% similarity)"),
        }])
        out = self._run(p).stdout
        assert "survive and need manual confirmation" in out
        assert "1/1 survive" in out

    def test_truncated_detail_is_called_unauditable_not_guessed(self, tmp_path):
        """
        The important one. A finding whose evidence was truncated must be
        reported as unauditable, never silently counted as genuine or as
        resolved.
        """
        p = self._write(tmp_path, [{
            "identifier": "10.1/y",
            "verdict": "mismatch",
            "reference_text": 'A. Author. A real title here. Journal, 2020.',
            "detail": "identifier resolves to a DIFFERENT work. Document claims 'A real",
        }])
        out = self._run(p).stdout
        assert "UNAUDITABLE" in out
        assert "cannot be re-adjudicated offline" in out

    def test_survivors_are_labelled_candidates_not_conclusions(self, tmp_path):
        p = self._write(tmp_path, [{
            "identifier": "10.1/x", "verdict": "mismatch",
            "reference_text": 'X. Y. (2020) "Some title of adequate length" J.',
            "detail": ("Document claims 'Some title of adequate length'; "
                       "record holds 'A completely different piece of work'"),
        }])
        out = self._run(p).stdout
        assert "CANDIDATES, not conclusions" in out
        assert "read the record before repeating" in out

    def test_file_with_no_mismatches_is_handled(self, tmp_path):
        p = self._write(tmp_path, [{
            "identifier": "10.1/a", "verdict": "verified",
            "reference_text": "x", "detail": "ok"}])
        assert "no mismatches stored" in self._run(p).stdout


class TestStatisticalPowerGuard:
    """
    An estimate whose interval spans 3% to 51% is not a measurement, however
    carefully computed. Presenting it alongside well-supported figures is the
    same error as reporting a network timeout as a fabricated citation: a
    confident claim the evidence does not support.
    """

    def test_tiny_sample_is_rejected(self):
        from citeaudit.corpus import estimate_is_usable
        usable, reason = estimate_is_usable(7, [0.026, 0.513])
        assert not usable
        assert "7 conclusive checks" in reason

    def test_wide_interval_is_rejected_even_with_adequate_n(self):
        """n alone is not enough — the interval is what makes a figure usable."""
        from citeaudit.corpus import estimate_is_usable
        usable, reason = estimate_is_usable(40, [0.05, 0.40])
        assert not usable
        assert "spans" in reason

    def test_well_supported_estimate_passes(self):
        from citeaudit.corpus import estimate_is_usable
        assert estimate_is_usable(1201, [0.1136, 0.1519])[0]
        assert estimate_is_usable(307, [0.0051, 0.0330])[0]

    def test_zero_and_missing_interval_rejected(self):
        from citeaudit.corpus import estimate_is_usable
        assert not estimate_is_usable(0, [None, None])[0]
        assert not estimate_is_usable(100, [None, None])[0]

    def test_banner_is_empty_for_a_usable_estimate(self):
        from citeaudit.corpus import power_banner
        assert power_banner(1201, [0.1136, 0.1519]) == []

    def test_banner_warns_without_suppressing_the_number(self):
        """
        Hiding an underpowered result would conceal that the measurement was
        attempted. It is shown, and marked unusable.
        """
        from citeaudit.corpus import power_banner
        lines = "\n".join(power_banner(7, [0.026, 0.513]))
        assert "not usable" in lines
        assert "must not be quoted" in lines
        assert "suppressing it would hide" in lines

    def test_wikipedia_report_carries_the_banner_when_underpowered(self):
        from citeaudit.wikipedia import WikiCheck, WikiStudy, summarise, to_markdown

        study = WikiStudy(articles_sampled=13, articles_with_citations=13, checks=[
            WikiCheck(article="A", template="journal", kind="doi",
                      identifier=f"10.1/{i}", claimed_title="t",
                      verdict="verified" if i else "not_found",
                      authority="crossref")
            for i in range(7)
        ])
        md = to_markdown(summarise(study))
        assert "not usable" in md


class TestDegradationGuard:
    """
    REGRESSION. Emptiness was not the only way to destroy a measurement. A
    throttled run returning 87 checks overwrote one holding 1,247, because 87
    is not zero and the empty-guard let it through.
    """

    def _write_existing(self, tmp_path, checks: int):
        import json
        (tmp_path / "summary.json").write_text(
            json.dumps({"method": {"total_checks": checks}}))

    def _study(self, n: int):
        from citeaudit.preprints import PreprintCheck, PreprintStudy
        return PreprintStudy(checks=[
            PreprintCheck(arxiv_id=str(i), category="cs.LG", reference_text="t",
                          kind="doi", identifier=f"10.1/{i}",
                          verdict="verified", authority="crossref")
            for i in range(n)
        ])

    def test_much_smaller_run_is_refused(self, tmp_path):
        from citeaudit.preprints import DegradedStudy, summarise, write_outputs
        self._write_existing(tmp_path, 1247)
        study = self._study(87)
        with pytest.raises(DegradedStudy) as exc:
            write_outputs(study, summarise(study), tmp_path)
        assert "1,247" in str(exc.value)

    def test_comparable_run_is_allowed(self, tmp_path):
        from citeaudit.preprints import summarise, write_outputs
        self._write_existing(tmp_path, 100)
        study = self._study(90)
        write_outputs(study, summarise(study), tmp_path)
        import json
        assert json.loads((tmp_path / "summary.json").read_text())[
            "method"]["total_checks"] == 90

    def test_larger_run_is_allowed(self, tmp_path):
        from citeaudit.preprints import summarise, write_outputs
        self._write_existing(tmp_path, 100)
        study = self._study(500)
        write_outputs(study, summarise(study), tmp_path)

    def test_override_is_explicit(self, tmp_path):
        """Replacing a better measurement must be a decision, not an accident."""
        from citeaudit.preprints import summarise, write_outputs
        self._write_existing(tmp_path, 1247)
        study = self._study(87)
        write_outputs(study, summarise(study), tmp_path, allow_smaller=True)

    def test_first_ever_run_is_not_blocked(self, tmp_path):
        from citeaudit.preprints import summarise, write_outputs
        study = self._study(50)
        write_outputs(study, summarise(study), tmp_path)

    def test_unreadable_existing_summary_does_not_block(self, tmp_path):
        """A corrupt prior result must not wedge every future run."""
        from citeaudit.preprints import summarise, write_outputs
        (tmp_path / "summary.json").write_text("not json")
        study = self._study(50)
        write_outputs(study, summarise(study), tmp_path)


class TestOpenAlexPreprintSampling:
    """
    arXiv rate-limits by IP and GitHub runners share address space with every
    other project on the platform. Eleven of twelve category queries returned
    HTTP 429 across consecutive runs, with correct pacing on our side — the
    quota was already spent by someone else.

    Sampling moved to OpenAlex, which halves the load on arXiv (only source
    tarballs still need it) and puts the fragile step on an API with a polite
    pool.
    """

    class _Client:
        mailto = "t@example.org"

        def __init__(self, payload=None, exc=None):
            self.payload, self.exc = payload, exc
            self.urls: list[str] = []

        def get(self, url, **kwargs):
            from citeaudit.http import Response
            self.urls.append(url)
            if self.exc:
                raise self.exc
            import json as _json
            return Response(url=url, status=200,
                            body=_json.dumps(self.payload or {}).encode())

    def _work(self, doi, title="A preprint title"):
        return {"id": "W1", "doi": doi, "title": title,
                "primary_location": {"source": {"display_name": "arXiv"}}}

    def test_arxiv_id_is_read_from_the_doi(self):
        from citeaudit.preprints import sample_via_openalex
        c = self._Client({"results": [
            self._work("https://doi.org/10.48550/arXiv.2401.12345")]})
        out = sample_via_openalex(c, count=10, seed=1)
        assert out == [("2401.12345", "arXiv", "A preprint title")]

    def test_non_arxiv_dois_are_excluded(self):
        """A Nature DOI has no source tarball to fetch."""
        from citeaudit.preprints import sample_via_openalex
        c = self._Client({"results": [
            self._work("https://doi.org/10.1038/nature14539", "Deep learning")]})
        assert sample_via_openalex(c, count=10, seed=1) == []

    def test_sampling_is_seeded_for_reproducibility(self):
        from citeaudit.preprints import sample_via_openalex
        c = self._Client({"results": []})
        sample_via_openalex(c, count=10, seed=4242)
        assert "seed=4242" in c.urls[0]

    def test_contact_address_is_sent(self):
        from citeaudit.preprints import sample_via_openalex
        c = self._Client({"results": []})
        sample_via_openalex(c, count=5, seed=1)
        assert "mailto=" in c.urls[0]

    def test_openalex_failure_returns_empty_rather_than_raising(self):
        """The caller falls back to arXiv; an exception would kill the study."""
        from citeaudit.http import Unreachable
        from citeaudit.preprints import sample_via_openalex
        c = self._Client(exc=Unreachable("down"))
        assert sample_via_openalex(c, count=5, seed=1) == []

    def test_run_falls_back_to_arxiv_when_openalex_is_empty(self, monkeypatch):
        import citeaudit.preprints as pp

        monkeypatch.setattr(pp, "sample_via_openalex", lambda *a, **k: [])
        called = {"arxiv": False}

        def fake_arxiv(client, *, categories, per_category):
            called["arxiv"] = True
            return iter([])

        monkeypatch.setattr(pp, "sample_preprints", fake_arxiv)
        pp.run(self._Client({"results": []}), categories=["cs.LG"],
               per_category=1, workers=1)
        assert called["arxiv"], "arXiv fallback was not attempted"
