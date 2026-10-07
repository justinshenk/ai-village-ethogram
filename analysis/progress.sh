#!/bin/sh
# Usage: progress.sh <percent> <label>  — writes a one-line bar for the status line.
pct=$1; shift
filled=$((pct / 10)); bar=""
i=0; while [ $i -lt 10 ]; do [ $i -lt $filled ] && bar="${bar}█" || bar="${bar}░"; i=$((i+1)); done
printf '%s %s%% %s\n' "$bar" "$pct" "$*" > "$(dirname "$0")/../.claude/progress.txt"
