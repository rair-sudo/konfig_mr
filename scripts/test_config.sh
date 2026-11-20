#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
printf '%s\n' '--- По умолчанию ---'
printf 'exit\n' | ./run.sh
printf '%s\n' '--- Только VFS ---'
printf 'exit\n' | ./run.sh --vfs vfs/minimal.csv
printf '%s\n' '--- Только скрипт ---'
./run.sh --script scripts/stage2.txt
printf '%s\n' '--- Оба параметра ---'
./run.sh --vfs vfs/minimal.csv --script scripts/stage2.txt
