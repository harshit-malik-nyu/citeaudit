# Author-written bibliographies: what happens outside the pipeline

**87 references** from **8 arXiv preprints** (8 sampled), parsed from the authors' own `.bbl` and `.bib` source files.

## Why a second corpus

The base-rate study measured references that *publishers deposited* — cleaned, structured, DOI-bearing metadata from a production pipeline. It found essentially perfect integrity: zero of 307 deposited reference DOIs failed to resolve.

Nobody writes a bibliography that way. A consulting report, a policy paper or a draft manuscript carries references as a human or a language model typed them. arXiv source packages contain the author's bibliography before any publisher touched it, which makes them the closest public proxy for that corpus.

## What this does and does not claim

Measures whether a reference as written can be verified. An unverified reference is NOT thereby fabricated. Reported in aggregate; no paper is named and no claim is made about any author.

## Headline

> **The unverified rate is not usable: 95% interval spans 16%, wider than the 15% needed for the figure to mean anything.**
>
> It is shown because suppressing it would hide that the measurement was attempted, but it must not be quoted, compared, or carried into any downstream claim until the sample is larger.

| | count |
|---|---:|
| References checked | 87 |
| Verified | 65 |
| Not found | 11 |
| Resolves to a different work | 0 |
| Not machine-checkable | 1 |
| Could not check | 10 |

**Unverified rate: 14.5%** of 76 conclusive checks (95% CI 8.3%–24.1%).

## By how the reference was written

| Form | Conclusive | Unverified | 95% CI |
|---|---:|---:|---|
| arxiv | 0 | n/a | — |
| bibliographic | 59 | 18.6% | 10.7%–30.4% |
| doi | 17 | 0.0% | 0.0%–18.4% |
| url | 0 | n/a | — |

The gap between identifier-bearing and description-only references is the cost of omitting a DOI, measured rather than asserted.

## By field

| Category | Conclusive | Unverified |
|---|---:|---:|
| cs.LG | 76 | 14.5% |

## Limits

- Preprints are a *proxy* for author-written bibliographies, not the target corpus. Consulting deliverables and government reports are not publicly samplable at scale, which is why no base rate for them exists and why this stands in.
- Sampling takes a recent window per category by submission date, not a uniform random draw, so the result reflects current practice rather than the historical corpus.
- LaTeX parsing is shallow. Entries it mangles are reported as unverifiable rather than guessed at, so parsing failure inflates the inconclusive count, never the unverified rate.
- An unverified reference is not a fabricated one. Thin citations, non-indexed venues and transcription errors all land here, and the base-rate study exists to keep those from being misread.