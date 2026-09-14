# Base rate: how often does citeaudit flag a genuine reference?

**598 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 299 | 298 | 0 | 0.0% (95% CI 0.0%–1.3%) |
| Described (DOI withheld) | 299 | 296 | 3 | 1.0% (95% CI 0.3%–2.9%) |

The OpenAlex fallback rescued **10** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 45 | 0.0% | 0.0%–7.9% |
| 2017 | 52 | 3.8% | 1.1%–13.0% |
| 2020 | 47 | 2.1% | 0.4%–11.1% |
| 2022 | 57 | 0.0% | 0.0%–6.3% |
| 2023 | 46 | 0.0% | 0.0%–7.7% |
| 2024 | 52 | 0.0% | 0.0%–6.9% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **1.0%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 1.0% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.29309/tpmj/2015.22.04.1313` | Child birth; comparison of complications between lithotomy position an |
| described | `10.3109/01443618609079206` | The birthing chair: an obstetric hazard? |
| described | `10.1115/dmd2018-6906` | 2018 Design of Medical Devices Conf |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.