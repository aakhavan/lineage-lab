# lineage-lab

A learning module beside [governor](../governor): it takes the dbt project governor built (`../olist-dbt`) and the Postgres test bed, puts them into **OpenMetadata** (catalogue, descriptions, tests, lineage) and emits **OpenLineage** events from a dbt run (viewed in Marquez, then sent to OpenMetadata), and measures how the three views of lineage agree.

It reads governor's outputs and changes nothing in `governor` or `olist-dbt`. Spec: `docs/spec.md`. Built step by step by the code factory (`plan.yaml`).
