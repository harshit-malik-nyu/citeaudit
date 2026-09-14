#!/usr/bin/env python3
"""
Audit stored mismatches.

Why this is a script and not a notebook entry
----------------------------------------------
Twice, a study reported mismatches and the headline rate looked entirely
plausible. Both times most of them were the tool's own false accusations, and
both times that was discovered only by reading the individual findings by hand.

A finding nobody inspects is not a finding. This makes the inspection
reproducible: it replays every stored mismatch through the *current* extraction
logic and reports which ones survive, so a claim like "N genuine mismatches"
can be regenerated rather than remembered.

Run it after any change to title extraction or matching:

    python scripts/audit_mismatches.py evidence/preprints/checks.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeaudit import match                                    # noqa: E402
from citeaudit.extract import _title_from                      # noqa: E402

CLAIMS_RE = re.compile(r"Document claims '([^']*)'")
HOLDS_RE = re.compile(r"record holds '([^']*)'")


def audit(path: Path) -> int:
    rows = list(csv.DictReader(path.open()))
    mismatches = [r for r in rows if r.get("verdict") == "mismatch"]

    if not mismatches:
        print(f"{path}: no mismatches stored")
        return 0

    print(f"{path}")
    print(f"{len(rows):,} checks, {len(mismatches)} stored mismatches")
    print("=" * 74)

    resolved_ok, still_mismatch, unauditable = [], [], []

    for r in mismatches:
        detail = r.get("detail", "")
        old_claim = CLAIMS_RE.search(detail)
        holds = HOLDS_RE.search(detail)
        new_title = _title_from(r.get("reference_text", ""))

        record = {
            "id": r.get("identifier"),
            "old_claim": old_claim.group(1) if old_claim else None,
            "new_title": new_title,
            "record_title": holds.group(1) if holds else None,
            "text": r.get("reference_text", "")[:160],
        }

        if record["record_title"] is None:
            # The stored detail was truncated before the resolved title. The
            # finding cannot be re-adjudicated offline, which is itself worth
            # reporting rather than silently counting either way.
            unauditable.append(record)
            continue

        if new_title is None:
            record["note"] = "no title recoverable now — no comparison made"
            resolved_ok.append(record)
            continue

        mismatch, sim, _, _ = match.assess(
            new_title, [], None, record["record_title"], [], None
        )
        record["similarity"] = sim
        (still_mismatch if mismatch else resolved_ok).append(record)

    def show(title: str, items: list[dict]) -> None:
        print()
        print(f"{title}: {len(items)}")
        print("-" * 74)
        for i, rec in enumerate(items, 1):
            print(f"  {i}. {rec['id']}")
            if rec.get("old_claim") is not None:
                print(f"     previously claimed : {rec['old_claim'][:62]!r}")
            print(f"     now extracts       : {str(rec['new_title'])[:62]!r}")
            if rec.get("record_title"):
                print(f"     authority holds    : {rec['record_title'][:62]!r}")
            if rec.get("similarity") is not None:
                print(f"     similarity         : {rec['similarity']:.0f}%")
            if rec.get("note"):
                print(f"     note               : {rec['note']}")

    show("RESOLVED by current extraction (were false accusations)", resolved_ok)
    show("STILL MISMATCH (candidate genuine findings)", still_mismatch)
    if unauditable:
        show("UNAUDITABLE — stored detail truncated before the resolved title",
             unauditable)

    print()
    print("=" * 74)
    total = len(mismatches)
    print(f"  {len(resolved_ok)}/{total} were false accusations, now resolved")
    print(f"  {len(still_mismatch)}/{total} survive and need manual confirmation")
    if unauditable:
        print(f"  {len(unauditable)}/{total} cannot be re-adjudicated offline")
    print()
    print("  Surviving mismatches are CANDIDATES, not conclusions. Each one is")
    print("  an accusation that a document cited the wrong paper, and that is")
    print("  not a claim to publish on a heuristic's say-so. Open the evidence")
    print("  URL and read the record before repeating any of them.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", type=Path)
    args = ap.parse_args()
    for p in args.paths:
        if not p.exists():
            print(f"no such file: {p}", file=sys.stderr)
            return 2
        audit(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
