"""LCS-based alignment of subtitle events by duration fingerprint.

This module is intentionally dependency-free so it can be unit-tested
without pysubs2.  It operates on plain objects that expose .start and .end
attributes (integers in milliseconds).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class TimedEvent(Protocol):
    """Minimal interface required by this module."""

    start: int
    end: int


# ---------------------------------------------------------------------------
# Duration bucketing
# ---------------------------------------------------------------------------

def bucket(duration_ms: float) -> int:
    """Quantize a subtitle duration into a coarse bucket.

    Returns:
        0 — Short  (< 1 000 ms)
        1 — Medium (1 000 – 2 500 ms)
        2 — Long   (> 2 500 ms)
    """
    if duration_ms < 1000:
        return 0
    if duration_ms <= 2500:
        return 1
    return 2


# ---------------------------------------------------------------------------
# LCS on bucket sequences
# ---------------------------------------------------------------------------

def lcs_align(
    src_events: Sequence[TimedEvent],
    tgt_events: Sequence[TimedEvent],
) -> list[tuple[int, int]]:
    """Return matched (src_idx, tgt_idx) pairs via LCS on duration buckets.

    The algorithm compares *bucket* values, not text, so it works across
    languages.  Standard O(n*m) DP — adequate for typical subtitle counts
    (< 2 000 entries).
    """
    n, m = len(src_events), len(tgt_events)

    src_buckets = [bucket(e.end - e.start) for e in src_events]
    tgt_buckets = [bucket(e.end - e.start) for e in tgt_events]

    # Build DP table
    dp: list[list[int]] = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if src_buckets[i - 1] == tgt_buckets[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    # Backtrack
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        if src_buckets[i - 1] == tgt_buckets[j - 1]:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1

    pairs.reverse()
    return pairs


# ---------------------------------------------------------------------------
# Dataclass used to pass timing back to the caller
# ---------------------------------------------------------------------------

@dataclass
class Timing:
    start: int
    end: int


# ---------------------------------------------------------------------------
# Interpolation for unmatched target entries
# ---------------------------------------------------------------------------

def interpolate(
    tgt_events: Sequence[TimedEvent],
    matches: list[tuple[int, int]],
    src_events: Sequence[TimedEvent],
) -> list[Timing]:
    """Assign a Timing to every target event.

    Matched entries take timing directly from their paired source event.
    Unmatched entries are distributed evenly in the gap between the nearest
    matched neighbours.  Edge cases:
    - Only a left neighbour  → extrapolate forward using original duration.
    - Only a right neighbour → extrapolate backward using original duration.
    - No neighbours at all   → keep original timing unchanged.
    """
    n_tgt = len(tgt_events)
    result: list[Timing | None] = [None] * n_tgt

    # Map tgt_idx → src_idx for matched pairs
    tgt_to_src: dict[int, int] = {tj: si for si, tj in matches}

    # Fill in matched timings first
    for tgt_idx, src_idx in tgt_to_src.items():
        result[tgt_idx] = Timing(
            start=src_events[src_idx].start,
            end=src_events[src_idx].end,
        )

    # Interpolate runs of unmatched indices
    i = 0
    while i < n_tgt:
        if result[i] is not None:
            i += 1
            continue

        # Find the extent of this unmatched run
        run_start = i
        while i < n_tgt and result[i] is None:
            i += 1
        run_end = i - 1  # inclusive

        run_len = run_end - run_start + 1

        # Locate neighbours
        left_timing: Timing | None = result[run_start - 1] if run_start > 0 else None
        right_timing: Timing | None = result[run_end + 1] if run_end + 1 < n_tgt else None

        if left_timing is not None and right_timing is not None:
            # Distribute evenly in [left.end, right.start]
            gap_start = left_timing.end
            gap_end = right_timing.start
            gap = gap_end - gap_start
            slot = gap / (run_len + 1)
            for k, idx in enumerate(range(run_start, run_end + 1), start=1):
                orig_dur = tgt_events[idx].end - tgt_events[idx].start
                s = int(gap_start + k * slot)
                result[idx] = Timing(start=s, end=s + orig_dur)

        elif left_timing is not None:
            # Extrapolate forward; stack subtitles sequentially
            cursor = left_timing.end
            for idx in range(run_start, run_end + 1):
                orig_dur = tgt_events[idx].end - tgt_events[idx].start
                result[idx] = Timing(start=cursor, end=cursor + orig_dur)
                cursor += orig_dur

        elif right_timing is not None:
            # Extrapolate backward from right neighbour
            cursor = right_timing.start
            for idx in range(run_end, run_start - 1, -1):
                orig_dur = tgt_events[idx].end - tgt_events[idx].start
                cursor -= orig_dur
                result[idx] = Timing(start=cursor, end=cursor + orig_dur)

        else:
            # No anchor at all — keep original
            for idx in range(run_start, run_end + 1):
                result[idx] = Timing(
                    start=tgt_events[idx].start,
                    end=tgt_events[idx].end,
                )

    return result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def align(
    src_events: Sequence[TimedEvent],
    tgt_events: Sequence[TimedEvent],
    *,
    verbose: bool = False,
) -> tuple[list[Timing], list[tuple[int, int]]]:
    """Align *tgt_events* to *src_events* and return (timings, matches).

    Args:
        src_events: Events with correct timestamps.
        tgt_events: Events with correct text but wrong timestamps.
        verbose:    If True, caller may use *matches* for diagnostics.

    Returns:
        timings: One Timing per target event (same length as tgt_events).
        matches: Raw (src_idx, tgt_idx) pairs from LCS.
    """
    if not src_events:
        return [Timing(e.start, e.end) for e in tgt_events], []

    matches = lcs_align(src_events, tgt_events)
    timings = interpolate(tgt_events, matches, src_events)
    return timings, matches
