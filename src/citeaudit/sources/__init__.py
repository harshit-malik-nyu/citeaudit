"""Authority clients. Each resolves an identifier or description to a record."""

from .arxiv import Arxiv
from .crossref import Crossref
from .openalex import OpenAlex

__all__ = ["Arxiv", "Crossref", "OpenAlex"]
