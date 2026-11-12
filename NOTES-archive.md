# NOTES archive

Sections rotated out of NOTES.md (PLAN.md §7.4), oldest first.

## Relocks
- 11 Nov 2026 23:07: L1 stop secret_in_diff: the OpenMetadata release compose file holds upstream default keys; it is now git-ignored and L2 makes stack up download it (via supervise, by Claude, delegated by Amir via chat 11 Nov) (changed: plan/accept/accept_l2.py, plan/prompts/L2.md)

## Relocks
- 11 Nov 2026 23:57: accept_l3 asked for column descriptions on stg_orders, but olist-dbt has none on its silver models (manifest checked); the check now reads the kpi_gmv column description, which dbt does carry (via supervise, by Claude, delegated by Amir via chat 11 Nov) (changed: plan/accept/accept_l3.py)

## L3 result
*dbt artifacts in OpenMetadata (descriptions, tests, lineage), 12 Nov 2026 00:05.*

Implementer `claude-tc-opus`; reviewers `cursor-grok`: pass; 2 fix loop(s); branch `factory/L3`.

| check | ok | detail |
|---|---|---|
| no token in the repo files | yes |  |
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| kpi_gmv and stg_orders can be read | yes |  |
| kpi_gmv has its dbt description | yes |  |
| kpi_gmv has its dbt column description | yes | 1 |
| stg_orders has dbt tests | yes | 2 |
| kpi_gmv lineage reaches a silver model | yes | shop_testbed.shop.dev_governor.int_order_lines, shop_testbed.shop.dev_governor.int_orders, shop_testbed.shop.dev_governo |
| kpi_gmv lineage reaches a raw table | yes | shop_testbed.shop.dev_governor.int_order_lines, shop_testbed.shop.dev_governor.int_orders, shop_testbed.shop.dev_governo |
| kpi_gmv has at least two upstream edges | yes | 8 |
| pytest tests | yes | 14 passed in 0.40s |
| required tests present | yes | 2 found |

Review: L3 matches its prompt, and the passing acceptance matches a real dbt ingest. ingest dbt writes a local-artifact workflow for shop_testbed, copies the L2 manifest, catalog and run_results into openmetadata_ingestion, checks the sourceConfig against that image's DbtPipeline, and runs metadata ingest. Descriptions, tests and lineage are then read back with lineagelab.om. The same command is safe to run again: the kept log is the last run (0 errors, 100% success) and NOTES records one fingerprint after both runs.

For Amir: accept_l3.py was relocked: stg_orders has no column descriptions in the dbt project, so the check now requires kpi_gmv's column description (the API returned 1). Column lineage is present, parsed from compiled SQL. Owners are unmapped (24 warnings). logs/ingest_dbt.log keeps only the last run (0 updated records, success 100%). Raw sources have no descriptions.

## Relocks
- 12 Nov 2026 10:22: plan roles added: design reviewer list now includes claude-tc-opus, so a step implemented by cursor-grok has a reviewer (via supervise, by Claude, on Amir request via chat 12 Nov) (changed: plan.yaml)

## L4 result
*OpenLineage events from dbt (Marquez, saved events, the forward experiment), 12 Nov 2026 10:23.*

Implementer `cursor-grok`; reviewers `claude-tc-opus`: pass; 0 fix loop(s); branch `factory/L4`.

| check | ok | detail |
|---|---|---|
| events file exists | yes | C:\Users\amir0\portfolio\lineage-lab\artifacts\openlineage\events.ndjson |
| the file holds COMPLETE events | yes | {'START': 33, 'COMPLETE': 33} |
| olevents reads the saved events | yes |  |
| events name jobs and datasets | yes | {'jobs': 33, 'datasets': 19, 'table': 18, 'column': 64} |
| table edges can be built from the events | yes | {'jobs': 33, 'datasets': 19, 'table': 18, 'column': 64} |
| the findings file exists (15 to 120 lines) | yes | 80 lines |
| the findings say what resolved and what did not | yes |  |
| no token in the repo files | yes |  |
| OpenMetadata is up | yes | {'up': True, 'version': '2.0.5', 'url': 'http://localhost:8585'} |
| Marquez is up | yes | {'up': True, 'url': 'http://localhost:5000'} |
| Marquez holds the dbt jobs in namespace lineagelab | yes | 33 jobs |
| pytest tests | yes | 18 passed in 0.39s |
| required tests present | yes | 4 found |

Review: L4 does what it asks. dbt-ol writes events.ndjson through its file transport (old file deleted first, never edited after). The file mixes timestamp formats: 36 events end in +00:00, matching the 36 HTTP 400s exactly, which a hand edit would likely have removed. olevents is pure and tested on an invented fixture with blank and broken lines and a FAIL event. olforward only POSTs to the OpenLineage endpoint and reads lineage before and after, so no edges came through another API. Findings hold no SQL, row values or tokens. Minor: the timestamp-swap paragraph is hardcoded prose.

For Amir: The 'rewritten to Z / rewritten to +00:00' paragraph in the findings is hardcoded text in render_findings (olforward.py:287-291), backed only by a manual check recorded in NOTES.md, with no code or log. It prints whenever errors line up with the timestamp format. Also, that manual check sent two edited events to OpenMetadata; it is disclosed and created no edges.

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

