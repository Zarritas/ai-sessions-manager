"""Tests for ai_sessions_manager.names."""

from __future__ import annotations

from pathlib import Path

from ai_sessions_manager.names import NamesStore, default_path


def test_default_path_uses_xdg(monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert default_path() == Path("/tmp/xdg/ai-sessions-manager/names.json")


def test_default_path_falls_back_to_home(monkeypatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/test")))
    assert default_path() == Path("/home/test/.config/ai-sessions-manager/names.json")


def test_get_missing_returns_none(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    assert store.get("unknown") is None


def test_set_and_get_round_trip(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    store.set("abc-123", "mi sesión")
    assert store.get("abc-123") == "mi sesión"

    # Fresh instance reads from disk
    other = NamesStore(tmp_path / "names.json")
    assert other.get("abc-123") == "mi sesión"


def test_delete_removes_entry(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    store.set("x", "foo")
    store.delete("x")
    assert store.get("x") is None
    assert NamesStore(tmp_path / "names.json").get("x") is None


def test_delete_missing_is_noop(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    store.delete("never-existed")  # no crash


def test_corrupt_json_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    path.write_text("this is not json {", encoding="utf-8")
    store = NamesStore(path)
    assert store.all() == {}
    # Can write over the corruption
    store.set("a", "b")
    assert NamesStore(path).get("a") == "b"


def test_non_dict_top_level_is_treated_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    path.write_text("[1,2,3]", encoding="utf-8")
    assert NamesStore(path).all() == {}


def test_write_is_atomic_no_temp_left(tmp_path: Path) -> None:
    store = NamesStore(tmp_path / "names.json")
    store.set("a", "b")
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".names.")]
    assert leftovers == []


def test_parent_dir_is_created(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "names.json"
    store = NamesStore(nested)
    store.set("x", "y")
    assert nested.exists()
