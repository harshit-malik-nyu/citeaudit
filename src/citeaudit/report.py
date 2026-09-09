"""
Report rendering.

Four output formats, one principle: every failure must be independently
checkable by the reader. Each finding carries the evidence URL that produced
the verdict, so a reader who distrusts this tool can confirm or refute any line
of it without running it.

That matters more than it sounds. A tool that says "this citation is fabricated"
and cannot show its working is asking for the same unearned trust that produced
the problem.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from .models import Finding, Report, Verdict

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

SYMBOL = {
    Verdict.VERIFIED: "OK  ",
    Verdict.MISMATCH: "MISM",
    Verdict.NOT_FOUND: "FAIL",
    Verdict.MALFORMED: "BAD ",
    Verdict.UNREACHABLE: "??  ",
    Verdict.UNVERIFIABLE: "--  ",
}

COLOUR = {
    Verdict.VERIFIED: "\033[32m",
    Verdict.MISMATCH: "\033[35m",
    Verdict.NOT_FOUND: "\033[31m",
    Verdict.MALFORMED: "\033[31m",
    Verdict.UNREACHABLE: "\033[33m",
    Verdict.UNVERIFIABLE: "\033[90m",
}
RESET = "\033[0m"

LABEL = {
    Verdict.VERIFIED: "Verified",
    Verdict.MISMATCH: "Resolves to a different work",
    Verdict.NOT_FOUND: "No such record",
    Verdict.MALFORMED: "Malformed identifier",
    Verdict.UNREACHABLE: "Could not check",
    Verdict.UNVERIFIABLE: "Not machine-checkable",
}

ORDER = [
    Verdict.NOT_FOUND, Verdict.MISMATCH, Verdict.MALFORMED,
    Verdict.UNREACHABLE, Verdict.UNVERIFIABLE, Verdict.VERIFIED,
]


def _score_text(report: Report) -> str:
    s = report.integrity_score
    if s is None:
        return "n/a (nothing could be conclusively checked)"
    return f"{s:.0%} of {report.conclusive} conclusive checks passed"


# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------

def to_terminal(report: Report, *, colour: bool = True,
                show_verified: bool = False) -> str:
    def c(v: Verdict, text: str) -> str:
        return f"{COLOUR[v]}{text}{RESET}" if colour else text

    lines: list[str] = []
    lines.append(f"citeaudit {report.tool_version}  —  {report.document}")
    lines.append("=" * 78)

    if report.total == 0:
        lines.append("No citations found.")
        return "\n".join(lines)

    for verdict in ORDER:
        group = [f for f in report.findings if f.verdict is verdict]
        if not group:
            continue
        if verdict is Verdict.VERIFIED and not show_verified:
            continue

        lines.append("")
        lines.append(c(verdict, f"{LABEL[verdict]} ({len(group)})"))
        lines.append("-" * 78)
        for f in group:
            cit = f.citation
            head = cit.identifier or (cit.claimed_title or cit.raw)[:70]
            lines.append(f"  {c(verdict, SYMBOL[verdict])} line {cit.line:<5} {head}")
            if cit.claimed_title and verdict is not Verdict.VERIFIED:
                lines.append(f"       document says: {cit.claimed_title[:66]!r}")
            if f.resolved_title and verdict is Verdict.MISMATCH:
                lines.append(f"       record holds:  {f.resolved_title[:66]!r}")
            if f.detail:
                for chunk in _wrap(f.detail, 68):
                    lines.append(f"       {chunk}")
            if f.evidence_url:
                lines.append(f"       check it: {f.evidence_url}")
            lines.append("")

    s = report.summary()
    lines.append("=" * 78)
    lines.append(
        f"{s['total_citations']} citations  |  "
        f"{s['verified']} verified  |  "
        f"{s['not_found']} not found  |  "
        f"{s['mismatch']} mismatched  |  "
        f"{s['malformed']} malformed"
    )
    if s["unreachable"] or s["unverifiable"]:
        lines.append(
            f"inconclusive: {s['unreachable']} unreachable, "
            f"{s['unverifiable']} not machine-checkable "
            f"(excluded from the score, not counted as failures)"
        )
    lines.append(f"integrity: {_score_text(report)}")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(report: Report, *, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Markdown — for PR comments and CI step summaries
# ---------------------------------------------------------------------------

def to_markdown(report: Report) -> str:
    s = report.summary()
    out: list[str] = []
    out.append(f"## citeaudit — `{report.document}`")
    out.append("")

    if report.total == 0:
        out.append("No citations found.")
        return "\n".join(out)

    failures = report.failures
    if failures:
        out.append(f"**{len(failures)} citation(s) did not hold up.**")
    else:
        out.append("**All conclusive checks passed.**")
    out.append("")

    out.append("| | count |")
    out.append("|---|---:|")
    out.append(f"| Verified | {s['verified']} |")
    out.append(f"| No such record | {s['not_found']} |")
    out.append(f"| Resolves to different work | {s['mismatch']} |")
    out.append(f"| Malformed | {s['malformed']} |")
    out.append(f"| Could not check | {s['unreachable']} |")
    out.append(f"| Not machine-checkable | {s['unverifiable']} |")
    out.append(f"| **Total** | **{s['total_citations']}** |")
    out.append("")
    out.append(f"Integrity: {_score_text(report)}")

    if failures:
        out.append("")
        out.append("### Failures")
        out.append("")
        out.append("| Line | Reference | Verdict | Detail | Evidence |")
        out.append("|---:|---|---|---|---|")
        for f in failures:
            cit = f.citation
            ref = (cit.identifier or cit.claimed_title or cit.raw)[:70]
            ev = f"[check]({f.evidence_url})" if f.evidence_url else "—"
            detail = f.detail.replace("|", "\\|")[:180]
            out.append(
                f"| {cit.line} | `{ref}` | {LABEL[f.verdict]} | {detail} | {ev} |"
            )

    inconclusive = report.inconclusive
    if inconclusive:
        out.append("")
        out.append(
            f"<details><summary>{len(inconclusive)} inconclusive "
            "(not counted as failures)</summary>"
        )
        out.append("")
        for f in inconclusive:
            ref = (f.citation.identifier or f.citation.claimed_title
                   or f.citation.raw)[:70]
            out.append(f"- line {f.citation.line}: `{ref}` — {f.detail}")
        out.append("")
        out.append("</details>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML — standalone, no assets, suitable for GitHub Pages
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--mut:#6b6b68;--line:#e4e4e1;
--ok:#1a7f37;--bad:#b3261e;--mis:#7b3fb8;--unk:#8a6d00;--card:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--fg:#f0efea;--mut:#9a9a94;
--line:#2c2c29;--ok:#4ac26b;--bad:#ff6b5e;--mis:#c08cf0;--unk:#e0b341;--card:#1c1c1a}}
*{box-sizing:border-box}
body{margin:0;padding:2.5rem 1.25rem;background:var(--bg);color:var(--fg);
font:16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Inter,system-ui,sans-serif}
.wrap{max-width:60rem;margin:0 auto}
h1{font-size:1.55rem;margin:0 0 .2rem;letter-spacing:-.02em}
.sub{color:var(--mut);font-size:.9rem;margin-bottom:2rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));
gap:.7rem;margin-bottom:2.2rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:.9rem}
.card .n{font-size:1.9rem;font-weight:640;letter-spacing:-.03em}
.card .l{font-size:.74rem;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.ok .n{color:var(--ok)}.bad .n{color:var(--bad)}.mis .n{color:var(--mis)}.unk .n{color:var(--unk)}
.score{background:var(--card);border:1px solid var(--line);border-radius:11px;
padding:1.05rem 1.2rem;margin-bottom:2.2rem}
.score b{font-size:1.25rem}
h2{font-size:1.02rem;margin:2.2rem 0 .8rem;text-transform:uppercase;
letter-spacing:.07em;color:var(--mut);font-weight:620}
.f{background:var(--card);border:1px solid var(--line);border-left-width:3px;
border-radius:9px;padding:.85rem 1rem;margin-bottom:.6rem}
.f.not_found,.f.malformed{border-left-color:var(--bad)}
.f.mismatch{border-left-color:var(--mis)}
.f.unreachable,.f.unverifiable{border-left-color:var(--unk)}
.f.verified{border-left-color:var(--ok)}
.ref{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.83rem;
word-break:break-all;margin-bottom:.35rem}
.meta{font-size:.83rem;color:var(--mut);margin:.2rem 0}
.meta .k{display:inline-block;min-width:6.7rem;color:var(--mut)}
.meta .v{color:var(--fg)}
a{color:inherit;text-decoration:underline;text-underline-offset:2px}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
color:var(--mut);font-size:.82rem}
"""


