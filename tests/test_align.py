"""Tests for subsync.align — dependency-free unit tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from subsync.align import bucket, lcs_align, interpolate, align, Timing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeEvent:
    start: int
    end: int
    text: str = ""


def make_events(*durations_ms: int, offset: int = 0) -> list[FakeEvent]:
    """Create a list of FakeEvents from a sequence of durations."""
    events: list[FakeEvent] = []
    cursor = offset
    for dur in durations_ms:
        events.append(FakeEvent(start=cursor, end=cursor + dur))
        cursor += dur + 200  # 200 ms gap between subtitles
    return events


# ---------------------------------------------------------------------------
# bucket()
# ---------------------------------------------------------------------------

class TestBucket:
    def test_short(self):
        assert bucket(0) == 0
        assert bucket(500) == 0
        assert bucket(999) == 0

    def test_medium(self):
        assert bucket(1000) == 1
        assert bucket(1800) == 1
        assert bucket(2500) == 1

    def test_long(self):
        assert bucket(2501) == 2
        assert bucket(5000) == 2
        assert bucket(10000) == 2

    def test_boundary_exactly_1000(self):
        assert bucket(1000) == 1

    def test_boundary_exactly_2500(self):
        assert bucket(2500) == 1

    def test_boundary_2501(self):
        assert bucket(2501) == 2


# ---------------------------------------------------------------------------
# lcs_align()
# ---------------------------------------------------------------------------

class TestLcsAlign:
    def test_identical_sequences(self):
        events = make_events(500, 1500, 3000)
        pairs = lcs_align(events, events)
        assert pairs == [(0, 0), (1, 1), (2, 2)]

    def test_empty_src(self):
        tgt = make_events(500, 1500)
        assert lcs_align([], tgt) == []

    def test_empty_tgt(self):
        src = make_events(500, 1500)
        assert lcs_align(src, []) == []

    def test_both_empty(self):
        assert lcs_align([], []) == []

    def test_no_common_buckets(self):
        # src all short (0), tgt all long (2)
        src = make_events(500, 600, 700)
        tgt = make_events(3000, 4000, 5000)
        pairs = lcs_align(src, tgt)
        assert pairs == []

    def test_partial_match(self):
        # src: short, medium, long  → buckets 0, 1, 2
        # tgt: short, long          → buckets 0, 2
        # LCS should match (0,0) and (2,1)
        src = make_events(500, 1500, 3000)
        tgt = make_events(500, 3000)
        pairs = lcs_align(src, tgt)
        assert (0, 0) in pairs
        assert (2, 1) in pairs

    def test_pairs_are_ordered(self):
        src = make_events(500, 1500, 3000, 500)
        tgt = make_events(500, 1500, 3000, 500)
        pairs = lcs_align(src, tgt)
        src_idxs = [p[0] for p in pairs]
        tgt_idxs = [p[1] for p in pairs]
        assert src_idxs == sorted(src_idxs)
        assert tgt_idxs == sorted(tgt_idxs)

    def test_mismatched_count_more_src(self):
        # src has extra entries — some src slots will be unmatched
        src = make_events(500, 1500, 3000, 1500, 500)
        tgt = make_events(500, 3000, 500)
        pairs = lcs_align(src, tgt)
        tgt_idxs = [p[1] for p in pairs]
        assert tgt_idxs == sorted(set(tgt_idxs))  # no duplicate tgt

    def test_mismatched_count_more_tgt(self):
        src = make_events(500, 3000, 500)
        tgt = make_events(500, 1500, 3000, 1500, 500)
        pairs = lcs_align(src, tgt)
        src_idxs = [p[0] for p in pairs]
        assert src_idxs == sorted(set(src_idxs))  # no duplicate src


# ---------------------------------------------------------------------------
# interpolate()
# ---------------------------------------------------------------------------

class TestInterpolate:
    def test_all_matched(self):
        src = make_events(500, 1500, 3000)
        tgt = make_events(400, 1200, 2800)
        matches = [(0, 0), (1, 1), (2, 2)]
        timings = interpolate(tgt, matches, src)
        assert len(timings) == 3
        assert timings[0].start == src[0].start
        assert timings[1].start == src[1].start
        assert timings[2].start == src[2].start

    def test_unmatched_middle_interpolated(self):
        # tgt has 3 events; src anchors at 0 and 2, leaving tgt[1] unmatched
        src = make_events(500, 1500, 3000)
        tgt = make_events(500, 800, 3000)
        matches = [(0, 0), (2, 2)]
        timings = interpolate(tgt, matches, src)
        assert len(timings) == 3
        # Middle timing must be between left anchor end and right anchor start
        assert timings[1].start >= timings[0].end
        assert timings[1].end <= timings[2].start

    def test_unmatched_at_start_extrapolates_backward(self):
        src = make_events(500, 1500)
        tgt = make_events(300, 1500)
        # Only tgt[1] is matched to src[1]
        matches = [(1, 1)]
        timings = interpolate(tgt, matches, src)
        assert len(timings) == 2
        # tgt[0] should be placed before tgt[1]
        assert timings[0].end <= timings[1].start

    def test_unmatched_at_end_extrapolates_forward(self):
        src = make_events(500, 1500)
        tgt = make_events(500, 300)
        # Only tgt[0] is matched to src[0]
        matches = [(0, 0)]
        timings = interpolate(tgt, matches, src)
        assert len(timings) == 2
        assert timings[1].start >= timings[0].end

    def test_no_matches_keeps_original(self):
        tgt = make_events(500, 1500, 3000)
        src = make_events(600, 1600, 3100)
        timings = interpolate(tgt, [], src)
        for t, e in zip(timings, tgt):
            assert t.start == e.start
            assert t.end == e.end

    def test_duration_preserved_for_matched(self):
        src = make_events(500, 1500)
        tgt = make_events(300, 800)  # different durations
        matches = [(0, 0), (1, 1)]
        timings = interpolate(tgt, matches, src)
        # Start/end come from src, not tgt
        assert timings[0].start == src[0].start
        assert timings[0].end == src[0].end
        assert timings[1].start == src[1].start
        assert timings[1].end == src[1].end


# ---------------------------------------------------------------------------
# align() — integration
# ---------------------------------------------------------------------------

class TestAlign:
    def test_empty_src_returns_original(self):
        tgt = make_events(500, 1500)
        timings, matches = align([], tgt)
        assert matches == []
        assert timings[0].start == tgt[0].start
        assert timings[1].start == tgt[1].start

    def test_same_count_identity(self):
        events = make_events(500, 1500, 3000)
        timings, matches = align(events, events)
        assert len(timings) == 3
        assert len(matches) == 3
        for t, e in zip(timings, events):
            assert t.start == e.start

    def test_output_length_matches_target(self):
        src = make_events(500, 1500, 3000, 500)
        tgt = make_events(500, 3000)
        timings, _ = align(src, tgt)
        assert len(timings) == len(tgt)

    def test_verbose_flag_does_not_raise(self):
        src = make_events(500, 1500, 3000)
        tgt = make_events(500, 1500, 3000)
        # verbose=True should not raise
        timings, matches = align(src, tgt, verbose=True)
        assert len(timings) == 3

    def test_more_target_than_source(self):
        src = make_events(500, 3000)
        tgt = make_events(500, 800, 1200, 3000)
        timings, matches = align(src, tgt)
        assert len(timings) == 4
        # Matched ones should have src timing
        matched_tgt = {tj for _, tj in matches}
        for si, tj in matches:
            assert timings[tj].start == src[si].start
