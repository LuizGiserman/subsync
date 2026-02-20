"""CLI entry point for subsync."""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import pysubs2

from .align import align


# Formats that pysubs2 can write
_VALID_FORMATS = {"srt", "ass", "vtt"}

# Map common file extensions to pysubs2 format strings
_EXT_TO_FORMAT: dict[str, str] = {
    ".srt": "srt",
    ".ass": "ass",
    ".ssa": "ass",
    ".vtt": "vtt",
}


def _derive_output_path(target_path: Path, format_override: str | None) -> Path:
    """Return the default output path when -o is not provided."""
    ext = ("." + format_override) if format_override else target_path.suffix
    return target_path.with_name(target_path.stem + "_synced" + ext)


def _format_from_path(path: Path) -> str | None:
    return _EXT_TO_FORMAT.get(path.suffix.lower())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subsync",
        description=(
            "Merge timestamps from SOURCE (correct timing) into TARGET "
            "(correct text, wrong timing)."
        ),
    )
    parser.add_argument(
        "source",
        metavar="source",
        help="Subtitle file with CORRECT timestamps (language A)",
    )
    parser.add_argument(
        "target",
        metavar="target",
        help="Subtitle file with CORRECT text, wrong timestamps (language B)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Output file path (default: <target_stem>_synced.<ext>)",
    )
    parser.add_argument(
        "--format",
        metavar="FORMAT",
        choices=_VALID_FORMATS,
        default=None,
        help="Force output format: srt | ass | vtt",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print alignment details to stderr",
    )
    return parser


def run(args: list[str] | None = None) -> int:
    """Parse *args* and execute subsync.  Returns exit code."""
    parser = _build_parser()
    ns = parser.parse_args(args)

    source_path = Path(ns.source)
    target_path = Path(ns.target)

    # --- Load files ---
    try:
        src_file: pysubs2.SSAFile = pysubs2.load(str(source_path))
    except Exception as exc:
        print(f"subsync: error loading source file: {exc}", file=sys.stderr)
        return 1

    try:
        tgt_file: pysubs2.SSAFile = pysubs2.load(str(target_path))
    except Exception as exc:
        print(f"subsync: error loading target file: {exc}", file=sys.stderr)
        return 1

    src_events = src_file.events
    tgt_events = tgt_file.events

    # --- Validate ---
    if not tgt_events:
        print("subsync: target file has no subtitle events — nothing to do.", file=sys.stderr)
        return 1

    if not src_events:
        print(
            "subsync: warning: source file has no events; target keeps original timestamps.",
            file=sys.stderr,
        )

    if len(src_events) != len(tgt_events):
        print(
            f"subsync: warning: subtitle counts differ "
            f"(source={len(src_events)}, target={len(tgt_events)}); "
            "using LCS alignment.",
            file=sys.stderr,
        )

    # --- Align ---
    timings, matches = align(src_events, tgt_events, verbose=ns.verbose)

    if ns.verbose:
        matched_src = {si for si, _ in matches}
        matched_tgt = {tj for _, tj in matches}
        unmatched_src = sorted(set(range(len(src_events))) - matched_src)
        unmatched_tgt = sorted(set(range(len(tgt_events))) - matched_tgt)

        print(f"subsync: LCS matched {len(matches)} pairs", file=sys.stderr)
        if unmatched_src:
            print(
                f"subsync: {len(unmatched_src)} source slot(s) with no target text "
                f"(indices: {unmatched_src[:10]}{'...' if len(unmatched_src) > 10 else ''})",
                file=sys.stderr,
            )
        if unmatched_tgt:
            print(
                f"subsync: {len(unmatched_tgt)} target event(s) interpolated "
                f"(indices: {unmatched_tgt[:10]}{'...' if len(unmatched_tgt) > 10 else ''})",
                file=sys.stderr,
            )

    # --- Build output SSAFile ---
    out_file = copy.deepcopy(tgt_file)
    for event, timing in zip(out_file.events, timings):
        event.start = timing.start
        event.end = timing.end

    # --- Determine output path and format ---
    output_path = Path(ns.output) if ns.output else _derive_output_path(target_path, ns.format)
    format_str = ns.format or _format_from_path(output_path)

    # --- Write ---
    try:
        if format_str:
            out_file.save(str(output_path), format_=format_str)
        else:
            out_file.save(str(output_path))
    except Exception as exc:
        print(f"subsync: error writing output: {exc}", file=sys.stderr)
        return 1

    print(
        f"subsync: wrote {len(out_file.events)} subtitles to {output_path}",
        file=sys.stderr,
    )
    return 0


def main() -> None:
    sys.exit(run())
