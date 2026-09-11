# Non-expert bibliographies: bounding the extrapolation

**16 references** from **2 randomly sampled Wikipedia articles** (2 drawn).

## Why this corpus

The business case rests on an extrapolation from arXiv preprints to consulting deliverables, and that is the load-bearing assumption in the whole project. Physicists using reference managers are not analysts assembling a client report under deadline.

Wikipedia bounds it. Citations there are written by non-specialists in inconsistent styles, mixing journal articles with news, government reports, books and bare URLs, with no reference manager and no publisher pipeline. In character that is much closer to a consulting bibliography than a physics preprint is.

## What is not claimed

Not an audit of Wikipedia and not a judgment about its reliability. The unit is the reference; results are aggregate and no article is named. Wikipedia cites a great deal of material no scholarly index covers, so an unverifiable reference here is expected, not an error.

## Result

**Unverified rate 75.0%** of 16 conclusive checks (95% CI 50.5%-89.8%).

| | count |
|---|---:|
| Verified | 4 |
| Not found | 12 |
| Resolves to a different work | 0 |

### By how the reference was given

| Form | Conclusive | Unverified |
|---|---:|---:|
| bibliographic | 16 | 75.0% |

### By source type

| Template | Conclusive | Unverified |
|---|---:|---:|
| cite book | 1 | 100.0% |
| cite journal | 1 | 100.0% |
| cite web | 14 | 71.4% |

The split by source type is the useful part. `cite journal` sits inside scholarly indexing; `cite report`, `cite book` and `cite news` largely do not, and a consulting bibliography is full of the latter. Their rate is the better guide to what a grey-literature document would score.

## Limits

- Sampling is biased toward substantial articles. Stubs carry no bibliography, so including them would measure nothing.
- Wikipedia is community-audited, with a culture of challenging unsourced claims. That plausibly makes it CLEANER than an unreviewed consulting report, so this is a lower bound on the target corpus, not an estimate of it.
- Citation templates are parsed structurally. References written as free text outside a template are not captured at all.