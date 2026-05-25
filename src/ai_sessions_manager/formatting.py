"""Pure formatting helpers used by both screens."""

from __future__ import annotations

import time
from datetime import datetime, timezone


def format_relative_time(epoch: float, *, now: float | None = None) -> str:
    """Return a short relative-time string: '3m', '2h', '5d', '3w', or 'YYYY-MM-DD'."""
    if now is None:
        now = time.time()
    delta = max(0, int(now - epoch))
    if delta < 60:
        return f"{delta}s"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    if delta < 7 * 86400:
        return f"{delta // 86400}d"
    if delta < 30 * 86400:
        return f"{delta // (7 * 86400)}w"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def format_size(num_bytes: int) -> str:
    """Human-readable size: 940B, 12K, 3.4M."""
    if num_bytes < 1024:
        return f"{num_bytes}B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes // 1024}K"
    return f"{num_bytes / (1024 * 1024):.1f}M"
