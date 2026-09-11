# Calibration: why the mismatch threshold is what it is

**2,493 labelled pairs** built from **260 real Crossref records** — 1,713 same-work and 780 different-work. Seed 20260909.

## Ground truth by construction

Same-work pairs take a real record and degrade its title the way bibliographies actually degrade — subtitle dropped, title truncated, case flattened, punctuation stripped, a transposition typo. The work is unchanged, so the correct verdict is VERIFIED.

Different-work pairs attach the DOI of one real paper to the title of another, which is exactly what a fabricated citation looks like. The correct verdict is MISMATCH.

No text is invented and no label is a judgment call. Both follow from how the pair was assembled.

## Is this set actually hard?

Same-work similarity spans 56–100%; different-work spans 0–63%.

The ranges **overlap**, with 16 different-work pairs scoring at or above the weakest same-work pair. Those are the cases the threshold has to adjudicate, and their presence is what makes the curve below meaningful.

## The trade-off

| Threshold | Precision | Recall | F1 | False accusations |
|---:|---:|---:|---:|---:|
| 24 | 1.000 | 0.017 | 0.033 | 0 |
| 30 | 1.000 | 0.037 | 0.072 | 0 |
| 36 | 1.000 | 0.106 | 0.192 | 0 |
| 42 | 1.000 | 0.258 | 0.410 | 0 |
| 48 | 1.000 | 0.518 | 0.682 | 0 |
| 54 | 1.000 | 0.910 | 0.953 | 0 |
| 60 | 1.000 | 0.992 | 0.996 | 0 |
| 64 ← | 1.000 | 1.000 | 1.000 | 0 |
| 66 | 1.000 | 1.000 | 1.000 | 0 |
| 72 | 1.000 | 1.000 | 1.000 | 0 |
| 78 | 1.000 | 1.000 | 1.000 | 0 |
| 84 | 1.000 | 1.000 | 1.000 | 0 |
| 90 | 1.000 | 1.000 | 1.000 | 0 |

```
precision ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
recall    ▁▁▁▁▁▁▁▁▁▁▂▂▃▃▄▅▆▇▇▇▇▇██████████████
          threshold 20 -> 90
```

## Chosen operating point

**Threshold 64** — precision 1.000, recall 1.000, 0 false accusations across 1,713 genuine pairs.

Selected as the highest recall available subject to a precision floor, not by maximising F1. F1 treats the two errors as equally costly. They are not: a false accusation against a real citation is what makes a user switch the tool off, and a tool that is off catches nothing.

## Where it fails

No different-work pair evaded detection at this threshold.

## Limits

- Perturbations model transcription and formatting degradation. They do not model translated titles, transliteration, or non-Latin scripts.
- Different-work pairs are the nearest confusable title available within the sample, which is harder than a random draw but still bounded by what the sample happens to contain. A fabrication engineered to match a specific claim could be closer still, so recall here remains an optimistic bound.
- Precision holds at 1.000 across the whole swept range. That is not the threshold's doing: the author-overlap corroboration rule in `match.assess` blocks an accusation whenever the claimed authors agree with the record, which protects genuine pairs independently of title similarity. The threshold governs recall; that rule governs precision.
- The sample is journal articles with abstracts, which skews toward well-formed metadata.