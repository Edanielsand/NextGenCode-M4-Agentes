"""Pruebas de la carga y del paso load, sin red."""

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
    assert load.main(["http://x"]) == 2
    assert "LOAD_API_KEY" in capsys.readouterr().out


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
