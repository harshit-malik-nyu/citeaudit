# Base rate: how often does citeaudit flag a genuine reference?

**614 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 307 | 305 | 0 | 0.0% (95% CI 0.0%–1.2%) |
| Described (DOI withheld) | 307 | 303 | 4 | 1.3% (95% CI 0.5%–3.3%) |

The OpenAlex fallback rescued **37** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 46 | 4.3% | 1.2%–14.5% |
| 2017 | 49 | 0.0% | 0.0%–7.3% |
| 2020 | 59 | 0.0% | 0.0%–6.1% |
| 2022 | 59 | 0.0% | 0.0%–6.1% |
| 2023 | 46 | 0.0% | 0.0%–7.7% |
| 2024 | 48 | 4.2% | 1.2%–14.0% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **1.3%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 1.3% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1016/j.sedgeo.2012.09.001` | Late-Pleistocene to Holocene sedimentary fills of the Cinarcik Basin o |
| described | `10.1007/s00367-006-0017-3` | Turbidites and their association with past earthquakes in the deep Cin |
| described | `10.1088/0031-9155/57/4/919` | The management of respiratory motion in radiation oncology report of A |
| described | `10.1109/cvpr.2016.90` | 2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR) |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.