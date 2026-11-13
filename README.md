# git-signed-commit-checker-cli

Check the recent commits in a git repo are signed, fail CI on an unsigned commit.

[![CI](https://github.com/haiderstudio/git-signed-commit-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/git-signed-commit-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`git_signed_commit_checker` looks at the recent commits in a git
repo (the newest 20 by default) and reports every commit that does
not carry a good signature — GPG or SSH, either counts, as long as
git itself verifies it as good. Each unsigned commit is listed with
its short hash, its author, and its date, plus what is wrong with
the signature: no signature, untrusted, bad, expired, revoked, or
a key that cannot be found. It exits 1 when any unsigned commit is
found, so it can fail a CI run. A repo where every checked commit
is signed exits 0.

- An unsigned commit in a repo that requires signing is either a
  machine that is not set up to sign, or a commit that should not
  be there. This tool names the exact commits before the push,
  instead of letting the merge or the audit find them.
- Only a good signature (`G` in git's `%G?` state) counts as
  signed. Anything else — `N` no signature, `U` untrusted, `B`
  bad, `X` expired, `Y` expired key, `R` revoked, `E` key not
  found — is reported and fails the check.
- `--limit N` checks only the most recent N commits.
  `--since DATE` checks only commits newer than a date, for
  example `2026-01-01`. `--all` checks commits on all branches,
  not just the current one.
- `--json` prints the result as JSON (the plain lines go to
  standard error), for scripts that read the result.
- A repo with no commits yet passes — there is nothing to flag.

## Who it is for

Teams that enforce signed commits, and anyone whose repo policy
says every commit must be signed. If your merge policy rejects
unsigned commits, this is the gate that says so before the push,
while the fix is still a local re-commit.

## What it does NOT do

- It does not sign anything. It is report-only — signing a commit
  is your setup's job, made after you see which commits are
  unsigned. It never signs or rewrites a commit, and it never
  changes a file.
- It checks local git history only. It does not check signatures through the GitHub API — that is a remote check on what GitHub received, a different job.
- It does not verify DCO sign-off. A `Signed-off-by` line in a
  commit message is not a GPG signature, and this tool does not
  look for it.
- It does not check who the signer is, only that the signature
  verifies as good. Per-author signing baselines are a different
  job.
- It does not touch the network. It reads the local repo only.

## How this differs

- v-zahajsky/github-signed-commits-checker (0 stars) checks
  signatures through the GitHub API — a remote check, needing
  the network and a repo on GitHub. This tool reads local git
  history only, works offline, and needs no account or token.
- jsquyres/signed-off-by-github-webhook (0 stars) is a webhook
  that verifies commits contain "Signed-off-by" — DCO sign-off,
  not a GPG signature. This tool checks real cryptographic
  signatures, not message text.
- Iceman2050/sig-baseline-checker (0 stars) builds per-author
  signing baselines from history and flags identity anomalies —
  anomaly detection, a different job from a straight pass/fail
  gate on the recent commits.
- CloudCorpRecords/commitcheck (0 stars) checks commit-message
  convention and DCO sign-off over a history range — again
  message text, not signatures.
- There is no exact-name rival: a GitHub search for
  "git-signed-commit-checker-cli" returns 0 results.

## Install

```sh
git clone https://github.com/haiderstudio/git-signed-commit-checker-cli.git
cd git-signed-commit-checker-cli
```

No dependencies to install — Python 3.8 or newer and git are
all it needs. (The clone step was not run here — it needs the
network — but the command is the standard one used by every
repo in this series, and everything after the clone is verified
on a fresh folder copy.)

## Usage

```sh
python3 src/git_signed_commit_checker.py [path] [--limit N] [--since DATE] [--all] [--json]
```

Run it inside a repo, or give the repo path. Exit codes: 0 means
every checked commit is signed, 1 means at least one unsigned
commit was found, 2 means a usage error (not a git repo, bad flag,
bad date, git missing).

```text
$ python3 src/git_signed_commit_checker.py
UNSIGNED 8fc10ad — Sample User — 2026-11-12 (no signature)
Checked 3 commit(s), 3 unsigned commit(s).
```

## Examples

### 1. The bundled sample repo (default limit of 20)

The examples folder builds a small repo with three unsigned
commits: two from today and one from 40 days ago. Run it with:

```sh
sh examples/run-example.sh
```

Real output from a run on 2026-11-12 (the short hashes change
on every run because the repo is rebuilt; the dates move with
the calendar — the verdicts stay the same):

```text
Sample repo built at /tmp/signed-commit-sample-repo
--- all recent commits (default limit 20) ---
UNSIGNED 8fc10ad — Sample User — 2026-11-12 (no signature)
UNSIGNED 1fa08fe — Sample User — 2026-11-12 (no signature)
UNSIGNED 33d50f8 — Sample User — 2026-10-03 (no signature)
Checked 3 commit(s), 3 unsigned commit(s).
--- only the newest commit ---
UNSIGNED 8fc10ad — Sample User — 2026-11-12 (no signature)
Checked 1 commit(s), 1 unsigned commit(s).
--- only commits from the last 7 days ---
UNSIGNED 8fc10ad — Sample User — 2026-11-12 (no signature)
UNSIGNED 1fa08fe — Sample User — 2026-11-12 (no signature)
Checked 2 commit(s), 2 unsigned commit(s).
```

The `--limit 1` run checks only the newest commit, and the
`--since` run drops the 40-day-old commit — both still fail,
because the remaining commits are unsigned too.

### 2. JSON output, for scripts

With `--json`, the same result comes back as JSON on standard
output (the plain lines go to standard error). Real output
from the sample repo, `--limit 1`:

```sh
python3 src/git_signed_commit_checker.py --json --limit 1 /tmp/signed-commit-sample-repo
```

```json
{
  "checked": 1,
  "commits": [
    {
      "author": "Sample User",
      "committed": "2026-11-12T05:15:09+00:00",
      "date": "2026-11-12",
      "hash": "8fc10ad78b6fb9b83209ab0db54fd0fb08312b78",
      "short_hash": "8fc10ad",
      "signed": false,
      "state": "N",
      "state_label": "no signature"
    }
  ],
  "limit": 1,
  "repo": "/tmp/signed-commit-sample-repo",
  "since": null,
  "unsigned": [
    {
      "author": "Sample User",
      "committed": "2026-11-12T05:15:09+00:00",
      "date": "2026-11-12",
      "hash": "8fc10ad78b6fb9b83209ab0db54fd0fb08312b78",
      "short_hash": "8fc10ad",
      "signed": false,
      "state": "N",
      "state_label": "no signature"
    }
  ]
}
```

This command exits 1, because the one commit it checked is unsigned.

### 3. An empty repo, and a folder that is not a repo

```sh
python3 src/git_signed_commit_checker.py /path/to/a/fresh/repo
python3 src/git_signed_commit_checker.py /tmp
```

```text
OK — 0 commit(s) checked, all commits are signed.
```

```text
Not a git repository: /tmp
```

The first command exits 0 — a repo with no commits has nothing
to flag. The second exits 2 — a plain message, not a crash.

## How it is tested

```sh
python3 tests/test_git_signed_commit_checker.py
```

The tests build real temp git repos and check the real output:
unsigned commits fail with hash, author, and date; `--limit`
and `--since` narrow the check both ways and together; an empty
repo passes; a non-repo and a missing path exit 2; a bad date
exits 2; `--all` includes other branches; `--json` parses and
matches; a detached HEAD does not crash; the bundled examples
run and report the same verdicts. The same suite also checks the
hygiene rules: no filler text, no secrets, no absolute home
paths, `.env` first in `.gitignore`, and the CI file carrying
the required markers.

**The signed-commit test, stated plainly:** the test suite makes
a real signed commit with a throwaway GPG key generated inside
a temp folder, and checks it passes. The key never leaves that
folder and the folder is deleted when the test ends — no key
material is stored in this repo. If `gpg` is missing, or the
throwaway key cannot be made, that one test is skipped and the
signed path is covered by the parsing tests for the `G` state
instead. The parsing tests cover every `%G?` state (`G`, `U`,
`B`, `N`, `X`, `Y`, `R`, `E`, and an unknown state) with no
repo needed.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small, focused
improvements are welcome — and the tool must stay report-only:
it never signs a commit and never rewrites history.

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Written from scratch for this repo. The idea — gating on signed
commits — is a common one; the code, the tests, and the wording
here are original. The four closest existing tools are named in
"How this differs" above.
