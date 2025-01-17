import contextlib
import importlib.util
import io
import json
import unittest

from configdiff.cli import main, use_color
from tests.helpers import TempDirTestCase, fixture


def run(*argv, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    # argparse writes --help/--version/usage errors to the real streams.
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv), out, err, io.StringIO(stdin))
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

    def test_color_always_and_never(self):
        a, b = fixture("app_old.json"), fixture("app_new.json")
        self.assertIn("\x1b[", run(a, b, "--color", "always")[1])
        self.assertNotIn("\x1b[", run(a, b, "--color", "never")[1])

    def test_color_auto_is_off_when_not_a_terminal(self):
        a, b = fixture("app_old.json"), fixture("app_new.json")
        self.assertNotIn("\x1b[", run(a, b)[1])

    def test_json_output_is_never_colored(self):
        a, b = fixture("app_old.json"), fixture("app_new.json")
        json.loads(run(a, b, "-o", "json", "--color", "always")[1])

    @unittest.skipUnless(importlib.util.find_spec("tomllib"), "tomllib needs Python 3.11")
    def test_toml_files(self):
        code, out, _ = run(fixture("service_old.toml"), fixture("service_new.toml"))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            '~ released: "2024-01-10" -> "2024-04-06"',
            "~ server.port: 8080 -> 8443",
            "~ server.tls: false -> true",
            "~ database.pool.max: 10 -> 20",
            '+ endpoints[0].methods[2]: "DELETE"',
        ])

    def test_redact_secrets_on_env_files(self):
        code, out, _ = run(fixture("prod.env"), fixture("staging.env"), "--redact-secrets")
        self.assertEqual(code, 1)
        self.assertIn("~ SECRET_KEY: \"<redacted>\" -> \"<redacted>\"", out)
        self.assertIn("postgres://app:***@db.internal:5432/app", out)
        self.assertNotIn("abc123", out)
        self.assertNotIn("def456", out)
        self.assertNotIn("s3cret", out)

    def test_redact_option_with_json_output(self):
        a = self.write("a.json", '{"db": {"pw": "one", "host": "h"}}')
        b = self.write("b.json", '{"db": {"pw": "two", "host": "h2"}}')
        _, out, _ = run(a, b, "--redact", "db.pw", "-o", "json")
        self.assertNotIn("one", out)
        self.assertNotIn("two", out)
        by_path = {c["path"]: c for c in json.loads(out)["changes"]}
        self.assertEqual(by_path["db.pw"]["new"], "<redacted>")
        self.assertEqual(by_path["db.host"]["new"], "h2")

    def test_without_redaction_secrets_are_shown(self):
        _, out, _ = run(fixture("prod.env"), fixture("staging.env"))
        self.assertIn("abc123", out)

    def test_stdin_needs_a_format(self):
        code, _, err = run("-", fixture("app_old.json"), stdin="{}")
        self.assertEqual(code, 2)
        self.assertIn("--format", err)

    def test_stdin_as_old(self):
        text = '{"version": "2.3.1", "name": "inventory-service", "debug": false}'
        code, out, _ = run("-", fixture("app_new.json"), "--old-format", "json", stdin=text)
        self.assertEqual(code, 1)
        self.assertIn("+ features", out)

    def test_stdin_as_new_with_format_for_both(self):
        code, out, _ = run(fixture("app_old.json"), "-", "-f", "json",
                           stdin=open(fixture("app_old.json")).read())
        self.assertEqual((code, out), (0, ""))

    def test_stdin_errors_are_named(self):
        code, _, err = run("-", fixture("app_old.json"), "-f", "json", stdin="{")
        self.assertEqual(code, 2)
        self.assertIn("<stdin>: invalid JSON", err)

    def test_stdin_for_both_sides_is_rejected(self):
        code, _, err = run("-", "-", "-f", "json")
        self.assertEqual(code, 2)
        self.assertIn("only one of", err)

    def test_comparing_different_formats(self):
        env = self.write("settings.env", "PORT=8080\nDEBUG=false\n")
        js = self.write("settings.json", '{"PORT": "8080", "DEBUG": false}')
        code, out, _ = run(env, js)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ['~ DEBUG: "false" -> false'])

    def test_coerce_makes_env_comparable_with_typed_formats(self):
        env = self.write("settings.env", "PORT=8080\nDEBUG=false\nNAME=svc\n")
        js = self.write("settings.json", '{"PORT": 8080, "DEBUG": false, "NAME": "svc"}')
        self.assertEqual(run(env, js)[0], 1)
        self.assertEqual(run(env, js, "--coerce")[0], 0)
        js2 = self.write("settings2.json", '{"PORT": 9090, "DEBUG": false, "NAME": "svc"}')
        code, out, _ = run(env, js2, "--coerce")
        self.assertEqual((code, out), (1, "~ PORT: 8080 -> 9090\n"))

    def test_forcing_the_format_of_an_oddly_named_file(self):
        a = self.write("one.conf", "[s]\nk = 1\n")
        b = self.write("two.conf", "[s]\nk = 2\n")
        self.assertEqual(run(a, b)[0], 2)
        code, out, _ = run(a, b, "--format", "ini")
        self.assertEqual((code, out), (1, '~ s.k: "1" -> "2"\n'))

    def test_keys_containing_dots_are_unambiguous(self):
        a = self.write("a.json", '{"logging": {"app.module": "INFO"}, "a": {"b": 1}}')
        b = self.write("b.json", '{"logging": {"app.module": "DEBUG"}, "a": {"b": 2}}')
        _, out, _ = run(a, b)
        self.assertEqual(out.splitlines(), [
            '~ logging["app.module"]: "INFO" -> "DEBUG"',
            "~ a.b: 1 -> 2",
        ])
        _, out, _ = run(a, b, "-i", 'logging["app.module"]')
        self.assertEqual(out.splitlines(), ["~ a.b: 1 -> 2"])

    def test_yaml_files(self):
        code, out, _ = run(fixture("compose_old.yaml"), fixture("compose_new.yaml"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(out.splitlines()), sorted([
            '+ services.web.ports[1]: "8443:443"',
            '~ services.web.environment.LOG_LEVEL: "info" -> "debug"',
            '~ services.worker.image: "registry.example.com/worker:1.4" -> '
            '"registry.example.com/worker:1.5"',
            "~ services.worker.deploy.replicas: 2 -> 4",
        ]))

    def test_unsupported_yaml_is_reported_with_a_line_number(self):
        a = self.write("a.yaml", "x: &a 1\ny: *a\n")
        code, _, err = run(a, a)
        self.assertEqual(code, 2)
        self.assertIn("a.yaml: invalid or unsupported YAML: line 1", err)

    def test_duplicate_keys_fail_unless_allowed(self):
        a = self.write("a.env", "PORT=1\nPORT=2\n")
        b = self.write("b.env", "PORT=2\n")
        code, _, err = run(a, b)
        self.assertEqual(code, 2)
        self.assertIn("PORT is defined twice", err)
        self.assertEqual(run(a, b, "--allow-duplicates")[0], 0)

    def test_ignore_file(self):
        ignore = self.write("ignore.txt", "# noise\nversion\n**.workers\n\ndatabase\n")
        code, out, _ = run(fixture("app_old.json"), fixture("app_new.json"), "--ignore-file", ignore)
        self.assertEqual((code, out), (1, '+ features[2]: "audit"\n'))

    def test_unreadable_ignore_file_is_a_usage_error(self):
        code, _, err = run(fixture("app_old.json"), fixture("app_new.json"),
                           "--ignore-file", self.tmp + "/nope.txt")
        self.assertEqual(code, 2)
        self.assertIn("cannot read ignore file", err)

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


class UseColorTests(unittest.TestCase):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    def test_modes(self):
        tty, pipe = self.Tty(), io.StringIO()
        self.assertTrue(use_color("always", pipe, {"NO_COLOR": "1"}))
        self.assertFalse(use_color("never", tty, {}))
        self.assertTrue(use_color("auto", tty, {}))
        self.assertFalse(use_color("auto", pipe, {}))

    def test_no_color_convention(self):
        self.assertFalse(use_color("auto", self.Tty(), {"NO_COLOR": "1"}))
        self.assertTrue(use_color("auto", self.Tty(), {"NO_COLOR": ""}))


if __name__ == "__main__":
    unittest.main()
