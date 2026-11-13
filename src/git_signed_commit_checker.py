#!/usr/bin/env python3
"""Check the recent commits in a git repo are signed.

One job only: in a git repo, list the recent commits that are not
signed with a good signature (GPG or SSH). Report-only — it never
signs a commit, never rewrites history, never changes anything.
Exits 1 when any unsigned (or badly signed) commit is found, 0
when every checked commit carries a good signature, 2 on usage
errors (not a git repo, bad flag, git missing).

Standard library only. Git itself is the tool being checked, so it
is called through subprocess — no third-party Python module is used.
The signature state comes from git log's %G? placeholder: G means a
good signature, N means no signature, and anything else (U
untrusted, B bad, X expired, Y expired key, R revoked, E key not
found) means the commit does not carry a good signature.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_LIMIT = 20

STATE_LABELS = {
    "G": "good signature",
    "U": "untrusted signature",
    "B": "bad signature",
    "N": "no signature",
    "X": "expired signature",
    "Y": "signature made with an expired key",
    "R": "signature made with a revoked key",
    "E": "signature made with a key that cannot be found",
}

# A record is: hash, author name, author date (ISO 8601), %G? state.
# The format string uses git's %x00 / %x1e placeholders, so the
# output carries real NUL / record-separator bytes — a comma or a
# space in an author name can never split a record the wrong way.
# (Literal NUL bytes cannot be passed in a subprocess argument,
# which is why the placeholders are written as text here.)
RECORD_SEP = "\x1e"
FIELD_SEP = "\x00"
LOG_FORMAT = "%H%x00%an%x00%aI%x00%G?%x1e"


def state_label(state):
    """Plain-language meaning of a git %G? signature state."""
    return STATE_LABELS.get(state, "unknown signature state")


def is_signed(state):
    """Only a good signature (G) counts as signed."""
    return state == "G"


def parse_record(record):
    """Parse one git log record into a commit dict, or None if bad.

    A record holds the full hash, the author name, the commit date
    in ISO 8601 form, and the one-letter %G? signature state.
    """
    if not record.strip():
        return None
    record = record.strip()
    fields = record.split(FIELD_SEP)
    if len(fields) != 4:
        return None
    commit_hash, author, committed, state = fields
    if not commit_hash or not author or not committed:
        return None
    state = state.strip()
    date = committed[:10]
    return {
        "hash": commit_hash,
        "short_hash": commit_hash[:7],
        "author": author,
        "date": date,
        "committed": committed,
        "state": state,
        "state_label": state_label(state),
        "signed": is_signed(state),
    }


def parse_log_output(output):
    """Parse the whole git log output into a list of commit dicts."""
    commits = []
    for record in output.split(RECORD_SEP):
        parsed = parse_record(record)
        if parsed is not None:
            commits.append(parsed)
    return commits


def run_git(repo, args, env=None):
    """Run a git command inside repo. Returns the CompletedProcess,
    or None when git cannot be started at all."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def is_git_repo(path):
    result = run_git(path, ["rev-parse", "--git-dir"])
    return result is not None and result.returncode == 0


def check_repo(path, limit=DEFAULT_LIMIT, since=None, all_refs=False):
    """Check one repo. Returns (report dict, error string or None).

    The report lists every checked commit and every commit that
    does not carry a good signature, newest first.
    """
    if not is_git_repo(path):
        return None, "Not a git repository: %s" % path
    args = ["log", "--format=" + LOG_FORMAT]
    if limit is not None:
        args += ["--max-count", str(limit)]
    if since is not None:
        args += ["--since", since]
    if all_refs:
        args += ["--all"]
    result = run_git(path, args)
    if result is None:
        return None, "git is not installed or not on PATH"
    if result.returncode != 0:
        message = result.stderr.strip()
        if "does not have any commits yet" in message or (
            "bad default revision" in message
        ):
            # A repo with no commits yet: nothing to flag.
            return {
                "repo": str(path),
                "checked": 0,
                "unsigned": [],
                "commits": [],
                "limit": limit,
                "since": since,
            }, None
        return None, message or "git log failed"
    commits = parse_log_output(result.stdout)
    unsigned = [item for item in commits if not item["signed"]]
    report = {
        "repo": str(path),
        "checked": len(commits),
        "unsigned": unsigned,
        "commits": commits,
        "limit": limit,
        "since": since,
    }
    return report, None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check the recent commits in a git repo are signed, fail CI on an unsigned commit."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="path to the git repo to check (default: current folder)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help="check only the most recent N commits (default: 20)",
    )
    parser.add_argument(
        "--since",
        default=None,
        metavar="DATE",
        help="check only commits newer than this date, for example 2026-01-01",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="check commits on all branches, not just the current one",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON on standard output (the plain lines go to standard error)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="git-signed-commit-checker-cli " + VERSION,
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be 1 or more")
    if args.since is not None:
        try:
            datetime.fromisoformat(args.since)
        except ValueError:
            parser.error("--since must be a date, for example 2026-01-01")
    path = Path(args.path)
    if not path.exists():
        print("No such path: %s" % path, file=sys.stderr)
        return 2
    probe = run_git(path, ["--version"])
    if probe is None:
        print("git is not installed or not on PATH", file=sys.stderr)
        return 2
    report, error = check_repo(path, args.limit, args.since, args.all)
    if error is not None:
        print(error, file=sys.stderr)
        return 2
    out = sys.stdout if not args.json else sys.stderr
    if report["unsigned"]:
        for item in report["unsigned"]:
            print(
                "UNSIGNED %s — %s — %s (%s)"
                % (
                    item["short_hash"],
                    item["author"],
                    item["date"],
                    item["state_label"],
                ),
                file=out,
            )
        print(
            "Checked %d commit(s), %d unsigned commit(s)."
            % (report["checked"], len(report["unsigned"])),
            file=out,
        )
    else:
        print(
            "OK — %d commit(s) checked, all commits are signed."
            % report["checked"],
            file=out,
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["unsigned"] else 0


if __name__ == "__main__":
    sys.exit(main())
