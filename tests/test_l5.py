"""Offline tests for the lineage comparison. Fixtures are small and use invented names."""
import pytest

from lineagelab import compare
from lineagelab.compare import normalise

MANIFEST = {
    "nodes": {
        "model.p.stg_a": {"resource_type": "model", "database": "db", "schema": "dev", "alias": "stg_a",
                          "name": "stg_a", "depends_on": {"nodes": ["source.p.raw.a"]}},
        "model.p.kpi_x": {"resource_type": "model", "database": "db", "schema": "dev", "alias": "kpi_x",
                          "name": "kpi_x", "depends_on": {"nodes": ["model.p.stg_a", "seed.p.lookup"]}},
        "seed.p.lookup": {"resource_type": "seed", "database": "db", "schema": "dev", "alias": "lookup",
                          "name": "lookup", "depends_on": {"nodes": []}},
        "test.p.not_null": {"resource_type": "test", "database": "db", "schema": "dev_test", "alias": "nn",
                            "name": "not_null", "depends_on": {"nodes": ["model.p.kpi_x"]}},
    },
    "sources": {
        "source.p.raw.a": {"resource_type": "source", "database": "db", "schema": "raw", "name": "a",
                           "identifier": "a_table"},
    },
}


def test_normalise_maps_each_view_to_schema_table():
    assert normalise("db.raw.orders", "manifest") == "raw.orders"
    assert normalise("svc.db.dev.stg_orders", "openmetadata") == "dev.stg_orders"
    assert normalise("svc.db.dev.stg_orders.order_id", "openmetadata") == "dev.stg_orders.order_id"
    assert normalise("postgres://host:5432/db.dev.stg_orders", "openlineage") == "dev.stg_orders"
    assert normalise("postgres://host:5432/db.dev.stg_orders.order_id", "openlineage") == "dev.stg_orders.order_id"
    assert normalise("warehouse/db.Dev.Kpi_X", "openlineage") == "dev.kpi_x"
    # the same table reaches the same name from every view
    same = {normalise("db.dev.kpi_x", "manifest"), normalise("svc.db.dev.kpi_x", "openmetadata"),
            normalise("pg://h:1/db.dev.kpi_x", "openlineage")}
    assert same == {"dev.kpi_x"}
    with pytest.raises(ValueError):
        normalise("db.dev.t", "marquez")


def test_unmatched_names_are_counted_not_dropped():
    for bad, view in [("dev.t", "manifest"), ("svc.db.t", "openmetadata"), ("a.b.c.d.e.f", "openmetadata"),
                      ("pg://h:1/sizes.cohort_size", "openlineage"), ("db.dev.t", "openlineage"),
                      ("svc..dev.t", "openmetadata")]:
        assert normalise(bad, view) is None, (bad, view)
    got = compare.normalise_edges([["pg://h:1/db.dev.a.x", "pg://h:1/db.dev.b.y"],
                                   ["pg://h:1/sizes.cohort_size", "pg://h:1/db.dev.b.z"]], "openlineage")
    assert got["edges"] == {("dev.a.x", "dev.b.y")}
    assert got["unmatched"] == ["pg://h:1/sizes.cohort_size"]
    r = compare.build([["db.raw.a", "db.dev.b"]],
                      {"table": [["s.db.raw.a", "s.db.dev.b"], ["s.db.b", "s.db.dev.b"]], "column": []},
                      {"table": [["n/db.raw.a", "n/db.dev.b"]], "column": [["n/sizes.c", "n/db.dev.b.c"]]})
    assert r["unmatched"] == {"manifest": [], "openmetadata": ["s.db.b"], "openlineage": ["n/sizes.c"]}
    assert compare.json_line(r)["unmatched"] == 2


def test_score_precision_and_recall():
    ref = [("raw.a", "dev.b"), ("dev.b", "dev.c"), ("dev.c", "dev.d"), ("raw.e", "dev.d")]
    other = [("raw.a", "dev.b"), ("dev.b", "dev.c"), ("dev.x", "dev.d")]
    s = compare.score(ref, other)
    assert s["shared"] == 2
    assert s["missing"] == [("dev.c", "dev.d"), ("raw.e", "dev.d")]
    assert s["extra"] == [("dev.x", "dev.d")]
    assert s["precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["recall"] == 0.5
    assert compare.score(ref, [])["precision"] == 0.0 and compare.score(ref, [])["recall"] == 0.0
    assert compare.score([], [])["precision"] == 1.0


def test_manifest_edges_include_sources():
    edges = compare.manifest_edges(MANIFEST)
    assert ["db.raw.a_table", "db.dev.stg_a"] in edges          # source -> model, by identifier
    assert ["db.dev.stg_a", "db.dev.kpi_x"] in edges
    assert ["db.dev.lookup", "db.dev.kpi_x"] in edges            # seeds are tables too
    assert not any("dev_test" in e[1] or e[0].endswith("kpi_x") for e in edges)  # tests are not models
    assert len(edges) == 3
    norm = compare.normalise_edges(edges, "manifest")
    assert ("raw.a_table", "dev.stg_a") in norm["edges"] and norm["unmatched"] == []
