# An unavailable authority is not a negative result

**Decision:** preserve an incomplete second lookup as inconclusive. Retain the
Crossref miss in the explanation; do not claim OpenAlex returned a negative
when it was unavailable or never consulted.

| Primary outcome | Secondary state | Citation verdict | Counted as failure? |
|---|---|---|---|
| Crossref did not match | OpenAlex unavailable | Unreachable | No |
| Crossref did not match | Fallback disabled | Unverifiable | No |
| Crossref did not match | Completed negative OpenAlex lookup | Not found in checked indexes | Yes, as a lookup finding—not proof of fabrication |

The same distinction applies to DOI resolution and bibliographic title search.
No extra network request or paid service is introduced by this correction.

## Why the denominator matters

A synthetic report with one verified citation and two inconclusive checks has
100% integrity among conclusive checks, but only 33.33% check coverage. Across
all three citations, the possible pass share ranges from 33.33% to 100% if the
inconclusive checks eventually fail or pass. These are identification bounds on
check outcomes, not confidence intervals or factual-truth probabilities.
An empty document has no denominator; both coverage and bounds are null.

JSON summaries now expose `check_coverage`, `all_citation_pass_share_bounds`
and the interpretation beside the existing `integrity_score`. A downstream
reviewer must not interpret a perfect score on the completed subset as complete
document verification. These additive fields do not certify the sources' claims.

## Business and product handling

An unavailable source routes to retry or manual review, not an accusation.
Disabled fallback is an explicitly incomplete workflow. Completed negative
lookups remain review findings because index coverage is incomplete. Neither
successful HTTP response nor matching bibliographic metadata establishes that
a source supports the surrounding substantive claim.

Existing failure-based exit behavior does not automatically block a run with only
inconclusive findings. Consumers that require complete checks must inspect
coverage and inconclusive counts; no stakeholder approval threshold is invented.
Historical evidence files are not silently rewritten as if these checks had run
against their original services again.

## Acceptance and reproduction

The regression tests exercise DOI and bibliography routes under outage, disabled
fallback and completed-miss states. They verify which services were called,
verdicts, failure counts and conclusive denominators. Aggregation tests cover
partial coverage, all-inconclusive and empty reports. All fixtures are synthetic.

```sh
python -m pytest -q tests/test_fallback_evidence.py
python analysis/fallback_review.py
```

The JSON companion records deterministic summary examples and source hashes.
The report generator needs only the standard library. Routing tests need the
repository's development dependencies and use no live external services.
