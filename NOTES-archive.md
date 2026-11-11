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

