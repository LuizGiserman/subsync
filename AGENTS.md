# AGENTS.md

## Project overview
CLI tool to sync subtitle timestamps across language files.
Source file provides correct timing; target file provides correct text.
Output merges them using LCS-based alignment.

## Dev setup
1. Install uv: https://docs.astral.sh/uv/
2. `uv sync` — creates venv + installs deps
3. `uv run python -m subsync source.srt target.srt -v`

## Running tests
`uv run pytest`

## Key files
- `src/subsync/align.py` — LCS algorithm + interpolation (no external deps)
- `src/subsync/cli.py`   — argparse CLI, orchestrates parsing + alignment + output
- `tests/fixtures/`      — sample subtitle files for testing

## Notes for agents
- pysubs2 SSAEvent.start/.end are in milliseconds (int)
- pysubs2 auto-detects format from file extension on load
- align.py is intentionally dependency-free (easy to unit test)
- Always commit after each logical step; push at end of session
