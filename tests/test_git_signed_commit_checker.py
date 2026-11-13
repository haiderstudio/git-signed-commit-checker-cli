#!/usr/bin/env python3
"""Tests for git-signed-commit-checker-cli. Standard library only.

The tests build real temp git repos (unsigned commits by default)
and check the real output. One test makes a real signed commit
with a throwaway GPG key made inside a temp folder; the key never
leaves that folder and the folder is deleted afterwards. If gpg is
missing, or the throwaway key cannot be made, that one test is
skipped and the signed path is still covered by the parsing tests.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "git_signed_commit_checker.py"
TOOL = str(SRC)
sys.path.insert(0, str(ROOT / "src"))
import git_signed_commit_checker as checker  # noqa: E402

BANNED_WORDS = ["lorem", "coming soon"]
BANNED_MARKERS = ["TODO", "FIXME", "XXX"]
CI_MARKERS = [
    "actions/checkout@v4",
    "actions/setup-python@v5",
    "python3 tests/test_git_signed_commit_checker.py",
    "push",
    "pull_request",
]
ALLOWED_IMPORTS = {
    "argparse",
    "json",
    "subprocess",
    "sys",
    "datetime",
    "os",
    "re",
    "shutil",
    "tempfile",
    "unittest",
    "pathlib",
}


def run_cli(args, cwd=None, env=None):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, TOOL] + args,
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def commit_date(days_ago):
    """A git date string N days ago, at noon UTC."""
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=days_ago
    )
    return when.strftime("%Y-%m-%dT%H:%M:%S")


class RepoBuilder:
    """Build a small git repo with unsigned commits at chosen dates."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.home = Path(tempfile.mkdtemp(prefix="git-home-"))
        self.env = dict(os.environ)
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        self.env["HOME"] = str(self.home)
        self.env["GIT_CONFIG_GLOBAL"] = str(self.home / "gitconfig")
        self.counter = 0
        self.run_git(["init", "-q", "-b", "main"])
        self.run_git(["config", "user.email", "tester@example.com"])
        self.run_git(["config", "user.name", "Test User"])
        self.run_git(["config", "commit.gpgsign", "false"])

    def run_git(self, args, env=None):
        full_env = dict(self.env)
        if env:
            full_env.update(env)
        return subprocess.run(
            ["git", "-C", str(self.path)] + args,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def commit(self, message, days_ago=0, author=None):
        self.counter += 1
        filename = "file%d.txt" % self.counter
        (self.path / filename).write_text("content %d\n" % self.counter)
        self.run_git(["add", filename])
        env = dict(self.env)
        when = commit_date(days_ago)
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
        if author:
            env["GIT_AUTHOR_NAME"] = author
        result = self.run_git(
            ["-c", "commit.gpgsign=false", "commit", "-qm", message], env=env
        )
        assert result.returncode == 0, result.stderr
        return self.run_git(["rev-parse", "HEAD"]).stdout.strip()

    def cleanup(self):
        shutil.rmtree(self.home, ignore_errors=True)


class ParseTests(unittest.TestCase):
    """Parsing of git log %G? states — no repo needed."""

    def record(self, state, author="Test User"):
        return "a" * 40 + "\x00" + author + "\x00" + "2026-11-12T10:00:00+00:00" + "\x00" + state

    def test_good_signature_is_signed(self):
        item = checker.parse_record(self.record("G"))
        self.assertTrue(item["signed"])
        self.assertEqual(item["state"], "G")
        self.assertEqual(item["state_label"], "good signature")

    def test_no_signature_is_unsigned(self):
        item = checker.parse_record(self.record("N"))
        self.assertFalse(item["signed"])
        self.assertEqual(item["state_label"], "no signature")

    def test_untrusted_signature_is_unsigned(self):
        item = checker.parse_record(self.record("U"))
        self.assertFalse(item["signed"])
        self.assertEqual(item["state_label"], "untrusted signature")

    def test_bad_signature_is_unsigned(self):
        item = checker.parse_record(self.record("B"))
        self.assertFalse(item["signed"])
        self.assertEqual(item["state_label"], "bad signature")

    def test_expired_signature_is_unsigned(self):
        item = checker.parse_record(self.record("X"))
        self.assertFalse(item["signed"])
        self.assertEqual(item["state_label"], "expired signature")

    def test_expired_key_is_unsigned(self):
        item = checker.parse_record(self.record("Y"))
        self.assertFalse(item["signed"])
        self.assertIn("expired key", item["state_label"])

    def test_revoked_key_is_unsigned(self):
        item = checker.parse_record(self.record("R"))
        self.assertFalse(item["signed"])
        self.assertIn("revoked", item["state_label"])

    def test_missing_key_is_unsigned(self):
        item = checker.parse_record(self.record("E"))
        self.assertFalse(item["signed"])
        self.assertIn("cannot be found", item["state_label"])

    def test_unknown_state_is_unsigned(self):
        item = checker.parse_record(self.record("Z"))
        self.assertFalse(item["signed"])
        self.assertEqual(item["state_label"], "unknown signature state")

    def test_empty_record_is_none(self):
        self.assertIsNone(checker.parse_record(""))
        self.assertIsNone(checker.parse_record("   "))

    def test_malformed_record_is_none(self):
        self.assertIsNone(checker.parse_record("abc\x00only-two-fields"))
        self.assertIsNone(checker.parse_record("a" * 40 + "\x00\x00\x00N"))

    def test_record_fields(self):
        item = checker.parse_record(self.record("N", author="Ada Lovelace"))
        self.assertEqual(item["hash"], "a" * 40)
        self.assertEqual(item["short_hash"], "a" * 7)
        self.assertEqual(item["author"], "Ada Lovelace")
        self.assertEqual(item["date"], "2026-11-12")
        self.assertEqual(item["committed"], "2026-11-12T10:00:00+00:00")

    def test_parse_log_output_multiple_records(self):
        output = self.record("G") + "\x1e" + self.record("N") + "\x1e"
        items = checker.parse_log_output(output)
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["signed"])
        self.assertFalse(items[1]["signed"])

    def test_parse_log_output_skips_bad_records(self):
        output = "garbage-line" + "\x1e" + self.record("N") + "\x1e"
        items = checker.parse_log_output(output)
        self.assertEqual(len(items), 1)

    def test_parse_log_output_empty(self):
        self.assertEqual(checker.parse_log_output(""), [])
        self.assertEqual(checker.parse_log_output("\x1e"), [])


