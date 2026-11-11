# AGENTS.md: rules for every agent in this repo

This repo is **lineage-lab**, a learning module beside governor, built step by step by the code factory. Your step prompt names what to read; read that, not whole documents.

## Hard rules
- **Never commit, push, branch or stash.** The factory commits.
- **Never read `.env` or `.env.*`**; never print, log or write a key, password or token. Settings are read by name from the environment. The only credentials allowed in files are the documented local defaults of the tools (OpenMetadata `admin@open-metadata.org` / `admin`, the governor test bed defaults in `../governor/testbed/README.md`). The OpenMetadata bot token is fetched at run time and kept in memory only.
- **Change only the paths your step allows** (plus `NOTES.md`). Never edit `plan/` (locked).
- **Never change anything in `../governor` or `../olist-dbt`.** Read them; work on the copy under `work/` (git-ignored). Never read `../governor/testbed/data/` (real data) and never copy data values into this repo: metadata only (names, types, descriptions, counts).
- Python 3.12 + uv. Keep the package's own dependencies light. Run the heavy command-line tools (`metadata`, `dbt`, `dbt-ol`) inside the OpenMetadata ingestion container (`docker exec`) or in isolated uv tool environments (`uvx --from ...`), never as dependencies of this package. Record every tool version you used in `stack/versions.yaml`.
- Docker: only the two stacks in `stack/` (compose projects `lineagelab_om` and `lineagelab_marquez`) and read access to the governor test bed Postgres on host port 55432. Never stop, remove or change the governor test bed containers or volumes. Never `docker system prune`.
- Tests under `tests/` run offline (no Docker, no network): they test pure functions on small fixtures. Live checks live in the acceptance scripts and in `python -m lineagelab.<module>` commands that print one JSON line last.
- The spec marks some facts "verify". When the real tool differs from the spec, follow the tool, and write what you found (one line each) under "Open questions" or your step result in `NOTES.md`. Do not fake a result to make a check pass; a finding is a valid outcome.

## Output rules
- Quiet commands; logs go to `logs/` (git-ignored); paste summaries, not logs.
- `NOTES.md`: add a short "<step> result" when you finish.