def _card(n: int, label: str, cls: str = "") -> str:
    return (f'<div class="card {cls}"><div class="n">{n}</div>'
            f'<div class="l">{html.escape(label)}</div></div>')


def _finding_html(f: Finding) -> str:
    cit = f.citation
    ref = html.escape(cit.identifier or cit.claimed_title or cit.raw)[:220]
    rows = [f'<div class="ref">{ref}</div>',
            f'<div class="meta"><span class="k">verdict</span>'
            f'<span class="v">{html.escape(LABEL[f.verdict])}</span></div>']

    if cit.claimed_title:
        rows.append(f'<div class="meta"><span class="k">document says</span>'
                    f'<span class="v">{html.escape(cit.claimed_title[:200])}</span></div>')
    if f.resolved_title:
        rows.append(f'<div class="meta"><span class="k">record holds</span>'
                    f'<span class="v">{html.escape(f.resolved_title[:200])}</span></div>')
    if f.title_similarity is not None:
        rows.append(f'<div class="meta"><span class="k">similarity</span>'
                    f'<span class="v">{f.title_similarity:.0f}%</span></div>')
    if f.detail:
        rows.append(f'<div class="meta"><span class="k">detail</span>'
                    f'<span class="v">{html.escape(f.detail[:400])}</span></div>')
    if f.evidence_url:
        u = html.escape(f.evidence_url)
        rows.append(f'<div class="meta"><span class="k">verify it</span>'
                    f'<span class="v"><a href="{u}" rel="nofollow noopener">{u[:110]}</a></span></div>')
    rows.append(f'<div class="meta"><span class="k">line</span>'
                f'<span class="v">{cit.line}</span></div>')
    return f'<div class="f {f.verdict.value}">{"".join(rows)}</div>'


