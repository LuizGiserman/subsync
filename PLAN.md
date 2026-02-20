# Plan: `subsync` — Subtitle Synchronization CLI (Python)

## Context
The user has a correctly-timed subtitle file (language A) and a second subtitle file
with correct text but wrong timestamps (language B, likely a translation). The goal is
to produce a new file combining the text from file B with the timestamps from file A.

When the two files have different subtitle counts (due to merges/splits during
translation), LCS on duration fingerprints finds the best alignment without comparing
text (which is in different languages).

## Tech Stack
- **Language**: Python 3
- **Package manager / venv**: `uv`
- **Key library**: `pysubs2` — handles SRT, ASS/SSA, VTT parsing/writing natively
- **Repo hosting**: GitHub (via `gh` CLI)

## CLI Interface
```
subsync [options] <source> <target>

Arguments:
  source      Subtitle file with CORRECT timestamps (language A)
  target      Subtitle file with CORRECT text, wrong timestamps (language B)

Options:
  -o, --output PATH     Output file path (default: <target_name>_synced.<ext>)
  --format FORMAT       Force output format: srt | ass | vtt
  -v, --verbose         Print alignment details to stderr
```

## Project Layout
```
subsync/
├── .github/
├── AGENTS.md            # Notes for AI agents working in this repo
├── pyproject.toml       # uv-managed project (replaces requirements.txt)
├── src/
│   └── subsync/
│       ├── __init__.py
│       ├── __main__.py  # entry point (`uv run python -m subsync`)
│       ├── cli.py       # argparse CLI wiring
│       └── align.py     # LCS alignment + interpolation
└── tests/
    ├── fixtures/        # sample .srt/.ass/.vtt files
    └── test_align.py
```

## Implementation Steps

### Step 1 — GitHub repo + project scaffold ✅
1. `gh repo create subsync --public --description "Subtitle sync CLI" --clone`
2. `cd subsync && uv init --name subsync`  (creates pyproject.toml, .python-version)
3. `uv add pysubs2`
4. Create `AGENTS.md`
5. Initial commit + push

### Step 2 — `align.py` ✅
Core alignment logic — pure Python, no pysubs2 dependency:

**Duration bucket quantization:**
```python
def bucket(duration_ms: float) -> int:
    if duration_ms < 1000: return 0   # Short
    if duration_ms <= 2500: return 1  # Medium
    return 2                          # Long
```

**LCS on bucket sequences:**
- Standard O(n*m) DP table comparing bucket values
- Backtrack to get matched `(src_idx, tgt_idx)` pairs in order

**Interpolation for unmatched target entries:**
- Find nearest matched neighbors left and right for each unmatched index
- Distribute evenly in the time gap between `left.end` and `right.start`
- Fallback: if only one neighbor, extrapolate using original duration
- If no neighbors at all, keep original timing unchanged

Commit: `"add LCS alignment module"`

### Step 3 — `cli.py` + `__main__.py` ✅
Flow:
```
1. argparse: source, target, -o, --format, -v
2. pysubs2.load(source_path)  → SSAFile (auto-detects format)
3. pysubs2.load(target_path)  → SSAFile
4. Warn to stderr if counts differ
5. align.align(src.events, tgt.events, verbose=...) → aligned events list
6. Build output: copy target SSAFile, replace .events with aligned list
7. Derive output path if -o not given: <target_stem>_synced.<ext>
8. output_file.save(output_path, format_=format_override or detected_from_ext)
9. Print summary (N subtitles written to path) to stderr
```

**Key pysubs2 API:**
- `pysubs2.load(path)` → `SSAFile`  (auto-detect: srt/ass/vtt/sub)
- `file.events` → `list[SSAEvent]`  (`.start`, `.end` in ms, `.text`)
- `file.save(path, format_=...)` → write (format_: `"srt"`, `"ass"`, `"vtt"`)

Note: `SSAFile` has no `.copy()` method — use `copy.deepcopy(tgt_file)` instead.

Commit: `"add CLI and main entry point"`

### Step 4 — AGENTS.md content ✅
```markdown
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
```

### Step 5 — Tests + fixtures ✅
Test coverage:
- `tests/test_align.py`: `bucket()`, `lcs_align()`, `interpolate()`, `align()` — 26 tests
- `tests/test_cli.py`: output path derivation, format detection, end-to-end — 21 tests
- `tests/fixtures/`: SRT pairs (same-count, mismatched count), ASS source, cross-format

**Total: 47 tests, all passing.**

### Step 6 — Final push ✅
- `git push` to GitHub

## Edge Cases
| Case | Handling |
|------|----------|
| Same count | LCS is 1:1; no interpolation |
| Wildly different counts | LCS matches longest common pattern; rest interpolated |
| Empty source | Warning; target keeps original timestamps |
| Empty target | Fatal error and exit 1 |
| Cross-format (SRT→ASS) | pysubs2 handles; output format follows target or `--format` |
| Unmatched source entries | Reported to stderr (timing slot with no target text) |

## Verification
```bash
uv sync
uv run python -m subsync source_en.srt target_fr.srt -v
# Check: output timestamps match source, text matches target

uv run python -m subsync source.srt target.ass --format vtt
# Check: valid VTT output

uv run pytest
```

## Implementation Notes (lessons learned)
- `pysubs2.SSAFile` has no `.copy()` method — use `copy.deepcopy(tgt_file)`
- `uv pip install -e .` is needed for editable installs so tests can import the package
- Duration bucket boundaries: `< 1000` = Short, `1000–2500` = Medium, `> 2500` = Long
- Fixture subtitle durations must have matching bucket sequences for 1:1 LCS test cases
