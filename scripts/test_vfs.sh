#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
for vfs in vfs/minimal.csv vfs/several.csv vfs/deep.csv; do
    printf '\n--- %s ---\n' "$vfs"
    ./run.sh --vfs "$vfs" --script scripts/stage3.txt
done
