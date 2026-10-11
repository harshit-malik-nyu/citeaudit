# Which references deserve a reviewer’s attention?

**Recommendation:** Triage unresolved references and retain retrieval evidence; only confirmed complete text may support an absence verdict.

This is an independent analytical case study. No client engagement, deployment, stakeholder acceptance or realized financial outcome is asserted.

## Decision and alternatives

Consider manual reference checking; identifier lookup; staged citation and quote triage. The decision owner is the operator responsible for the workflow. An analyst owns evidence quality; the workflow owner owns review capacity and the acceptable error cost. These are proposed responsibilities, not named stakeholders who approved the work.

## Evidence and correction

Binary cache now preserves source archives. Extracted LaTeX is an excerpt, not proof of complete coverage. The action installs its selected revision.

Frozen preprint checks and binary/partial-text fixtures replace dependence on new live API calls. `analysis/output/manifest.json` identifies inputs, their hashes and observation counts. `analysis/questions.sql` exposes the aggregation and denominators; `analysis/build.py` rebuilds it locally. The source snapshot is the source of truth for descriptive claims. Earlier notebooks, figures and evidence JSON describe their original run unless explicitly regenerated.

## Economics and sensitivity

The current [executive decision summary](../analysis/output/decision_lab/executive-summary.md) compares **Manual reference audit**, **Metadata audit plus human exceptions**, and **Automatic rejection on missing quotation**. The model separates Exception resolution: 35% at 12 minutes, Read and resolve references, Rejection appeal: 8% at 25 minutes, Resolution requests.

The [assumption register](../analysis/decision_spec.json) labels all quantities, unit costs, incident rates and risk ceilings as planning assumptions. A 27-scenario grid varies volume, activity costs and incident risk. Risk and reviewer-capacity gates can veto the cheapest alternative. Expected-loss scenarios, salaried capacity and actual cash outlay are reported separately. The older `business_case.json` is a simple illustrative baseline, superseded for option selection by this richer model.

**Decision reversal:** If automation increases false refutations or exception resolution erases saved review effort, retain manual review for that source class.

## Product measurement

Primary metric: **Verified or explicitly unresolved references / submitted references.**

Guardrails: False refutations must be zero in offline partial-text fixtures; cache must preserve bytes.

A terminal result includes verdict, authority and evidence; unavailable sources remain inconclusive. Instrument each workflow with `started`, then one `completed` or `failed` event. Sessions still open remain incomplete in the denominator. `analysis/product.py` rejects duplicated events, invalid transitions, negative or nonfinite elapsed time, mixed evidence sources and unexpected fields. Only opaque session/event IDs, event type, elapsed milliseconds and evidence source are permitted. Do not log names, prompts, documents or case data.

The checked-in `events.synthetic.jsonl` is a small contract fixture: one completed, one failed and one incomplete session. Its completion rate is a QA expectation, not usage evidence. Actual adoption remains unmeasured. For an offline package, replaying known cases and validating these contracts is the achievable substitute for waiting on real users.

## Experiment and acceptance

For a future product comparison, randomly assign at the independent case or user level before exposure, keep assignment stable, and analyze intention-to-treat. Use an independent calibration split where thresholds are learned. Cluster repeated observations by household, paper, contract or user as appropriate. Fix the primary outcome and stopping point before inspection. Retain failures and attrition; do not remove hard cases after assignment.

Illustrative planning: a 50% baseline completion rate and a 5 percentage-point minimum effect require approximately 1,570 independent units per arm at two-sided 5% significance and 80% power using the conservative normal approximation. This is a design example, not an executed experiment or promised detectable effect under clustering. Multiply by the justified design effect for clustered units. A successful QA fixture does not substitute for this causal experiment.

For the delivered offline version, acceptance means all available offline regressions pass, evidence queries reconcile to input counts, deterministic rebuilds reproduce the same output hashes, and unsupported claims remain explicitly scoped. A statistical certificate additionally requires its documented iid, fixed-policy and calibration assumptions. If these fail, report inconclusive or infeasible rather than silently relaxing the threshold.

## Interview walkthrough

Explain the business decision first, then trace one result through the SQL to its source. Demonstrate the failure case that motivated the correction. Change an economic input and describe the decision boundary. Close by separating measured retrospective evidence, simulated validation and what remains unknown. This demonstrates data, business and product analysis without implying experience or outcomes the repository cannot establish.

## Product analysis and experiment decision

The decision laboratory supplies 2,560 explicitly synthetic assigned units across eight weekly cohorts and two project-specific segments. Its stage funnel uses all assigned units, including non-starters. D28 retention excludes immature cohorts; it never treats unobserved returns as failures. Segment results are exploratory.

**Stages:** document_opened → audit_completed → qualified_report_exported. **Guardrail incident:** false refutation in report. **Unit:** editor account; papers grouped within editor. **Repeat-use interpretation:** editor audits another eligible document.

The synthetic A/B decision uses intention-to-treat activation, an incident-rate guardrail, Wilson/Newcombe uncertainty, allocation diagnostics and a fixed-horizon sample-size plan. A primary metric win is insufficient when the guardrail fails. There is no real-world causal or adoption claim. Confirmatory rollout would require a prespecified population, meaningful minimum effect, acceptable incident margin and an appropriate cluster design; these are defined as requirements, not fabricated approvals.

**Prioritized next decisions:**

1. Keep partial-text and unreachable-source outcomes separate from conclusive failures.
2. Prioritize exception explanations and report export before adding more source integrations.
3. Evaluate paper-level false refutations alongside time to a usable report.

The workflow-activation experiment is an adoption-mechanics study; it does not replace the domain quality metric above. The synthetic fixture deliberately includes a harmful treatment segment. Its hold result is a validation success, not evidence that a real product failed.
