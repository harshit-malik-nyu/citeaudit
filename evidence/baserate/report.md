# Base rate: how often does citeaudit flag a genuine reference?

**334 checks** across **33 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 167 | 166 | 1 | 0.6% (95% CI 0.1%–3.3%) |
| Described (DOI withheld) | 167 | 166 | 1 | 0.6% (95% CI 0.1%–3.3%) |

The OpenAlex fallback rescued **14** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 32 | 0.0% | 0.0%–10.7% |
| 2017 | 35 | 0.0% | 0.0%–9.9% |
| 2020 | 25 | 4.0% | 0.7%–19.5% |
| 2022 | 33 | 0.0% | 0.0%–10.4% |
| 2023 | 24 | 0.0% | 0.0%–13.8% |
| 2024 | 18 | 0.0% | 0.0%–17.6% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **0.6%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 0.6% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.