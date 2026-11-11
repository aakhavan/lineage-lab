"""A small OpenMetadata client.

`client()` logs in with the documented local admin default, fetches the `ingestion-bot` JWT and keeps it
in memory only (module state, never written or printed). `get/put/post` call the REST API with that token.
`table(fqn)` and `upstream(fqn, depth)` return what the API returned, reshaped by the pure functions
`reshape_table` and `reshape_lineage` (tested offline on saved payloads). Nothing is invented or cached.

API calls used (checked against the server's Swagger, /swagger.json, OpenMetadata 2.0.5; see NOTES.md):
  POST /api/v1/users/login                {"email", "password": base64(password)} -> {"accessToken", ...}
  GET  /api/v1/bots/name/ingestion-bot     -> {"botUser": {"id", "name", ...}}
  GET  /api/v1/users/auth-mechanism/{id}   -> {"authType": "JWT", "config": {"JWTToken": ...}}
  GET  /api/v1/tables/name/{fqn}?fields=columns,tags
  GET  /api/v1/dataQuality/testCases?entityLink=<#E::table::fqn>&includeAllTests=true  (paging.total)
  GET  /api/v1/lineage/table/name/{fqn}?upstreamDepth=N&downstreamDepth=0
"""
from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import quote

import httpx

from lineagelab.stack import load_versions

ADMIN_EMAIL = "admin@open-metadata.org"   # documented local default (AGENTS.md)
ADMIN_PASSWORD = "admin"                  # documented local default (AGENTS.md)
BOT = "ingestion-bot"

_state: dict[str, Any] = {"http": None}


def api_url() -> str:
    return os.environ.get("LAB_OM_API") or load_versions()["stacks"]["om"]["urls"]["api"]


def _login(http: httpx.Client) -> str:
    pw = base64.b64encode(ADMIN_PASSWORD.encode()).decode()
    r = http.post("/v1/users/login", json={"email": ADMIN_EMAIL, "password": pw})
    r.raise_for_status()
    return r.json()["accessToken"]


def _bot_token(http: httpx.Client, admin_token: str) -> str:
    h = {"Authorization": f"Bearer {admin_token}"}
    r = http.get(f"/v1/bots/name/{BOT}", headers=h)
    r.raise_for_status()
    bot_user_id = r.json()["botUser"]["id"]
    r = http.get(f"/v1/users/auth-mechanism/{bot_user_id}", headers=h)
    r.raise_for_status()
    return r.json()["config"]["JWTToken"]


def client() -> httpx.Client:
    """Log in, fetch the ingestion-bot JWT, and keep an authenticated client in memory."""
    if _state["http"] is None:
        http = httpx.Client(base_url=api_url().rstrip("/"), timeout=60)
        token = _bot_token(http, _login(http))
        http.headers["Authorization"] = f"Bearer {token}"
        _state["http"] = http
    return _state["http"]


def bot_token() -> str:
    """The in-memory ingestion-bot JWT (for workflow configs filled at run time; never write it to the repo)."""
    return client().headers["Authorization"].removeprefix("Bearer ")


def _path(path: str) -> str:
    path = "/" + path.lstrip("/")
    return path.removeprefix("/api") if path.startswith("/api/") else path


def get(path: str, **params: Any) -> Any:
    r = client().get(_path(path), params=params or None)
    r.raise_for_status()
    return r.json()


def put(path: str, json: Any) -> Any:
    r = client().put(_path(path), json=json)
    r.raise_for_status()
    return r.json() if r.content else None


def post(path: str, json: Any) -> Any:
    r = client().post(_path(path), json=json)
    r.raise_for_status()
    return r.json() if r.content else None


def _get_or_none(path: str, **params: Any) -> Any | None:
    r = client().get(_path(path), params=params or None)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


# ---- pure reshaping (tested offline) -------------------------------------------------------------

def _tag_fqns(tags: list[dict] | None) -> list[str]:
    return [t["tagFQN"] for t in (tags or []) if t.get("tagFQN")]


def reshape_table(payload: dict, test_cases: dict | None) -> dict:
    """Table entity (+ testCases list response) -> the spec's normalised table dict."""
    return {
        "fqn": payload["fullyQualifiedName"],
        "description": payload.get("description"),
        "columns": [
            {
                "name": c["name"],
                "data_type": c.get("dataType"),
                "description": c.get("description"),
                "tags": _tag_fqns(c.get("tags")),
            }
            for c in payload.get("columns") or []
        ],
        "tags": _tag_fqns(payload.get("tags")),
        "tests": int(((test_cases or {}).get("paging") or {}).get("total", len((test_cases or {}).get("data") or []))),
    }


def reshape_lineage(payload: dict) -> dict:
    """Lineage response (entity, nodes, upstreamEdges by id) -> {nodes, edges, column_edges} by FQN."""
    by_id: dict[str, str] = {}
    root = payload.get("entity") or {}
    for n in [root, *(payload.get("nodes") or [])]:
        if n.get("id") and n.get("fullyQualifiedName"):
            by_id[n["id"]] = n["fullyQualifiedName"]
    edges: list[list[str]] = []
    column_edges: list[list[str]] = []
    for e in payload.get("upstreamEdges") or []:
        src, dst = by_id.get(e["fromEntity"]), by_id.get(e["toEntity"])
        if src is None or dst is None:
            raise ValueError(f"lineage edge refers to an entity not in nodes: {e['fromEntity']} -> {e['toEntity']}")
        if [src, dst] not in edges:
            edges.append([src, dst])
        for col in ((e.get("lineageDetails") or {}).get("columnsLineage") or []):
            for f in col.get("fromColumns") or []:
                pair = [f, col["toColumn"]]
                if col.get("toColumn") and pair not in column_edges:
                    column_edges.append(pair)
    nodes = sorted({x for e in edges for x in e} | ({root["fullyQualifiedName"]} if root.get("fullyQualifiedName") else set()))
    return {"nodes": nodes, "edges": sorted(edges), "column_edges": sorted(column_edges)}


# ---- live readers --------------------------------------------------------------------------------

def table(fqn: str) -> dict | None:
    payload = _get_or_none(f"/v1/tables/name/{quote(fqn, safe='')}", fields="columns,tags")
    if payload is None:
        return None
    tests = get("/v1/dataQuality/testCases", entityLink=f"<#E::table::{fqn}>", includeAllTests="true", limit=1)
    return reshape_table(payload, tests)


def upstream(fqn: str, depth: int = 3) -> dict:
    payload = get(f"/v1/lineage/table/name/{quote(fqn, safe='')}", upstreamDepth=depth, downstreamDepth=0)
    return reshape_lineage(payload)
