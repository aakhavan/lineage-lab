# lineage-lab

A learning module beside [governor](../governor): it takes the dbt project governor built (`../olist-dbt`) and the Postgres test bed, puts them into **OpenMetadata** (catalogue, descriptions, tests, lineage) and emits **OpenLineage** events from a dbt run (viewed in Marquez, then sent to OpenMetadata), and measures how the three views of lineage agree.

It reads governor's outputs and changes nothing in `governor` or `olist-dbt`. Spec: `docs/spec.md`. Built step by step by the code factory (`plan.yaml`).

## Run the whole lab from nothing

Needs Docker (at least 6 GiB and 4 vCPUs for OpenMetadata), Python 3.12 with `uv`, and the governor test bed running on host port 55432:
`docker compose -f ../governor/testbed/docker-compose.yml up -d --wait` (the lab never starts, stops or changes it).
Set `GOVERNOR_BUILD_PASSWORD` in the environment for the dbt steps. Each command prints one JSON line last.

| # | command | what it shows |
|---|---|---|
| 1 | `uv run python -m lineagelab.stack up` | Starts OpenMetadata 2.0.5 and Marquez and waits until healthy (`stack status` prints both). |
| 2 | `uv run python -m lineagelab.workcopy` | Copies `../olist-dbt` to `work/olist-dbt` (no `target/`, `logs/`, `.git`). |
| 3 | `uv run python -m lineagelab.dbtrun build` | `dbt build` + `dbt docs generate` on target `dev`: 15 models, 18 tests, the three artifacts. |
| 4 | `uv run python -m lineagelab.ingest database` | Registers service `shop_testbed` and catalogues schemas `raw`, `dev_governor`, `analytics`. |
| 5 | `uv run python -m lineagelab.ingest dbt` | Loads the dbt artifacts: descriptions, tests and results, table and column lineage. |
| 6 | `uv run python -m lineagelab.olrun` | `dbt-ol build`: OpenLineage events go to Marquez and to `artifacts/openlineage/events.ndjson`. |
| 7 | `uv run python -m lineagelab.olforward` | Experiment: posts the saved events to OpenMetadata's OpenLineage endpoint; writes `docs/findings/openlineage-to-openmetadata.md`. |
| 8 | `uv run python -m lineagelab.compare report` | Compares manifest, OpenMetadata and OpenLineage lineage; writes `docs/lineage-compare.md`. |

`uv run python -m lineagelab.stack down` stops both stacks and keeps their volumes.

URLs to open:
- OpenMetadata UI: http://localhost:8585 (local default login `admin@open-metadata.org` / `admin`). Open `shop_testbed > shop > dev_governor > kpi_gmv` and its **Lineage** tab (after steps 4 and 5).
- Marquez UI: http://localhost:3000, namespace `lineagelab` (after step 6). Marquez API: http://localhost:5000.
- OpenMetadata's Airflow (ingestion container): http://localhost:8080.

## What I learned

- **All three views agree on table lineage.** The manifest's `depends_on` gives 18 edges from `raw` sources through staging and intermediate models to `kpi_*`. OpenMetadata (upstream of every `kpi_*`) and dbt-ol events give the same 18: precision and recall are both 1.0. OpenMetadata and OpenLineage also agree on all 63 column edges. The only difference is the CTE `sizes` in `kpi_cohort_retention`, which dbt-ol's SQL parser reported as an input dataset (`docs/lineage-compare.md`).
- **OpenMetadata keeps one edge per table pair, and the first writer's label stays.** After the OpenLineage post, every edge said `source: OpenLineage`. Re-running the dbt workflow updated the same edges (merging column lineage) but did not change that label, because `overrideLineage` is off by default. Do not take `source` as the full history of an edge.
- **dbt-ol names resolve in OpenMetadata with no mapping, but its timestamps may not.** `postgres://localhost:55432` + `shop.<schema>.<table>` landed on `shop_testbed.shop.<schema>.<table>`. Events with `eventTime` ending in `+00:00` (tests and the parent run) were rejected with HTTP 400, and tests add no table edge anyway (`docs/findings/openlineage-to-openmetadata.md`).
