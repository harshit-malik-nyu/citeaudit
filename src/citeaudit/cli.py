"""
Command-line interface.

Exit codes are the contract with CI:

    0   no failures (inconclusive checks do not fail a build)
    1   at least one citation did not hold up
    2   the tool itself could not run

Inconclusive results deliberately do not fail a build by default. A checker
that goes red because an API had a bad afternoon gets switched off within a
week, and a switched-off check protects nobody. `--strict` is available for
release gates where that trade-off runs the other way.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .extract import UnsupportedDocument
from .http import Client
from .models import Report
from .report import to_html, to_json, to_markdown, to_terminal
from .verify import Verifier

log = logging.getLogger("citeaudit")

EXIT_OK, EXIT_FAILURES, EXIT_ERROR = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="citeaudit",
        description="Verify that the citations in a document actually exist.",
        epilog="Exit 0 = clean, 1 = failures found, 2 = tool error.",
    )
    p.add_argument("paths", nargs="+", metavar="FILE",
                   help="documents to check (.md .txt .html .pdf .docx)")
    p.add_argument("--format", choices=["terminal", "json", "markdown", "html"],
                   default="terminal")
    p.add_argument("-o", "--output", metavar="PATH",
                   help="write to a file instead of stdout")
    p.add_argument("--show-verified", action="store_true",
                   help="include passing citations in terminal output")
    p.add_argument("--no-urls", action="store_true",
                   help="skip liveness checks on plain web links")
    p.add_argument("--no-search", action="store_true",
                   help="do not search for references that carry no identifier")
    p.add_argument("--check-quotes", action="store_true",
                   help="also verify quoted passages against open source text "
                        "where available (slower; coverage is limited by "
                        "paywalls)")
    p.add_argument("--strict", action="store_true",
                   help="also fail on inconclusive checks")
    p.add_argument("--fail-under", type=float, metavar="PCT", default=None,
                   help="fail if integrity score falls below this percentage")
    p.add_argument("--cache-dir", default=".citeaudit-cache",
                   help="response cache location (empty string disables)")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--mailto", default=os.environ.get("CITEAUDIT_MAILTO"),
                   help="contact address sent to scholarly APIs, per their "
                        "polite-pool conventions")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("-q", "--quiet", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--version", action="version", version=f"citeaudit {__version__}")
    return p


def merge(reports: list[Report]) -> Report:
    """Combine per-file reports into one."""
    if len(reports) == 1:
        return reports[0]
    merged = Report(
        document=f"{len(reports)} documents",
        findings=[f for r in reports for f in r.findings],
        tool_version=__version__,
    )
    return merged


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else
              (logging.ERROR if args.quiet else logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
    )

    client = Client(
        version=__version__,
        mailto=args.mailto,
        cache_dir=None if (args.no_cache or not args.cache_dir) else args.cache_dir,
        use_cache=not args.no_cache,
        timeout=args.timeout,
    )
    verifier = Verifier(
        client,
        check_urls=not args.no_urls,
        search_unidentified=not args.no_search,
        check_quotes=args.check_quotes,
        workers=args.workers,
    )

    reports: list[Report] = []
    for path in args.paths:
        try:
            reports.append(verifier.verify_file(path))
        except FileNotFoundError:
            print(f"citeaudit: no such file: {path}", file=sys.stderr)
            return EXIT_ERROR
        except UnsupportedDocument as exc:
            print(f"citeaudit: {exc}", file=sys.stderr)
            return EXIT_ERROR

    report = merge(reports)

    if args.format == "json":
        text = to_json(report)
    elif args.format == "markdown":
        text = to_markdown(report)
    elif args.format == "html":
        text = to_html(report)
    else:
        text = to_terminal(
            report,
            colour=sys.stdout.isatty() and not args.output,
            show_verified=args.show_verified,
        )

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        if not args.quiet:
            print(f"wrote {args.output}")
    else:
        print(text)

    # GitHub Actions step summary, when running in CI.
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write(to_markdown(report) + "\n")
        except OSError:
            pass

    # -- exit code ---------------------------------------------------------
    failed = len(report.failures) > 0 or len(report.quote_failures) > 0
    if args.strict and report.inconclusive:
        failed = True
    if args.fail_under is not None:
        score = report.integrity_score
        if score is not None and score * 100 < args.fail_under:
            failed = True

    if not args.quiet and client.stats["failures"]:
        print(
            f"\nnote: {client.stats['failures']} request(s) could not be "
            "completed; those citations are reported as inconclusive rather "
            "than as failures.",
            file=sys.stderr,
        )

    return EXIT_FAILURES if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
