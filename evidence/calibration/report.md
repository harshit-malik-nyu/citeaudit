# Calibration: why the mismatch threshold is what it is

**684 labelled pairs** built from **88 real Crossref records** — 422 same-work and 262 different-work. Seed 20260909.

## Ground truth by construction

Same-work pairs take a real record and degrade its title the way bibliographies actually degrade — subtitle dropped, title truncated, case flattened, punctuation stripped, a transposition typo. The work is unchanged, so the correct verdict is VERIFIED.

Different-work pairs attach the DOI of one real paper to the title of another, which is exactly what a fabricated citation looks like. The correct verdict is MISMATCH.

No text is invented and no label is a judgment call. Both follow from how the pair was assembled.

## The trade-off

| Threshold | Precision | Recall | F1 | False accusations |
|---:|---:|---:|---:|---:|
| 24 | 1.000 | 0.038 | 0.074 | 0 |
| 30 | 1.000 | 0.080 | 0.148 | 0 |
| 36 | 1.000 | 0.218 | 0.357 | 0 |
| 42 | 1.000 | 0.603 | 0.752 | 0 |
| 48 | 1.000 | 0.947 | 0.973 | 0 |
| 54 | 1.000 | 1.000 | 1.000 | 0 |
| 60 | 1.000 | 1.000 | 1.000 | 0 |
| 66 | 1.000 | 1.000 | 1.000 | 0 |
| 72 | 1.000 | 1.000 | 1.000 | 0 |
| 78 | 1.000 | 1.000 | 1.000 | 0 |
| 84 | 1.000 | 1.000 | 1.000 | 0 |
| 90 ← | 1.000 | 1.000 | 1.000 | 0 |

```
precision ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
recall    ▁▁▁▁▁▁▁▁▂▂▃▅▆▆▇▇▇███████████████████
          threshold 20 -> 90
```

## Chosen operating point

**Threshold 90** — precision 1.000, recall 1.000, 0 false accusations across 422 genuine pairs.

Selected as the highest recall available subject to a precision floor, not by maximising F1. F1 treats the two errors as equally costly. They are not: a false accusation against a real citation is what makes a user switch the tool off, and a tool that is off catches nothing.

## Where it fails

No different-work pair evaded detection at this threshold.

## Limits

- Perturbations model transcription and formatting degradation. They do not model translated titles, transliteration, or non-Latin scripts.
- Different-work pairs are drawn at random across the sample. Real fabrications may be *topically* closer to the claim than a random draw, which would make them harder to catch than this measures. Recall here is therefore an optimistic bound.
- The sample is journal articles with abstracts, which skews toward well-formed metadata.