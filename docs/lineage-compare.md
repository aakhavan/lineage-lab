# Three views of lineage compared

Written by `python -m lineagelab.compare report`. Metadata only: table and column names, counts.
Names are normalised to `<schema>.<table>` and `<schema>.<table>.<column>` by
`lineagelab.compare.normalise` (rules in its module docstring).

- **manifest**: `depends_on` of every dbt model in `manifest.json`, sources as `raw` tables. The reference.
- **openmetadata**: `om.upstream` (depth 6) of every `kpi_*` table in `shop_testbed.shop.dev_governor`.
- **openlineage**: `olevents.edges` of the saved dbt-ol events (COMPLETE events only).

## Edge counts

| view | table edges | column edges |
|---|---:|---:|
| manifest | 18 | n/a (dbt has no column lineage) |
| openmetadata | 18 | 63 |
| openlineage | 18 | 63 |

## Table edges against the manifest

| view | shared | missing | extra | precision | recall |
|---|---:|---:|---:|---:|---:|
| openmetadata | 18 | 0 | 0 | 1.0 | 1.0 |
| openlineage | 18 | 0 | 0 | 1.0 | 1.0 |

Missing from openmetadata (0):
- none

Extra in openmetadata (0):
- none

Missing from openlineage (0):
- none

Extra in openlineage (0):
- none

### Where OpenMetadata's table edges came from

OpenMetadata 2.0.5 keeps one edge per pair of tables, with one `lineageDetails.source`. The dbt
workflow (L3) and the OpenLineage endpoint (L4 forward) both write to that same edge. Without
`overrideLineage` in the dbt workflow, a later dbt run merges its column lineage into the edge and
keeps the source label that is already there. So the label tells you who wrote the edge first after
it was created or overridden, and the column list on the edge is the union of both writers.

| source | edges |
|---|---:|
| OpenLineage | 18 |

OpenMetadata and OpenLineage table edges: 18 in both, 0 only in OpenMetadata, 0 only in OpenLineage (Jaccard 1.0).

## Column edges: OpenMetadata against OpenLineage

| in both | only OpenMetadata | only OpenLineage | Jaccard |
|---:|---:|---:|---:|
| 63 | 0 | 0 | 1.0 |

### Five example disagreements

Target columns whose upstream columns differ between the two views.

- none: the two column edge sets are equal.

## Unmatched names

Names no rule could map: 1. Edges with an unmatched end are left out of the
comparison above and listed here, never dropped silently.

- manifest: 0
- openmetadata: 0
- openlineage: 1: `postgres://localhost:55432/sizes.cohort_size`

An OpenLineage name with only two parts (`<name>.<column>` with no database or schema) is a
CTE or subquery alias that dbt-ol's SQL parser reported as an input dataset. No table has that
name, so it cannot be mapped, and OpenMetadata cannot resolve it either.
