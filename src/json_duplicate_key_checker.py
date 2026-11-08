#!/usr/bin/env python3
"""Find duplicate keys in JSON files, fail CI when a key appears twice.

Run: python3 src/json_duplicate_key_checker.py examples/clean.json
     python3 src/json_duplicate_key_checker.py examples/duplicates.json
     python3 src/json_duplicate_key_checker.py examples/
     python3 src/json_duplicate_key_checker.py --stdin < config.json

The problem is quiet: standard JSON parsing silently keeps the last
value when a key appears twice in one object and drops the rest —
no error, no warning. A hand-edited config file can lose a value
that way and nobody notices until something breaks. This tool
reads each JSON file, reports every key that appears twice in the
same object — with its file, line number, and the object it sits
in — and exits 1 when any duplicate is found, so it can fail a CI
run. A clean file exits 0.

The same key in different objects is fine: `"port"` under
`"server"` and `"port"` under `"database"` are two different keys
in two different objects, and this tool stays quiet. Only a repeat
inside one object counts. Keys are compared exactly as JSON sees
them, so `"Port"` and `"port"` are different keys, and `"a"` and
the escaped form `"\\u0061"` are the same key.

A file that is not valid JSON is reported too, with the line and
column from the parser — a broken file fails the check rather than
being skipped. A file that is not valid UTF-8 is reported the same
way.

It never rewrites a file. It is report-only and runs fully offline:
it sends nothing anywhere and needs no API key.

Exit codes: 0 when no duplicate is found, 1 when any duplicate (or
broken file) is found, 2 for a usage or input problem (a missing
path, a bad flag, no JSON files to check).

Python standard library only.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

VERSION = "1.0.0"


def _child_path(path, key):
    """Append one object key to a JSON path for display."""
    if key.isidentifier() or key.replace("-", "_").isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key)}]"


class _KeyScanner:
    """Walk valid JSON text and record every object key with its line.

    The text is checked with json.loads first (see check_text), so
    this scanner only ever runs on valid JSON. It keeps a stack of
    objects: a key that repeats inside one object is a duplicate,
    and the same key in a different object is not.
    """

    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1
        self.problems = []

    def _skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\n\r":
            if self.text[self.pos] == "\n":
                self.line += 1
            self.pos += 1

    def _parse_string(self):
        start = self.pos
        self.pos += 1
        while True:
            char = self.text[self.pos]
            if char == "\\":
                self.pos += 2
                continue
            if char == '"':
                self.pos += 1
                break
            if char == "\n":
                self.line += 1
            self.pos += 1
        return json.loads(self.text[start:self.pos])

    def _parse_number(self):
        while self.pos < len(self.text) and self.text[self.pos] in "-+0123456789.eE":
            self.pos += 1

    def _parse_literal(self):
        while self.pos < len(self.text) and self.text[self.pos].isalpha():
            self.pos += 1

    def _parse_value(self, path):
        self._skip_ws()
        char = self.text[self.pos]
        if char == "{":
            self._parse_object(path)
        elif char == "[":
            self._parse_array(path)
        elif char == '"':
            self._parse_string()
        elif char in "-0123456789":
            self._parse_number()
        else:
            self._parse_literal()

    def _parse_object(self, path):
        self.pos += 1
        self._skip_ws()
        seen = {}
        if self.text[self.pos] == "}":
            self.pos += 1
            return
        while True:
            self._skip_ws()
            key_line = self.line
            key = self._parse_string()
            if key in seen:
                self.problems.append((path, key, key_line))
            else:
                seen[key] = key_line
            self._skip_ws()
            self.pos += 1
            self._parse_value(_child_path(path, key))
            self._skip_ws()
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            self.pos += 1
            return

    def _parse_array(self, path):
        self.pos += 1
        self._skip_ws()
        index = 0
        if self.text[self.pos] == "]":
            self.pos += 1
            return
        while True:
            self._parse_value(f"{path}[{index}]")
            index += 1
            self._skip_ws()
            if self.text[self.pos] == ",":
                self.pos += 1
                continue
            self.pos += 1
            return


def check_text(text):
    """Return the problems in one JSON document as a list of dicts.

    Each problem has `line`, `key`, and `path` (the object the key
    sits in, `$` for the top level). A document that is not valid
    JSON returns one problem with an empty key and the parser's
    message.
    """
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return [{"line": exc.lineno, "key": "", "path": "", "error": str(exc)}]
    scanner = _KeyScanner(text)
    scanner._parse_value("$")
    return [
        {"line": line, "key": key, "path": path, "error": ""}
        for path, key, line in scanner.problems
    ]


def collect_from_file(path):
    """Return the problems in one file, as a list of dicts."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [
            {
                "line": 0,
                "key": "",
                "path": "",
                "error": "file is not valid UTF-8",
            }
        ]
    except OSError as exc:
        return [
            {
                "line": 0,
                "key": "",
                "path": "",
                "error": f"cannot read file: {exc.strerror}",
            }
        ]
    return check_text(text)


