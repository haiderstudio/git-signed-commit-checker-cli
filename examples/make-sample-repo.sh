#!/bin/sh
# Build a small sample git repo for the examples.
# Three unsigned commits: two from today, one from 40 days ago.
# The checker flags all three, so the sample always fails (exit 1)
# — that is the point of the example.
set -e
SAMPLE_DIR="${TMPDIR:-/tmp}/signed-commit-sample-repo"
rm -rf "$SAMPLE_DIR"
mkdir -p "$SAMPLE_DIR"
cd "$SAMPLE_DIR"
git init -q -b main
git config user.email "sample@example.com"
git config user.name "Sample User"
git config commit.gpgsign false
echo "sample project" > README.md
git add README.md
GIT_AUTHOR_DATE="$(date -d '40 days ago' '+%Y-%m-%dT%H:%M:%S')" \
GIT_COMMITTER_DATE="$(date -d '40 days ago' '+%Y-%m-%dT%H:%M:%S')" \
  git commit -qm "old change"
echo "notes" > notes.txt
git add notes.txt
git commit -qm "add notes"
echo "more notes" >> notes.txt
git add notes.txt
git commit -qm "more notes"
echo "Sample repo built at $SAMPLE_DIR"
