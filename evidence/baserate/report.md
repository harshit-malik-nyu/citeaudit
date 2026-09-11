# Base rate: how often does citeaudit flag a genuine reference?

**640 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 320 | 316 | 3 | 0.9% (95% CI 0.3%–2.7%) |
| Described (DOI withheld) | 320 | 317 | 3 | 0.9% (95% CI 0.3%–2.7%) |

The OpenAlex fallback rescued **15** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 52 | 1.9% | 0.3%–10.1% |
| 2017 | 48 | 0.0% | 0.0%–7.4% |
| 2020 | 52 | 3.8% | 1.1%–13.0% |
| 2022 | 56 | 0.0% | 0.0%–6.4% |
| 2023 | 54 | 0.0% | 0.0%–6.6% |
| 2024 | 58 | 0.0% | 0.0%–6.2% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **0.9%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 0.9% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.