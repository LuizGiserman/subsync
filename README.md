# subsync

Subtitle synchronization CLI — combine correct timestamps from one subtitle file
with correct text from another (e.g., when you have a well-timed English SRT and a
translated French SRT with bad timestamps).

## Installation

```bash
uv sync
```

## Usage

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

### Examples

```bash
# Basic usage
uv run python -m subsync source_en.srt target_fr.srt

# Verbose alignment info
uv run python -m subsync source_en.srt target_fr.srt -v

# Cross-format output
uv run python -m subsync source.srt target.ass --format vtt -o output.vtt
```

## How it works

1. Load both subtitle files with [pysubs2](https://github.com/tkarabela/pysubs2)
2. Quantize each subtitle's duration into buckets (Short/Medium/Long)
3. Run LCS (Longest Common Subsequence) on the bucket sequences to find the best
   timestamp↔text alignment without comparing text (works across languages)
4. Interpolate timestamps for unmatched target entries from neighboring anchors
5. Write output combining source timestamps with target text

## Running tests

```bash
uv run pytest
```
