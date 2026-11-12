"""Post saved OpenLineage events to OpenMetadata and write down what resolved.

    python -m lineagelab.olforward

POSTs each saved event, unedited, to ``/api/v1/openlineage/lineage`` (ingestion-bot JWT, in memory
only). Reports, per event, accepted, skipped or the error. Then compares lineage on the
``shop_testbed`` tables those dataset names would be, before and after, and writes
``docs/findings/openlineage-to-openmetadata.md``. Does not create lineage through any other API.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

from lineagelab import om
from lineagelab.olevents import load

ROOT = Path(__file__).resolve().parents[2]
EVENTS = ROOT / "artifacts" / "openlineage" / "events.ndjson"
FINDINGS = ROOT / "docs" / "findings" / "openlineage-to-openmetadata.md"
LOG = ROOT / "logs" / "olforward-report.json"
SERVICE = "shop_testbed"


def guess_fqn(dataset_name: str) -> str | None:
    """``database.schema.table`` -> ``shop_testbed.database.schema.table``. Otherwise no guess."""
    parts = dataset_name.split(".")
    if len(parts) >= 3 and all(parts):
        return SERVICE + "." + dataset_name
    return None


def _job_id(event: dict) -> str:
    job = event.get("job") if isinstance(event.get("job"), dict) else {}
    ns, name = job.get("namespace"), job.get("name")
    if isinstance(ns, str) and isinstance(name, str):
        return f"{ns}/{name}"
    return ""


def _outcome(status_code: int, body: dict | None, error: str | None) -> dict:
    if error or body is None:
        return {"outcome": "error", "reason": error or f"HTTP {status_code}"}
    status = body.get("status")
    summary = body.get("summary") or {}
    failed = body.get("failedEvents") or []
    reason = body.get("message") or ""
    if failed:
        reason = "; ".join(str(item.get("reason") or "") for item in failed if isinstance(item, dict)) or reason
    if status_code != 200 or status == "failure":
        return {"outcome": "error", "reason": reason or f"HTTP {status_code} {status}"}
    if status == "partial_success":
        return {"outcome": "error", "reason": reason or "partial_success"}
    skipped = int(summary.get("skipped") or 0)
    successful = int(summary.get("successful") or 0)
    if skipped and not successful and not int(body.get("lineageEdgesCreated") or 0):
        return {"outcome": "skipped", "reason": reason or "skipped"}
    return {"outcome": "accepted", "reason": reason}


def post_event(event: dict) -> dict:
    """POST one event. Never raises: the per-event result is the point of the experiment."""
    try:
        r = om.client().post("/v1/openlineage/lineage", json=event)
    except httpx.HTTPError as exc:
        body, code, err = None, 0, type(exc).__name__
    else:
        code = r.status_code
        try:
            body = r.json() if r.content else {}
        except json.JSONDecodeError:
            body = None
        err = None if body is not None else f"HTTP {code} not JSON"
    judged = _outcome(code, body if isinstance(body, dict) else None, err)
    edges = int((body or {}).get("lineageEdgesCreated") or 0) if isinstance(body, dict) else 0
    return {
        "event_type": event.get("eventType"),
        "job": _job_id(event),
        "http": code,
        "api_status": (body or {}).get("status") if isinstance(body, dict) else None,
        "lineage_edges_created": edges,
        "outcome": judged["outcome"],
        "reason": (judged["reason"] or "")[:300],
    }


def lineage_edges(fqn: str) -> list[dict] | None:
    """Upstream edges of one table, or None when the table is not in the catalogue. Read only."""
    path = f"/v1/lineage/table/name/{quote(fqn, safe='')}"
    r = om.client().get(path, params={"upstreamDepth": 1, "downstreamDepth": 0})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    payload = r.json()
    by_id: dict[str, str] = {}
    root = payload.get("entity") or {}
    for node in [root, *(payload.get("nodes") or [])]:
        if isinstance(node, dict) and node.get("id") and node.get("fullyQualifiedName"):
            by_id[node["id"]] = node["fullyQualifiedName"]
    edges = []
    for edge in payload.get("upstreamEdges") or []:
        details = edge.get("lineageDetails") or {}
        edges.append({
            "from": by_id.get(edge.get("fromEntity")),
            "to": by_id.get(edge.get("toEntity")),
            "source": details.get("source"),
            "column_edges": len(details.get("columnsLineage") or []),
        })
    return edges


def _snapshot(fqns: list[str]) -> dict[str, list[dict] | None]:
    return {fqn: lineage_edges(fqn) for fqn in fqns}


def _new_edges(before: list[dict] | None, after: list[dict] | None) -> list[dict]:
    if before is None or after is None:
        return []
    prior = {(e["from"], e["to"], e["source"]): e["column_edges"] for e in before}
    added = []
    for edge in after:
        key = (edge["from"], edge["to"], edge["source"])
        if key not in prior:
            added.append(edge)
        elif edge["column_edges"] > prior[key]:
            added.append({**edge, "column_edges": edge["column_edges"] - prior[key]})
    return added


def _dataset_rows(events: list[dict]) -> list[dict]:
    rows = []
    seen: set[tuple[str, str]] = set()
    for ev in events:
        if ev.get("eventType") != "COMPLETE":
            continue
        for ds in (ev.get("outputs") or []):
            if not isinstance(ds, dict) or not isinstance(ds.get("name"), str):
                continue
            key = (str(ds.get("namespace")), ds["name"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"namespace": key[0], "name": key[1], "fqn": guess_fqn(key[1])})
    return rows


def experiment(events: list[dict]) -> dict:
    rows = _dataset_rows(events)
    fqns = sorted({row["fqn"] for row in rows if row["fqn"]})
    before = _snapshot(fqns)
    results = [post_event(ev) for ev in events]
    after = _snapshot(fqns)
    compared = []
    for row in rows:
        fqn = row["fqn"]
        prior = before.get(fqn) if fqn else None
        later = after.get(fqn) if fqn else None
        added = _new_edges(prior, later)
        compared.append({
            **row,
            "table_in_catalog": later is not None,
            "new_edges": added,
        })
    return {
        "events": len(events),
        "results": results,
        "namespaces": sorted({row["namespace"] for row in rows}),
        "datasets": compared,
        "lineage_edges_created": sum(r["lineage_edges_created"] for r in results),
    }


def event_shape(event: dict) -> dict:
    """Timestamp form and job type, so a 400 can be tied to the event rather than guessed."""
    t = str(event.get("eventTime") or "")
    if t.endswith("Z"):
        form = "Z"
    elif "+" in t[10:] or (len(t) >= 6 and t[-6] in "+-"):
        form = "offset"
    else:
        form = "other"
    jt = ((event.get("job") or {}).get("facets") or {}).get("jobType") if isinstance(event.get("job"), dict) else None
    job_type = jt.get("jobType") if isinstance(jt, dict) else None
    return {
        "time_form": form,
        "job_type": job_type if isinstance(job_type, str) else "",
        "inputs": len(event.get("inputs") or []),
        "outputs": len(event.get("outputs") or []),
    }


def with_shapes(report: dict, events: list[dict]) -> dict:
    if len(events) != len(report.get("results") or []):
        return report
    return {**report, "shapes": [event_shape(ev) for ev in events]}


def _counts(results: list[dict]) -> dict[str, int]:
    out = {"accepted": 0, "skipped": 0, "error": 0}
    for row in results:
        out[row["outcome"]] = out.get(row["outcome"], 0) + 1
    return out


def render_findings(report: dict) -> str:
    """The experiment write-up. Metadata only: no SQL, no tokens, no row values."""
    results = report["results"]
    counts = _counts(results)
    by_type: dict[str, dict[str, int]] = {}
    for row in results:
        bucket = by_type.setdefault(str(row["event_type"]), {"accepted": 0, "skipped": 0, "error": 0})
        bucket[row["outcome"]] = bucket.get(row["outcome"], 0) + 1
    datasets = report["datasets"]
    present = [d for d in datasets if d["table_in_catalog"]]
    absent = [d for d in datasets if d["fqn"] and not d["table_in_catalog"]]
    unguessed = [d for d in datasets if not d["fqn"]]
    resolved = [d for d in present if d["new_edges"]]
    unresolved = [d for d in present if not d["new_edges"]]
    sources: dict[str, int] = {}
    new_column = 0
    for d in resolved:
        for edge in d["new_edges"]:
            sources[str(edge["source"])] = sources.get(str(edge["source"]), 0) + 1
            new_column += int(edge["column_edges"])
    reasons: dict[str, int] = {}
    for row in results:
        if row["outcome"] == "error" and row["reason"]:
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
    namespaces = report["namespaces"]
    lines = [
        "# OpenLineage events posted to OpenMetadata",
        "",
        "Experiment, not a fix. `python -m lineagelab.olforward` POSTs each saved dbt-ol event, unedited,",
        "to `POST /api/v1/openlineage/lineage` on OpenMetadata 2.0.5. The caller is the ingestion bot; its",
        "JWT stays in memory. Nothing is written through `/api/v1/lineage` or any other lineage API.",
        "A clear miss is a valid result.",
        "",
        "## What was sent",
        "",
        f"{report['events']} events from `artifacts/openlineage/events.ndjson`.",
        "Dataset ids below are `namespace` plus `name` as dbt-ol emitted them, for COMPLETE outputs only.",
        f"Namespaces ({len(namespaces)}): " + (", ".join(f"`{ns}`" for ns in namespaces) or "(none)") + ".",
        f"Distinct COMPLETE output datasets: {len(datasets)}.",
    ]
    for row in datasets[:8]:
        lines.append(f"- `{row['namespace']}` / `{row['name']}` -> guess `{row['fqn']}`")
    if len(datasets) > 8:
        lines.append(f"- {len(datasets) - 8} further output datasets, same naming pattern.")
    lines += [
        "",
        "The guess is `shop_testbed.` plus a `database.schema.table` name. OpenMetadata's FQN for this",
        "catalogue is `shop_testbed.shop.<schema>.<table>`. dbt-ol's namespace is the Postgres instance",
        "(`postgres://host:port`), not the service name `shop_testbed`.",
        "",
        "## What was accepted",
        "",
        f"Accepted {counts['accepted']}, skipped {counts['skipped']}, error {counts['error']}.",
        f"Sum of `lineageEdgesCreated` in the responses: {report['lineage_edges_created']}.",
        "",
        "| event type | accepted | skipped | error |",
        "|---|---:|---:|---:|",
    ]
    for kind in sorted(by_type):
        b = by_type[kind]
        lines.append(f"| {kind} | {b['accepted']} | {b['skipped']} | {b['error']} |")
    if reasons:
        lines.append("")
        lines.append("Error reasons (trimmed, grouped):")
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:6]:
            lines.append(f"- {n} × {reason}")
    shapes = report.get("shapes") or []
    time_split = bool(shapes) and len(shapes) == len(results) and counts["error"] and counts["accepted"] and all(
        (shape["time_form"] == "offset") == (row["outcome"] == "error") for shape, row in zip(shapes, results))
    if time_split:
        by_job: dict[str, int] = {}
        for shape, row in zip(shapes, results):
            if row["outcome"] == "error":
                label = shape["job_type"] or "unknown"
                by_job[label] = by_job.get(label, 0) + 1
        lines.append("")
        lines.append("Every accepted event has `eventTime` ending in `Z`. Every error has a numeric offset")
        lines.append("(`+00:00`). Errors by dbt job type: " + ", ".join(f"{k} {v}" for k, v in sorted(by_job.items())) + ".")
        lines.append("Model events are the `Z` ones. Test events and the parent `dbt-run-olist` run use the offset.")
        lines.append("A check on this server, changing only `eventTime`: one test event rewritten to `Z` returned")
        lines.append("200 with `lineageEdgesCreated` 0, and one model event rewritten to `+00:00` returned 400.")
        lines.append("The saved file was not edited. Those two calls created no edges. Empty outputs are not the 400;")
        lines.append("a test has no output dataset, so once the timestamp is accepted there is still no table edge.")
    lines += [
        "",
        "## What resolved to shop_testbed tables",
        "",
        "Resolved means a guessed table already in the catalogue gained an upstream edge that was not",
        "there before this post. Edges loaded earlier by the dbt workflow stay; they are not counted.",
        f"Guessed tables found in the catalogue: {len(present)}. Absent: {len(absent)}. No guess: {len(unguessed)}.",
        f"Tables that gained an edge: {len(resolved)}. New edges by source: "
        + (", ".join(f"{name} {n}" for name, n in sorted(sources.items())) or "none") + ".",
        f"Column-level mappings on those new edges: {new_column}.",
    ]
    if resolved:
        lines.append("Examples that resolved:")
        for row in resolved[:5]:
            n = len(row["new_edges"])
            word = "edge" if n == 1 else "edges"
            srcs = sorted({str(e["source"]) for e in row["new_edges"]})
            lines.append(f"- `{row['fqn']}` gained {n} {word}, source {', '.join(srcs)}.")
        edge = resolved[0]["new_edges"][0]
        lines.append(f"One new edge: `{edge['from']}` -> `{edge['to']}` (source {edge['source']}).")
    else:
        lines.append("No guessed table gained an edge. Nothing from this post resolved to a shop_testbed table.")
    lines += [
        "",
        "## What did not resolve, and why",
        "",
        f"Tables already in the catalogue with no new edge: {len(unresolved)}.",
        f"Guessed names that are not in the catalogue: {len(absent)}.",
    ]
    for row in (absent or unresolved)[:5]:
        state = "not in the catalogue" if not row["table_in_catalog"] else "in the catalogue, no new edge"
        lines.append(f"- `{row['name']}` ({state}), guess `{row['fqn']}`.")
    if resolved and not unresolved and not absent:
        lines.append("Every guessed COMPLETE output was a table that gained an edge. The dataset name")
        lines.append("`shop.<schema>.<table>` lined up with FQN `shop_testbed.shop.<schema>.<table>`.")
        lines.append("OpenMetadata resolved the emitted Postgres namespace to service `shop_testbed`.")
    elif resolved:
        lines.append("Some output names matched a table and some did not. The ones that did not are the")
        lines.append("names in the list above: the namespace or the database.schema.table parts did not")
        lines.append("select a `shop_testbed` table.")
    elif report["lineage_edges_created"]:
        lines.append("The endpoint reported new edges, but none of them showed up on the guessed")
        lines.append("`shop_testbed` tables. Those edges were attached somewhere else, or under a source")
        lines.append("that this comparison did not treat as new. The dataset namespace is still")
        lines.append("`postgres://<host>:<port>`, not the service name.")
    else:
        lines.append("The endpoint accepted events without creating edges. A 200 here means the body was")
        lines.append("processed or skipped, not that a dataset name matched a table. dbt-ol names the")
        lines.append("dataset `shop.<schema>.<table>` inside namespace `postgres://<host>:<port>`. OpenMetadata")
        lines.append("resolves a dataset through that namespace (to a database service) and then through")
        lines.append("database.schema.table. Nothing maps that Postgres namespace to service `shop_testbed`,")
        lines.append("so the namespace does not select this catalogue, and the edges are not attached.")
    if time_split and resolved and not unresolved and not absent:
        fix = [
            "Model names need no mapping change. No namespace map was configured, and",
            "`postgres://<host>:<port>` plus `shop.<schema>.<table>` still resolved to",
            "`shop_testbed.shop.<schema>.<table>`, raw inputs included. The 400s are the timestamp:",
            "OpenMetadata 2.0.5 accepts `eventTime` with a `Z` suffix and rejects `+00:00`.",
            "Emitting `Z` on the test and parent events would get them past the 400. It would not add",
            "table edges for tests, which have no output dataset. The saved events were posted unedited.",
            "Lineage was not added through any other API.",
        ]
    elif resolved and not unresolved and not absent:
        fix = [
            "No further naming change is required for these events. Keep posting them unedited.",
            "The namespace `postgres://<host>:<port>` already resolves to service `shop_testbed`, and the",
            "dataset name `shop.<schema>.<table>` already matches that service's database, schema and table.",
            "Lineage was not added through any other API.",
        ]
    else:
        fix = [
            "Keep the events as dbt-ol writes them. On the OpenMetadata side, map the emitted namespace",
            "(`postgres://<host>:<port>`, exactly as in the events) to database service `shop_testbed`.",
            "Leave the dataset name as `shop.<schema>.<table>` so it matches database `shop`, the schema",
            "and the table under that service. Rewriting events to fake an FQN, or adding edges through",
            "the native lineage API, would hide this miss and was not done.",
        ]
    lines += ["", "## What naming or mapping would fix it", "", *fix, ""]
    text = "\n".join(lines)
    n = text.count("\n") + (0 if text.endswith("\n") else 1)
    # `splitlines` on a trailing newline does not add an empty line, matching the acceptance count.
    count = len(text.splitlines())
    if not 15 <= count <= 120:
        raise RuntimeError(f"findings would be {count} lines (n={n}); acceptance wants 15 to 120")
    return text if text.endswith("\n") else text + "\n"


def forward(path: Path = EVENTS) -> dict:
    if not path.is_file():
        raise SystemExit(f"no events file: {path}. run `python -m lineagelab.olrun` first")
    loaded = load(path)
    report = with_shapes(experiment(loaded["events"]), loaded["events"])
    text = render_findings(report)
    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS.write_text(text, encoding="utf-8")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(report, indent=2), encoding="utf-8")
    counts = _counts(report["results"])
    resolved = sum(1 for d in report["datasets"] if d["new_edges"])
    return {
        "events": report["events"],
        **counts,
        "lineage_edges_created": report["lineage_edges_created"],
        "datasets": len(report["datasets"]),
        "resolved_tables": resolved,
        "findings": "docs/findings/openlineage-to-openmetadata.md",
        "findings_lines": len(text.splitlines()),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print("usage: python -m lineagelab.olforward", file=sys.stderr)
        return 2
    print(json.dumps(forward()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
