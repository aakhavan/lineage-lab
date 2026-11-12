# NOTES: lineage-lab

Rules: under 150 lines. Current state, open questions, last two steps' result + additions. Older sections go to `NOTES-archive.md` (the factory rotates).

## Current state
L5 done. python -m lineagelab.compare report writes docs/lineage-compare.md and prints one JSON line. The manifest has 18 table edges. OpenMetadata and OpenLineage each have 18 table edges (precision 1.0, recall 1.0 against the manifest) and 63 column edges, all shared. One unmatched name, the CTE sizes in kpi_cohort_retention (postgres://localhost:55432/sizes.cohort_size), is counted and listed; that edge is left out of the score. Every OpenMetadata edge is labeled source OpenLineage because overrideLineage is off, so the column set is the union of the dbt workflow and the OpenLineage post. README has the run from nothing. 22 tests pass.

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
- L3 (verify, YAML shape): checked against the installed 2.0.5 model inside the container (`DbtPipeline`, `extra=forbid`; `DbtLocalConfig` keys dbtManifestFilePath / dbtCatalogFilePath / dbtRunResultsFilePath / dbtSourcesFilePath). `ingest dbt` validates the rendered sourceConfig with that model before every run. Direct `docker exec` and WebFetch were blocked in the session, so the check is part of the module run.
- L3 (verify, artifacts): local file paths must exist in the runner, so the three artifacts are `docker cp`'d to /tmp/lineagelab_dbt in the container and removed with the YAML afterwards.
- L3 finding: governor's `models/staging/_staging.yml` has `description: ''` for every staging and intermediate column; only the seven single-column kpi_* models carry column descriptions. OpenMetadata therefore shows 0 column descriptions on stg_orders, and the acceptance check "stg_orders has column descriptions" fails. Not faked: the fix belongs in ../olist-dbt (governor), not here.
- L3: OM 2.0.5 rejects `upstreamDepth > 3` (HTTP 400). `om.upstream` now fetches deeper lineage in steps of at most 3.
- L3: dbt owners are not mapped (24 warnings: no OM user/team named governor_admin, governor_build, or the persona names). They are harmless, and owners are out of scope.
- L4 (verify, transport): one `dbt-ol build` is enough. Composite transport, file append plus HTTP `api/v1/lineage` on Marquez. Config is YAML under `logs/` because `OPENLINEAGE__` values are lowercased. Column lineage needs no flag; `catalog.json` was already in `target/` and the build left it unchanged.
- L5: OpenMetadata 2.0.5 keeps one edge per table pair, with one `lineageDetails.source`. After the L4 forward, all 18 edges say `source: OpenLineage`. L5 re-ran `ingest dbt` (rc 0): the edges' updatedAt/updatedBy changed, but source and description stayed OpenLineage (DbtPipeline `overrideLineage` defaults to false, so the dbt workflow merges). The current OM column set (63) is therefore the union of dbt and OpenLineage. L3 counted 63 dbt column edges and OpenLineage has 63 mapped edges, so the two parsers almost certainly agree; that is an inference, not a separate measurement. A clean dbt-only view would need `overrideLineage: true` in ingest.py (not in L5's paths).
- L5: dbt-ol reports CTE `sizes` (kpi_cohort_retention) as input dataset `postgres://localhost:55432/sizes` (column `cohort_size`). compare lists it as unmatched; OpenMetadata did not resolve it.
- L4 (verify, OpenMetadata): model events (`eventTime` with `Z`) resolved with no namespace map configured. Test and parent events (`+00:00`) get HTTP 400 "Invalid request format". Rewriting only the timestamp accepts them and still creates no test edge (no output dataset).

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

## Additions for L4
L4 should keep the L2 artifacts and the catalogue L3 already loaded. work/olist-dbt/target holds manifest.json and catalog.json from dbt docs generate (dbt 1.12.6, dbt-postgres 1.11.0) and run_results.json restored from dbt build (15 models, 18 tests, PASS=33). A later dbt run overwrites target/ and run_results.json; copy the build file aside if test results must survive. Profile governor, target dev, schema dev_governor, password GOVERNOR_BUILD_PASSWORD. OpenMetadata 2.0.5 is at http://localhost:8585, service shop_testbed, FQN shop_testbed.shop.<schema>.<table>. dev_governor has 15 model descriptions, 7 column descriptions on kpi_* only (staging and intermediate column descriptions are empty in the dbt YAML), 18 test cases, and lineage raw to stg to int to kpi. kpi_gmv at depth 4 has 9 nodes and 8 edges, including raw.olist_orders_dataset, olist_order_items_dataset and olist_customers_dataset, plus column lineage (63 column edges in the schema, 28 upstream of kpi_gmv). om.upstream asks for depth in steps of at most 3; the server returns HTTP 400 above 3. Owners were not mapped. Marquez 0.51.1 is at http://localhost:5000. Do not start, stop or change the governor test bed, and do not write ../olist-dbt.

