# Author-written bibliographies: what happens outside the pipeline

**329 references** from **34 arXiv preprints** (50 sampled), parsed from the authors' own `.bbl` and `.bib` source files.

## Why a second corpus

The base-rate study measured references that *publishers deposited* — cleaned, structured, DOI-bearing metadata from a production pipeline. It found essentially perfect integrity: zero of 307 deposited reference DOIs failed to resolve.

Nobody writes a bibliography that way. A consulting report, a policy paper or a draft manuscript carries references as a human or a language model typed them. arXiv source packages contain the author's bibliography before any publisher touched it, which makes them the closest public proxy for that corpus.

## What this does and does not claim

Measures whether a reference as written can be verified. An unverified reference is NOT thereby fabricated. Reported in aggregate; no paper is named and no claim is made about any author.

## Headline

| | count |
|---|---:|
| References checked | 329 |
| Verified | 298 |
| Not found | 21 |
| Resolves to a different work | 8 |
| Not machine-checkable | 2 |
| Could not check | 0 |

**Unverified rate: 8.9%** of 327 conclusive checks (95% CI 6.2%–12.4%).

## By how the reference was written

| Form | Conclusive | Unverified | 95% CI |
|---|---:|---:|---|
| arxiv | 18 | 22.2% | 9.0%–45.2% |
| bibliographic | 219 | 9.6% | 6.4%–14.2% |
| doi | 90 | 4.4% | 1.7%–10.9% |
| url | 0 | n/a | — |

The gap between identifier-bearing and description-only references is the cost of omitting a DOI, measured rather than asserted.

## By field

| Category | Conclusive | Unverified |
|---|---:|---:|
| cs.LG | 104 | 10.6% |
| econ.GN | 60 | 5.0% |
| physics.soc-ph | 43 | 9.3% |
| q-bio.QM | 48 | 4.2% |
| stat.AP | 72 | 12.5% |

## Limits

- Preprints are a *proxy* for author-written bibliographies, not the target corpus. Consulting deliverables and government reports are not publicly samplable at scale, which is why no base rate for them exists and why this stands in.
- Sampling takes a recent window per category by submission date, not a uniform random draw, so the result reflects current practice rather than the historical corpus.
- LaTeX parsing is shallow. Entries it mangles are reported as unverifiable rather than guessed at, so parsing failure inflates the inconclusive count, never the unverified rate.
- An unverified reference is not a fabricated one. Thin citations, non-indexed venues and transcription errors all land here, and the base-rate study exists to keep those from being misread.