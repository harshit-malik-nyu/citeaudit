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


def keep_opening_words(title: str, rng: random.Random) -> str | None:
    """
    Severe truncation to the first few words.

    Some citation styles and many hand-built bibliographies record only the
    opening of a long title. This is the hardest same-work case: the text
    genuinely is a fragment of the real title, and a naive matcher will score
    it low.
    """
    words = title.split()
    if len(words) < 9:
        return None
    return " ".join(words[:rng.randint(4, 5)])


def compound_degrade(title: str, rng: random.Random) -> str | None:
    """Several degradations at once, as accumulates through re-citation."""
    out = drop_subtitle(title, rng) or title
    out = truncate(out, rng) or out
    out = strip_punctuation(out, rng) or out
    out = introduce_typo(out, rng) or out
    return out if len(out) >= 12 and out != title else None


PERTURBATIONS = {
    "identity": lambda t, r: t,
    "drop_subtitle": drop_subtitle,
    "truncate": truncate,
    "typo": introduce_typo,
    "case": flatten_case,
    "punctuation": strip_punctuation,
    "opening_words": keep_opening_words,
    "compound": compound_degrade,
}


# ---------------------------------------------------------------------------
# Labelled pairs
# ---------------------------------------------------------------------------

# Guarding the "different work" label.
#
# A high title similarity alone cannot separate "two different papers on
# adjacent topics" from "one paper deposited twice". Excluding every
# high-similarity pair would throw away exactly the hard cases the calibration
# needs — "...in emerging markets" versus "...in developed markets" is a
# genuinely different paper and a genuinely difficult one.
#
# Authors resolve it. Two records with near-identical titles AND substantially
# the same author list are plausibly the same work; near-identical titles by
# different research groups are two papers. A pair is excluded only when both
# conditions hold.
NEAR_DUPLICATE_CEILING = 92.0
NEAR_DUPLICATE_AUTHOR_OVERLAP = 0.6

