"""Run the real command line in a subprocess."""
import json
import os
import subprocess
import sys
import unittest

from tests.helpers import TempDirTestCase, fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_diff(*args, stdin=None, env=None):
    done = subprocess.run([sys.executable, "-m", "configdiff", *args], cwd=ROOT, input=stdin,
                          capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, **(env or {})))
    return done.returncode, done.stdout, done.stderr


class EndToEndTests(TempDirTestCase):
    def test_exit_status_follows_diff(self):
        old, new = fixture("app_old.json"), fixture("app_new.json")
        self.assertEqual(config_diff(old, old)[0], 0)
        code, out, err = config_diff(old, new)
        self.assertEqual((code, err), (1, ""))
        self.assertIn("~ server.workers: 4 -> 8", out)

    def test_errors_exit_2_with_a_message_on_stderr(self):
        code, out, err = config_diff(fixture("app_old.json"), self.tmp + "/missing.json")
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("config-diff: error: cannot read"))

    def test_usage_errors_exit_2(self):
        for args in ([], ["only-one.json"], ["a.json", "b.json", "--fail-on", "nope"],
                     ["a.json", "b.json", "-i", "a["]):
            code, out, err = config_diff(*args)
            self.assertEqual(code, 2, args)
            self.assertEqual(out, "")
            self.assertIn("usage:", err)

    def test_stdin_and_json_output(self):
        text = open(fixture("app_old.json")).read()
        code, out, _ = config_diff("-", fixture("app_new.json"), "--old-format", "json",
                                   "-o", "json", stdin=text)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["summary"]["changed"], 3)

    def test_cross_format_ci_gate(self):
        env = self.write("prod.env", "PORT=8080\nDEBUG=false\n")
        cfg = self.write("prod.toml", "PORT = 8080\nDEBUG = false\n")
        if sys.version_info >= (3, 11):
            self.assertEqual(config_diff(env, cfg, "--coerce", "-q")[0], 0)
        other = fixture("app_old.json")  # shares no keys: everything is removed or added
        self.assertEqual(config_diff(env, other, "--fail-on", "changed", "-q")[0], 0)
        self.assertEqual(config_diff(env, other, "--fail-on", "removed", "-q")[0], 1)

    def test_color_only_when_asked_in_a_pipe(self):
        old, new = fixture("app_old.json"), fixture("app_new.json")
        self.assertNotIn("\x1b[", config_diff(old, new)[1])
        self.assertIn("\x1b[", config_diff(old, new, "--color", "always")[1])

    def test_directories(self):
        code, out, _ = config_diff(fixture("envs/old"), fixture("envs/new"), "--summary")
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[-1].startswith("4 of 5 files differ"))

    def test_help_and_version(self):
        code, out, _ = config_diff("--help")
        self.assertEqual(code, 0)
        self.assertIn("exit status:", out)
        code, out, _ = config_diff("--version")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^config-diff \d+\.\d+\.\d+")


if __name__ == "__main__":
    unittest.main()
