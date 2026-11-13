# Sample output

Real output of `sh examples/run-example.sh`, run on 2026-11-12.
The sample repo is rebuilt on every run, so the short hashes change;
the commit dates move with the calendar. The verdicts stay the same:
all three sample commits are unsigned.

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
