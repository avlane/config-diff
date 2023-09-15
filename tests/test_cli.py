import contextlib
import io
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
