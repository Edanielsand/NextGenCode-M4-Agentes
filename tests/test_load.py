"""Pruebas de la carga y del paso load, sin red."""

import httpx

import verification.__main__ as runner
from verification import load


def test_percentile_picks_the_nearest_rank():
    assert load.percentile([5, 1, 3, 2, 4], 50) == 3
    assert load.percentile([5, 1, 3, 2, 4], 95) == 5
    assert load.percentile([], 50) == 0.0


def test_summary_counts_errors_and_rate():
    summary = load.summarize([(True, 0.1), (True, 0.2), (False, 0.3), (True, 0.4)], 2)
    assert (summary["requests"], summary["successes"], summary["errors"]) == (4, 3, 1)
    assert summary["error_rate"] == 0.25
    assert summary["rps"] == 2


def test_the_key_never_comes_from_an_argument(monkeypatch, capsys):
    monkeypatch.delenv("LOAD_API_KEY", raising=False)
    monkeypatch.delenv("LOAD_API_KEYS", raising=False)
    assert load.main(["http://x"]) == 2
    assert "LOAD_API_KEYS" in capsys.readouterr().out


def test_keys_come_from_the_plural_variable_first():
    env = {"LOAD_API_KEYS": "a, b,,c ", "LOAD_API_KEY": "z"}
    assert load.parse_keys(env) == ["a", "b", "c"]


def test_keys_fall_back_to_the_single_variable():
    assert load.parse_keys({"LOAD_API_KEY": "z"}) == ["z"]
    assert load.parse_keys({}) == []


def test_requests_are_spread_across_keys_in_turns(monkeypatch, capsys):
    seen = []

    def handler(request):
        seen.append(request.headers["X-API-Key"])
        return httpx.Response(200, json={"answer": "ok"})

    real_client = httpx.Client
    monkeypatch.setattr(load.httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    monkeypatch.delenv("LOAD_API_KEY", raising=False)
    monkeypatch.setenv("LOAD_API_KEYS", "k1,k2,k3")
    code = load.main(["http://x", "--n", "7", "--concurrency", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert seen == ["k1", "k2", "k3", "k1", "k2", "k3", "k1"]
    assert "clientes:   3" in out


def test_no_key_appears_in_the_output(monkeypatch, capsys):
    real_client = httpx.Client
    monkeypatch.setattr(load.httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"detail": "limite"})), **kw))
    monkeypatch.setenv("LOAD_API_KEYS", "secret-one,secret-two")
    load.main(["http://x", "--n", "4", "--concurrency", "1"])
    out = capsys.readouterr().out
    assert "secret-one" not in out
    assert "secret-two" not in out
    assert "429: 4" in out


def test_exit_code_is_nonzero_above_one_percent(monkeypatch):
    monkeypatch.setenv("LOAD_API_KEY", "k")
    monkeypatch.setattr(load, "run_load", lambda *a: {
        "requests": 50, "successes": 49, "errors": 1, "error_rate": 0.02,
        "p50_ms": 1, "p95_ms": 2, "rps": 3})
    assert load.main(["http://x"]) == 1


def test_exit_code_is_zero_at_or_below_one_percent(monkeypatch):
    monkeypatch.setenv("LOAD_API_KEY", "k")
    monkeypatch.setattr(load, "run_load", lambda *a: {
        "requests": 100, "successes": 99, "errors": 1, "error_rate": 0.01,
        "p50_ms": 1, "p95_ms": 2, "rps": 3})
    assert load.main(["http://x"]) == 0


def test_runner_has_the_load_step():
    assert "load" in runner.STEPS


def test_breakdown_counts_codes_and_network_errors():
    outcomes = ["429"] * 3 + ["200"] * 2 + ["502", "red (ReadTimeout)"]
    assert load.format_breakdown(outcomes) == (
        "200: 2, 429: 3, 502: 1, red (ReadTimeout): 1")


def test_run_load_breaks_down_and_prints_only_first_details(monkeypatch, capsys):
    def handler(request):
        n = handler.calls = getattr(handler, "calls", 0) + 1
        if n == 1:
            return httpx.Response(200, json={"answer": "ok"})
        if n == 2:
            raise httpx.ConnectTimeout("boom")
        return httpx.Response(429, json={"detail": f"limite {n}"})

    real_client = httpx.Client
    monkeypatch.setattr(load.httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv("LOAD_API_KEY", "secret-key")
    code = load.main(["http://x", "--n", "7", "--concurrency", "1"])
    out = capsys.readouterr().out
    assert code == 1
    assert "200: 1, 429: 5, red (ConnectTimeout): 1" in out
    assert out.count("detail 429:") == 3
    assert "secret-key" not in out
