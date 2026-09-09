"""
HTTP transport shared by every authority client.

Three responsibilities, all of which exist to protect the integrity of the
verdict rather than to make the tool fast:

    Retry        Transient failures must not be mistaken for missing records.
                 A 5xx or a timeout is retried with backoff, and only after
                 exhausting retries is the check reported UNREACHABLE — never
                 NOT_FOUND.

    Rate limit   Public scholarly APIs are free and maintained on goodwill.
                 Requests are paced and identify themselves with a contact
                 address, per Crossref's polite-pool convention.

    Cache        Responses are stored on disk keyed by URL. This makes runs
                 reproducible, keeps repeat checks off the network, and gives
                 an auditor the actual bytes the verdict was derived from.

Only stdlib is used, so the tool installs without a transitive dependency tree
of its own. A citation checker with a large supply chain is an awkward artifact.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
DEFAULT_RETRIES = 3
DEFAULT_MIN_INTERVAL = 0.12  # seconds between calls to the same host

USER_AGENT_TEMPLATE = (
    "citeaudit/{version} (+https://github.com/{repo}; mailto:{mailto})"
)


class Unreachable(RuntimeError):
    """The authority could not be consulted. Distinct from 'no such record'."""


class NotFound(LookupError):
    """The authority was consulted and holds no such record."""


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    from_cache: bool = False

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8", errors="replace"))

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Cache:
    """Content-addressed response cache."""

    def __init__(self, directory: str | Path | None, enabled: bool = True):
        self.enabled = enabled and directory is not None
        self.dir = Path(directory) if directory else None
        if self.enabled and self.dir:
            self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()[:24]
        assert self.dir is not None
        return self.dir / f"{digest}.json"

    def get(self, url: str) -> Response | None:
        if not self.enabled:
            return None
        p = self._path(url)
        if not p.exists():
            return None
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        return Response(
            url=rec["url"], status=rec["status"],
            body=rec["body"].encode("utf-8"), from_cache=True,
        )

    def put(self, resp: Response) -> None:
        if not self.enabled or resp.status >= 500:
            return
        rec = {
            "url": resp.url,
            "status": resp.status,
            "body": resp.body.decode("utf-8", errors="replace"),
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            self._path(resp.url).write_text(json.dumps(rec))
        except OSError:
            pass


class Client:
    """Polite, retrying HTTP client."""

    def __init__(
        self,
        *,
        version: str = "0.1.0",
        mailto: str | None = None,
        repo: str = "citeaudit",
        cache_dir: str | Path | None = None,
        use_cache: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        min_interval: float = DEFAULT_MIN_INTERVAL,
    ):
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self.cache = Cache(cache_dir, use_cache)
        self.mailto = mailto or os.environ.get("CITEAUDIT_MAILTO", "anonymous@example.com")
        self.user_agent = USER_AGENT_TEMPLATE.format(
            version=version, repo=repo, mailto=self.mailto
        )
        self._last_call: dict[str, float] = {}
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "failures": 0}

    def _pace(self, host: str) -> None:
        last = self._last_call.get(host)
        if last is not None:
            wait = self.min_interval - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_call[host] = time.monotonic()

    def get(self, url: str, *, accept: str = "application/json",
            allow_404: bool = True, method: str = "GET") -> Response:
        """
        Fetch a URL.

        Raises NotFound on 404 (the authority answered: no such record) and
        Unreachable on anything that leaves the question open.
        """
        cached = self.cache.get(url)
        if cached is not None:
            self.stats["cache_hits"] += 1
            if cached.status == 404 and allow_404:
                raise NotFound(url)
            return cached

        host = urllib.parse.urlparse(url).netloc
        last_error: Exception | None = None

        for attempt in range(self.retries):
            if attempt:
                # Exponential backoff with jitter, so parallel runs do not
                # synchronise into a thundering herd against a free API.
                delay = (2 ** attempt) * 0.5 + random.uniform(0, 0.3)
                time.sleep(delay)
                self.stats["retries"] += 1

            self._pace(host)
            req = urllib.request.Request(
                url, method=method,
                headers={"Accept": accept, "User-Agent": self.user_agent},
            )
            try:
                self.stats["requests"] += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    resp = Response(url=url, status=r.status, body=r.read())
                self.cache.put(resp)
                return resp

            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    resp = Response(url=url, status=404, body=b"")
                    self.cache.put(resp)
                    if allow_404:
                        raise NotFound(url) from exc
                    return resp
                if exc.code in (429, 500, 502, 503, 504):
                    last_error = exc
                    continue          # transient — retry
                # 4xx other than 404 and 429: the request itself is wrong.
                last_error = exc
                break

            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                continue

        self.stats["failures"] += 1
        raise Unreachable(f"{url}: {last_error}") from last_error

    def head_ok(self, url: str) -> tuple[bool, int]:
        """
        Liveness check for a plain web link.

        Tries HEAD, falling back to GET, because a large share of servers
        mishandle HEAD and returning 405 as 'dead link' would be wrong.
        """
        for method, accept in (("HEAD", "*/*"), ("GET", "*/*")):
            try:
                r = self.get(url, accept=accept, allow_404=False, method=method)
                if r.status < 400:
                    return True, r.status
                if r.status in (403, 405, 406):
                    continue          # try the other verb
                return False, r.status
            except NotFound:
                return False, 404
            except Unreachable:
                continue
        raise Unreachable(url)
