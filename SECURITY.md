# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key, token, or secret. It only reads the git repo you point it at, and it never signs a commit, never rewrites history, never deletes anything, and never changes a file. It writes nothing except the report on standard output (and usage errors on standard error).

The signed-commit test in the test suite makes a throwaway GPG key inside a temp folder and deletes the folder when the test ends. No key material is ever stored in this repo.

If you find a case where the tool changes anything, or reports a pass for a commit that is not signed with a good signature, please open an issue describing the exact commands and input. Do not include any real secret in the report.
