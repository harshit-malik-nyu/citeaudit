#!/usr/bin/env python3
"""
Run the base-rate and calibration studies against live authorities.

Executed by CI. Writes to evidence/baserate/ and evidence/calibration/, which
are committed so the numbers in the README can be traced to the run that
produced them.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from citeaudit import __version__
from citeaudit.calibrate import (
    build_pairs, choose_operating_point, fetch_reference_works, sweep,
    write_outputs as write_calibration,
)
from citeaudit.corpus import run_study, summarise, write_outputs as write_baserate
from citeaudit.http import Client

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--study",
                choices=["baserate", "calibration", "preprints", "all"],
                default="all")
    ap.add_argument("--per-year", type=int, default=40)
    ap.add_argument("--max-refs", type=int, default=5)
    ap.add_argument("--max-checks", type=int, default=4000)
    ap.add_argument("--calibration-works", type=int, default=260)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--mailto", default="citeaudit-ci@users.noreply.github.com")
    ap.add_argument("--preprints-per-category", type=int, default=10)
    ap.add_argument("--preprint-max-checks", type=int, default=900)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    client = Client(version=__version__, mailto=args.mailto,
                    cache_dir=str(ROOT / ".study-cache"), timeout=30)

    if args.study in ("baserate", "all"):
        print("=" * 70)
        print("BASE RATE STUDY")
        print("=" * 70)
        years = [2014, 2017, 2020, 2022, 2023, 2024]
        result = run_study(
            client=client, years=years, per_year=args.per_year,
            max_refs_per_work=args.max_refs, seed=args.seed,
            workers=args.workers, max_checks=args.max_checks,
        )
        summary = summarise(result)
        write_baserate(result, summary, ROOT / "evidence" / "baserate")

        dsc = summary.get("described_mode") or {}
        idt = summary.get("identified_mode") or {}
        print(f"\nsource works      : {summary['method']['source_works']:,}")
        print(f"total checks      : {summary['method']['total_checks']:,}")
        if idt.get("false_positive_rate") is not None:
            print(f"identified FP rate: {idt['false_positive_rate']:.2%}")
        if dsc.get("false_positive_rate") is not None:
            lo, hi = dsc["false_positive_ci95"]
            print(f"described FP rate : {dsc['false_positive_rate']:.2%} "
                  f"(95% CI {lo:.2%}-{hi:.2%})")
        print(f"fallback rescues  : {summary.get('fallback_rescues', 0):,}")
        print(f"http requests     : {client.stats['requests']:,}")

    if args.study in ("calibration", "all"):
        print()
        print("=" * 70)
        print("CALIBRATION STUDY")
        print("=" * 70)
        works = fetch_reference_works(client, count=args.calibration_works,
                                      seed=args.seed)
        if not works:
            print("could not fetch reference works; skipping calibration",
                  file=sys.stderr)
            return 1

        pairs = build_pairs(works, seed=args.seed)
        curve = sweep(pairs)
        chosen = choose_operating_point(curve, min_precision=0.99)
        meta = {"works": len(works), "seed": args.seed, "pairs": len(pairs),
                "min_precision": 0.99}
        write_calibration(pairs, curve, chosen, meta,
                          ROOT / "evidence" / "calibration")

        n_pos = sum(1 for p in pairs if p.is_truly_different)
        print(f"\nreference works   : {len(works):,}")
        print(f"labelled pairs    : {len(pairs):,} "
              f"({len(pairs) - n_pos:,} same / {n_pos:,} different)")
        if chosen:
            print(f"chosen threshold  : {chosen['threshold']:.0f}")
            print(f"  precision       : {chosen['precision']:.3f}")
            print(f"  recall          : {chosen['recall']:.3f}")
            print(f"  false accusations: {chosen['false_positive']}")
        else:
            print("no threshold met the precision floor")

    if args.study in ("preprints", "all"):
        print()
        print("=" * 70)
        print("PREPRINT CORPUS STUDY")
        print("=" * 70)
        from citeaudit import preprints

        study = preprints.run(
            client,
            categories=["cs.LG", "econ.GN", "q-bio.QM", "stat.AP", "physics.soc-ph"],
            per_category=args.preprints_per_category,
            max_checks=args.preprint_max_checks,
            workers=args.workers,
        )
        psum = preprints.summarise(study)
        preprints.write_outputs(study, psum, ROOT / "evidence" / "preprints")

        o = psum["overall"]
        print(f"\npapers sampled     : {psum['method']['papers_sampled']:,}")
        print(f"with bibliography  : {psum['method']['papers_with_bibliography']:,}")
        print(f"references checked : {o['checks']:,}")
        print(f"conclusive         : {o['conclusive']:,}")
        if o["unverified_rate"] is not None:
            lo, hi = o["unverified_ci95"]
            print(f"unverified rate    : {o['unverified_rate']:.2%} "
                  f"(95% CI {lo:.2%}-{hi:.2%})")
        print(f"http requests      : {client.stats['requests']:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
