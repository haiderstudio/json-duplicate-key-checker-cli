# json-duplicate-key-checker-cli

Find duplicate keys in JSON files, fail CI when a key appears twice.

[![CI](https://github.com/haiderstudio/json-duplicate-key-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/json-duplicate-key-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`json_duplicate_key_checker` reads JSON files and checks every
object in them for a key that appears twice:

- Standard JSON parsing silently keeps the last value when a key
  appears twice in one object and drops the rest — no error, no
  warning. A hand-edited config file can lose a value that way and
  nobody notices until something breaks. This tool reports every
  repeated key with its file, line number, and the object it sits
  in, and exits 1 when any duplicate is found — so it can fail a
  CI run. A clean file exits 0.
- The same key in different objects is fine: `"port"` under
  `"server"` and `"port"` under `"database"` are two different
  keys in two different objects, and this tool stays quiet. Only
  a repeat inside one object counts. That includes objects inside
  arrays: two items in one array can each carry `"id"`, but one
  item carrying `"id"` twice is a duplicate.
- Keys are compared exactly as JSON sees them: `"Port"` and
  `"port"` are different keys, and `"a"` and the escaped form
  `"\u0061"` are the same key.
- A file that is not valid JSON is reported too, with the line and
  column from the parser — a broken file fails the check rather
  than being skipped. A file that is not valid UTF-8 is reported
  the same way.
- Files come from the command line (one or more), or from a
  folder walk: every `.json` file under a folder, recursively by
  default (`--no-recursive` stops at the top level). `.git`
  folders are never walked, and directory links are never
  followed, so a link cycle cannot loop the check.
- `--exclude PATTERN` skips files by glob, for example
  `--exclude 'generated-*'`. It can be repeated.
- `--stdin` reads one JSON document from standard input.
- `--json` prints the result as machine-readable JSON (the
  summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never rewrites a
  file, sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not remove duplicate keys or rewrite a file. A
  duplicate is reported; deciding which value to keep is your
  job.
- It does not check that a JSON file is well formed beyond
  parsing it — that is Day 19's `json-formatter-validator-cli`
  job. This tool's one job is duplicate keys; a file can be
  valid JSON and still lose data to a repeated key.
- It does not check that a key exists, or that a value has the
  right type. Duplicate keys only.
- It does not fetch anything. Every input is a local file or
  standard input.

## Who it is for

Anyone who edits JSON config by hand and wants to know nothing
vanished silently: a developer keeping app settings, a docs
writer keeping translation files, or anyone adding a CI step
that fails the build when a key appears twice. A duplicated key
deletes a config value with no error at all — this catches it
before the file is deployed.

## How this differs from similar tools

The exact name `json-duplicate-key-checker-cli` matches 0
repositories on GitHub (checked Nov 8, 2026), and
`json duplicate key checker` and `json duplicate key cli`
match 0 too. The wider field is small and all 0 stars:
RebelBIrd/prettier-rm-duplicate-json-keys and
Dearest/prettier-plugin-remove-duplicate-json-keys are Prettier
plugins that *remove* duplicates — they rewrite your files, the
opposite of a report-only check. nradawg/duplicate-key-guard
catches duplicates by validating the token stream, in
JavaScript. veron-spec/json-key-audit is the closest thing to
this job — a read-only Python CLI that finds duplicate JSON
keys — at 0 stars with no test or CI claim. The research file
also lists Dexter-Ou/json-key-check (0 stars), the same job as
an untested script, and gloaysa/json-language-checker (0 stars),
which compares keys between two files — a different job.
None of them is a tested CLI that walks a folder, reports every
duplicate with a file and line, and exits 1 for CI. This tool
does that one job: a Python standard-library-only CLI that
reads JSON files, reports every repeated key with a file, line,
and object path, and exits 1 on a duplicate — no install
beyond Python, no website, no network.

## Install

Python standard library only — no packages to download. You need
Python 3.8 or newer. Clone the repo and run it in place:

```
git clone https://github.com/haiderstudio/json-duplicate-key-checker-cli.git
cd json-duplicate-key-checker-cli
python3 src/json_duplicate_key_checker.py examples/clean.json
```

```
OK — 1 file(s) checked, no duplicate keys.
```

## Usage

Check one file:

```
python3 src/json_duplicate_key_checker.py examples/clean.json
```

Check a file with duplicates:

```
python3 src/json_duplicate_key_checker.py examples/duplicates.json
```

```
FAIL examples/duplicates.json:3: duplicate key 'name' in object $
FAIL examples/duplicates.json:7: duplicate key 'port' in object $.server
FAIL examples/duplicates.json:12: duplicate key 'id' in object $.items[0]
Checked 1 file(s), 3 problem(s) in 1 file(s).
```

Check a whole folder:

```
python3 src/json_duplicate_key_checker.py examples/
```

```
FAIL examples/duplicates.json:3: duplicate key 'name' in object $
FAIL examples/duplicates.json:7: duplicate key 'port' in object $.server
FAIL examples/duplicates.json:12: duplicate key 'id' in object $.items[0]
FAIL examples/configs/app.json:3: duplicate key 'debug' in object $
Checked 3 file(s), 4 problem(s) in 2 file(s).
```

Check one document from standard input:

```
echo '{"a": 1, "a": 2}' | python3 src/json_duplicate_key_checker.py --stdin
```

```
FAIL <stdin>:1: duplicate key 'a' in object $
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

A broken file fails the check with the parser's position:

```
echo '{"a": 1,}' | python3 src/json_duplicate_key_checker.py --stdin
```

```
FAIL <stdin>:1: not valid JSON: Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
Checked 1 file(s), 1 problem(s) in 1 file(s).
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/json_duplicate_key_checker.py examples/duplicates.json --json
```

```
{
  "files": [
    {
      "file": "examples/duplicates.json",
      "problems": [
        {
          "line": 3,
          "key": "name",
          "path": "$",
          "error": ""
        },
        {
          "line": 7,
          "key": "port",
          "path": "$.server",
          "error": ""
        },
        {
          "line": 12,
          "key": "id",
          "path": "$.items[0]",
          "error": ""
        }
      ]
    }
  ],
  "summary": {
    "checked": 1,
    "files_with_problems": 1,
    "duplicates": 3,
    "errors": 0
  }
}
```

Exit codes: 0 when no duplicate is found, 1 when any duplicate
(or broken file) is found, 2 for a usage problem (no JSON files
given, a bad flag, a missing file or folder).

## Examples

### 1. Three duplicates in one file

`examples/duplicates.json` carries one of each case — a
top-level repeat, a nested repeat, and a repeat inside an array
item:

```
python3 src/json_duplicate_key_checker.py examples/duplicates.json
```

```
FAIL examples/duplicates.json:3: duplicate key 'name' in object $
FAIL examples/duplicates.json:7: duplicate key 'port' in object $.server
FAIL examples/duplicates.json:12: duplicate key 'id' in object $.items[0]
Checked 1 file(s), 3 problem(s) in 1 file(s).
```

### 2. The same key in different objects is fine

`examples/clean.json` repeats `"host"`, `"port"`, `"name"`,
and `"enabled"` — each time in a different object — and passes:

```
python3 src/json_duplicate_key_checker.py examples/clean.json
```

```
OK — 1 file(s) checked, no duplicate keys.
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the clean file (pass), then the file with
duplicates (fail, on purpose), then the whole folder (fail, on
purpose — it also picks up `examples/configs/app.json`, which
repeats `"debug"`). Its full output is in
`examples/sample-output.md`, ending with
`Checked 3 file(s), 4 problem(s) in 2 file(s).` The duplicates
and folder runs exit 1, which is the expected result — the
script ends with exit 0 so it can be run as a demo.

## How it is tested

54 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_json_duplicate_key_checker.py
```

The tests cover: duplicate detection (top level, nested,
inside array items, second array item, deep nesting, three
occurrences reported twice, escaped keys matching plain keys,
unicode keys, keys with spaces in the path display, a top-level
array of objects), the cases that must pass (same key in
different objects, case-different keys, clean objects, empty
objects and arrays, numbers, literals, strings with escaped
quotes and braces), line numbers (single-line, multi-line,
exact lines), broken files (trailing comma, empty document,
parser message and line), the CLI (exit 0/1/2, `--stdin`,
`--json` output, `--version`, bad flags, missing paths, empty
folders, folder walking, `--no-recursive`, `.git` skipped,
`--exclude`, several files at once, input files left
unchanged), the bundled examples (sample output compared
byte-for-byte against a fresh run, and the README-quoted
outputs checked against it), and hygiene checks (no
placeholder text, no absolute paths, stdlib imports only,
`.env` first in `.gitignore`).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking JSON for duplicate keys is not new — the similar tools
named above (the Prettier removal plugins, the JavaScript token
guard, the read-only audit CLI) are listed in "How this
differs" — but every line of code here is original, and the tool
builds on nothing but Python's standard library.
