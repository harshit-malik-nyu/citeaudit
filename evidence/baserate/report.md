# Base rate: how often does citeaudit flag a genuine reference?

**668 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 334 | 330 | 0 | 0.0% (95% CI 0.0%–1.1%) |
| Described (DOI withheld) | 334 | 327 | 7 | 2.1% (95% CI 1.0%–4.3%) |

The OpenAlex fallback rescued **27** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 48 | 6.2% | 2.1%–16.8% |
| 2017 | 60 | 0.0% | 0.0%–6.0% |
| 2020 | 51 | 7.8% | 3.1%–18.5% |
| 2022 | 60 | 0.0% | 0.0%–6.0% |
| 2023 | 58 | 0.0% | 0.0%–6.2% |
| 2024 | 57 | 0.0% | 0.0%–6.3% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **2.1%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 2.1% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1590/1516-4446-2012-3501` | The quest for better diagnosis: DSM-5 or RDoC? |
| described | `10.1201/9781420036091` | Design and analysis of cross-over trials (Second ed.) |
| described | `10.1016/j.materresbull.2011.05.022` | Synthesis and properties of A6B2(OH)16Cl2.4H2O (A=Mg, Ni, Zn, Co, Mn a |
| described | `10.2135/cropsci2009.11.0666` | Tolerance to postharvest physiological deterioration in cassava roots< |
| described | `10.1016/j.ecolmodel.2018.12.013` | Grazing and aridity reduce perennial grass abundance in semi-arid rang |
| described | `10.4321/s1135-57272014000100007` | Meta-analysis of group comparison and meta-analysis of reliability gen |
| described | `10.1126/science.1103094` | Pie-rolapithecus catalaunicus, a new Middle Miocene great ape from Spa |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.