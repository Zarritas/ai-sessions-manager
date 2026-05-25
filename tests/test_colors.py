"""Tests for session colour resolution and the manual override store."""

from __future__ import annotations

from pathlib import Path

import pytest

from multi_claude.colors import ColorRule, SessionColorsStore, resolve_style
from multi_claude.session import Session


def _session(
    sid: str = "sid-x",
    *,
    branch: str | None = "main",
    prompt: str = "do the thing",
    cwd: str | None = "/repo",
    last_activity: float = 1000.0,
    display_name: str | None = None,
) -> Session:
    return Session(
        id=sid,
        path=Path(f"/p/{sid}.jsonl"),
        first_prompt=prompt,
        branch=branch,
        cwd=cwd,
        message_count=10,
        size_bytes=4096,
        last_activity=last_activity,
        display_name=display_name,
    )


# --- store ----------------------------------------------------------------- #


def test_store_persists_color(tmp_path: Path) -> None:
    store = SessionColorsStore(tmp_path / "colors.json")
    store.set("sid-1", "bold red")
    assert store.get("sid-1") == "bold red"


def test_store_delete(tmp_path: Path) -> None:
    store = SessionColorsStore(tmp_path / "colors.json")
    store.set("sid-1", "bold red")
    store.delete("sid-1")
    assert store.get("sid-1") is None


def test_store_handles_missing_file(tmp_path: Path) -> None:
    store = SessionColorsStore(tmp_path / "absent.json")
    assert store.get("anything") is None


def test_store_handles_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    store = SessionColorsStore(path)
    assert store.all() == {}


def test_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "colors.json"
    SessionColorsStore(path).set("sid", "bold cyan")
    assert SessionColorsStore(path).get("sid") == "bold cyan"


# --- rule parsing + matching --------------------------------------------- #


def test_rule_from_dict_rejects_garbage() -> None:
    assert ColorRule.from_dict({"when": "", "color": "red"}) is None
    assert ColorRule.from_dict({"when": "branch=main", "color": ""}) is None
    assert ColorRule.from_dict({"when": "branch=main"}) is None
    assert ColorRule.from_dict("not a dict") is None  # type: ignore[arg-type]


def test_resolve_no_rules_no_manual_returns_none() -> None:
    assert resolve_style(_session()) is None


def test_manual_override_wins(tmp_path: Path) -> None:
    store = SessionColorsStore(tmp_path / "c.json")
    store.set("sid-x", "bold magenta")
    rules = [ColorRule(when="branch=main", color="bold green")]
    assert resolve_style(_session(), manual=store, rules=rules) == "bold magenta"


def test_branch_exact_match_case_insensitive() -> None:
    rules = [ColorRule(when="branch=MAIN", color="bold green")]
    assert resolve_style(_session(branch="main"), rules=rules) == "bold green"


def test_branch_glob_match() -> None:
    rules = [ColorRule(when="branch~=feature/*", color="bold cyan")]
    assert resolve_style(_session(branch="feature/login"), rules=rules) == "bold cyan"
    assert resolve_style(_session(branch="main"), rules=rules) is None


def test_prompt_regex_match() -> None:
    rules = [ColorRule(when="prompt~=^/", color="bold yellow")]
    assert resolve_style(_session(prompt="/refine-task https://..."), rules=rules) == "bold yellow"
    assert resolve_style(_session(prompt="plain prompt"), rules=rules) is None


def test_active_true_match() -> None:
    rules = [ColorRule(when="active=true", color="bold red")]
    assert resolve_style(_session(), rules=rules, is_active=True) == "bold red"
    assert resolve_style(_session(), rules=rules, is_active=False) is None


def test_age_threshold_match() -> None:
    rules = [ColorRule(when="age<1h", color="bold green")]
    now = 10_000.0
    fresh = _session(last_activity=now - 60)
    stale = _session(last_activity=now - 7200)
    assert resolve_style(fresh, rules=rules, now=now) == "bold green"
    assert resolve_style(stale, rules=rules, now=now) is None


def test_first_matching_rule_wins() -> None:
    rules = [
        ColorRule(when="active=true", color="bold red"),
        ColorRule(when="branch=main", color="bold green"),
    ]
    assert resolve_style(_session(branch="main"), rules=rules, is_active=True) == "bold red"
    assert resolve_style(_session(branch="main"), rules=rules, is_active=False) == "bold green"


def test_malformed_when_does_not_explode() -> None:
    """Typo'd rule should silently not match — never colour everything by accident."""
    rules = [ColorRule(when="brnch=main", color="bold red")]
    assert resolve_style(_session(branch="main"), rules=rules) is None


def test_unknown_field_yields_no_match() -> None:
    rules = [ColorRule(when="unknown_field=value", color="bold red")]
    assert resolve_style(_session(), rules=rules) is None


@pytest.mark.parametrize(
    "expr,expected_age",
    [
        ("age<30s", 30.0),
        ("age<5m", 300.0),
        ("age<2h", 7200.0),
        ("age<1d", 86400.0),
        ("age<1w", 604800.0),
    ],
)
def test_age_units(expr: str, expected_age: float) -> None:
    rules = [ColorRule(when=expr, color="x")]
    now = 1_000_000.0
    # Just within the window
    just_in = _session(last_activity=now - expected_age + 1)
    just_out = _session(last_activity=now - expected_age - 1)
    assert resolve_style(just_in, rules=rules, now=now) == "x"
    assert resolve_style(just_out, rules=rules, now=now) is None
