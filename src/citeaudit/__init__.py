"""
citeaudit — verify that the citations in a document actually exist.

Extracts every DOI, arXiv identifier, URL, and bibliographic reference from a
document and checks each against the authority that can answer for it, then
reports which ones do not hold up.
"""

__version__ = "0.1.0"

from .models import Citation, Finding, Kind, Report, Verdict  # noqa: E402

__all__ = ["Citation", "Finding", "Kind", "Report", "Verdict", "__version__"]
