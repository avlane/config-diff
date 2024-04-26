import unittest

from configdiff.diffing import ADDED, CHANGED, REMOVED, Change
from configdiff.paths import parse_pattern
from configdiff.redact import REDACTED, mask_url_password, redact_changes, secret_patterns


class MaskUrlTests(unittest.TestCase):
    def test_password_is_hidden_user_is_kept(self):
        self.assertEqual(mask_url_password("postgres://app:s3cret@db:5432/x"),
                         "postgres://app:***@db:5432/x")

    def test_urls_without_credentials_are_untouched(self):
        for text in ("http://example.com/a:b@c", "postgres://db/x", "no url at all", "a:b@c"):
            self.assertEqual(mask_url_password(text), text)

    def test_user_only_is_untouched(self):
        self.assertEqual(mask_url_password("ssh://git@host/repo"), "ssh://git@host/repo")


class RedactChangesTests(unittest.TestCase):
    def test_values_at_matching_paths_are_replaced(self):
        changes = [Change(CHANGED, ("db", "password"), "old", "new"),
                   Change(ADDED, ("api", "token"), new="t"),
                   Change(REMOVED, ("x", "secret"), old="s"),
                   Change(CHANGED, ("db", "host"), "a", "b")]
        out = redact_changes(changes, [parse_pattern("**.password"), parse_pattern("**.token"),
                                       parse_pattern("**.secret")])
        self.assertEqual(out, [
            Change(CHANGED, ("db", "password"), REDACTED, REDACTED),
            Change(ADDED, ("api", "token"), None, REDACTED),
            Change(REMOVED, ("x", "secret"), REDACTED, None),
            Change(CHANGED, ("db", "host"), "a", "b"),
        ])

    def test_nested_values_below_a_match_are_hidden(self):
        changes = [Change(ADDED, ("creds",), new={"user": "u", "pw": "p"})]
        out = redact_changes(changes, [parse_pattern("creds")])
        self.assertEqual(out[0].new, REDACTED)

    def test_secrets_inside_an_added_section_are_hidden(self):
        changes = [Change(ADDED, ("db",), new={"host": "h", "Password": "pw",
                                               "clients": [{"api_key": "k", "n": 1}]})]
        out = redact_changes(changes, secret_patterns())
        self.assertEqual(out[0].new, {"host": "h", "Password": REDACTED,
                                      "clients": [{"api_key": REDACTED, "n": 1}]})

    def test_url_masking_is_optional(self):
        changes = [Change(CHANGED, ("url",), "pg://u:a@h", "pg://u:b@h")]
        self.assertEqual(redact_changes(changes, [])[0].old, "pg://u:a@h")
        masked = redact_changes(changes, [], mask_urls=True)[0]
        self.assertEqual((masked.old, masked.new), ("pg://u:***@h", "pg://u:***@h"))

    def test_default_patterns_match_common_names_case_insensitively(self):
        patterns = secret_patterns()
        for key in ("password", "DB_PASSWORD", "ApiKey", "api_key", "access_token", "SECRET_KEY",
                    "client_secret", "private_key", "credentials"):
            self.assertTrue(any(p.matches(("section", key)) for p in patterns), key)
        for key in ("host", "port", "username", "keyboard"):
            self.assertFalse(any(p.matches(("section", key)) for p in patterns), key)


if __name__ == "__main__":
    unittest.main()
