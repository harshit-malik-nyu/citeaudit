# Base rate: how often does citeaudit flag a genuine reference?

**598 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 299 | 297 | 1 | 0.3% (95% CI 0.1%–1.9%) |
| Described (DOI withheld) | 299 | 293 | 6 | 2.0% (95% CI 0.9%–4.3%) |

The OpenAlex fallback rescued **20** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 50 | 0.0% | 0.0%–7.1% |
| 2017 | 51 | 2.0% | 0.3%–10.3% |
| 2020 | 56 | 3.6% | 1.0%–12.1% |
| 2022 | 44 | 0.0% | 0.0%–8.0% |
| 2023 | 44 | 2.3% | 0.4%–11.8% |
| 2024 | 54 | 3.7% | 1.0%–12.5% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **2.0%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 2.0% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1007/978-3-319-17308-5_2` | Responsible innovation 2: Concepts, approaches, and applications |
| described | `10.1007/978-3-319-56469-2_2` | Climate change, extreme events and disaster risk reduction: towards su |
| described | `10.1016/s1130-1473(02)70628-3` | Proposal and justification of aprotocol |
| identified | `10.11159/icnfa17.2017` | The 3rd world congress on new technologies |
| described | `10.11159/icnfa17.2017` | The 3rd world congress on new technologies |
| described | `10.2991/aebmr.k.220501.006` | Tenth international conference on entrepreneurship and business manage |
| described | `10.1378/chest.14-0733` | Task Force for Mass Critical Care. Surge capacity principles: Care of  |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.