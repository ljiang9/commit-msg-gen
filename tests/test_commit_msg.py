import unittest

from commit_msg_gen import (EXAMPLE_DIFF, build_commit_message, infer_scope,
                            infer_type, parse_diff)


class TestParse(unittest.TestCase):
    def setUp(self):
        self.p = parse_diff(EXAMPLE_DIFF)

    def test_finds_files(self):
        self.assertIn("auth/login.py", self.p["files"])
        self.assertIn("tests/test_login.py", self.p["files"])
        self.assertIn("README.md", self.p["files"])

    def test_classifies_new_file(self):
        self.assertIn("tests/test_login.py", self.p["added"])

    def test_counts_insertions_deletions(self):
        self.assertGreater(self.p["insertions"], 0)
        self.assertGreaterEqual(self.p["deletions"], 1)

    def test_keywords_extracted(self):
        self.assertIn("fix", self.p["keywords"])


class TestInfer(unittest.TestCase):
    def test_type_is_fix_for_auth_login(self):
        p = parse_diff(EXAMPLE_DIFF)
        t = infer_type(p)
        self.assertEqual(t, "fix")

    def test_scope_auth(self):
        p = parse_diff(EXAMPLE_DIFF)
        self.assertEqual(infer_scope(p), "auth")

    def test_docs_type(self):
        diff = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
 # hi
+update docs
"""
        self.assertEqual(infer_type(parse_diff(diff)), "docs")

    def test_chore_fallback(self):
        diff = """diff --git a/.gitignore b/.gitignore
--- a/.gitignore
+++ b/.gitignore
@@ -1 +1,2 @@
 a
+.env
"""
        self.assertIn(infer_type(parse_diff(diff)), ("chore",))


class TestBuild(unittest.TestCase):
    def test_message_format(self):
        msg = build_commit_message(EXAMPLE_DIFF)
        lines = msg.splitlines()
        self.assertTrue(lines[0].startswith("fix"))
        self.assertIn(":", lines[0])
        self.assertIn("insertions", msg)


if __name__ == "__main__":
    unittest.main()
