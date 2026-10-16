#!/usr/bin/env bash
# Print the before/after table (Markdown) for your result slide.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
need python3
python3 "$ROOT/tools/compare.py" "$ROOT/results/before.json" "$ROOT/results/after.json"
