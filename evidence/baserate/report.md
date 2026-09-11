# Base rate: how often does citeaudit flag a genuine reference?

**620 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 310 | 310 | 0 | 0.0% (95% CI 0.0%–1.2%) |
| Described (DOI withheld) | 310 | 310 | 0 | 0.0% (95% CI 0.0%–1.2%) |

The OpenAlex fallback rescued **19** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 49 | 0.0% | 0.0%–7.3% |
| 2017 | 52 | 0.0% | 0.0%–6.9% |
| 2020 | 52 | 0.0% | 0.0%–6.9% |
| 2022 | 53 | 0.0% | 0.0%–6.8% |
| 2023 | 56 | 0.0% | 0.0%–6.4% |
| 2024 | 48 | 0.0% | 0.0%–7.4% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **0.0%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 0.0% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.