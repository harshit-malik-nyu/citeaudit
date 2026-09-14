"""
Tests for the CLI contract and the HTTP layer.

These were the two least-covered modules in the project and the two whose
contracts matter most to anyone actually using it.

The CLI's exit codes are what gate a CI pipeline. If `--fail-under` silently
stops failing, every build that depends on it goes green while citations rot.

The HTTP layer is where the NOT_FOUND / UNREACHABLE distinction is actually
decided. Every honesty guarantee in the verdict taxonomy rests on this module
retrying a 503 and not retrying a 404, and on a timeout never being mistaken
for a missing record.
"""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from citeaudit.cli import EXIT_ERROR, EXIT_FAILURES, EXIT_OK, main
from citeaudit.http import (
    Cache, Client, NotFound, Response, Unreachable,
)


# ===========================================================================
# HTTP layer
# ===========================================================================

class FakeOpener:
    """Scripted urlopen replacement."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.script_default()
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)

    def script_default(self):
        return (200, b"{}")


class _FakeResponse:
    def __init__(self, pair):
        self.status, self._body = pair

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


@pytest.fixture
def client() -> Client:
    return Client(cache_dir=None, use_cache=False, retries=3,
                  min_interval=0.0, backoff=0.0)


class TestRetrySemantics:

    def test_404_raises_not_found_without_retrying(self, client, monkeypatch):
        """
        A 404 is an ANSWER: the authority has no such record. Retrying it wastes
        a request and, worse, invites treating the eventual failure as
        inconclusive when it is actually conclusive.
        """
        opener = FakeOpener([_http_error(404)])
        monkeypatch.setattr("urllib.request.urlopen", opener)
        with pytest.raises(NotFound):
            client.get("https://api.example.org/works/10.1/x")
        assert opener.calls == 1

    def test_503_is_retried_then_reported_unreachable(self, client, monkeypatch):
        """
        A 503 is NOT an answer. After exhausting retries it must surface as
        Unreachable, never as NotFound — otherwise a bad afternoon at Crossref
        reads as a document full of fabricated citations.
        """
        opener = FakeOpener([_http_error(503)] * 3)
        monkeypatch.setattr("urllib.request.urlopen", opener)
        with pytest.raises(Unreachable):
            client.get("https://api.example.org/works/10.1/x")
        assert opener.calls == 3

    def test_transient_failure_then_success_returns_data(self, client, monkeypatch):
        opener = FakeOpener([_http_error(503), (200, b'{"ok": true}')])
        monkeypatch.setattr("urllib.request.urlopen", opener)
        resp = client.get("https://api.example.org/x")
        assert resp.json() == {"ok": True}
        assert opener.calls == 2

    def test_rate_limit_is_treated_as_transient(self, client, monkeypatch):
        """429 means slow down, not 'no such record'."""
        opener = FakeOpener([_http_error(429), (200, b"{}")])
        monkeypatch.setattr("urllib.request.urlopen", opener)
        client.get("https://api.example.org/x")
        assert opener.calls == 2

    def test_timeout_becomes_unreachable_not_not_found(self, client, monkeypatch):
        opener = FakeOpener([TimeoutError("timed out")] * 3)
        monkeypatch.setattr("urllib.request.urlopen", opener)
        with pytest.raises(Unreachable):
            client.get("https://api.example.org/x")

    def test_client_error_is_not_retried(self, client, monkeypatch):
        """A 400 means the request is malformed; repeating it cannot help."""
        opener = FakeOpener([_http_error(400)])
        monkeypatch.setattr("urllib.request.urlopen", opener)
        with pytest.raises(Unreachable):
            client.get("https://api.example.org/x")
        assert opener.calls == 1

    def test_failure_counter_tracks_unreachable_calls(self, client, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen",
                            FakeOpener([_http_error(503)] * 3))
        with pytest.raises(Unreachable):
            client.get("https://api.example.org/x")
        assert client.stats["failures"] == 1


class TestCache:

    def test_roundtrip(self, tmp_path):
        cache = Cache(tmp_path)
        cache.put(Response(url="https://x/1", status=200, body=b'{"a":1}'))
        got = cache.get("https://x/1")
        assert got is not None
        assert got.json() == {"a": 1}
        assert got.from_cache

    def test_miss_returns_none(self, tmp_path):
        assert Cache(tmp_path).get("https://never-fetched") is None

    def test_server_errors_are_not_cached(self, tmp_path):
        """Caching a 503 would make a transient outage permanent."""
        cache = Cache(tmp_path)
        cache.put(Response(url="https://x/2", status=503, body=b""))
        assert cache.get("https://x/2") is None

    def test_404_is_cached_and_replays_as_not_found(self, tmp_path):
        """A 404 is a real answer and worth remembering."""
        cache = Cache(tmp_path)
        cache.put(Response(url="https://x/3", status=404, body=b""))
        assert cache.get("https://x/3") is not None

    def test_cached_404_still_raises_through_the_client(self, tmp_path, monkeypatch):
        c = Client(cache_dir=tmp_path, use_cache=True, retries=1,
                   min_interval=0.0, backoff=0.0)
        c.cache.put(Response(url="https://x/4", status=404, body=b""))
        monkeypatch.setattr("urllib.request.urlopen",
                            FakeOpener([(200, b"should not be reached")]))
        with pytest.raises(NotFound):
            c.get("https://x/4")

    def test_disabled_cache_never_stores(self, tmp_path):
        cache = Cache(tmp_path, enabled=False)
        cache.put(Response(url="https://x/5", status=200, body=b"{}"))
        assert cache.get("https://x/5") is None

    def test_corrupt_cache_entry_is_ignored(self, tmp_path):
        """A damaged cache must degrade to a miss, never crash a run."""
        cache = Cache(tmp_path)
        cache.put(Response(url="https://x/6", status=200, body=b"{}"))
        for f in tmp_path.iterdir():
            f.write_text("not json at all")
        assert cache.get("https://x/6") is None


class TestPoliteness:

    def test_user_agent_carries_a_contact_address(self):
        c = Client(version="9.9.9", mailto="someone@example.org",
                   cache_dir=None, backoff=0.0)
        assert "9.9.9" in c.user_agent
        assert "someone@example.org" in c.user_agent

    def test_head_falls_back_to_get_on_405(self, client, monkeypatch):
        """
        Many servers mishandle HEAD. Reporting 405 as a dead link would flag
        working URLs as broken.
        """
        monkeypatch.setattr("urllib.request.urlopen",
                            FakeOpener([_http_error(405), (200, b"")]))
        alive, status = client.head_ok("https://example.org/paper.pdf")
        assert alive and status == 200

    def test_head_reports_a_genuine_404_as_dead(self, client, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen",
                            FakeOpener([_http_error(404)]))
        alive, status = client.head_ok("https://example.org/gone")
        assert not alive and status == 404


# ===========================================================================
# CLI contract
# ===========================================================================

CLEAN_DOC = """# A document

