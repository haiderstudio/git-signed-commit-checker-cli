#!/bin/sh
# Run the checker on the bundled sample repo and show the report.
# The checker exits 1 because the sample repo's commits are all
# unsigned; that is the point of the example, so this script exits 0.
cd "$(dirname "$0")/.." || exit 2
sh examples/make-sample-repo.sh
echo "--- all recent commits (default limit 20) ---"
python3 src/git_signed_commit_checker.py "${TMPDIR:-/tmp}/signed-commit-sample-repo" || true
echo "--- only the newest commit ---"
python3 src/git_signed_commit_checker.py --limit 1 "${TMPDIR:-/tmp}/signed-commit-sample-repo" || true
echo "--- only commits from the last 7 days ---"
python3 src/git_signed_commit_checker.py --since "$(date -d '7 days ago' '+%Y-%m-%d')" "${TMPDIR:-/tmp}/signed-commit-sample-repo" || true
