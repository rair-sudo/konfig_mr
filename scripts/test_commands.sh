#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
for stage in scripts/stage4.txt scripts/stage5.txt; do
    printf '\n--- %s ---\n' "$stage"
    ./run.sh --vfs vfs/deep.csv --script "$stage"
done
