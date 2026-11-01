# Base rate: how often does citeaudit flag a genuine reference?

**590 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 295 | 294 | 1 | 0.3% (95% CI 0.1%–1.9%) |
| Described (DOI withheld) | 295 | 291 | 4 | 1.4% (95% CI 0.5%–3.4%) |

The OpenAlex fallback rescued **19** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 34 | 5.9% | 1.6%–19.1% |
| 2017 | 55 | 1.8% | 0.3%–9.6% |
| 2020 | 54 | 1.9% | 0.3%–9.8% |
| 2022 | 48 | 0.0% | 0.0%–7.4% |
| 2023 | 52 | 0.0% | 0.0%–6.9% |
| 2024 | 52 | 0.0% | 0.0%–6.9% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **1.4%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 1.4% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.5840/jsce200525122` | Touch on trial: power and the right to physical affection |
| described | `10.5858/2007-131-777-eeaeii` | Emerging eosinophilic (allergic) esophagitis: increased incidence or i |
| described | `10.1002/3527601678` | Calculations of NMR and EPR Parameters. Theory and Applications |
| described | `10.1056/nejmoa2001017` | China Novel Coronavirus Investigating and Research Team. A novel coron |
| identified | `10.2581/zenodo.61119` | ORBIT: IDL Software for Visual, Spectroscopic, and Combined Orbits |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.