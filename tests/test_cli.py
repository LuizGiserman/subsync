"""Tests for subsync.cli — output path derivation, format detection, end-to-end."""

from __future__ import annotations

from pathlib import Path

import pysubs2
import pytest

from subsync.cli import _derive_output_path, _format_from_path, _load_file, run

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# _derive_output_path()
# ---------------------------------------------------------------------------

class TestDeriveOutputPath:
    def test_same_extension_no_override(self):
        p = _derive_output_path(Path("/tmp/movie_fr.srt"), None)
        assert p == Path("/tmp/movie_fr_synced.srt")

    def test_format_override_changes_extension(self):
        p = _derive_output_path(Path("/tmp/movie_fr.srt"), "vtt")
        assert p == Path("/tmp/movie_fr_synced.vtt")

    def test_ass_extension(self):
        p = _derive_output_path(Path("/movies/sub.ass"), None)
        assert p == Path("/movies/sub_synced.ass")

    def test_vtt_input(self):
        p = _derive_output_path(Path("subs/en.vtt"), None)
        assert p == Path("subs/en_synced.vtt")

    def test_stem_with_dots(self):
        p = _derive_output_path(Path("/tmp/movie.part1.srt"), None)
        assert p.name == "movie.part1_synced.srt"


# ---------------------------------------------------------------------------
# _format_from_path()
# ---------------------------------------------------------------------------

class TestFormatFromPath:
    def test_srt(self):
        assert _format_from_path(Path("out.srt")) == "srt"

    def test_ass(self):
        assert _format_from_path(Path("out.ass")) == "ass"

    def test_ssa(self):
        assert _format_from_path(Path("out.ssa")) == "ass"

    def test_vtt(self):
        assert _format_from_path(Path("out.vtt")) == "vtt"

    def test_unknown_extension(self):
        assert _format_from_path(Path("out.xyz")) is None

    def test_case_insensitive(self):
        assert _format_from_path(Path("out.SRT")) == "srt"
        assert _format_from_path(Path("out.ASS")) == "ass"


# ---------------------------------------------------------------------------
# run() — end-to-end with fixture files
# ---------------------------------------------------------------------------