def to_html(report: Report, *, title: str = "citeaudit report",
            show_verified: bool = True) -> str:
    s = report.summary()
    score = report.integrity_score
    score_str = "n/a" if score is None else f"{score:.0%}"

    parts: list[str] = []
    parts.append(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f'<div class="wrap">'
    )
    parts.append(f"<h1>{html.escape(title)}</h1>")
    parts.append(
        f'<div class="sub">{html.escape(report.document)} · '
        f"checked {html.escape(report.generated_at)} · "
        f"citeaudit {html.escape(report.tool_version)}</div>"
    )

    parts.append('<div class="cards">')
    parts.append(_card(s["total_citations"], "citations"))
    parts.append(_card(s["verified"], "verified", "ok"))
    parts.append(_card(s["not_found"], "no such record", "bad"))
    parts.append(_card(s["mismatch"], "wrong work", "mis"))
    parts.append(_card(s["malformed"], "malformed", "bad"))
    parts.append(_card(s["unreachable"] + s["unverifiable"], "inconclusive", "unk"))
    parts.append("</div>")

    parts.append(
        f'<div class="score"><b>Integrity {score_str}</b><br>'
        f'<span class="meta">{html.escape(_score_text(report))}. '
        "Inconclusive checks are excluded from the denominator rather than "
        "counted as passes or failures.</span></div>"
    )

    for verdict in ORDER:
        group = [f for f in report.findings if f.verdict is verdict]
        if not group or (verdict is Verdict.VERIFIED and not show_verified):
            continue
        parts.append(f"<h2>{html.escape(LABEL[verdict])} ({len(group)})</h2>")
        parts.extend(_finding_html(f) for f in group)

    parts.append(
        "<footer>Every finding links to the authority record it came from, so "
        "any line of this report can be confirmed or refuted without rerunning "
        "the tool. Generated by "
        '<a href="https://github.com/harshit-malik-nyu/citeaudit">citeaudit</a>.'
        "</footer>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)
