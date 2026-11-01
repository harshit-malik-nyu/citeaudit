# Provenance note

The files in this directory were **recovered from git history** (commit
`5dba50d`) after a later run destroyed them.

## What happened

A preprint run sampled zero papers — the HTTP client was pacing every host at
0.12s, and arXiv's API guidelines ask for roughly three seconds. Ignoring that
gets a client throttled until every query returns an empty feed.

The empty result was then written straight over this measurement: 1,247 checks
across 122 papers, replaced with zeros. Nothing warned. The run reported
"0 papers sampled" as though that were a finding.

## What changed

- `write_outputs` now raises `EmptyStudy` rather than writing an empty result.
- The runner isolates each study, names any that produced no data, and exits
  non-zero so a failed run cannot be read as a clean one.
- Pacing is per-host, with arXiv at 3s.
- Sampling failures log at ERROR and an empty feed is flagged as probable
  throttling.

Regression tests: `TestEmptyStudyGuard`, `TestHostPacing`.

## Caveat on these numbers

This run **predates** the author-name extraction fix, so its mismatch count
(11) is inflated — roughly seven of those were the tool falsely reporting a
single author name as a wrong-paper citation. The unverified rate is largely
unaffected, since mismatches are a small share of total failures, but treat the
mismatch figure as superseded.

Kept because a recovered measurement with a stated caveat is worth more than a
directory of zeros.
