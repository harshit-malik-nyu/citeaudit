# citeaudit

**Verify that the citations in a document actually exist.**

[![ci](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/ci.yml/badge.svg)](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/ci.yml)
[![live-verification](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/live-verification.yml/badge.svg)](https://github.com/harshit-malik-nyu/citeaudit/actions/workflows/live-verification.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Point it at a document. It extracts every DOI, arXiv identifier, URL, and
bibliographic reference, checks each against the authority that can answer for
it, and tells you which ones do not hold up.

```bash
pip install citeaudit
citeaudit report.docx
```

---

## Why this exists

Between October 2025 and May 2026, three of the world's four largest
professional services firms retracted or corrected published reports containing
citations that did not exist.

- **Deloitte Australia** refunded part of a A$440,000 contract with the
  Department of Employment and Workplace Relations after a 237-page assurance
  review was found to contain a fabricated quote attributed to a federal court
  judge and references to academic papers that had never been written.
  ([The Guardian](https://www.theguardian.com/australia-news/2025/oct/06/deloitte-to-pay-money-back-to-albanese-government-after-using-ai-in-440000-report))
- **EY** withdrew a study after a majority of its citations could not be
  verified.
- **KPMG** opened a review and withdrew a report over similar failures.

Every one of those documents passed internal quality assurance and partner
review. Two passed client sign-off.

The reason is not that reviewers were careless. It is that professional review
was designed to catch the mistakes humans make — arithmetic slips, logical
gaps, weak sourcing. Machine-generated text fails differently. It produces
references that are correctly formatted, plausibly titled, attributed to real
researchers in the right field, and published in journals that exist. Nothing
about them looks wrong, because nothing about them *is* wrong except that the
paper was never written.

Checking that by hand takes about ninety seconds per reference. A 237-page
report has hundreds. That arithmetic is why it does not get done, and it is the
entire reason this tool exists.

## What it catches that a link checker does not

A link checker asks "does this URL respond". That is the wrong question, and
answering it well provides false assurance.

The dangerous failure is a **real DOI attached to the wrong paper**. The link
resolves. A reviewer clicks it and lands on a genuine article in a real journal.
The citation passes every check that stops at HTTP 200 — and it is still wrong,
because it is not the source that supports the claim being made.

citeaudit compares what the document *claims* about a reference against what
the authority actually *holds* under that identifier:

```
MISM  line 42   10.1038/nature14539
      document says: 'Procedural fairness in machine-assisted eligibility determination'
      record holds:  'Deep learning'
      identifier resolves to a DIFFERENT work (8% title similarity)
      check it: https://doi.org/10.1038/nature14539
```

It also catches references carrying no identifier at all, by searching Crossref
for the described work. If nothing close exists, that is reported — which is
how a confident reference to a paper nobody ever wrote gets found.

## What the measurements say

Three studies against live Crossref, OpenAlex and arXiv. Results committed to
[`evidence/`](evidence/), refreshed on a schedule.

They exist because a verdict is uninterpretable without them. If a document
scores 91%, you cannot tell whether that is alarming or ordinary until you know
what ordinary is — and before this, nobody had measured it.

### The headline: where citation integrity actually breaks down

| Corpus | Unverified rate | 95% CI |
|---|---:|---|
| Publisher-deposited, DOI supplied | **0.00%** | 0.00–1.24% |
| Publisher-deposited, no identifier | **1.30%** | 0.51–3.30% |
| **Author-written bibliographies** | **8.87%** | 6.25–12.45% |

A **sevenfold gap**, and it is the most useful number in this repository.

References that publishers deposit are near-perfect: not one of 307 DOI-bearing
entries failed to resolve. References as *authors actually write them* — the
same scholarly works, cited by hand — verify at 8.87%.

The difference is not the literature. It is the pipeline. Deposited metadata is
machine-validated at source; a typed bibliography is not validated by anyone.

That matters because **the corpus where fabrication has been found has no
pipeline at all.** Consulting deliverables, government reports and internal
memoranda are written like the third row and checked like nothing. If
peer-reviewed literature with a validation pipeline still drifts to 8.87% once
a human types the reference, the expectation for a document with no pipeline
should be set accordingly.

### Two base rates, and why both are needed

**[Deposited references](evidence/baserate/report.md)** — 614 checks across 72
randomly sampled published papers, stratified by year.

Ground truth comes free from the construction. Take real papers, take their
deposited reference lists; every entry carries a DOI, so every cited work
provably exists. Hide the DOI, check by description alone, and **every
NOT_FOUND is a definite false positive.** No labelling, no annotator judgment.

This measures the tool's error rate. At 0.00% with identifiers and 1.30%
without, citeaudit does not meaningfully manufacture false alarms.

**[Author-written references](evidence/preprints/report.md)** — 329 references
from 34 arXiv preprints, parsed from the authors' own `.bbl` and `.bib` source
before any publisher touched them.

This measures the world's error rate, on the corpus type that matters. Because
the first study bounds the tool's contribution at ~1%, the remaining ~8% is
attributable to the bibliographies, not the checker. Neither study means much
alone; together they separate instrument from signal.

| How the reference was written | Conclusive | Unverified |
|---|---:|---:|
| Carries a DOI | 90 | 4.4% |
| Description only | 219 | 9.6% |
| arXiv identifier | 18 | 22.2% |

Supplying a DOI halves the unverified rate. That is a concrete, free
intervention any organisation can mandate tomorrow.

**What 8.87% is not.** It is not a fabrication rate. Non-indexed venues,
workshop papers, technical reports and transcription errors all land in the
same bucket, and the tool says so. The claim is narrow and deliberate: this is
how often a reference *as written* can be verified against public authorities.
Results are aggregate; no paper is named and no claim is made about any author.

The run did surface **8 genuine mismatches** — identifiers that resolve to a
different work than the citing text claims — in bibliographies nobody planted.

### Why the mismatch threshold is 66

[Full report](evidence/calibration/report.md) · 2,501 labelled pairs from 260
real Crossref records

Same-work pairs take a real record and degrade its title the way bibliographies
actually degrade. Different-work pairs attach one paper's DOI to the *nearest
confusable title* in the sample — a plausible title in the right field, which
is what a fabrication looks like. Labels follow from construction, not judgment.

| Threshold | Precision | Recall |
|---:|---:|---:|
| 48 | 1.000 | 0.437 |
| 54 | 1.000 | 0.881 |
| 60 | 1.000 | 0.992 |
| **66** | **1.000** | **1.000** |

Zero false accusations across 1,720 genuine pairs. The operating point is
chosen on a precision floor rather than by maximising F1, because the two
errors are not equally costly: a false accusation is what makes someone switch
the tool off, and a tool that is off catches nothing.

Across independent draws the minimum threshold reaching full recall landed at
62 and at 66. The upper end is set, so the configured value achieves full
recall on both draws rather than only on the one that produced it. Reporting
the band rather than a single run's answer is the honest form — a calibration
that moves with the sample and is quoted as a point estimate is a calibration
being oversold.

**A note on how this was reached.** The first calibration run returned perfect
precision *and* recall at every threshold from 54 to 90 — which looked like
success and was actually a failed measurement. Positives had been built by
pairing random titles from unrelated fields, so the two classes never met and
no threshold had anything to adjudicate. The labelled set was rebuilt around
nearest-neighbour confusions. The report now states explicitly whether the
classes overlap, so a future perfect score is visibly either earned or
meaningless.

### What it is worth

[Full sizing](docs/business-case.md)

A single retraction costs an estimated **A$732k** — of which the publicly
reported refund is about 15%. Three of the four largest firms had one in eight
months. Against a mitigation cost near A$35k, breakeven sits at one incident
every 21 years, and the net stays positive across an order of magnitude on
every assumption.

Every input in that model is labelled OBSERVED, ESTIMATE, or DERIVED, and the
weakest one is named rather than buried.

## Verdicts

The taxonomy is the most important design decision in the tool.

| Verdict | Meaning | Counts as failure |
|---|---|:---:|
| `VERIFIED` | Resolves, and the record matches the claim | |
| `MISMATCH` | Resolves, but to a **different work** than claimed | ✓ |
| `NOT_FOUND` | Well-formed identifier, no such record exists | ✓ |
| `MALFORMED` | Identifier is syntactically invalid | ✓ |
| `UNREACHABLE` | Could not complete the check | |
| `UNVERIFIABLE` | No identifier and no title specific enough to search | |

**A network timeout is not evidence of fabrication.** A tool that reports
"citation not found" when an API was slow is committing precisely the error it
exists to catch: emitting a confident claim its evidence does not support.
`UNREACHABLE` and `NOT_FOUND` are separate verdicts, counted separately, and
inconclusive checks are excluded from the integrity score's denominator rather
than silently passed or failed.

Where nothing could be checked, the score is `n/a` — never 0% or 100%.

## Usage

```bash
citeaudit report.docx                      # human-readable
citeaudit paper.pdf --format json -o out.json
citeaudit *.md --format html -o report.html
citeaudit thesis.tex --show-verified       # include passing citations

citeaudit draft.md --fail-under 95         # gate on integrity score
citeaudit draft.md --strict                # inconclusive also fails
```

Supported inputs: `.md` `.txt` `.rst` `.tex` `.html` `.pdf` `.docx`

Exit codes: `0` clean, `1` failures found, `2` tool error.

### As a GitHub Action

```yaml
- uses: harshit-malik-nyu/citeaudit@v1
  with:
    paths: 'docs/**/*.md reports/*.pdf'
    fail-under: '95'
    mailto: 'you@example.com'
```

### As a library

```python
from citeaudit.verify import Verifier

report = Verifier().verify_file("manuscript.docx")
for finding in report.failures:
    print(finding.citation.raw, finding.detail, finding.evidence_url)
```

## Live evidence

This repository does not ask you to take its word for anything.

**Most recent live run** against the real Crossref and arXiv APIs
([full JSON](evidence/demo-report.json)):

| | |
|---|---:|
| Citations checked | 14 |
| Verified | 8 |
| Resolves to a different work | 1 |
| No such record | 4 |
| Could not check (inconclusive) | 1 |
| **Integrity** | **62% of 13 conclusive checks** |

The mismatch is the one worth looking at:

```
line 63   10.1038/nature14539
  document claims : Procedural baselines for administrative automation in social welfare
  record holds    : Deep learning
  similarity      : 22%
  evidence        : https://doi.org/10.1038/nature14539
```

That DOI is real. [Open it](https://doi.org/10.1038/nature14539) — you land on a
genuine Nature paper by LeCun, Bengio and Hinton. Every link checker passes it.
It is still the wrong source for the claim it was attached to.

The unreachable link is equally deliberate: an unresolvable domain, reported as
inconclusive rather than counted as a fabrication.

A [scheduled workflow](.github/workflows/live-verification.yml) runs the tool
against the real Crossref and arXiv APIs every week and commits what they
returned:

- [`evidence/demo-report.json`](evidence/) — full findings with evidence URLs
- [`evidence/demo-report.md`](evidence/) — the same, readable
- [`evidence/manifest.json`](evidence/) — timestamps, commit SHA, run URL, artifact hashes
- [`docs/index.html`](docs/) — rendered report, published to GitHub Pages

Every finding carries an `evidence_url` pointing at the authority record that
produced the verdict. You can confirm or refute any line of any report without
running this code.

## Authorities

| Authority | Answers | Limits |
|---|---|---|
| [Crossref](https://www.crossref.org) | Does this DOI exist, and what is it | Covers scholarly publishing; not books, reports, or grey literature |
| [arXiv](https://arxiv.org) | Does this preprint exist | Preprints only |
| HTTP | Does this URL respond | Liveness only — proves nothing about content |

Both scholarly APIs are free and maintained on public goodwill. The client
paces its requests and identifies itself with a contact address per Crossref's
polite-pool convention. Please set `--mailto`.

## Limitations

Stated plainly, because a verification tool that oversells itself is
self-refuting.

- **A `NOT_FOUND` is not proof of fabrication.** Crossref does not cover books,
  government reports, working papers, or most grey literature. A real reference
  to a real report will fail this check. The tool reports what the authority
  said; judgment stays with you.
- **`VERIFIED` does not mean the source supports the claim.** It means the
  reference points at a real work that matches the description. Whether that
  work actually says what the document claims is a different problem, and this
  tool does not attempt it.
- **Quote verification is not implemented.** Deloitte's fabricated judicial
  quote would not be caught by this version. Catching it requires full-text
  retrieval, which is licensing-constrained for most publishers.
- **Reference parsing is heuristic.** Citation styles vary enormously.
  Unparsed references are reported as `UNVERIFIABLE` rather than skipped
  silently, so you can see what the tool could not read.
- **Title matching has thresholds**, set conservatively so that a false
  accusation is rarer than a missed detection. See
  [`src/citeaudit/match.py`](src/citeaudit/match.py) for the reasoning.

## Reproducing the studies

Every figure above is regenerated by one command against live authorities:

```bash
make install
python scripts/run_studies.py --study all
```

Results land in `evidence/`. The workflow runs monthly, or on demand by
touching `.studies-trigger`. Sampling is seeded, so a given seed redraws the
same papers.

## Development

```bash
make install
make test       # 99 offline tests
make live       # 9 live tests against real APIs
make demo
python -m build # wheel + sdist
```

The test suite is split deliberately. Offline tests use stub transports so a
failure always means the code is wrong, never that an API was slow. Live tests
skip rather than fail when an authority is unreachable — the same distinction
the tool draws between `NOT_FOUND` and `UNREACHABLE`.

## License

MIT
