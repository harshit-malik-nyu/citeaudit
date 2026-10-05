# Non-expert bibliographies: bounding the extrapolation

**1,566 references** from **260 randomly sampled Wikipedia articles** (260 drawn).

## Why this corpus

The business case rests on an extrapolation from arXiv preprints to consulting deliverables, and that is the load-bearing assumption in the whole project. Physicists using reference managers are not analysts assembling a client report under deadline.

Wikipedia bounds it. Citations there are written by non-specialists in inconsistent styles, mixing journal articles with news, government reports, books and bare URLs, with no reference manager and no publisher pipeline. In character that is much closer to a consulting bibliography than a physics preprint is.

## What is not claimed

Not an audit of Wikipedia and not a judgment about its reliability. The unit is the reference; results are aggregate and no article is named. Wikipedia cites a great deal of material no scholarly index covers, so an unverifiable reference here is expected, not an error.

## Result

### The comparable figure

**15.2% unverified** across 567 scholarly-template references (95% CI 12.5%-18.4%).

This is the number to compare with the arXiv corpus, and the only one that measures citation integrity rather than index coverage. `{{cite journal}}`, `{{cite arxiv}}`, `{{cite conference}}` and `{{cite thesis}}` point at material Crossref and OpenAlex are the right authorities for.

### Grey-literature templates, reported separately

62.6% unverified across 999 references (`cite web`, `cite news`, `cite book`, `cite report`).

**This is not an integrity finding and must not be read as one.** Checking journalism and government web pages against a scholarly index measures whether that index covers journalism. It does not. A high rate here is the expected result for perfectly real references, and folding it into a headline would be a category error.

It is still worth reporting, because it quantifies how much of a mixed bibliography sits outside scholarly indexing altogether — which is the coverage problem any tool pointed at a consulting report runs into first.

### All templates combined

45.4% across 1,566 checks (95% CI 43.0%-47.9%). Shown for completeness only; the split above is the meaningful cut.

| | count |
|---|---:|
| Verified | 855 |
| Not found | 707 |
| Resolves to a different work | 4 |

### By how the reference was given

| Form | Conclusive | Unverified |
|---|---:|---:|
| bibliographic | 1,101 | 63.9% |
| doi | 465 | 1.5% |

### By source type

| Template | Conclusive | Unverified |
|---|---:|---:|
| cite book | 315 | 44.4% |
| cite journal | 560 | 14.5% |
| cite news | 103 | 82.5% |
| cite report | 9 | 66.7% |
| cite thesis | 7 | 71.4% |
| cite web | 572 | 68.9% |

The split by source type is the useful part. `cite journal` sits inside scholarly indexing; `cite report`, `cite book` and `cite news` largely do not, and a consulting bibliography is full of the latter. Their rate is the better guide to what a grey-literature document would score.

## Limits

- Sampling is biased toward substantial articles. Stubs carry no bibliography, so including them would measure nothing.
- Wikipedia is community-audited, with a culture of challenging unsourced claims. That plausibly makes it CLEANER than an unreviewed consulting report, so this is a lower bound on the target corpus, not an estimate of it.
- Citation templates are parsed structurally. References written as free text outside a template are not captured at all.