def gather(paths, exclude, recursive):
    """Walk the given paths and return (entries, checked_files).

    entries is a list of (file, problem); checked_files is a list
    of every JSON file read, clean or not.
    """
    entries = []
    checked = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(raw)
        if path.is_file():
            checked.append(str(path))
            for problem in collect_from_file(path):
                entries.append((str(path), problem))
            continue
        if recursive:
            for dirpath, dirnames, filenames in _walk(path):
                for name in filenames:
                    candidate = Path(dirpath) / name
                    if candidate.suffix != ".json":
                        continue
                    if _excluded(candidate, path, exclude):
                        continue
                    checked.append(str(candidate))
                    for problem in collect_from_file(candidate):
                        entries.append((str(candidate), problem))
        else:
            for candidate in sorted(path.iterdir()):
                if not candidate.is_file():
                    continue
                if candidate.suffix != ".json":
                    continue
                if _excluded(candidate, path, exclude):
                    continue
                checked.append(str(candidate))
                for problem in collect_from_file(candidate):
                    entries.append((str(candidate), problem))
    return entries, checked


def _walk(root):
    """os.walk that never enters .git and never follows links."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        yield dirpath, dirnames, sorted(filenames)


def _excluded(candidate, root, patterns):
    name = candidate.name
    try:
        rel = str(candidate.relative_to(root))
    except ValueError:
        rel = name
    return any(
        fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern)
        for pattern in patterns
    )


def _format_problem(location, problem):
    if problem["error"]:
        if problem["line"]:
            return f"FAIL {location}:{problem['line']}: not valid JSON: {problem['error']}"
        return f"FAIL {location}: {problem['error']}"
    return (
        f"FAIL {location}:{problem['line']}: duplicate key "
        f"'{problem['key']}' in object {problem['path']}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="json-duplicate-key-checker-cli",
        description="Find duplicate keys in JSON files.",
    )
    parser.add_argument("paths", nargs="*", help="files or folders to check")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one JSON document from standard input",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not walk into subfolders",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON (summary goes to stderr)",
    )
    parser.add_argument("--version", action="store_true", help="print the version")
    args = parser.parse_args(argv)

    if args.version:
        print(f"json-duplicate-key-checker-cli {VERSION}")
        return 0

    entries = []
    checked_files = set()
    try:
        if args.paths:
            found, checked = gather(
                args.paths, args.exclude, not args.no_recursive
            )
            entries.extend(found)
            checked_files.update(checked)
    except FileNotFoundError as exc:
        print(f"error: no such file or folder: {exc}", file=sys.stderr)
        return 2

    if args.stdin:
        for problem in check_text(sys.stdin.read()):
            entries.append(("<stdin>", problem))
        checked_files.add("<stdin>")

    if not checked_files:
        print("error: no JSON files to check", file=sys.stderr)
        return 2

    problems = entries
    duplicates = [p for _f, p in problems if not p["error"]]
    errors = [p for _f, p in problems if p["error"]]
    bad_files = len({f for f, _p in problems})
    total = len(problems)

    if args.json:
        files = []
        for name in sorted(checked_files):
            file_problems = [p for f, p in problems if f == name]
            files.append({"file": name, "problems": file_problems})
        result = {
            "files": files,
            "summary": {
                "checked": len(checked_files),
                "files_with_problems": bad_files,
                "duplicates": len(duplicates),
                "errors": len(errors),
            },
        }
        print(json.dumps(result, indent=2))
        if problems:
            print(
                f"Checked {len(checked_files)} file(s), {total} "
                f"problem(s) in {bad_files} file(s).",
                file=sys.stderr,
            )
        else:
            print(
                f"OK — {len(checked_files)} file(s) checked, "
                "no duplicate keys.",
                file=sys.stderr,
            )
        return 1 if problems else 0

    for location, problem in problems:
        print(_format_problem(location, problem))
    if problems:
        print(
            f"Checked {len(checked_files)} file(s), {total} "
            f"problem(s) in {bad_files} file(s)."
        )
        return 1
    print(
        f"OK — {len(checked_files)} file(s) checked, no duplicate keys."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