No citations of any kind appear in this text.
"""

DOC_WITH_BAD_DOI = """# A document

A claim resting on a source [1].

## References

[1] Author, A. (2020). "A title of entirely adequate length". doi:10.9999/definitely-not-real
"""


@pytest.fixture
def offline(monkeypatch):
    """
    Every network call fails as unreachable — no verdict may be a failure.

    Backoff is zeroed too: these tests exercise the CLI contract, not the
    wall-clock behaviour of exponential retry, and sleeping through it made the
    suite take a minute.
    """
    def boom(*a, **k):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr("urllib.request.urlopen", boom)

    import citeaudit.http as http_mod
    original = http_mod.Client.__init__

    def fast_init(self, *args, **kwargs):
        kwargs.setdefault("backoff", 0.0)
        kwargs.setdefault("min_interval", 0.0)
        original(self, *args, **kwargs)

    monkeypatch.setattr(http_mod.Client, "__init__", fast_init)


class TestCliExitCodes:

    def test_document_with_no_citations_exits_clean(self, tmp_path, capsys):
        p = tmp_path / "clean.md"
        p.write_text(CLEAN_DOC)
        assert main([str(p), "--no-cache"]) == EXIT_OK
        assert "No citations found." in capsys.readouterr().out

    def test_missing_file_is_a_tool_error_not_a_finding(self, tmp_path, capsys):
        """
        Exit 2, not 1. A missing file is the operator's mistake; reporting it as
        a citation failure would be a lie about the document.
        """
        code = main([str(tmp_path / "nope.md")])
        assert code == EXIT_ERROR
        assert "no such file" in capsys.readouterr().err

    def test_unsupported_format_is_a_tool_error(self, tmp_path, capsys):
        p = tmp_path / "thing.xyz"
        p.write_text("content")
        assert main([str(p)]) == EXIT_ERROR
        assert "Cannot read" in capsys.readouterr().err

    def test_unreachable_authorities_do_not_fail_the_build(self, tmp_path, offline):
        """
        THE most important CLI guarantee. If a scholarly API is down, the build
        must stay green. A checker that goes red on someone else's outage gets
        switched off within a week, and a switched-off check protects nobody.
        """
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        assert main([str(p), "--no-cache", "--no-urls"]) == EXIT_OK

    def test_strict_mode_does_fail_on_inconclusive(self, tmp_path, offline):
        """The opt-in for release gates, where the trade-off runs the other way."""
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        assert main([str(p), "--no-cache", "--no-urls", "--strict"]) == EXIT_FAILURES

    def test_fail_under_is_not_triggered_by_an_unscorable_run(self, tmp_path, offline):
        """
        With nothing conclusively checked the score is None, not 0%. A
        threshold must not fire on an absence of evidence.
        """
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        assert main([str(p), "--no-cache", "--no-urls",
                     "--fail-under", "99"]) == EXIT_OK


class TestCliOutput:

    def test_json_output_is_valid_and_structured(self, tmp_path, offline):
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        out = tmp_path / "r.json"
        main([str(p), "--no-cache", "--no-urls", "--format", "json",
              "-o", str(out)])
        data = json.loads(out.read_text())
        assert "summary" in data and "findings" in data
        assert data["summary"]["total_citations"] >= 1

    def test_html_output_is_self_contained(self, tmp_path, offline):
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        out = tmp_path / "r.html"
        main([str(p), "--no-cache", "--no-urls", "--format", "html",
              "-o", str(out)])
        html = out.read_text()
        assert html.startswith("<!doctype html>")
        assert "<style>" in html

    def test_markdown_output_written(self, tmp_path, offline):
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        out = tmp_path / "r.md"
        main([str(p), "--no-cache", "--no-urls", "--format", "markdown",
              "-o", str(out)])
        assert "citeaudit" in out.read_text()

    def test_output_directory_is_created(self, tmp_path, offline):
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        out = tmp_path / "nested" / "deep" / "r.json"
        main([str(p), "--no-cache", "--no-urls", "--format", "json",
              "-o", str(out)])
        assert out.exists()

    def test_multiple_documents_are_merged(self, tmp_path, offline, capsys):
        a, b = tmp_path / "a.md", tmp_path / "b.md"
        a.write_text(DOC_WITH_BAD_DOI)
        b.write_text(DOC_WITH_BAD_DOI)
        main([str(a), str(b), "--no-cache", "--no-urls"])
        assert "2 documents" in capsys.readouterr().out

    def test_terminal_output_has_no_colour_when_writing_to_a_file(
            self, tmp_path, offline):
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        out = tmp_path / "r.txt"
        main([str(p), "--no-cache", "--no-urls", "-o", str(out)])
        assert "\033[" not in out.read_text()


class TestCliStepSummary:

    def test_github_step_summary_is_appended_when_present(
            self, tmp_path, offline, monkeypatch):
        summary = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        main([str(p), "--no-cache", "--no-urls"])
        assert "citeaudit" in summary.read_text()

    def test_missing_step_summary_path_is_harmless(self, tmp_path, offline,
                                                   monkeypatch):
        monkeypatch.setenv("GITHUB_STEP_SUMMARY",
                           str(tmp_path / "no" / "such" / "dir" / "s.md"))
        p = tmp_path / "doc.md"
        p.write_text(DOC_WITH_BAD_DOI)
        assert main([str(p), "--no-cache", "--no-urls"]) == EXIT_OK


class TestConcurrentPacing:
    """
    REGRESSION. Rate limiting read and wrote a shared timestamp with no lock.
    Six verifier threads each checked it, each concluded enough time had
    elapsed, and all six fired together — an effective rate six times the
    configured one.

    arXiv answered with HTTP 429 for 11 of 12 categories. The study collected 8
    papers instead of 96, and the resulting 87-check result then overwrote a
    1,247-check measurement.
    """

    def test_pacing_holds_across_threads(self, monkeypatch):
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor

        timestamps: list[float] = []
        guard = threading.Lock()

        def fake(req, timeout=None):
            with guard:
                timestamps.append(time.monotonic())
            return _FakeResponse((200, b"{}"))

        monkeypatch.setattr("urllib.request.urlopen", fake)

        interval = 0.05
        c = Client(cache_dir=None, use_cache=False,
                   min_interval=interval, backoff=0.0)

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda i: c.get(f"https://one-host.example/{i}"),
                          range(6)))

        ordered = sorted(timestamps)
        gaps = [b - a for a, b in zip(ordered, ordered[1:])]
        assert len(gaps) == 5
        # Allow a little scheduler slack, but nothing near the ~0 of the bug.
        assert min(gaps) >= interval * 0.8, f"requests bunched: {gaps}"

    def test_per_host_pacing_does_not_serialise_unrelated_hosts(self, monkeypatch):
        """Politeness to one authority must not throttle calls to another."""
        from citeaudit.http import HOST_MIN_INTERVAL
        assert HOST_MIN_INTERVAL["export.arxiv.org"] > HOST_MIN_INTERVAL.get(
            "en.wikipedia.org", 1.0)

    def test_stats_are_updated_under_a_lock(self, monkeypatch):
        """Counters shared by six threads need the same protection."""
        from concurrent.futures import ThreadPoolExecutor

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=None: _FakeResponse((200, b"{}")))
        c = Client(cache_dir=None, use_cache=False, min_interval=0.0, backoff=0.0)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: c.get(f"https://h.example/{i}"), range(64)))
        assert c.stats["requests"] == 64
