# Author-written bibliographies: what happens outside the pipeline

**1,259 references** from **122 arXiv preprints**, parsed from the authors' own `.bbl` and `.bib` source files.

Accumulated across runs: 1,247 references were collected earlier and 12 were added by the most recent run.

arXiv rate-limits by IP and CI runners share address space, so any single run may collect a hundred papers or none for reasons unrelated to this code. Each run therefore contributes what it managed to fetch and skips papers already covered, rather than depending on one lucky execution. Stating the split matters: an accumulated total presented as a single run's output would overstate what any one execution achieved.

## Why a second corpus

The base-rate study measured references that *publishers deposited* — cleaned, structured, DOI-bearing metadata from a production pipeline. It found essentially perfect integrity: zero of 307 deposited reference DOIs failed to resolve.

Nobody writes a bibliography that way. A consulting report, a policy paper or a draft manuscript carries references as a human or a language model typed them. arXiv source packages contain the author's bibliography before any publisher touched it, which makes them the closest public proxy for that corpus.

## What this does and does not claim

Measures whether a reference as written can be verified. An unverified reference is NOT thereby fabricated. Reported in aggregate; no paper is named and no claim is made about any author.

## Headline

| | count |
|---|---:|
| References checked | 1,259 |
| Verified | 1,053 |
| Not found | 147 |
| Resolves to a different work | 11 |
| Not machine-checkable | 48 |
| Could not check | 0 |

**Unverified rate: 13.0%** of 1,211 conclusive checks (95% CI 11.3%–15.1%).

## By how the reference was written

| Form | Conclusive | Unverified | 95% CI |
|---|---:|---:|---|
| arxiv | 66 | 6.1% | 2.4%–14.6% |
| bibliographic | 796 | 17.8% | 15.3%–20.7% |
| doi | 349 | 3.4% | 2.0%–5.9% |
| url | 0 | n/a | — |

The gap between identifier-bearing and description-only references is the cost of omitting a DOI, measured rather than asserted.

## By field

| Category | Conclusive | Unverified |
|---|---:|---:|
| arXiv (Cornell University) | 10 | 0.0% |
| astro-ph.GA | 39 | 12.8% |
| cond-mat.stat-mech | 77 | 6.5% |
| cs.CR | 112 | 12.5% |
| cs.CY | 98 | 25.5% |
| cs.LG | 147 | 16.3% |
| econ.GN | 82 | 11.0% |
| eess.SY | 138 | 7.2% |
| math.ST | 127 | 5.5% |
| physics.soc-ph | 81 | 12.3% |
| q-bio.QM | 96 | 11.5% |
| q-fin.GN | 98 | 18.4% |
| stat.AP | 106 | 18.9% |

## Limits

- Preprints are a *proxy* for author-written bibliographies, not the target corpus. Consulting deliverables and government reports are not publicly samplable at scale, which is why no base rate for them exists and why this stands in.
- Sampling takes a recent window per category by submission date, not a uniform random draw, so the result reflects current practice rather than the historical corpus.
- LaTeX parsing is shallow. Entries it mangles are reported as unverifiable rather than guessed at, so parsing failure inflates the inconclusive count, never the unverified rate.
- An unverified reference is not a fabricated one. Thin citations, non-indexed venues and transcription errors all land here, and the base-rate study exists to keep those from being misread.