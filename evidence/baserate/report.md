# Base rate: how often does citeaudit flag a genuine reference?

**656 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 328 | 326 | 0 | 0.0% (95% CI 0.0%–1.2%) |
| Described (DOI withheld) | 328 | 327 | 1 | 0.3% (95% CI 0.1%–1.7%) |

The OpenAlex fallback rescued **18** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 58 | 0.0% | 0.0%–6.2% |
| 2017 | 50 | 0.0% | 0.0%–7.1% |
| 2020 | 53 | 0.0% | 0.0%–6.8% |
| 2022 | 55 | 0.0% | 0.0%–6.5% |
| 2023 | 56 | 0.0% | 0.0%–6.4% |
| 2024 | 56 | 1.8% | 0.3%–9.4% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **0.3%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 0.3% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1109/tthz.2012.2183740` | First demonstration of a tunable electronic source in the 2.5 to 2.7 T |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.