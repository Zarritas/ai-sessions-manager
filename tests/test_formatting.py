"""Tests for multi_claude.formatting."""

from __future__ import annotations

from multi_claude.formatting import format_relative_time, format_size


def test_format_relative_time_seconds() -> None:
    assert format_relative_time(100.0, now=130.0) == "30s"


def test_format_relative_time_minutes() -> None:
    assert format_relative_time(0.0, now=600.0) == "10m"


def test_format_relative_time_hours() -> None:
    assert format_relative_time(0.0, now=7200.0) == "2h"


def test_format_relative_time_days() -> None:
    assert format_relative_time(0.0, now=3 * 86400.0) == "3d"


def test_format_relative_time_weeks() -> None:
    assert format_relative_time(0.0, now=14 * 86400.0) == "2w"


def test_format_relative_time_falls_back_to_iso_date() -> None:
    # > 30 days → "YYYY-MM-DD"
    assert format_relative_time(0.0, now=40 * 86400.0).count("-") == 2


def test_format_size_bytes() -> None:
    assert format_size(500) == "500B"


def test_format_size_kb() -> None:
    assert format_size(2048) == "2K"


def test_format_size_mb() -> None:
    assert format_size(int(1.5 * 1024 * 1024)) == "1.5M"
