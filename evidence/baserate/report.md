# Base rate: how often does citeaudit flag a genuine reference?

**628 checks** across **72 published papers**, sampled at random from Crossref and stratified by publication year (2014–2024). Seed 20260909.

## Why these references are known to be genuine

References deposited by publishers in real published papers. Ground truth is guaranteed by construction: every reference carries a DOI, so the cited work exists. Any NOT_FOUND is therefore a definite false positive.

## Headline

| Mode | Checks | Verified | False positives | FP rate |
|---|---:|---:|---:|---:|
| Identified (DOI given) | 314 | 313 | 0 | 0.0% (95% CI 0.0%–1.2%) |
| Described (DOI withheld) | 314 | 304 | 10 | 3.2% (95% CI 1.7%–5.8%) |

The OpenAlex fallback rescued **25** references that Crossref alone would have reported as non-existent.

## By publication year of the citing paper

| Year | Checks | FP rate | 95% CI |
|---:|---:|---:|---|
| 2014 | 52 | 3.8% | 1.1%–13.0% |
| 2017 | 49 | 6.1% | 2.1%–16.5% |
| 2020 | 56 | 1.8% | 0.3%–9.4% |
| 2022 | 48 | 2.1% | 0.4%–10.9% |
| 2023 | 52 | 0.0% | 0.0%–6.9% |
| 2024 | 57 | 5.3% | 1.8%–14.4% |

## How to read a document score against this

On references that are genuine, citeaudit reports NOT_FOUND about **3.2%** of the time when no identifier is supplied. A document whose references carry no DOIs should therefore be expected to show roughly that failure rate before any real problem is present.

A NOT_FOUND rate materially above 3.2% is the signal worth investigating. A rate at or below it is consistent with normal coverage gaps and says nothing about fabrication.

## What the false positives actually are

Every entry below is a genuine work that citeaudit failed to find. Listing them is more useful than the rate alone, because the pattern tells you where the coverage gap lives.

| Mode | DOI | Claimed title |
|---|---|---|
| described | `10.1046/j.1464-410x.2002.02656.x` | The urethral plate-does it grow into the genital tubercle or within it |
| described | `10.1016/j.amepre.2011.10.021` | Public Health Department Accreditation: setting the research agenda. |
| described | `10.1111/sji.12061` | Atrial fibrillation: inflammation in disguise? |
| described | `10.1177/000331970505600206` | Clinical echocardiographic and homodynamic characteristics of rheumati |
| described | `10.1016/j.jacc.2011.07.035` | Valvular heart disease: The value of 3-dimensional echocardiography |
| described | `10.1161/circheartfailure.116.003255` | Survival benefits of invasive versus conservative strategies in heart  |
| described | `10.4159/harvard.9780674330702` | Sexual selection and animal genitalia |
| described | `10.22600/1518-8795.ienci2016v21n2p153` | Evasão e retenção escolar no curso de licenciatura em química do Insti |
| described | `10.1016/j.econedurev.2003.10.006` | Come and stay a while: does financial aid effect retention conditioned |
| described | `10.1016/j.seta.2021.101474` | Study and analysis of SARIMA and LSTM in forecasting time series data |

## Limits

- The sample is drawn from `type:journal-article` with deposited references. It is representative of the indexed scholarly literature, not of consulting reports, government documents, or grey literature — the very corpora where fabrication has actually been found.
- References were required to carry both a DOI and a title, which biases toward well-deposited records. The true false-positive rate on messier bibliographies is likely higher.
- This measures whether a genuine work can be *found*. It does not measure whether a fabricated work is correctly *rejected*; that is what the calibration study covers.