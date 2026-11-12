"""Offline tests for OpenLineage event summaries. The fixture uses invented names."""
from pathlib import Path

from lineagelab import olevents

FIX = Path(__file__).resolve().parent / "fixtures" / "ol_events.ndjson"


def test_load_skips_blank_and_broken_lines_and_counts_them():
    loaded = olevents.load(FIX)
    assert loaded["blank"] == 2
    assert loaded["broken"] == 2
    assert [ev["eventType"] for ev in loaded["events"]] == ["START", "COMPLETE", "COMPLETE", "FAIL"]


def test_summary_counts_runs_jobs_datasets_and_facets():
    s = olevents.summary(olevents.load(FIX))
    assert s["events"] == 4
    assert s["runs"] == 3
    assert s["jobs"] == 2
    assert s["datasets"] == 6
    assert s["event_types"] == {"START": 1, "COMPLETE": 2, "FAIL": 1}
    assert s["facets"] == {
        "nominalTime": 1,
        "jobType": 1,
        "parent": 2,
        "sql": 2,
        "schema": 6,
        "columnLineage": 2,
        "errorMessage": 1,
    }
    assert s["column_lineage_outputs"] == 2


def test_edges_come_from_complete_events_only():
    e = olevents.edges(olevents.load(FIX))
    assert e["table"] == [
        ["warehouse/fruit.raw.seed", "warehouse/fruit.mart.apple"],
        ["warehouse/fruit.raw.seed", "warehouse/fruit.mart.pear"],
        ["warehouse/fruit.raw.leaf", "warehouse/fruit.mart.pear"],
    ]
    # the FAIL event names a different pair; it must not become an edge
    assert ["warehouse/fruit.raw.rotten", "warehouse/fruit.quarantine.bad"] not in e["table"]
    assert ["warehouse/fruit.raw.rotten.green", "warehouse/fruit.quarantine.bad.color"] not in e["column"]


def test_column_edges_come_from_the_column_lineage_facet():
    e = olevents.edges(olevents.load(FIX))
    assert e["column"] == [
        ["warehouse/fruit.raw.seed.id", "warehouse/fruit.mart.apple.id"],
        ["warehouse/fruit.raw.seed.shade", "warehouse/fruit.mart.apple.color"],
    ]
