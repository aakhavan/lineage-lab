# lineage-lab: spec (batch 1, L1-L5)

Agreed with Amir on 11 Nov 2026. A learning module for OpenMetadata and OpenLineage, separate from governor so governor's `main` stays frozen for the capstone. It may or may not be shown in the capstone.

Facts below come from the vendors' docs read on 11 Nov 2026. Lines marked **(verify)** were not confirmed there: check them against the running stack and write the result in `NOTES.md`.

## 1. Inputs (read-only)

- `../olist-dbt`: the dbt project governor built (profile `governor`; target `dev` = schema `dev_governor` with the build login, password from env `GOVERNOR_BUILD_PASSWORD`; target `prod` = schema `analytics`). Never changed; steps work on a copy in `work/olist-dbt/` made by `python -m lineagelab.workcopy` (copies the project without `target/`, `logs/` and `.git`).
- The governor test bed: Postgres 16 on host port 55432, database `shop`, schemas `raw`, `dev_governor`, `analytics`. It must be running (`docker compose -f ../governor/testbed/docker-compose.yml up -d --wait`); the lab never starts, stops or changes it. Connection for metadata reads: env `LAB_PG_DSN`, default the documented test-bed admin DSN.

## 2. The stacks (L1)

- **OpenMetadata 2.0.5**, the Postgres flavour of the official quickstart compose file (`https://github.com/open-metadata/OpenMetadata/releases/download/2.0.5-release/docker-compose-postgres.yml`, Apache-2.0), saved unchanged as `stack/openmetadata/docker-compose.yml` with a first comment line naming the URL and the download date; compose project `lineagelab_om`. UI on 8585 (default login `admin@open-metadata.org` / `admin`), the ingestion container's Airflow on 8080, search on 9200. Needs at least 6 GiB and 4 vCPUs for Docker (the machine has 64 GB).
- **Marquez** (the OpenLineage reference backend), a small compose file `stack/marquez/docker-compose.yml` with pinned image tags (API, web UI, its own Postgres); compose project `lineagelab_marquez`; API on 5000, UI on 3000 **(verify the current image names, tags and ports; move a port if it is taken and record it)**.
- `python -m lineagelab.stack up|down|status [--only om|marquez]`: `up` starts and waits until healthy, `down` stops and keeps volumes, `status` prints one JSON line `{"openmetadata": {"up": bool, "version": str|null, "url": str}, "marquez": {"up": bool, "url": str}}`. Ports and URLs come from `stack/versions.yaml`, which also records every image tag and tool version used.
- `lineagelab.om`: a small client. `client()` logs in with the default admin login, fetches the `ingestion-bot` JWT **(verify the API calls for this)** and keeps it in memory; `get(path, **params)`, `put(path, json)`, `post(path, json)`; and two normalised readers used by acceptance:
  - `table(fqn) -> {"fqn", "description", "columns": [{"name", "data_type", "description", "tags": [str]}], "tags": [str], "tests": int} | None`
  - `upstream(fqn, depth=3) -> {"nodes": [fqn, ...], "edges": [[from_fqn, to_fqn], ...], "column_edges": [[from_fqn.col, to_fqn.col], ...]}`
  These return what the API returned, reshaped; nothing is invented or cached.

## 3. Catalogue: the database in OpenMetadata (L2)

- `python -m lineagelab.workcopy` makes `work/olist-dbt/`; `python -m lineagelab.dbtrun build` runs `dbt build` and `dbt docs generate` there on target `dev` (so `dev_governor` is populated and `target/` holds `manifest.json`, `catalog.json`, `run_results.json`); one JSON line with the counts of models, tests passed and failed. dbt runs in an isolated environment (see `AGENTS.md`), dbt-core 1.12 with dbt-postgres, as governor uses.
- `python -m lineagelab.ingest database`: registers one Postgres database service named `shop_testbed` in OpenMetadata and runs the metadata ingestion for database `shop`, schemas `raw`, `dev_governor`, `analytics` only. The workflow YAML is written by code to `work/ingest/database.yaml` (no secret in the repo: the DSN parts and the bot token are filled in at run time). Preferred runner: `docker exec` into the ingestion container, where the `metadata` CLI matches the server version, reaching the test bed as `host.docker.internal:55432`; fallback `uvx --from "openmetadata-ingestion[postgres,dbt]"` pinned to the server's version **(verify which works on this Windows machine and record it)**.
- Table FQNs are `shop_testbed.shop.<schema>.<table>`.

