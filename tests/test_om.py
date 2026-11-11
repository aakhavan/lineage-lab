"""Offline tests for lineagelab.om reshaping.

Fixtures are payloads the real OpenMetadata 2.0.5 API returned for a throwaway catalogue
(service `lineagelab_fixture`, created and hard-deleted during L1), with ids replaced by `id-N`,
users/timestamps blanked and paging cursors removed.
"""
import json
from pathlib import Path

import pytest

from lineagelab import om

FIX = Path(__file__).resolve().parent / "fixtures"
S = "lineagelab_fixture.shop.s"


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_table_and_upstream_reshape_api_payloads():
    t = om.reshape_table(_load("om_table.json"), _load("om_testcases.json"))
    assert t == {
        "fqn": f"{S}.stg_orders",
        "description": "Staged orders",
        "columns": [
            {"name": "order_id", "data_type": "VARCHAR", "description": "Order key", "tags": []},
            {"name": "customer_id", "data_type": "VARCHAR", "description": None, "tags": []},
        ],
        "tags": ["Tier.Tier2"],
        "tests": 2,  # paging.total (one table test + one column test), not the length of the 1-item page
    }

    up = om.reshape_lineage(_load("om_lineage.json"))
    assert up["nodes"] == sorted(f"{S}.{n}" for n in ("orders_mart", "raw_customers", "raw_orders", "stg_orders"))
    assert up["edges"] == [
        [f"{S}.raw_customers", f"{S}.orders_mart"],
        [f"{S}.raw_orders", f"{S}.stg_orders"],
        [f"{S}.stg_orders", f"{S}.orders_mart"],
    ]
    assert up["column_edges"] == [
        [f"{S}.raw_customers.email", f"{S}.orders_mart.customer_email"],
        [f"{S}.raw_orders.customer_id", f"{S}.stg_orders.customer_id"],
        [f"{S}.raw_orders.order_id", f"{S}.stg_orders.order_id"],
        [f"{S}.stg_orders.order_id", f"{S}.orders_mart.order_id"],
    ]


def test_reshape_keeps_column_tags_and_rejects_unknown_edge_ids():
    payload = _load("om_table.json")
    payload["columns"][1]["tags"] = [{"tagFQN": "PII.Sensitive"}]
    assert om.reshape_table(payload, None)["columns"][1]["tags"] == ["PII.Sensitive"]
    assert om.reshape_table(payload, None)["tests"] == 0

    lin = _load("om_lineage.json")
    lin["upstreamEdges"][0]["fromEntity"] = "id-unknown"
    with pytest.raises(ValueError):
        om.reshape_lineage(lin)