class CliTests(unittest.TestCase):
    """End-to-end runs against real temp git repos."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="signed-check-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make_repo(self):
        repo = RepoBuilder(Path(self.tmp) / "repo")
        self.addCleanup(repo.cleanup)
        return repo

    def test_all_unsigned_exit_1_lists_each_commit(self):
        repo = self.make_repo()
        first = repo.commit("first commit", days_ago=2)
        second = repo.commit("second commit", days_ago=0)
        result = run_cli([str(repo.path)])
        self.assertEqual(result.returncode, 1)
        self.assertIn(first[:7], result.stdout)
        self.assertIn(second[:7], result.stdout)
        self.assertIn("Test User", result.stdout)
        self.assertIn("Checked 2 commit(s), 2 unsigned commit(s).", result.stdout)

    def test_unsigned_line_format(self):
        repo = self.make_repo()
        commit_hash = repo.commit("one commit", days_ago=1)
        result = run_cli([str(repo.path)])
        line = result.stdout.splitlines()[0]
        self.assertRegex(
            line,
            r"^UNSIGNED [0-9a-f]{7} — Test User — \d{4}-\d{2}-\d{2} \(no signature\)$",
        )
        self.assertTrue(line.startswith("UNSIGNED " + commit_hash[:7]))

    def test_limit_1_checks_only_newest(self):
        repo = self.make_repo()
        repo.commit("old commit", days_ago=30)
        newest = repo.commit("new commit", days_ago=0)
        result = run_cli(["--limit", "1", str(repo.path)])
        self.assertEqual(result.returncode, 1)
        self.assertIn(newest[:7], result.stdout)
        self.assertIn("Checked 1 commit(s), 1 unsigned commit(s).", result.stdout)

    def test_limit_2_checks_two_newest(self):
        repo = self.make_repo()
        repo.commit("commit one", days_ago=30)
        repo.commit("commit two", days_ago=10)
        repo.commit("commit three", days_ago=0)
        result = run_cli(["--limit", "2", str(repo.path)])
        self.assertIn("Checked 2 commit(s), 2 unsigned commit(s).", result.stdout)

    def test_limit_zero_and_negative_exit_2(self):
        repo = self.make_repo()
        repo.commit("one commit")
        for bad in ("0", "-1"):
            result = run_cli(["--limit", bad, str(repo.path)])
            self.assertEqual(result.returncode, 2, bad)

    def test_since_excludes_old_commits(self):
        repo = self.make_repo()
        repo.commit("old commit", days_ago=40)
        repo.commit("recent commit", days_ago=1)
        since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        result = run_cli(["--since", since, str(repo.path)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Checked 1 commit(s), 1 unsigned commit(s).", result.stdout)

    def test_since_and_limit_combined(self):
        repo = self.make_repo()
        repo.commit("old commit", days_ago=40)
        repo.commit("middle commit", days_ago=3)
        repo.commit("new commit", days_ago=0)
        since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        result = run_cli(["--since", since, "--limit", "1", str(repo.path)])
        self.assertIn("Checked 1 commit(s), 1 unsigned commit(s).", result.stdout)

    def test_since_invalid_date_exit_2(self):
        repo = self.make_repo()
        repo.commit("one commit")
        result = run_cli(["--since", "not-a-date", str(repo.path)])
        self.assertEqual(result.returncode, 2)
        self.assertIn("--since must be a date", result.stderr)

    def test_non_git_directory_exit_2(self):
        plain = Path(self.tmp) / "plain"
        plain.mkdir()
        result = run_cli([str(plain)])
        self.assertEqual(result.returncode, 2)
        self.assertIn("Not a git repository", result.stderr)

    def test_missing_path_exit_2(self):
        result = run_cli([str(Path(self.tmp) / "no-such-folder")])
        self.assertEqual(result.returncode, 2)
        self.assertIn("No such path", result.stderr)

    def test_empty_repo_exit_0(self):
        repo = self.make_repo()
        result = run_cli([str(repo.path)])
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK — 0 commit(s) checked, all commits are signed.", result.stdout)

    def test_default_path_is_current_folder(self):
        repo = self.make_repo()
        repo.commit("one commit")
        result = run_cli([], cwd=str(repo.path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Checked 1 commit(s), 1 unsigned commit(s).", result.stdout)

    def test_runs_from_tmp(self):
        repo = self.make_repo()
        repo.commit("one commit")
        result = run_cli([str(repo.path)], cwd="/tmp")
        self.assertEqual(result.returncode, 1)

    def test_runs_from_root(self):
        repo = self.make_repo()
        repo.commit("one commit")
        result = run_cli([str(repo.path)], cwd="/")
        self.assertEqual(result.returncode, 1)

    def test_json_output_parses_and_matches(self):
        repo = self.make_repo()
        commit_hash = repo.commit("one commit", days_ago=1)
        result = run_cli(["--json", str(repo.path)])
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertEqual(data["checked"], 1)
        self.assertEqual(len(data["unsigned"]), 1)
        item = data["unsigned"][0]
        self.assertEqual(item["hash"], commit_hash)
        self.assertEqual(item["author"], "Test User")
        self.assertEqual(item["state"], "N")
        self.assertFalse(item["signed"])
        # The plain lines go to standard error when --json is used.
        self.assertIn("UNSIGNED", result.stderr)

    def test_json_on_clean_repo(self):
        repo = self.make_repo()
        result = run_cli(["--json", str(repo.path)])
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual(data["checked"], 0)
        self.assertEqual(data["unsigned"], [])

    def test_version_flag(self):
        result = run_cli(["--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("git-signed-commit-checker-cli", result.stdout)

    def test_bad_flag_exit_2(self):
        result = run_cli(["--no-such-flag"])
        self.assertEqual(result.returncode, 2)

    def test_git_missing_exit_2(self):
        repo = self.make_repo()
        repo.commit("one commit")
        env = {"PATH": ""}
        result = run_cli([str(repo.path)], env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("git is not installed", result.stderr)

    def test_all_flag_includes_other_branch(self):
        repo = self.make_repo()
        repo.commit("main commit", days_ago=0)
        repo.run_git(["checkout", "-qb", "side"])
        side_hash = repo.commit("side commit", days_ago=0)
        repo.run_git(["checkout", "-q", "main"])
        default = run_cli([str(repo.path)])
        self.assertIn("Checked 1 commit(s)", default.stdout)
        with_all = run_cli(["--all", str(repo.path)])
        self.assertEqual(with_all.returncode, 1)
        self.assertIn(side_hash[:7], with_all.stdout)
        self.assertIn("Checked 2 commit(s), 2 unsigned commit(s).", with_all.stdout)

    def test_detached_head_does_not_crash(self):
        repo = self.make_repo()
        commit_hash = repo.commit("one commit")
        repo.run_git(["checkout", "-q", commit_hash])
        result = run_cli([str(repo.path)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("Checked 1 commit(s)", result.stdout)

    def test_author_with_spaces_reported(self):
        repo = self.make_repo()
        repo.commit("one commit", author="Ada Lovelace")
        result = run_cli([str(repo.path)])
        self.assertIn("Ada Lovelace", result.stdout)

    def test_signed_commit_passes_with_real_key(self):
        """A real signed commit, made with a throwaway GPG key.

        The key lives in a temp GNUPGHOME and is deleted with it.
        Skipped only when gpg is missing or the key cannot be made.
        """
        if shutil.which("gpg") is None:
            self.skipTest("gpg is not installed")
        gnupg_home = Path(tempfile.mkdtemp(prefix="gpg-test-"))
        self.addCleanup(shutil.rmtree, gnupg_home, True)
        key_params = gnupg_home / "keyparams"
        key_params.write_text(
            "Key-Type: eddsa\n"
            "Key-Curve: ed25519\n"
            "Name-Real: Test Signer\n"
            "Name-Email: test-signer@example.com\n"
            "Expire-Date: 0\n"
            "%no-protection\n"
            "%commit\n"
        )
        env = dict(os.environ)
        env["GNUPGHOME"] = str(gnupg_home)
        made = subprocess.run(
            ["gpg", "--batch", "--gen-key", str(key_params)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if made.returncode != 0:
            self.skipTest("throwaway GPG key could not be made: " + made.stderr.strip())
        listed = subprocess.run(
            ["gpg", "--list-keys", "--with-colons"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        key_id = None
        for line in listed.stdout.splitlines():
            if line.startswith("fpr:"):
                key_id = line.split(":")[9]
                break
        if not key_id:
            self.skipTest("throwaway GPG key id could not be read")
        repo = self.make_repo()
        repo.run_git(["config", "user.email", "test-signer@example.com"])
        repo.run_git(["config", "user.name", "Test Signer"])
        repo.run_git(["config", "user.signingkey", key_id])
        repo.run_git(["config", "commit.gpgsign", "true"])
        (repo.path / "signed.txt").write_text("signed content\n")
        repo.run_git(["add", "signed.txt"])
        signed = repo.run_git(
            ["commit", "-qm", "signed commit"], env={"GNUPGHOME": str(gnupg_home)}
        )
        self.assertEqual(signed.returncode, 0, signed.stderr)
        result = run_cli(
            [str(repo.path)], env={"GNUPGHOME": str(gnupg_home)}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK — 1 commit(s) checked, all commits are signed.", result.stdout)

    def test_mixed_signed_and_unsigned_lists_only_unsigned(self):
        """Signed commit passes, unsigned commit is the only one listed."""
        if shutil.which("gpg") is None:
            self.skipTest("gpg is not installed")
        gnupg_home = Path(tempfile.mkdtemp(prefix="gpg-test-"))
        self.addCleanup(shutil.rmtree, gnupg_home, True)
        key_params = gnupg_home / "keyparams"
        key_params.write_text(
            "Key-Type: eddsa\n"
            "Key-Curve: ed25519\n"
            "Name-Real: Test Signer\n"
            "Name-Email: test-signer@example.com\n"
            "Expire-Date: 0\n"
            "%no-protection\n"
            "%commit\n"
        )
        env = dict(os.environ)
        env["GNUPGHOME"] = str(gnupg_home)
        made = subprocess.run(
            ["gpg", "--batch", "--gen-key", str(key_params)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if made.returncode != 0:
            self.skipTest("throwaway GPG key could not be made")
        listed = subprocess.run(
            ["gpg", "--list-keys", "--with-colons"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        key_id = None
        for line in listed.stdout.splitlines():
            if line.startswith("fpr:"):
                key_id = line.split(":")[9]
                break
        if not key_id:
            self.skipTest("throwaway GPG key id could not be read")
        repo = self.make_repo()
        repo.run_git(["config", "user.email", "test-signer@example.com"])
        repo.run_git(["config", "user.name", "Test Signer"])
        repo.run_git(["config", "user.signingkey", key_id])
        repo.run_git(["config", "commit.gpgsign", "true"])
        (repo.path / "signed.txt").write_text("signed content\n")
        repo.run_git(["add", "signed.txt"])
        signed = repo.run_git(
            ["commit", "-qm", "signed commit"], env={"GNUPGHOME": str(gnupg_home)}
        )
        self.assertEqual(signed.returncode, 0, signed.stderr)
        signed_hash = repo.run_git(["rev-parse", "HEAD"]).stdout.strip()
        unsigned_hash = repo.commit("unsigned commit", days_ago=0)
        result = run_cli(
            [str(repo.path)], env={"GNUPGHOME": str(gnupg_home)}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(unsigned_hash[:7], result.stdout)
        self.assertNotIn(signed_hash[:7], result.stdout)
        self.assertIn("Checked 2 commit(s), 1 unsigned commit(s).", result.stdout)


class HygieneTests(unittest.TestCase):
    """Repo hygiene: no filler, no secrets, no absolute paths, CI sane."""

    def repo_files(self):
        found = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            parts = set(path.parts)
            if ".git" in parts or "__pycache__" in parts or "tests" in parts:
                continue
            found.append(path)
        return found

    def test_no_banned_words_in_repo_files(self):
        bad = []
        for path in self.repo_files():
            text = path.read_text(errors="ignore")
            lowered = text.lower()
            for word in BANNED_WORDS + [w.lower() for w in BANNED_MARKERS]:
                if word in lowered:
                    bad.append("%s: %s" % (path.name, word))
        self.assertEqual(bad, [])

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertTrue(lines, ".gitignore is empty")
        self.assertEqual(lines[0], ".env")

    def test_no_absolute_home_paths_in_repo_files(self):
        home = str(Path.home())
        bad = []
        for path in self.repo_files():
            if home in path.read_text(errors="ignore"):
                bad.append(str(path))
        self.assertEqual(bad, [])

    def test_no_env_file_present(self):
        self.assertFalse((ROOT / ".env").exists())

    def test_ci_yml_has_required_markers(self):
        text = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        for marker in CI_MARKERS:
            self.assertIn(marker, text, "ci.yml is missing: " + marker)
        self.assertIn('"3.12"', text)

    def test_no_third_party_imports(self):
        import ast

        found = set()
        for path in [ROOT / "src" / "git_signed_commit_checker.py"]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for item in node.names:
                        found.add(item.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module.split(".")[0])
        extra = found - ALLOWED_IMPORTS
        self.assertEqual(extra, set(), "non-stdlib imports: %s" % extra)

    def test_readme_states_scope_plainly(self):
        text = (ROOT / "README.md").read_text()
        for phrase in [
            "local git history only",
            "does not check signatures through the GitHub API",
            "does not verify DCO sign-off",
            "does not sign anything",
            "github-signed-commits-checker",
            "signed-off-by-github-webhook",
            "sig-baseline-checker",
        ]:
            self.assertIn(phrase, text, "README is missing: " + phrase)

    def test_examples_run_and_report_unsigned(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UNSIGNED", result.stdout)
        self.assertIn("Checked 3 commit(s), 3 unsigned commit(s).", result.stdout)
        sample = (ROOT / "examples" / "sample-output.md").read_text()
        self.assertIn("UNSIGNED", sample)

    def test_required_files_exist(self):
        for rel in [
            "README.md",
            "LICENSE",
            ".gitignore",
            "CONTRIBUTING.md",
            "SECURITY.md",
            ".github/workflows/ci.yml",
            ".github/ISSUE_TEMPLATE/bug_report.md",
            ".github/ISSUE_TEMPLATE/feature_request.md",
            "src/git_signed_commit_checker.py",
            "tests/test_git_signed_commit_checker.py",
            "examples/make-sample-repo.sh",
            "examples/run-example.sh",
            "examples/sample-output.md",
        ]:
            self.assertTrue((ROOT / rel).is_file(), "missing: " + rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
