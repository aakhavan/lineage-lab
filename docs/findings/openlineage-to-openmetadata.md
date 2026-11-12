# OpenLineage events posted to OpenMetadata

Experiment, not a fix. `python -m lineagelab.olforward` POSTs each saved dbt-ol event, unedited,
to `POST /api/v1/openlineage/lineage` on OpenMetadata 2.0.5. The caller is the ingestion bot; its
JWT stays in memory. Nothing is written through `/api/v1/lineage` or any other lineage API.
A clear miss is a valid result.

## What was sent

66 events from `artifacts/openlineage/events.ndjson`.
Dataset ids below are `namespace` plus `name` as dbt-ol emitted them, for COMPLETE outputs only.
Namespaces (1): `postgres://localhost:55432`.
Distinct COMPLETE output datasets: 15.
- `postgres://localhost:55432` / `shop.dev_governor.stg_customers` -> guess `shop_testbed.shop.dev_governor.stg_customers`
- `postgres://localhost:55432` / `shop.dev_governor.stg_reviews` -> guess `shop_testbed.shop.dev_governor.stg_reviews`
- `postgres://localhost:55432` / `shop.dev_governor.stg_order_items` -> guess `shop_testbed.shop.dev_governor.stg_order_items`
- `postgres://localhost:55432` / `shop.dev_governor.stg_orders` -> guess `shop_testbed.shop.dev_governor.stg_orders`
- `postgres://localhost:55432` / `shop.dev_governor.int_orders` -> guess `shop_testbed.shop.dev_governor.int_orders`
- `postgres://localhost:55432` / `shop.dev_governor.int_order_reviews` -> guess `shop_testbed.shop.dev_governor.int_order_reviews`
- `postgres://localhost:55432` / `shop.dev_governor.int_order_lines` -> guess `shop_testbed.shop.dev_governor.int_order_lines`
- `postgres://localhost:55432` / `shop.dev_governor.kpi_on_time_delivery_rate` -> guess `shop_testbed.shop.dev_governor.kpi_on_time_delivery_rate`
- 7 further output datasets, same naming pattern.

The guess is `shop_testbed.` plus a `database.schema.table` name. OpenMetadata's FQN for this
catalogue is `shop_testbed.shop.<schema>.<table>`. dbt-ol's namespace is the Postgres instance
(`postgres://host:port`), not the service name `shop_testbed`.

## What was accepted

Accepted 30, skipped 0, error 36.
Sum of `lineageEdgesCreated` in the responses: 18.

| event type | accepted | skipped | error |
|---|---:|---:|---:|
| COMPLETE | 15 | 0 | 18 |
| START | 15 | 0 | 18 |

Error reasons (trimmed, grouped):
- 36 × Invalid request format

Every accepted event has `eventTime` ending in `Z`. Every error has a numeric offset
(`+00:00`). Errors by dbt job type: JOB 2, TEST 34.
Model events are the `Z` ones. Test events and the parent `dbt-run-olist` run use the offset.
A check on this server, changing only `eventTime`: one test event rewritten to `Z` returned
200 with `lineageEdgesCreated` 0, and one model event rewritten to `+00:00` returned 400.
The saved file was not edited. Those two calls created no edges. Empty outputs are not the 400;
a test has no output dataset, so once the timestamp is accepted there is still no table edge.

## What resolved to shop_testbed tables

Resolved means a guessed table already in the catalogue gained an upstream edge that was not
there before this post. Edges loaded earlier by the dbt workflow stay; they are not counted.
Guessed tables found in the catalogue: 15. Absent: 0. No guess: 0.
Tables that gained an edge: 15. New edges by source: OpenLineage 18.
Column-level mappings on those new edges: 54.
Examples that resolved:
- `shop_testbed.shop.dev_governor.stg_customers` gained 1 edge, source OpenLineage.
- `shop_testbed.shop.dev_governor.stg_reviews` gained 1 edge, source OpenLineage.
- `shop_testbed.shop.dev_governor.stg_order_items` gained 1 edge, source OpenLineage.
- `shop_testbed.shop.dev_governor.stg_orders` gained 1 edge, source OpenLineage.
- `shop_testbed.shop.dev_governor.int_orders` gained 2 edges, source OpenLineage.
One new edge: `shop_testbed.shop.raw.olist_customers_dataset` -> `shop_testbed.shop.dev_governor.stg_customers` (source OpenLineage).

## What did not resolve, and why

Tables already in the catalogue with no new edge: 0.
Guessed names that are not in the catalogue: 0.
Every guessed COMPLETE output was a table that gained an edge. The dataset name
`shop.<schema>.<table>` lined up with FQN `shop_testbed.shop.<schema>.<table>`.
OpenMetadata resolved the emitted Postgres namespace to service `shop_testbed`.

## What naming or mapping would fix it

Model names need no mapping change. No namespace map was configured, and
`postgres://<host>:<port>` plus `shop.<schema>.<table>` still resolved to
`shop_testbed.shop.<schema>.<table>`, raw inputs included. The 400s are the timestamp:
OpenMetadata 2.0.5 accepts `eventTime` with a `Z` suffix and rejects `+00:00`.
Emitting `Z` on the test and parent events would get them past the 400. It would not add
table edges for tests, which have no output dataset. The saved events were posted unedited.
Lineage was not added through any other API.
