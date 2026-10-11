# Reduce reference-review work without turning missing text into a refutation

Use Citeaudit to prioritize editorial review, retaining inconclusive verdicts. The product objective is a usable, correctly qualified report, not maximum rejection rate.

**Observed evidence:** The frozen preprint checks retain references clustered within papers. Partial retrieved LaTeX is explicitly an excerpt; absent text cannot establish fabrication. Nine live API tests passed during publication.

**Decision owner:** Editorial quality lead (proposed role, not a client).

**Base planning case:** Metadata audit plus human exceptions. This is conditional on the assumptions, not deployment approval.

| Alternative | Economic cost | Cash outlay | Reviewer hours | Passes risk and capacity |
|---|---:|---:|---:|---|
| Manual reference audit | $50,850 | $0 | 900.0 | False |
| Metadata audit plus human exceptions | $17,070 | $4,620 | 210.0 | True |
| Automatic rejection on missing quotation | $19,370 | $2,620 | 100.0 | False |

Economic cost includes valued staff capacity and scenario incident losses. Cash outlay excludes salaried capacity and contingent losses. These are not realized savings.

**Sensitivity across 27 equally enumerated scenarios:** Metadata audit plus human exceptions: 18, NO FEASIBLE OPTION: 9. Grid counts are not probabilities.

**Synthetic product experiment:** HOLD. Primary effect 3.6%; 95% interval [-0.3%, 7.4%]. Guardrail effect 0.8%; interval [0.1%, 1.6%]. These numbers test the decision logic, not product performance.

**Priority order:**

1. Keep partial-text and unreachable-source outcomes separate from conclusive failures.
2. Prioritize exception explanations and report export before adding more source integrations.
3. Evaluate paper-level false refutations alongside time to a usable report.

**What would reverse the recommendation:** If automation increases false refutations or exception resolution erases saved review effort, retain manual review for that source class.

**Remaining uncertainty:** Synthetic author journeys do not establish adoption; metadata agreement does not prove a paper supports a claim.
