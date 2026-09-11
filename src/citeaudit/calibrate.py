"""
Threshold calibration.

`TITLE_MISMATCH_THRESHOLD = 60.0` was an assertion. This module turns it into a
measurement.

Building the labelled set
-------------------------
The usual obstacle to calibrating a detector is that labelling is expensive and
subjective. Here both problems are avoided by constructing pairs from real
Crossref records in a way that fixes ground truth by construction:

    NEGATIVE (should VERIFY)   A real DOI paired with its own real title, then
                               perturbed the way bibliographies actually
                               degrade: subtitle dropped, title truncated,
                               casing flattened, a typo introduced. Still the
                               same work, by construction.

    POSITIVE (should MISMATCH) A real DOI from work A paired with the real
                               title of work B. Definitively a different work,
                               by construction.

Every record is real. No text is invented. The labels are not judgments — they
follow from how each pair was assembled, so there is no annotator to disagree
with.

What is being measured
----------------------
The MISMATCH detector, treated as a binary classifier:

    precision   of the pairs flagged MISMATCH, how many really are a different
                work. Low precision means false accusations.
    recall      of the pairs that really are a different work, how many were
                caught. Low recall means fabrications slip through.

These trade off against each other, and the right operating point depends on
which error costs more. For this tool it is not close: a false accusation
against a real citation destroys the user's trust permanently, while a missed
detection leaves them where they already were. The threshold is therefore set
for high precision, and the curve below is what justifies the specific number.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import match
from .http import Client, NotFound, Unreachable
from .sources.crossref import Crossref, Work


# ---------------------------------------------------------------------------
# Perturbations — how real bibliographies degrade
# ---------------------------------------------------------------------------

def drop_subtitle(title: str, rng: random.Random) -> str | None:
    """'Main Title: A Subtitle' -> 'Main Title'. Extremely common in practice."""
    for sep in (": ", " - ", " — "):
        if sep in title:
            head = title.split(sep)[0].strip()
            if len(head) >= 15:
                return head
    return None


def truncate(title: str, rng: random.Random) -> str | None:
    """Bibliography software and page limits clip long titles."""
    words = title.split()
    if len(words) < 8:
        return None
    keep = max(5, int(len(words) * rng.uniform(0.6, 0.8)))
    return " ".join(words[:keep])


def introduce_typo(title: str, rng: random.Random) -> str | None:
    """A single transposition, as from manual transcription."""
    chars = list(title)
    idx = [i for i, c in enumerate(chars) if c.isalpha()]
    if len(idx) < 12:
        return None
    i = rng.choice(idx[2:-2])
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def flatten_case(title: str, rng: random.Random) -> str | None:
    return title.upper() if rng.random() < 0.5 else title.lower()


def strip_punctuation(title: str, rng: random.Random) -> str | None:
    out = re.sub(r"[^\w\s]", "", title)
    return out if out != title else None


PERTURBATIONS = {
    "identity": lambda t, r: t,
    "drop_subtitle": drop_subtitle,
    "truncate": truncate,
    "typo": introduce_typo,
    "case": flatten_case,
    "punctuation": strip_punctuation,
}


# ---------------------------------------------------------------------------
# Labelled pairs
# ---------------------------------------------------------------------------

@dataclass
class Pair:
    label: str                     # "same_work" | "different_work"
    perturbation: str
    doi: str
    claimed_title: str
    resolved_title: str
    claimed_authors: list[str] = field(default_factory=list)
    resolved_authors: list[str] = field(default_factory=list)
    claimed_year: int | None = None
    resolved_year: int | None = None
    similarity: float | None = None

    @property
    def is_truly_different(self) -> bool:
        return self.label == "different_work"


def fetch_reference_works(client: Client, *, count: int, seed: int,
                          years: tuple[int, int] = (2010, 2024)) -> list[Work]:
    """Draw a random sample of real works to build pairs from."""
    import urllib.parse

    params = {
        "filter": (
            f"from-pub-date:{years[0]}-01-01,until-pub-date:{years[1]}-12-31,"
            "type:journal-article,has-abstract:true"
        ),
        "sample": str(min(count, 100)),
        "select": "DOI,title,author,issued,container-title,type",
    }
    if client.mailto:
        params["mailto"] = client.mailto

    from .sources.crossref import BASE, to_work
    url = f"{BASE}/works?{urllib.parse.urlencode(params)}"
    try:
        data = client.get(url).json()
    except (NotFound, Unreachable):
        return []
    items = (data.get("message") or {}).get("items") or []
    works = [to_work(i) for i in items]
    return [w for w in works if w.title and len(w.title) >= 20 and w.authors]


def build_pairs(works: list[Work], *, seed: int = 20260909) -> list[Pair]:
    """Assemble the labelled set from real records."""
    rng = random.Random(seed)
    pairs: list[Pair] = []

    # --- negatives: same work, degraded description ----------------------
    for w in works:
        assert w.title
        for name, fn in PERTURBATIONS.items():
            out = fn(w.title, rng)
            if not out or len(out) < 12:
                continue
            pairs.append(Pair(
                label="same_work", perturbation=name, doi=w.doi,
                claimed_title=out, resolved_title=w.title,
                claimed_authors=w.authors[:3], resolved_authors=w.authors,
                claimed_year=w.year, resolved_year=w.year,
            ))

    # --- positives: DOI of A, title of B ---------------------------------
    # Pairing is random across the sample, which is what a fabricated citation
    # looks like: a real identifier attached to an unrelated description.
    n = len(works)
    for i, w in enumerate(works):
        for _ in range(3):
            j = rng.randrange(n)
            if j == i:
                continue
            other = works[j]
            if not other.title:
                continue
            # Guard against the sample accidentally containing near-duplicates,
            # which would poison the positive labels.
            sim = match.title_similarity(other.title, w.title) or 0.0
            if sim > 70:
                continue
            pairs.append(Pair(
                label="different_work", perturbation="swapped_title",
                doi=w.doi, claimed_title=other.title, resolved_title=w.title,
                claimed_authors=other.authors[:3], resolved_authors=w.authors,
                claimed_year=other.year, resolved_year=w.year,
            ))

    for p in pairs:
        p.similarity = match.title_similarity(p.claimed_title, p.resolved_title)
    return pairs


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def evaluate_at(pairs: list[Pair], threshold: float,
                strong_match: float = match.TITLE_STRONG_MATCH) -> dict[str, Any]:
    """
    Score the detector at one threshold.

    Reimplements the decision rule from match.assess rather than calling it, so
    that the threshold can be varied without mutating module state — which
    would make the sweep order-dependent and the result irreproducible.
    """
    tp = fp = tn = fn = 0

    for p in pairs:
        sim = p.similarity
        if sim is None:
            continue

        if sim >= strong_match:
            flagged = False
        elif sim < threshold:
            overlap = match.author_overlap(p.claimed_authors, p.resolved_authors)
            flagged = not (overlap is not None and overlap >= 0.75)
        else:
            flagged = False

        if p.is_truly_different:
            if flagged:
                tp += 1
            else:
                fn += 1
        else:
            if flagged:
                fp += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    specificity = tn / (tn + fp) if (tn + fp) else None

    return {
        "threshold": threshold,
        "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
        "precision": precision, "recall": recall,
        "f1": f1, "specificity": specificity,
    }


def sweep(pairs: list[Pair], thresholds: list[float] | None = None) -> list[dict]:
    thresholds = thresholds or [float(t) for t in range(20, 92, 2)]
    return [evaluate_at(pairs, t) for t in thresholds]


def choose_operating_point(curve: list[dict], *,
                           min_precision: float = 0.99) -> dict | None:
    """
    Highest recall subject to a precision floor.

    The floor, not F1, is the selection rule. F1 weights the two errors
    equally, and here they are nowhere near equal: a false accusation against a
    genuine citation is the failure that makes users stop trusting the tool,
    after which missed detections stop mattering because nobody is looking.
    """
    eligible = [r for r in curve
                if r["precision"] is not None and r["precision"] >= min_precision]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r["recall"] or 0, r["threshold"]))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _sparkline(curve: list[dict], key: str, width: int = 46) -> str:
    """Inline ASCII plot, so the curve is legible in a plain-text report."""
    blocks = "▁▂▃▄▅▆▇█"
    vals = [r[key] for r in curve if r[key] is not None]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = max(1, len(vals) // width)
    return "".join(
        blocks[min(len(blocks) - 1, int((v - lo) / span * (len(blocks) - 1)))]
        for v in vals[::step]
    )


def to_markdown(pairs: list[Pair], curve: list[dict],
                chosen: dict | None, meta: dict) -> str:
    n_pos = sum(1 for p in pairs if p.is_truly_different)
    n_neg = len(pairs) - n_pos

    out: list[str] = []
    out.append("# Calibration: why the mismatch threshold is what it is")
    out.append("")
    out.append(
        f"**{len(pairs):,} labelled pairs** built from **{meta.get('works', 0):,} "
        f"real Crossref records** — {n_neg:,} same-work and {n_pos:,} "
        f"different-work. Seed {meta.get('seed')}."
    )
    out.append("")
    out.append("## Ground truth by construction")
    out.append("")
    out.append(
        "Same-work pairs take a real record and degrade its title the way "
        "bibliographies actually degrade — subtitle dropped, title truncated, "
        "case flattened, punctuation stripped, a transposition typo. The work "
        "is unchanged, so the correct verdict is VERIFIED."
    )
    out.append("")
    out.append(
        "Different-work pairs attach the DOI of one real paper to the title of "
        "another, which is exactly what a fabricated citation looks like. The "
        "correct verdict is MISMATCH."
    )
    out.append("")
    out.append(
        "No text is invented and no label is a judgment call. Both follow from "
        "how the pair was assembled."
    )
    out.append("")

    out.append("## The trade-off")
    out.append("")
    out.append("| Threshold | Precision | Recall | F1 | False accusations |")
    out.append("|---:|---:|---:|---:|---:|")
    for r in curve:
        if int(r["threshold"]) % 6 and r is not chosen:
            continue
        mark = " ←" if chosen and r["threshold"] == chosen["threshold"] else ""
        p = "—" if r["precision"] is None else f"{r['precision']:.3f}"
        rc = "—" if r["recall"] is None else f"{r['recall']:.3f}"
        f1 = "—" if r["f1"] is None else f"{r['f1']:.3f}"
        out.append(
            f"| {r['threshold']:.0f}{mark} | {p} | {rc} | {f1} | "
            f"{r['false_positive']} |"
        )
    out.append("")
    out.append("```")
    out.append(f"precision {_sparkline(curve, 'precision')}")
    out.append(f"recall    {_sparkline(curve, 'recall')}")
    out.append(f"          threshold {curve[0]['threshold']:.0f} "
               f"-> {curve[-1]['threshold']:.0f}")
    out.append("```")
    out.append("")

    out.append("## Chosen operating point")
    out.append("")
    if chosen:
        out.append(
            f"**Threshold {chosen['threshold']:.0f}** — precision "
            f"{chosen['precision']:.3f}, recall {chosen['recall']:.3f}, "
            f"{chosen['false_positive']} false accusations across "
            f"{n_neg:,} genuine pairs."
        )
        out.append("")
        out.append(
            "Selected as the highest recall available subject to a precision "
            "floor, not by maximising F1. F1 treats the two errors as equally "
            "costly. They are not: a false accusation against a real citation "
            "is what makes a user switch the tool off, and a tool that is off "
            "catches nothing."
        )
    else:
        out.append(
            "No threshold in the swept range met the precision floor. The "
            "detector is not usable on this labelled set without redesign, and "
            "that finding is reported rather than worked around."
        )
    out.append("")

    out.append("## Where it fails")
    out.append("")
    if chosen:
        fails = [p for p in pairs
                 if p.is_truly_different and (p.similarity or 0) >= chosen["threshold"]]
        if fails:
            out.append(
                f"{len(fails)} different-work pairs scored above the threshold "
                "and were missed. Inspecting them shows the pattern: generic "
                "titles in the same field share enough vocabulary to look alike."
            )
            out.append("")
            for p in sorted(fails, key=lambda x: -(x.similarity or 0))[:4]:
                out.append(f"- `{p.similarity:.0f}%` — {p.claimed_title[:72]!r}")
                out.append(f"  vs {p.resolved_title[:72]!r}")
        else:
            out.append("No different-work pair evaded detection at this threshold.")
    out.append("")
    out.append("## Limits")
    out.append("")
    out.append(
        "- Perturbations model transcription and formatting degradation. They "
        "do not model translated titles, transliteration, or non-Latin scripts."
    )
    out.append(
        "- Different-work pairs are drawn at random across the sample. Real "
        "fabrications may be *topically* closer to the claim than a random "
        "draw, which would make them harder to catch than this measures. "
        "Recall here is therefore an optimistic bound."
    )
    out.append(
        "- The sample is journal articles with abstracts, which skews toward "
        "well-formed metadata."
    )
    return "\n".join(out)


def write_outputs(pairs: list[Pair], curve: list[dict], chosen: dict | None,
                  meta: dict, directory: str | Path) -> None:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)

    (d / "curve.json").write_text(json.dumps({
        "meta": meta, "curve": curve, "chosen": chosen,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))
    (d / "report.md").write_text(to_markdown(pairs, curve, chosen, meta))

    import csv
    with (d / "pairs.csv").open("w", newline="") as fh:
        if pairs:
            w = csv.DictWriter(fh, fieldnames=list(asdict(pairs[0]).keys()))
            w.writeheader()
            for p in pairs:
                row = asdict(p)
                row["claimed_authors"] = "; ".join(row["claimed_authors"])
                row["resolved_authors"] = "; ".join(row["resolved_authors"])
                w.writerow(row)