## Additions for L5
dbt-ol dataset names (namespace postgres://localhost:55432, name shop.<schema>.<table>) resolve in OpenMetadata 2.0.5 to shop_testbed.shop.<schema>.<table> with no namespace map. Model events (eventTime ending in Z) are accepted. Test events and the parent run event (+00:00) get HTTP 400 'Invalid request format'. Tests have no output dataset, so they add no table edge even when accepted. logs/olforward-report.json has per-event results. OpenMetadata now holds OpenLineage-source edges next to the dbt-workflow edges; account for both sources when comparing lineage in L5.

## L5 result
*Three views of lineage compared, 12 Nov 2026 10:36.*

Implementer `claude-tc-opus`; reviewers `cursor-grok`: pass; 0 fix loop(s); branch `factory/L5`.

| check | ok | detail |
|---|---|---|
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| compare report prints its JSON line | yes | 18}, "openmetadata": {"table_edges": 18, "column_edges": 63, "precision": 1.0, "recall": 1.0}, "openlineage": {"table_ed |
| the manifest gives the reference table edges | yes | 18 |
| openmetadata has edge counts, precision and recall | yes | {'table_edges': 18, 'column_edges': 63, 'precision': 1.0, 'recall': 1.0} |
| openlineage has edge counts, precision and recall | yes | {'table_edges': 18, 'column_edges': 63, 'precision': 1.0, 'recall': 1.0} |
| unmatched names are counted | yes | 1 |
| docs/lineage-compare.md exists | yes | 75 lines |
| the report shows the manifest edge count | yes |  |
| README has the command lineagelab.stack up | yes |  |
| README has the command lineagelab.ingest database | yes |  |
| README has the command lineagelab.ingest dbt | yes |  |
| README has the command lineagelab.olrun | yes |  |
| README has the command lineagelab.compare report | yes |  |
| no token in the repo files | yes |  |
| pytest tests | yes | 22 passed in 0.47s |
| required tests present | yes | 4 found |

Review: L5 does what its prompt asks. normalise is the one name mapper and is unit-tested; an edge with an unmapped end stays out of the score and the raw name is counted and listed (live: the CTE postgres://localhost:55432/sizes.cohort_size). score() runs only against manifest table edges. The markdown and the JSON line come from the same dict and match: 18 table edges, 63 column edges, precision 1.0, recall 1.0, unmatched 1. README gives the full run order, URLs, and three findings.

For Amir: Acceptance checks the JSON shape and that the manifest count occurs in the markdown; it does not recompute precision. The 63-edge column agreement is on the merged OpenMetadata graph (every edge labeled OpenLineage). A dbt-only view would need overrideLineage, which this step does not change.

## Additions for the next plan
compare.normalise is the only name mapper. manifest: database.schema.table, drop the database. openmetadata: service.database.schema.table[.column], drop service and database. openlineage: namespace/name, with name shop.schema.table[.column] and namespace postgres://host:port, drop the namespace and shop. Unmapped names are listed and those edges are not scored. Live: 18 manifest table edges; OpenMetadata and OpenLineage each 18 table edges, precision 1.0, recall 1.0, and 63 column edges (Jaccard 1.0). olevents has 64 column edges; the one held out is postgres://localhost:55432/sizes.cohort_size (CTE sizes in kpi_cohort_retention). OpenMetadata keeps one edge per table pair and all 18 are source OpenLineage. overrideLineage is false, so the 63 columns are the union of the dbt workflow and the L4 post, not a dbt-only set. FQN shop_testbed.shop.<schema>.<table>. python -m lineagelab.compare report writes docs/lineage-compare.md and prints that JSON. The README lists the run from nothing.
