# NOTES: lineage-lab

Rules: under 150 lines. Current state, open questions, last two steps' result + additions. Older sections go to `NOTES-archive.md` (the factory rotates).

## Current state
L2 is done (11 Nov 2026). work/olist-dbt is a copy of ../olist-dbt without top-level target/, logs/ or .git, built with dbt 1.12.6 and dbt-postgres 1.11.0 on target dev only (15 models in dev_governor, 18 tests passed). target/ holds manifest.json and catalog.json from docs generate, and run_results.json from the build. OpenMetadata 2.0.5 has database service shop_testbed, database shop, schemas raw (9 tables), dev_governor (22) and analytics (17); ingestion was DatabaseMetadata via docker exec in openmetadata_ingestion, with sample data and profiling off. Marquez 0.51.1 is still up. stack up downloads the gitignored OpenMetadata compose file when it is missing. The governor test bed was not started, stopped or reconfigured.

## Open questions
- Docker engine / compose version not recorded: `docker version` / `docker compose version` were blocked by the factory session's permission rules (`docker ps` was allowed). `stack/versions.yaml` has `docker_engine: null`.
- OM compose binds `./docker-volume/db-data-postgres` (relative to `stack/openmetadata/`) for its Postgres data; git-ignored. `down` keeps it and the named volumes.
- OM compose uses fixed `container_name`s (`openmetadata_server`, `openmetadata_ingestion`, ...): L2's `docker exec` target is `openmetadata_ingestion`.
- L2 (verify, runner): `docker exec` in `openmetadata_ingestion` works on this Windows machine (test bed reached as host.docker.internal:55432, server as http://openmetadata-server:8585/api); the uvx fallback is coded but was not run. Recorded as `tools.ingest_runner: docker_exec`.
- L2: the OM 2.x DatabaseMetadata workflow has no sample-data switch; sample data and profiling live in separate Profiler/AutoClassification workflows, which the lab never runs. Checked after ingestion: sampleData of dev_governor.stg_orders has 0 rows.
- L2: `dbt docs generate` overwrites target/run_results.json; dbtrun puts the build's run_results.json back, so L3 gets the test results.
- L2: the ingestion logs a harmless warning (`pg_stat_statements` does not exist; that is query-usage collection only).
- L2: the service connection (with the test-bed admin DSN parts, documented local default) is stored in OpenMetadata by the PUT; the bot JWT is only in work/ingest/database.yaml and in /tmp of the container during the run (removed after).
- `uv --version` was not permitted in the factory session; the uv version is not recorded.

## L2 result
*Work copy, dbt build with artifacts, and the database in OpenMetadata, 11 Nov 2026 23:25.*

Implementer `claude-tc-opus`; reviewers `cursor-grok`: pass; 0 fix loop(s); branch `factory/L2`.

| check | ok | detail |
|---|---|---|
| work copy has target/manifest.json | yes |  |
| work copy has target/catalog.json | yes |  |
| work copy has target/run_results.json | yes |  |
| the work copy has no .git | yes |  |
| work/, artifacts/ and logs/ are not tracked | yes |  |
| no token in the repo files | yes |  |
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| tables can be read from OpenMetadata | yes |  |
| dev_governor.stg_orders is in OpenMetadata with its columns | yes | 6 columns |
| dev_governor.kpi_gmv is in OpenMetadata with its columns | yes | 2 columns |
| analytics.kpi_gmv is in OpenMetadata with its columns | yes | 2 columns |
| pytest tests | yes | 12 passed in 0.32s |
| required tests present | yes | 5 found |

Review: L2 does what its prompt asks, and the acceptance pass matches the run. The work copy skips top-level target/, logs/ and .git and leaves ../olist-dbt read-only. dbt 1.12.6 / dbt-postgres 1.11.0 built work/olist-dbt with --target dev (dev_governor only, 33/33 PASS); run_results.json is that build, restored after docs generate. Ingest used docker exec in openmetadata_ingestion for DatabaseMetadata on database shop, schemas raw, dev_governor and analytics only, with no profiler; the workflow YAML is under gitignored work/ and the container copy was removed.

For Amir: Live acceptance shows the three tables exist. Schema exclusion is shown by the workflow filters plus ingest_database.log: database shop, Filtered 5, 0 errors. The offline test rejects public, information_schema and lookalike names. The uvx fallback is coded and was not executed. GetQueries ran and stored nothing because pg_stat_statements is missing. The shop_testbed service in OpenMetadata stores the documented test-bed admin connection. The bot JWT is only in work/ingest/database.yaml; the container copy was removed.

## L1 result
*The two stacks (OpenMetadata 2.0.5, Marquez) and the OpenMetadata client, 11 Nov 2026 23:12.*

Implementer `claude-tc-opus`; reviewers `cursor-grok`: pass; 0 fix loop(s); branch `factory/L1`.

| check | ok | detail |
|---|---|---|
| OpenMetadata compose file names its release URL | yes |  |
| OpenMetadata images are 2.0.5 | yes |  |
| Marquez compose file exists with pinned tags | yes |  |
| stack/versions.yaml exists | yes |  |
| no token in the repo files | yes |  |
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| OpenMetadata reports version 2.0.x | yes | 2.0.5 |
| Marquez API answers | yes | 200 |
| om.client() logs in and an unknown table is None | yes |  |
| pytest tests | yes | 5 passed in 0.22s |
| required tests present | yes | 4 found |

Review: L1 is in place and the acceptance pass is consistent with the code. Image tags are pinned and listed in stack/versions.yaml. The OpenMetadata compose file is the 2.0.5 release file plus a dated source comment, git-ignored so upstream default keys stay out of the commit. Marquez 0.51.1 is pinned; its database port is not published. stack.py uses only compose projects lineagelab_om and lineagelab_marquez with -p, and down keeps volumes. om.table and om.upstream reshape API fields (paging.total, edges by id) and return None for an unknown table. Docker engine version is recorded as null.

For Amir: plan/prompts/L2.md and plan/accept/accept_l2.py were edited so the next step downloads the git-ignored OpenMetadata compose file. That edit is outside L1's allowed paths; NOTES records it as delegated after the secret_in_diff stop. This review did not re-download the release file to byte-compare it. Committed files contain only documented local defaults (OpenMetadata admin, Marquez dev database). Docker engine version is still null.

## Additions for L2
The OpenMetadata compose file is git-ignored (stack/openmetadata/docker-compose.yml) because the release file contains upstream default keys. It is present on this machine with a first comment line dated 2026-11-11; stack up does not download it yet. L2's prompt item 0 is already updated to download it from stacks.om.source in stack/versions.yaml when missing, and accept_l2.py requires test_missing_compose_file_is_downloaded_from_the_recorded_url. Both stacks are left running: OpenMetadata 2.0.5 at http://localhost:8585 (project lineagelab_om, ingestion container openmetadata_ingestion, Airflow 8080, search 9200, its Postgres published on 5432) and Marquez 0.51.1 at http://localhost:5000 with UI on 3000 (project lineagelab_marquez; DB port not published). Use 0.51.1, not the older GitHub release 0.50.0. om.client() keeps the ingestion-bot JWT in memory; bot_token() returns it for the workflow file under work/. Login is POST /api/v1/users/login with a base64 password; the bot JWT is GET /api/v1/bots/name/ingestion-bot then GET /api/v1/users/auth-mechanism/{id}. table() uses paging.total; upstream() joins upstreamEdges by entity id. The catalogue is empty. docker_engine in versions.yaml is null. Do not start, stop, or change the governor test bed (host port 55432).

## Additions for L3
Artifacts for L3 are in work/olist-dbt/target/: manifest.json and catalog.json from dbt docs generate (dbt 1.12.6, 22:17:00Z); run_results.json restored from dbt build (22:16:53Z, 15 models, 18 tests, PASS=33, 0 failed). Docs generate overwrites run_results; keep the restored build file so test results survive. dbt command: uvx --from dbt-core==1.12.6 --with dbt-postgres==1.11.0, project and profiles dirs work/olist-dbt, --target dev, profile governor, schema dev_governor. Password is GOVERNOR_BUILD_PASSWORD (no default). Do not use target prod. Service shop_testbed is registered; FQN shop_testbed.shop.<schema>.<table>; counts raw 9, dev_governor 22, analytics 17. Verified runner: docker exec openmetadata_ingestion (CLI 2.0.5.1, server 2.0.5), test bed host.docker.internal:55432, API http://openmetadata-server:8585/api. docker cp the YAML to /tmp, ingest, then rm it. uvx fallback was not run; pin openmetadata-ingestion[postgres]~=2.0.5.0 has no dbt extra. JWT from om.bot_token() stays in gitignored work/ only. No profiler or sample data. GetQueries stored nothing (pg_stat_statements missing). stack up downloads the gitignored OM compose file if missing. Do not start, stop, or change the governor test bed; do not write ../olist-dbt.