class TestRunEndToEnd:
    def test_same_count_srt_to_srt(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source_same.srt"),
            str(FIXTURES / "target_same.srt"),
            "-o", str(out),
        ])
        assert rc == 0
        assert out.exists()
        result = pysubs2.load(str(out))
        # Timestamps must come from source
        src = pysubs2.load(str(FIXTURES / "source_same.srt"))
        tgt = pysubs2.load(str(FIXTURES / "target_same.srt"))
        assert len(result.events) == len(tgt.events)
        for r_ev, s_ev in zip(result.events, src.events):
            assert r_ev.start == s_ev.start
            assert r_ev.end == s_ev.end

    def test_text_preserved(self, tmp_path):
        out = tmp_path / "out.srt"
        run([
            str(FIXTURES / "source_same.srt"),
            str(FIXTURES / "target_same.srt"),
            "-o", str(out),
        ])
        result = pysubs2.load(str(out))
        tgt = pysubs2.load(str(FIXTURES / "target_same.srt"))
        for r_ev, t_ev in zip(result.events, tgt.events):
            assert r_ev.text == t_ev.text

    def test_mismatched_count(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source_en.srt"),
            str(FIXTURES / "target_mismatch.srt"),
            "-o", str(out),
        ])
        assert rc == 0
        result = pysubs2.load(str(out))
        tgt = pysubs2.load(str(FIXTURES / "target_mismatch.srt"))
        assert len(result.events) == len(tgt.events)

    def test_verbose_flag(self, tmp_path, capsys):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source_en.srt"),
            str(FIXTURES / "target_fr.srt"),
            "-o", str(out),
            "-v",
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "LCS matched" in captured.err

    def test_default_output_path(self, tmp_path):
        import shutil
        tgt = tmp_path / "target_fr.srt"
        shutil.copy(str(FIXTURES / "target_fr.srt"), str(tgt))
        rc = run([
            str(FIXTURES / "source_en.srt"),
            str(tgt),
        ])
        assert rc == 0
        expected = tmp_path / "target_fr_synced.srt"
        assert expected.exists()

    def test_format_override_to_vtt(self, tmp_path):
        out = tmp_path / "out.vtt"
        rc = run([
            str(FIXTURES / "source_en.srt"),
            str(FIXTURES / "target_fr.srt"),
            "-o", str(out),
            "--format", "vtt",
        ])
        assert rc == 0
        assert out.exists()
        content = out.read_text()
        assert content.startswith("WEBVTT")

    def test_cross_format_ass_source(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source.ass"),
            str(FIXTURES / "target_fr.srt"),
            "-o", str(out),
        ])
        # source has 3 events, target has 5 — mismatched, but should not crash
        assert rc == 0
        result = pysubs2.load(str(out))
        tgt = pysubs2.load(str(FIXTURES / "target_fr.srt"))
        assert len(result.events) == len(tgt.events)

    def test_missing_source_returns_error(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(tmp_path / "nonexistent.srt"),
            str(FIXTURES / "target_fr.srt"),
            "-o", str(out),
        ])
        assert rc == 1

    def test_missing_target_returns_error(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source_en.srt"),
            str(tmp_path / "nonexistent.srt"),
            "-o", str(out),
        ])
        assert rc == 1

    def test_output_timestamps_monotonic(self, tmp_path):
        out = tmp_path / "out.srt"
        run([
            str(FIXTURES / "source_en.srt"),
            str(FIXTURES / "target_fr.srt"),
            "-o", str(out),
        ])
        result = pysubs2.load(str(out))
        for ev in result.events:
            assert ev.start < ev.end, "Each event must have positive duration"


# ---------------------------------------------------------------------------
# _load_file() — encoding fallback
# ---------------------------------------------------------------------------

class TestLoadFile:
    def test_loads_utf8(self):
        f = _load_file(FIXTURES / "source_en.srt")
        assert len(f.events) == 5

    def test_loads_cp1252_fixture(self):
        # tests/fixtures/target_cp1252.srt is saved in Windows-1252 encoding
        f = _load_file(FIXTURES / "target_cp1252.srt")
        assert len(f.events) == 3
        # French accented characters must survive the round-trip
        combined = " ".join(ev.text for ev in f.events)
        assert "é" in combined
        assert "à" in combined

    def test_loads_latin1_file(self, tmp_path):
        srt = (
            "1\r\n00:00:01,000 --> 00:00:02,000\r\n"
            "Stra\xdfe und Geb\xe4ude.\r\n\r\n"
        )
        p = tmp_path / "latin1.srt"
        p.write_bytes(srt.encode("latin-1"))
        f = _load_file(p)
        assert len(f.events) == 1
        assert "Straße" in f.events[0].text

    def test_explicit_encoding_respected(self):
        # Passing encoding= explicitly should work without trying fallbacks
        f = _load_file(FIXTURES / "target_cp1252.srt", encoding="cp1252")
        assert len(f.events) == 3

    def test_raises_on_unreadable_file(self, tmp_path):
        p = tmp_path / "bad.srt"
        p.write_bytes(b"\xff\xfe" + b"\x00" * 10)  # not valid in any fallback
        with pytest.raises(Exception):
            _load_file(p)

    def test_end_to_end_cp1252_target(self, tmp_path):
        out = tmp_path / "out.srt"
        rc = run([
            str(FIXTURES / "source_same.srt"),
            str(FIXTURES / "target_cp1252.srt"),
            "-o", str(out),
        ])
        assert rc == 0
        result = pysubs2.load(str(out))
        assert len(result.events) == 3
        combined = " ".join(ev.text for ev in result.events)
        assert "é" in combined
