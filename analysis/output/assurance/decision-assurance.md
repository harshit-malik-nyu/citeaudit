# Decision assurance: citeaudit

Use Citeaudit to prioritize editorial review, retaining inconclusive verdicts. The product objective is a usable, correctly qualified report, not maximum rejection rate.

**Evidence:** The frozen preprint checks retain references clustered within papers. Partial retrieved LaTeX is explicitly an excerpt; absent text cannot establish fabrication. Nine live API tests passed during publication.

**Uncertainty:** Synthetic author journeys do not establish adoption; metadata agreement does not prove a paper supports a claim.

## Robustness of the assumed business case

| Alternative | Feasible grid cases / 27 | Worst regret when feasible | Maximum volume at fixed review capacity |
|---|---:|---:|---:|
| Manual reference audit | 3 | $24,097.50 | 2666 |
| Metadata audit plus human exceptions | 18 | $0.00 | 11428 |
| Automatic rejection on missing quotation | 0 | No feasible case | 24000 |

**Robust minimax choice:** None. No option is feasible across the entire stress grid.

Finite assumed grid, not a probability distribution or protection outside the grid. Conditional regret never overrides feasibility. Null robust option means no unconditional recommendation. Cost regret is relative to the cheapest feasible option in that same scenario. Failure counts can overlap.

## Missing-outcome sensitivity

| Outcomes masked per arm | Primary effect bounds | Incident effect bounds | Every completion clears margins? |
|---|---:|---:|---|
| 0% | [3.6%, 3.6%] | [0.8%, 0.8%] | False |
| 5% | [-2.0%, 8.0%] | [-4.1%, 5.9%] | False |
| 10% | [-6.6%, 13.4%] | [-9.1%, 10.9%] | False |
| 20% | [-16.3%, 23.7%] | [-19.1%, 20.9%] | False |

These are identification bounds on deliberately masked synthetic outcomes, not confidence intervals or measured missingness. Failures and non-starters remain in the assigned denominator. Passing this sensitivity check would still require statistical and domain-quality gates.

## Domain measurement contract

**Decision:** Route citation problems to useful author review without treating incomplete retrieval as contradiction.

**Primary outcome:** Confirmed actionable citation issues per reviewed paper, with reviewer minutes per confirmed issue.

**Denominator:** All eligible papers and all attempted references, including retrieval failures; report reference coverage separately.

**Independent unit:** Paper; references within a paper share authors, topics and retrieval sources.

**Quality guardrail:** False refutation rate and unresolved-reference rate, with adjudicated labels separate from metadata matches.

**Minimum required data:** Paper/reference IDs, retrieval completeness, source hash, verdict, adjudication status, reviewer time and resolved/unresolved outcome.

**Missingness and failure handling:** Failed retrieval and partial excerpts are unresolved, not clean citations or refutations. Keep them in coverage reporting.

**Release rule:** Require sufficiently bounded false refutation and useful issue yield before expanding automatic decisions; metadata agreement alone never establishes claim support.

**Reversal trigger:** Rising unresolved coverage or false refutations makes automatic rejection inappropriate; return to exception review.

## Interview defense

**Why is a missing quote not enough?**

An excerpt may omit the relevant passage. Absence becomes meaningful only under adequate retrieval and an appropriate comparison.

**What would adoption tell us?**

Repeat use shows workflow engagement. It does not show that citation verdicts are correct, so I measure adjudicated quality separately.

## Implementation handoff

1. Freeze the eligible population, denominator, outcome horizon and proposed decision owner before comparison.
2. Reconcile assignment and outcome records at the independence unit; classify missingness without deleting cases.
3. Estimate the domain outcome and its uncertainty separately from activation. Apply risk and capacity vetoes before comparing costs.
4. Record approve, hold, or reverse with the evidence version and violated gate. An unmeasured required domain gate means HOLD.

The supplied cluster-budget grid is a planning sensitivity check with assumed ICC. It is not an estimate from real clusters and does not guarantee joint power. No stakeholder approval or real experiment is asserted.
