#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The duplicates run exits 1 because the example files carry
# duplicate keys on purpose — that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- check the clean file ---"
python3 src/json_duplicate_key_checker.py examples/clean.json
echo "--- check the file with duplicates ---"
python3 src/json_duplicate_key_checker.py examples/duplicates.json || true
echo "--- check the whole examples folder ---"
python3 src/json_duplicate_key_checker.py examples/ || true