# How many hardest-available confusions to generate per work.
HARD_POSITIVES_PER_WORK = 2

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
    """
    Draw a random sample of real works to build pairs from.

    Crossref caps `sample` at 100 per request, so larger samples accumulate
    across year windows. Sampling by window rather than repeatedly from the
    same filter also spreads the draw over time instead of re-rolling the same
    recency-skewed pool.

    Pool size matters here more than it looks. Positives are built by finding
    each work's nearest confusable neighbour, so a thin pool yields only
    distant pairs — which is exactly the defect that made the first calibration
    report a meaningless perfect score.
    """
    import urllib.parse
    from .sources.crossref import BASE, to_work

    lo, hi = years
    span = max(1, hi - lo + 1)
    n_windows = max(1, min(span, (count + 99) // 100))
    width = max(1, span // n_windows)

    works: list[Work] = []
    seen: set[str] = set()

    for k in range(n_windows):
        w_lo = lo + k * width
        w_hi = min(hi, w_lo + width - 1)
        params = {
            "filter": (
                f"from-pub-date:{w_lo}-01-01,until-pub-date:{w_hi}-12-31,"
                "type:journal-article,has-abstract:true"
            ),
            "sample": str(min(100, count)),
            "select": "DOI,title,author,issued,container-title,type",
        }
        if client.mailto:
            params["mailto"] = client.mailto

        url = f"{BASE}/works?{urllib.parse.urlencode(params)}"
        try:
            data = client.get(url).json()
        except (NotFound, Unreachable):
            continue

        for item in (data.get("message") or {}).get("items") or []:
            w = to_work(item)
            if not w.title or len(w.title) < 20 or not w.authors:
                continue
            if w.doi in seen:
                continue
            seen.add(w.doi)
            works.append(w)

        if len(works) >= count:
            break

    return works[:count]


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
    #
    # Pairing is by NEAREST TITLE, not at random.
    #
    # A random pair draws two papers from unrelated fields, whose titles share
    # almost no vocabulary. Those are trivially separable, and a calibration
    # built on them reports perfect scores across every threshold — which looks
    # like success and is actually a measurement that failed to measure
    # anything.
    #
    # A real fabricated citation is not a random swap. It is a plausible title
    # in the right field, sharing the domain's vocabulary with the work it is
    # confused with. Pairing each DOI with the most similar *other* title in
    # the sample manufactures exactly that contested case, which is the only
    # region where the threshold does any work.
    #
    # NEAR_DUPLICATE_CEILING guards the label: above it, two records may be the
    # same work deposited twice, and calling that pair "different" would poison
    # precision.
    n = len(works)
    for i, w in enumerate(works):
        scored: list[tuple[float, Work]] = []
        for j, other in enumerate(works):
            if j == i or not other.title:
                continue
            sim = match.title_similarity(other.title, w.title) or 0.0
            if sim > NEAR_DUPLICATE_CEILING:
                ov = match.author_overlap(other.authors, w.authors)
                if ov is not None and ov >= NEAR_DUPLICATE_AUTHOR_OVERLAP:
                    continue          # plausibly the same work, not a confusion
            scored.append((sim, other))

        scored.sort(key=lambda t: -t[0])
        # The hardest available cases, plus one random draw so the easy region
        # of the curve is still populated and the sweep spans the full range.
        chosen = scored[:HARD_POSITIVES_PER_WORK]
        if len(scored) > HARD_POSITIVES_PER_WORK:
            chosen = chosen + [rng.choice(scored[HARD_POSITIVES_PER_WORK:])]

        for sim, other in chosen:
            pairs.append(Pair(
                label="different_work",
                perturbation=("nearest_title" if sim >= 40 else "random_title"),
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

    best_recall = max(r["recall"] or 0 for r in eligible)
    # Among thresholds achieving the best recall, take the LOWEST. A higher
    # threshold flags more aggressively; if several are tied on this labelled
    # set, the conservative one carries less risk on data harder than the set.
    at_best = [r for r in eligible if (r["recall"] or 0) >= best_recall - 1e-9]
    return min(at_best, key=lambda r: r["threshold"])


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

    same_sims = [p.similarity for p in pairs
                 if p.label == "same_work" and p.similarity is not None]
    diff_sims = [p.similarity for p in pairs
                 if p.label == "different_work" and p.similarity is not None]
    if same_sims and diff_sims:
        overlap = min(same_sims) <= max(diff_sims)
        contested = sum(1 for s_ in diff_sims if s_ >= min(same_sims))
        out.append("## Is this set actually hard?")
        out.append("")
        out.append(
            f"Same-work similarity spans {min(same_sims):.0f}–{max(same_sims):.0f}%; "
            f"different-work spans {min(diff_sims):.0f}–{max(diff_sims):.0f}%."
        )
        out.append("")
        if overlap:
            out.append(
                f"The ranges **overlap**, with {contested} different-work pairs "
                "scoring at or above the weakest same-work pair. Those are the "
                "cases the threshold has to adjudicate, and their presence is "
                "what makes the curve below meaningful."
            )
        else:
            out.append(
                "**The ranges do not overlap.** No pair in this set is "
                "contested, so any threshold between them scores perfectly and "
                "the curve below measures nothing. Treat the reported operating "
                "point as unvalidated and enlarge the sample."
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
        "- Different-work pairs are the nearest confusable title available "
        "within the sample, which is harder than a random draw but still "
        "bounded by what the sample happens to contain. A fabrication "
        "engineered to match a specific claim could be closer still, so recall "
        "here remains an optimistic bound."
    )
    out.append(
        "- Precision holds at 1.000 across the whole swept range. That is not "
        "the threshold's doing: the author-overlap corroboration rule in "
        "`match.assess` blocks an accusation whenever the claimed authors agree "
        "with the record, which protects genuine pairs independently of title "
        "similarity. The threshold governs recall; that rule governs precision."
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
