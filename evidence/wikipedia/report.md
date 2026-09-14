# Non-expert bibliographies: bounding the extrapolation

**680 references** from **120 randomly sampled Wikipedia articles** (120 drawn).

## Why this corpus

The business case rests on an extrapolation from arXiv preprints to consulting deliverables, and that is the load-bearing assumption in the whole project. Physicists using reference managers are not analysts assembling a client report under deadline.

Wikipedia bounds it. Citations there are written by non-specialists in inconsistent styles, mixing journal articles with news, government reports, books and bare URLs, with no reference manager and no publisher pipeline. In character that is much closer to a consulting bibliography than a physics preprint is.

## What is not claimed

Not an audit of Wikipedia and not a judgment about its reliability. The unit is the reference; results are aggregate and no article is named. Wikipedia cites a great deal of material no scholarly index covers, so an unverifiable reference here is expected, not an error.

## Result

### The comparable figure

**13.9% unverified** across 237 scholarly-template references (95% CI 10.1%-18.9%).

This is the number to compare with the arXiv corpus, and the only one that measures citation integrity rather than index coverage. `{{cite journal}}`, `{{cite arxiv}}`, `{{cite conference}}` and `{{cite thesis}}` point at material Crossref and OpenAlex are the right authorities for.

### Grey-literature templates, reported separately

58.0% unverified across 441 references (`cite web`, `cite news`, `cite book`, `cite report`).

**This is not an integrity finding and must not be read as one.** Checking journalism and government web pages against a scholarly index measures whether that index covers journalism. It does not. A high rate here is the expected result for perfectly real references, and folding it into a headline would be a category error.

It is still worth reporting, because it quantifies how much of a mixed bibliography sits outside scholarly indexing altogether — which is the coverage problem any tool pointed at a consulting report runs into first.

### All templates combined

42.6% across 678 checks (95% CI 39.0%-46.4%). Shown for completeness only; the split above is the meaningful cut.

| | count |
|---|---:|
| Verified | 389 |
| Not found | 286 |
| Resolves to a different work | 3 |

### By how the reference was given

| Form | Conclusive | Unverified |
|---|---:|---:|
| arxiv | 0 | n/a |
| bibliographic | 479 | 58.9% |
| doi | 199 | 3.5% |

### By source type

| Template | Conclusive | Unverified |
|---|---:|---:|
| cite book | 160 | 43.1% |
| cite conference | 2 | 0.0% |
| cite journal | 233 | 13.7% |
| cite news | 48 | 79.2% |
| cite report | 8 | 50.0% |
| cite thesis | 2 | 50.0% |
| cite web | 225 | 64.4% |

The split by source type is the useful part. `cite journal` sits inside scholarly indexing; `cite report`, `cite book` and `cite news` largely do not, and a consulting bibliography is full of the latter. Their rate is the better guide to what a grey-literature document would score.

## Limits

- Sampling is biased toward substantial articles. Stubs carry no bibliography, so including them would measure nothing.
- Wikipedia is community-audited, with a culture of challenging unsourced claims. That plausibly makes it CLEANER than an unreviewed consulting report, so this is a lower bound on the target corpus, not an estimate of it.
- Citation templates are parsed structurally. References written as free text outside a template are not captured at all.