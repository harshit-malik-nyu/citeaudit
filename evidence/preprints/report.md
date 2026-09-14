# Author-written bibliographies: what happens outside the pipeline

**0 references** from **0 arXiv preprints** (0 sampled), parsed from the authors' own `.bbl` and `.bib` source files.

## Why a second corpus

The base-rate study measured references that *publishers deposited* — cleaned, structured, DOI-bearing metadata from a production pipeline. It found essentially perfect integrity: zero of 307 deposited reference DOIs failed to resolve.

Nobody writes a bibliography that way. A consulting report, a policy paper or a draft manuscript carries references as a human or a language model typed them. arXiv source packages contain the author's bibliography before any publisher touched it, which makes them the closest public proxy for that corpus.

## What this does and does not claim

Measures whether a reference as written can be verified. An unverified reference is NOT thereby fabricated. Reported in aggregate; no paper is named and no claim is made about any author.

## Headline

| | count |
|---|---:|
| References checked | 0 |
| Verified | 0 |
| Not found | 0 |
| Resolves to a different work | 0 |
| Not machine-checkable | 0 |
| Could not check | 0 |

**Unverified rate: n/a** of 0 conclusive checks (95% CI —).

## Limits

- Preprints are a *proxy* for author-written bibliographies, not the target corpus. Consulting deliverables and government reports are not publicly samplable at scale, which is why no base rate for them exists and why this stands in.
- Sampling takes a recent window per category by submission date, not a uniform random draw, so the result reflects current practice rather than the historical corpus.
- LaTeX parsing is shallow. Entries it mangles are reported as unverifiable rather than guessed at, so parsing failure inflates the inconclusive count, never the unverified rate.
- An unverified reference is not a fabricated one. Thin citations, non-indexed venues and transcription errors all land here, and the base-rate study exists to keep those from being misread.