"""Tests for the bulk-cleanup date parser and modal preset wiring."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_sessions_manager.modals import _CLEANUP_PRESETS, _DEFAULT_PRESET_IDX, _parse_iso_date


def test_parse_iso_date_valid() -> None:
    ts = _parse_iso_date("2025-01-15")
    assert ts is not None
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert (dt.year, dt.month, dt.day) == (2025, 1, 15)
    assert (dt.hour, dt.minute, dt.second) == (0, 0, 0)


def test_parse_iso_date_strips_whitespace() -> None:
    assert _parse_iso_date("  2024-06-01  ") is not None


def test_parse_iso_date_rejects_garbage() -> None:
    assert _parse_iso_date("not-a-date") is None
    assert _parse_iso_date("01/01/2025") is None  # only YYYY-MM-DD
    assert _parse_iso_date("") is None
    assert _parse_iso_date("2025-13-01") is None  # invalid month
    assert _parse_iso_date("2025-02-30") is None  # invalid day


def test_presets_are_ordered_and_have_custom_last() -> None:
    """Day counts strictly grow; last entry is the 'custom date' marker."""
    days = [d for _, d in _CLEANUP_PRESETS if d is not None]
    assert days == sorted(days)
    assert _CLEANUP_PRESETS[-1][1] is None
    # Default must point to a numeric preset, not the custom one.
    assert _CLEANUP_PRESETS[_DEFAULT_PRESET_IDX][1] is not None
