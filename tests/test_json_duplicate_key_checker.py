"""Tests for json_duplicate_key_checker — standard library unittest only."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(SRC))

import json_duplicate_key_checker as checker  # noqa: E402


def run_cli(*args, cwd=None, stdin=None):
    argv = [sys.executable, str(SRC / "json_duplicate_key_checker.py"), *args]
    return subprocess.run(
        argv, capture_output=True, text=True, cwd=cwd or ROOT, input=stdin
    )


def write(tmp, name, text=""):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def problems(text):
    return checker.check_text(text)


class CheckTextTests(unittest.TestCase):
    def test_clean_object(self):
        self.assertEqual(problems('{"a": 1, "b": 2}'), [])

    def test_empty_object_and_array(self):
        self.assertEqual(problems("{}"), [])
        self.assertEqual(problems("[]"), [])
        self.assertEqual(problems('{"a": {}}'), [])

    def test_top_level_duplicate(self):
        found = problems('{"name": "x", "name": "y"}')
        self.assertEqual(
            found,
            [{"line": 1, "key": "name", "path": "$", "error": ""}],
        )

    def test_nested_duplicate(self):
        text = '{\n  "server": {\n    "port": 1,\n    "port": 2\n  }\n}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "port")
        self.assertEqual(found[0]["path"], "$.server")
        self.assertEqual(found[0]["line"], 4)

    def test_duplicate_inside_array_item(self):
        text = '{\n  "items": [\n    {"id": 1, "id": 2},\n    {"id": 3}\n  ]\n}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "id")
        self.assertEqual(found[0]["path"], "$.items[0]")
        self.assertEqual(found[0]["line"], 3)

    def test_same_key_in_different_objects_is_not_a_duplicate(self):
        text = (
            '{\n  "server": {"port": 1},\n  "database": {"port": 2},\n'
            '  "items": [{"name": "a"}, {"name": "b"}]\n}'
        )
        self.assertEqual(problems(text), [])

    def test_case_different_keys_are_not_duplicates(self):
        self.assertEqual(problems('{"Port": 1, "port": 2}'), [])

    def test_three_occurrences_reported_twice(self):
        found = problems('{"a": 1, "a": 2, "a": 3}')
        self.assertEqual(len(found), 2)
        self.assertTrue(all(p["key"] == "a" for p in found))

    def test_escaped_key_matches_plain_key(self):
        found = problems('{"a": 1, "\\u0061": 2}')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "a")

    def test_deeply_nested_duplicate(self):
        text = '{\n  "a": {\n    "b": {\n      "c": 1,\n      "c": 2\n    }\n  }\n}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], "$.a.b")
        self.assertEqual(found[0]["line"], 5)

    def test_duplicate_in_second_array_item(self):
        text = '{\n  "items": [\n    {"id": 1},\n    {"id": 2, "id": 3}\n  ]\n}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], "$.items[1]")

    def test_single_line_json_line_is_one(self):
        found = problems('{"a": 1, "a": 2}')
        self.assertEqual(found[0]["line"], 1)

    def test_multiline_line_numbers(self):
        text = '{\n  "a": 1,\n  "b": 2,\n  "a": 3\n}'
        found = problems(text)
        self.assertEqual(found[0]["line"], 4)

    def test_invalid_json_reports_parser_error(self):
        found = problems('{"a": 1,}')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "")
        self.assertIn("Expecting property name", found[0]["error"])
        self.assertEqual(found[0]["line"], 1)

    def test_empty_document_is_invalid(self):
        found = problems("")
        self.assertEqual(len(found), 1)
        self.assertIn("Expecting value", found[0]["error"])

    def test_trailing_comma_in_array_is_invalid(self):
        found = problems("[1, 2,]")
        self.assertEqual(len(found), 1)
        self.assertIn("Expecting value", found[0]["error"])

    def test_primitives_and_literals_parse(self):
        self.assertEqual(
            problems('[1, -2.5, 1e10, true, false, null, "x"]'), []
        )
        self.assertEqual(problems('{"a": NaN}'), [])

    def test_string_escapes_do_not_confuse_scanner(self):
        text = '{"a": "has \\"quote\\" and } brace", "a": 2}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "a")

    def test_unicode_key(self):
        found = problems('{"café": 1, "café": 2}')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "café")

    def test_key_with_space_in_path_display(self):
        text = '{\n  "my key": {\n    "x": 1,\n    "x": 2\n  }\n}'
        found = problems(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], '$["my key"]')

    def test_top_level_array_of_objects(self):
        found = problems('[{"a": 1, "a": 2}]')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], "$[0]")


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_clean_file_has_no_problems(self):
        path = write(self.tmp.name, "good.json", '{"a": 1}\n')
        self.assertEqual(checker.collect_from_file(path), [])

    def test_non_utf8_file_is_a_problem(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_bytes(b'{"a": 1}\n\xff\xfe\n')
        found = checker.collect_from_file(path)
        self.assertEqual(len(found), 1)
        self.assertIn("not valid UTF-8", found[0]["error"])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            checker.gather(
                [str(Path(self.tmp.name) / "nope.json")], [], True
            )

    def test_gather_counts_clean_files(self):
        write(self.tmp.name, "good.json", '{"a": 1}\n')
        write(self.tmp.name, "bad.json", '{"a": 1, "a": 2}\n')
        entries, checked = checker.gather([self.tmp.name], [], True)
        self.assertEqual(len(checked), 2)
        self.assertEqual(len(entries), 1)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_clean_file_exits_zero(self):
        path = write(self.tmp.name, "good.json", '{"a": 1, "b": 2}\n')
        result = run_cli(str(path))
        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "OK — 1 file(s) checked, no duplicate keys.", result.stdout
        )

    def test_bad_file_exits_one_with_line_numbers(self):
        path = write(
            self.tmp.name,
            "bad.json",
            '{\n  "name": "x",\n  "name": "y"\n}\n',
        )
        result = run_cli(str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            f"FAIL {path}:3: duplicate key 'name' in object $",
            result.stdout,
        )
        self.assertIn(
            "Checked 1 file(s), 1 problem(s) in 1 file(s).", result.stdout
        )

    def test_top_level_and_nested_and_array_cases(self):
        path = write(
            self.tmp.name,
            "mixed.json",
            '{\n  "a": 1,\n  "a": 2,\n  "s": {"p": 1, "p": 2},\n'
            '  "items": [{"id": 1, "id": 2}]\n}\n',
        )
        result = run_cli(str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate key 'a' in object $", result.stdout)
        self.assertIn("duplicate key 'p' in object $.s", result.stdout)
        self.assertIn(
            "duplicate key 'id' in object $.items[0]", result.stdout
        )

    def test_same_key_in_different_objects_passes(self):
        path = write(
            self.tmp.name,
            "ok.json",
            '{"server": {"port": 1}, "database": {"port": 2}}\n',
        )
        result = run_cli(str(path))
        self.assertEqual(result.returncode, 0)

    def test_invalid_json_exits_one(self):
        path = write(self.tmp.name, "broken.json", '{"a": 1,}\n')
        result = run_cli(str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid JSON", result.stdout)
        self.assertIn("Expecting property name", result.stdout)

    def test_stdin_duplicate(self):
        result = run_cli("--stdin", stdin='{"a": 1, "a": 2}\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "FAIL <stdin>:1: duplicate key 'a' in object $", result.stdout
        )

    def test_stdin_clean(self):
        result = run_cli("--stdin", stdin='{"a": 1}\n')
        self.assertEqual(result.returncode, 0)
        self.assertIn("no duplicate keys", result.stdout)

    def test_stdin_invalid(self):
        result = run_cli("--stdin", stdin='{"a": 1,}\n')
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid JSON", result.stdout)

    def test_json_output_parses(self):
        path = write(
            self.tmp.name, "bad.json", '{\n  "a": 1,\n  "a": 2\n}\n'
        )
        result = run_cli(str(path), "--json")
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(data["summary"]["checked"], 1)
        self.assertEqual(data["summary"]["duplicates"], 1)
        self.assertEqual(data["summary"]["files_with_problems"], 1)
        self.assertEqual(data["files"][0]["problems"][0]["key"], "a")
        self.assertIn("Checked 1 file(s)", result.stderr)

    def test_json_clean(self):
        path = write(self.tmp.name, "good.json", '{"a": 1}\n')
        result = run_cli(str(path), "--json")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["summary"]["duplicates"], 0)
        self.assertIn("no duplicate keys", result.stderr)

    def test_version(self):
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("json-duplicate-key-checker-cli", result.stdout)

    def test_missing_path_exits_two(self):
        result = run_cli(str(Path(self.tmp.name) / "nope.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("no such file or folder", result.stderr)

    def test_no_input_exits_two(self):
        result = run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no JSON files to check", result.stderr)

    def test_empty_folder_exits_two(self):
        result = run_cli(self.tmp.name)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no JSON files to check", result.stderr)

    def test_bad_flag_exits_two(self):
        result = run_cli("--nope")
        self.assertEqual(result.returncode, 2)

    def test_folder_walk(self):
        write(self.tmp.name, "good.json", '{"a": 1}\n')
        write(self.tmp.name, "sub/bad.json", '{"a": 1, "a": 2}\n')
        write(self.tmp.name, "sub/notes.txt", '{"a": 1, "a": 2}\n')
        result = run_cli(self.tmp.name)
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Checked 2 file(s), 1 problem(s) in 1 file(s).", result.stdout
        )

    def test_no_recursive(self):
        write(self.tmp.name, "good.json", '{"a": 1}\n')
        write(self.tmp.name, "sub/bad.json", '{"a": 1, "a": 2}\n')
        result = run_cli(self.tmp.name, "--no-recursive")
        self.assertEqual(result.returncode, 0)

    def test_git_folder_skipped(self):
        write(self.tmp.name, ".git/hooks/bad.json", '{"a": 1, "a": 2}\n')
        write(self.tmp.name, "good.json", '{"a": 1}\n')
        result = run_cli(self.tmp.name)
        self.assertEqual(result.returncode, 0)

    def test_exclude(self):
        write(self.tmp.name, "good.json", '{"a": 1}\n')
        write(self.tmp.name, "skip.json", '{"a": 1, "a": 2}\n')
        result = run_cli(self.tmp.name, "--exclude", "skip.json")
        self.assertEqual(result.returncode, 0)

    def test_multiple_files(self):
        good = write(self.tmp.name, "good.json", '{"a": 1}\n')
        bad = write(self.tmp.name, "bad.json", '{"a": 1, "a": 2}\n')
        result = run_cli(str(good), str(bad))
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Checked 2 file(s), 1 problem(s) in 1 file(s).", result.stdout
        )

    def test_input_files_unchanged(self):
        path = write(self.tmp.name, "bad.json", '{"a": 1, "a": 2}\n')
        before = path.read_text()
        run_cli(str(path))
        self.assertEqual(path.read_text(), before)

    def test_bundled_examples(self):
        clean = run_cli("examples/clean.json")
        self.assertEqual(clean.returncode, 0)
        self.assertIn(
            "OK — 1 file(s) checked, no duplicate keys.", clean.stdout
        )
        bad = run_cli("examples/duplicates.json")
        self.assertEqual(bad.returncode, 1)
        self.assertIn(
            "FAIL examples/duplicates.json:3: duplicate key 'name' "
            "in object $",
            bad.stdout,
        )
        self.assertIn(
            "FAIL examples/duplicates.json:7: duplicate key 'port' "
            "in object $.server",
            bad.stdout,
        )
        self.assertIn(
            "FAIL examples/duplicates.json:12: duplicate key 'id' "
            "in object $.items[0]",
            bad.stdout,
        )
        self.assertIn(
            "Checked 1 file(s), 3 problem(s) in 1 file(s).", bad.stdout
        )
        whole = run_cli("examples/")
        self.assertEqual(whole.returncode, 1)
        self.assertIn(
            "FAIL examples/configs/app.json:3: duplicate key 'debug' "
            "in object $",
            whole.stdout,
        )
        self.assertIn(
            "Checked 3 file(s), 4 problem(s) in 2 file(s).", whole.stdout
        )

    def test_sample_output_matches_a_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout, (EXAMPLES / "sample-output.md").read_text()
        )

    def test_run_example_script_exits_zero(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0)


class HygieneTests(unittest.TestCase):
    """The template gate: no placeholder text, no secrets, no local
    paths, stdlib imports only. The scan skips .git and __pycache__
    (Day 21 rule) and skips tests/ itself (Day 22 pattern), because
    this file's own banned-word list would otherwise trip it."""

    BANNED = ("TODO", "FIXME", "coming soon", "lorem", "API_KEY")

    def _repo_files(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        hits = []
        for path in self._repo_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for word in self.BANNED:
                if word in text:
                    hits.append(f"{path.relative_to(ROOT)}: {word}")
        self.assertEqual(hits, [])

    def test_no_absolute_local_paths(self):
        hits = []
        for path in self._repo_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "/home/" in text or "/Users/" in text or "C:\\" in text:
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_stdlib_only_imports(self):
        import ast

        allowed = {
            "argparse",
            "fnmatch",
            "json",
            "os",
            "sys",
            "pathlib",
            # Test file only: json, subprocess, tempfile, unittest.
            "subprocess",
            "tempfile",
            "unittest",
        }
        src = ROOT / "src" / "json_duplicate_key_checker.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        self.assertEqual(imported - allowed, set())

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_readme_quoted_outputs_are_real(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn(
            "FAIL examples/duplicates.json:3: duplicate key 'name' "
            "in object $",
            readme,
        )
        self.assertIn(
            "Checked 1 file(s), 3 problem(s) in 1 file(s).", readme
        )
        self.assertIn(
            "OK — 1 file(s) checked, no duplicate keys.", readme
        )


if __name__ == "__main__":
    unittest.main()
