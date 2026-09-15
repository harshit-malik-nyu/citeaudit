# Base rate: how often does citeaudit flag a genuine reference?

**598 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 299 | 299 | 0 | 0.0% (95% CI 0.0%–1.3%) |
| Described (DOI withheld) | 299 | 294 | 5 | 1.7% (95% CI 0.7%–3.9%) |

The OpenAlex fallback rescued **27** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 42 | 0.0% | 0.0%–8.4% |
| 2017 | 51 | 7.8% | 3.1%–18.5% |
| 2020 | 47 | 0.0% | 0.0%–7.6% |
| 2022 | 52 | 0.0% | 0.0%–6.9% |
| 2023 | 48 | 2.1% | 0.4%–10.9% |
| 2024 | 59 | 0.0% | 0.0%–6.1% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **1.7%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 1.7% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1109/tii.2011.2176742` | A fair and high throughput reader‐to‐reader anti‐collision protocol in |
| described | `10.1109/tie.2009.2021869` | An efficient reader anti‐collision algorithm in dense RFID networks wi |
| described | `10.1016/s1359-1789(97)00001-3` | Video game violence: A review of the empirical literature |
| described | `10.4101/jvwr.v7i2.7096` | White man's virtual world: A systematic content analysis of gender and |
| described | `10.1117/12.2232103` | Proc. SPIE Conf. Ser. Vol. 9908, Ground-based and Airborne Instrumenta |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.