import contextlib
import io
import json
import unittest

from configdiff.cli import main
from tests.helpers import TempDirTestCase, fixture


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    # argparse writes --help/--version/usage errors to the real streams.
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv), out, err)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class CliTests(TempDirTestCase):
    def test_identical_files_exit_0_and_print_nothing(self):
        code, out, err = run(fixture("app_old.json"), fixture("app_old.json"))
        self.assertEqual((code, out, err), (0, "", ""))

    def test_reordered_keys_are_not_a_difference(self):
        a = self.write("a.json", '{"x": 1, "y": {"p": 1, "q": 2}}')
        b = self.write("b.json", '{"y": {"q": 2, "p": 1}, "x": 1}')
        self.assertEqual(run(a, b)[0], 0)

    def test_differences_exit_1(self):
        code, out, _ = run(fixture("app_old.json"), fixture("app_new.json"))
        self.assertEqual(code, 1)
        self.assertIn('~ version: "2.3.1" -> "2.4.0"', out)
        self.assertIn("~ server.workers: 4 -> 8", out)
        self.assertIn("~ database.pool.max: 10 -> 20", out)
        self.assertIn("+ database.timeout: 30", out)
        self.assertIn('+ features[2]: "audit"', out)
        self.assertEqual(len(out.splitlines()), 5)

    def test_ini_files(self):
        code, out, _ = run(fixture("settings_old.ini"), fixture("settings_new.ini"))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            '~ database.host: "db1.internal" -> "db2.internal"',
            '~ logging.level: "INFO" -> "DEBUG"',
        ])

    def test_env_files(self):
        code, out, _ = run(fixture("prod.env"), fixture("staging.env"))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            '~ APP_ENV: "production" -> "staging"',
            '~ DATABASE_URL: "postgres://app:s3cret@db.internal:5432/app" -> '
            '"postgres://app:s3cret@db.staging:5432/app"',
            '~ SECRET_KEY: "abc123" -> "def456"',
            '+ DEBUG: "1"',
        ])

    def test_json_output(self):
        code, out, _ = run(fixture("app_old.json"), fixture("app_new.json"), "-o", "json")
        self.assertEqual(code, 1)
        doc = json.loads(out)
        self.assertEqual(doc["summary"], {"added": 2, "removed": 0, "changed": 3})

    def test_json_output_when_equal(self):
        code, out, _ = run(fixture("app_old.json"), fixture("app_old.json"), "--output", "json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["equal"])

    def test_ignore_option(self):
        code, out, _ = run(fixture("app_old.json"), fixture("app_new.json"),
                           "-i", "version", "--ignore", "**.workers", "-i", "database")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ['+ features[2]: "audit"'])

    def test_ignoring_everything_exits_0(self):
        code, out, _ = run(fixture("app_old.json"), fixture("app_new.json"), "-i", "**")
        self.assertEqual((code, out), (0, ""))

    def test_bad_pattern_is_a_usage_error(self):
        code, _, err = run(fixture("app_old.json"), fixture("app_new.json"), "-i", "a[")
        self.assertEqual(code, 2)
        self.assertIn("missing ]", err)

    def test_list_key(self):
        a, b = fixture("servers_old.json"), fixture("servers_new.json")
        code, out, _ = run(a, b, "-k", "servers=name")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            "- servers[name=web-1]: " + '{"name": "web-1", "port": 8001, "tags": ["a"]}',
            "~ servers[name=web-2].port: 8002 -> 9002",
            "+ servers[name=web-3]: " + '{"name": "web-3", "port": 8003, "tags": []}',
        ])

    def test_list_key_json_segments(self):
        a, b = fixture("servers_old.json"), fixture("servers_new.json")
        _, out, _ = run(a, b, "-k", "servers=name", "-o", "json")
        segments = [c["segments"] for c in json.loads(out)["changes"]]
        self.assertEqual(segments[1], ["servers", {"item": {"name": "web-2"}}, "port"])

    def test_list_key_without_field_is_a_usage_error(self):
        code, _, err = run(fixture("servers_old.json"), fixture("servers_new.json"), "-k", "servers")
        self.assertEqual(code, 2)
        self.assertIn("PATH=FIELD", err)

    def test_unordered_option(self):
        a = self.write("a.json", '{"tags": ["x", "y"], "other": [1, 2]}')
        b = self.write("b.json", '{"tags": ["y", "x"], "other": [2, 1]}')
        code, out, _ = run(a, b, "-u", "tags")
        self.assertEqual(code, 1)
        self.assertEqual(len(out.splitlines()), 2)  # only "other" still differs
        self.assertEqual(run(a, b, "--unordered-lists")[0], 0)

    def test_missing_file_exits_2(self):
        code, out, err = run(fixture("app_old.json"), self.tmp + "/missing.json")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("config-diff: error: cannot read", err)

    def test_unknown_extension_exits_2(self):
        a = self.write("a.txt", "x")
        code, _, err = run(a, a)
        self.assertEqual(code, 2)
        self.assertIn("cannot tell the format", err)

    def test_invalid_json_exits_2(self):
        a = self.write("a.json", "{")
        code, _, err = run(a, fixture("app_old.json"))
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)

    def test_version(self):
        code, out, _ = run("--version")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("config-diff "))


if __name__ == "__main__":
    unittest.main()
