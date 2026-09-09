"""
Core types.

The verdict taxonomy is the most important design decision in this tool, so it
lives at the top of the codebase rather than buried in the checker.

A citation checker that cannot distinguish "this reference does not exist" from
"I could not reach the server" is committing the exact error it was built to
catch: emitting a confident claim that its evidence does not support. A network
timeout is not evidence of fabrication. Those are separate verdicts here, they
are counted separately, and an inconclusive check never contributes to a
failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """Outcome of checking one citation."""

    VERIFIED = "verified"
    """Identifier resolves, and the resolved record matches what the document
    claimed about it."""

    MISMATCH = "mismatch"
    """Identifier resolves, but to a different work than the document claimed.
    The most dangerous category: the reference looks legitimate, the DOI is
    real, and a reviewer clicking it lands on *something*, so it survives
    casual checking. Only a metadata comparison catches it."""

    NOT_FOUND = "not_found"
    """Identifier is well-formed but does not resolve against the authority.
    This is the fabrication signature."""

    UNREACHABLE = "unreachable"
    """The check could not be completed — timeout, rate limit, service error.
    INCONCLUSIVE. Never counted as a failure, never reported as fabrication."""

    UNVERIFIABLE = "unverifiable"
    """No machine-checkable identifier and no title specific enough to search.
    The tool declines to guess."""

    MALFORMED = "malformed"
    """Identifier is syntactically invalid and cannot be resolved by anyone."""

    @property
    def is_failure(self) -> bool:
        """Verdicts that indicate a real integrity problem."""
        return self in (Verdict.NOT_FOUND, Verdict.MISMATCH, Verdict.MALFORMED)

    @property
    def is_inconclusive(self) -> bool:
        return self in (Verdict.UNREACHABLE, Verdict.UNVERIFIABLE)


class Kind(str, Enum):
    """What sort of reference was extracted."""

    DOI = "doi"
    ARXIV = "arxiv"
    URL = "url"
    BIBLIOGRAPHIC = "bibliographic"
    """Author/title/year with no resolvable identifier. Verified by searching
    the authority for a matching record — which is how a plausible-sounding
    reference to a paper that was never written gets caught."""


@dataclass
class Citation:
    """A reference as it appears in the document, before any checking."""

    raw: str
    kind: Kind
    line: int = 0
    identifier: str | None = None
    claimed_title: str | None = None
    claimed_authors: list[str] = field(default_factory=list)
    claimed_year: int | None = None
    context: str = ""

    def key(self) -> str:
        return f"{self.kind.value}:{self.identifier or self.claimed_title or self.raw}"


@dataclass
class Finding:
    """The result of checking one citation against an authority."""

    citation: Citation
    verdict: Verdict
    authority: str
    detail: str = ""
    resolved_title: str | None = None
    resolved_authors: list[str] = field(default_factory=list)
    resolved_year: int | None = None
    title_similarity: float | None = None
    author_overlap: float | None = None
    evidence_url: str | None = None
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["citation"]["kind"] = self.citation.kind.value
        d["verdict"] = self.verdict.value
        return d


@dataclass
class Report:
    """Aggregate result for one document."""

    document: str
    findings: list[Finding] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    tool_version: str = ""

    # -- counts ------------------------------------------------------------

    def count(self, verdict: Verdict) -> int:
        return sum(1 for f in self.findings if f.verdict is verdict)

    @property
    def total(self) -> int:
        return len(self.findings)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict.is_failure]

    @property
    def inconclusive(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict.is_inconclusive]

    @property
    def conclusive(self) -> int:
        """Citations the tool could actually reach a verdict on."""
        return self.total - len(self.inconclusive)

    @property
    def integrity_score(self) -> float | None:
        """
        Share of CONCLUSIVE checks that passed.

        Deliberately computed over conclusive checks only. Including
        unreachable citations in the denominator would let a flaky network
        quietly depress the score, and including them in the numerator would
        let it inflate one. Where nothing could be checked, the score is None
        rather than a misleading 1.0 or 0.0.
        """
        if self.conclusive == 0:
            return None
        return self.count(Verdict.VERIFIED) / self.conclusive

    def summary(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "generated_at": self.generated_at,
            "tool_version": self.tool_version,
            "total_citations": self.total,
            "verified": self.count(Verdict.VERIFIED),
            "mismatch": self.count(Verdict.MISMATCH),
            "not_found": self.count(Verdict.NOT_FOUND),
            "malformed": self.count(Verdict.MALFORMED),
            "unreachable": self.count(Verdict.UNREACHABLE),
            "unverifiable": self.count(Verdict.UNVERIFIABLE),
            "conclusive_checks": self.conclusive,
            "integrity_score": self.integrity_score,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "findings": [f.to_dict() for f in self.findings],
        }
