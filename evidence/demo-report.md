## citeaudit — `examples/demo.md`

**5 citation(s) did not hold up.**

| | count |
|---|---:|
| Verified | 8 |
| No such record | 4 |
| Resolves to different work | 1 |
| Malformed | 0 |
| Could not check | 1 |
| Not machine-checkable | 0 |
| **Total** | **14** |

Integrity: 62% of 13 conclusive checks passed

### Failures

| Line | Reference | Verdict | Detail | Evidence |
|---:|---|---|---|---|
| 59 | `10.1016/j.jpuba.2021.02.014` | No such record | Neither Crossref nor OpenAlex holds a record for this DOI. Two independent indexes have no registration for it. | [check](https://api.crossref.org/works/10.1016/j.jpuba.2021.02.014) |
| 61 | `10.9911/erla.2020.13.4.055` | No such record | Neither Crossref nor OpenAlex holds a record for this DOI. Two independent indexes have no registration for it. | [check](https://api.crossref.org/works/10.9911/erla.2020.13.4.055) |
| 63 | `The reasoned decision requirement and automated administrative action` | No such record | no indexed record matches this description. Closest was 'Choline Requirement, Distribution and Concentration in Laying Hens.' at 58% similarity, below the threshold for a match. | [check](https://doi.org/10.31390/gradschool_disstheses.1478) |
| 69 | `Procedural fairness in machine-assisted eligibility determination: a l` | No such record | no indexed record matches this description. Closest was 'A longitudinal study of visual function in multiple sclerosis: With a note on the Cambridge Grating Test' at 55% similarity | [check](https://doi.org/10.3109/01658109309038141) |
| 73 | `10.1038/nature14539` | Resolves to a different work | identifier resolves to a DIFFERENT work. Document claims 'Procedural baselines for administrative automation in social welfare'; record holds 'Deep learning' (22% similarity) | [check](https://doi.org/10.1038/nature14539) |

### Quotations

| | count |
|---|---:|
| Located in source | 1 |
| **Absent from full text** | **1** |
| Not in abstract (inconclusive) | 0 |
| No open text available | 0 |
| No citation attached | 0 |

Quote coverage 100%. Most scholarly text is paywalled; only complete retrieved text can establish that a passage is absent, so the rest are inconclusive rather than failures.

> **Line 30** — not present in the source
> `welfare eligibility determinations should be fully delegated to automated systems without human review`
> complete text of the source was retrieved (4,716 words) and this passage does not appear in it. Closest match scored 49%.

<details><summary>1 inconclusive (not counted as failures)</summary>

- line 76: `https://this-domain-does-not-resolve-citeaudit.invalid/report.pdf` — check could not be completed: https://this-domain-does-not-resolve-citeaudit.invalid/report.pdf

</details>