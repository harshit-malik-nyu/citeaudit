## citeaudit — `examples/demo.md`

**5 citation(s) did not hold up.**

| | count |
|---|---:|
| Verified | 5 |
| No such record | 4 |
| Resolves to different work | 1 |
| Malformed | 0 |
| Could not check | 4 |
| Not machine-checkable | 0 |
| **Total** | **14** |

Integrity: 50% of 10 conclusive checks passed

### Failures

| Line | Reference | Verdict | Detail | Evidence |
|---:|---|---|---|---|
| 49 | `10.1016/j.jpuba.2021.02.014` | No such record | Neither Crossref nor OpenAlex holds a record for this DOI. Two independent indexes have no registration for it. | [check](https://api.crossref.org/works/10.1016/j.jpuba.2021.02.014) |
| 51 | `10.9911/erla.2020.13.4.055` | No such record | Neither Crossref nor OpenAlex holds a record for this DOI. Two independent indexes have no registration for it. | [check](https://api.crossref.org/works/10.9911/erla.2020.13.4.055) |
| 53 | `The reasoned decision requirement and automated administrative action` | No such record | no indexed record matches this description. Closest was 'Choline Requirement, Distribution and Concentration in Laying Hens.' at 58% similarity, below the threshold for a match. | [check](https://doi.org/10.31390/gradschool_disstheses.1478) |
| 59 | `Procedural fairness in machine-assisted eligibility determination: a l` | No such record | no indexed record matches this description. Closest was 'A longitudinal study of visual function in multiple sclerosis: With a note on the Cambridge Grating Test' at 55% similarity | [check](https://doi.org/10.3109/01658109309038141) |
| 63 | `10.1038/nature14539` | Resolves to a different work | identifier resolves to a DIFFERENT work. Document claims 'Procedural baselines for administrative automation in social welfare'; record holds 'Deep learning' (22% similarity) | [check](https://doi.org/10.1038/nature14539) |

<details><summary>4 inconclusive (not counted as failures)</summary>

- line 47: `1810.04805` — check could not be completed: https://export.arxiv.org/api/query?id_list=1810.04805&max_results=1: The read operation timed out
- line 57: `1906.02530` — check could not be completed: https://export.arxiv.org/api/query?id_list=1906.02530&max_results=1: HTTP Error 429: Unknown Error
- line 61: `1703.01365` — check could not be completed: https://export.arxiv.org/api/query?id_list=1703.01365&max_results=1: The read operation timed out
- line 66: `https://this-domain-does-not-resolve-citeaudit.invalid/report.pdf` — check could not be completed: https://this-domain-does-not-resolve-citeaudit.invalid/report.pdf

</details>