## 4. dbt in OpenMetadata (L3)

- `python -m lineagelab.ingest dbt`: the dbt workflow for service `shop_testbed` from the three artifact files in `work/olist-dbt/target/` (only `manifest.json` is required; the docs list the result as models, table and column lineage, descriptions, tests and results, tags, owners). Workflow YAML written to `work/ingest/dbt.yaml` **(verify the YAML shape for local artifact files against the installed version; if the files must be inside the container, copy them in)**.
- Expected afterwards, on the `dev_governor` tables: model and column descriptions (governor wrote them in D10), dbt tests on the staging keys, and lineage from `raw` sources through staging and intermediate to the `kpi_*` models.

## 5. OpenLineage events (L4)

- `python -m lineagelab.olrun`: runs `dbt-ol build` (package `openlineage-dbt`, artifact mode) on the work copy, target `dev`, twice over the same dbt invocation if needed: events go to Marquez (`OPENLINEAGE_URL` = the Marquez API, namespace `lineagelab`) and are also saved one JSON event per line in `artifacts/openlineage/events.ndjson` (git-ignored) **(verify how to get both: a composite transport, a file transport plus a replay to Marquez, or two runs; verify that dbt-ol works with dbt-core 1.12 and whether the column-lineage facet needs a flag)**.
- `lineagelab.olevents`: pure functions over the saved events: `summary(events) -> {"events", "runs", "jobs", "datasets", "event_types": {...}, "facets": {name: count}, "column_lineage_outputs": int}` and `edges(events) -> {"table": [[in, out], ...], "column": [[in.col, out.col], ...]}` built from each COMPLETE event's inputs, outputs and `columnLineage` facet. Dataset ids are `namespace/name` exactly as emitted.
- `python -m lineagelab.olforward`: posts the saved events to OpenMetadata's OpenLineage endpoint (`/api/v1/openlineage/lineage`; it needs `EditLineage` on tables and resolves datasets to **table** entities) and reports, per event, accepted or the error. Whether the Postgres dataset names dbt-ol emits resolve to `shop_testbed` tables is **not known**: this command is an experiment. Its result goes to `docs/findings/openlineage-to-openmetadata.md` (what was sent, what resolved, what did not and why, what naming or mapping would fix it). A clear "it does not resolve, because ..." is a valid result; do not add lineage through another API to make it look as if it worked.

## 6. Three views of lineage (L5)

- `lineagelab.compare`: three edge sets over the same models, table level and column level where a view has it:
  1. **manifest**: from `manifest.json` (`depends_on` of models; sources as `raw` tables). This is the reference for table edges.
  2. **openmetadata**: `om.upstream` of every `kpi_*` table after L3.
  3. **openlineage**: `olevents.edges` after L4.
  Names are normalised to `<schema>.<table>` (and `<schema>.<table>.<column>`) by documented rules in one function with unit tests.
- `python -m lineagelab.compare report` writes `docs/lineage-compare.md`: per view the number of table and column edges, and against the manifest the missing and extra table edges (precision and recall); for column edges the pairwise overlap between OpenMetadata and OpenLineage and five example disagreements. Metadata only, no data values. One JSON line with the same numbers.

## 7. Later (not in this batch)

Push what dbt cannot carry (KPI catalogue as glossary terms, certified status, PII tags, owners) through the API; impact questions answered through OpenMetadata's MCP server and scored against the manifest; ODCS contracts generated from governor's approved design.
