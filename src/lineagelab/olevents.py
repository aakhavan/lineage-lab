"""Pure functions over saved OpenLineage events (one JSON object per line).

Dataset ids are ``namespace/name`` exactly as emitted. A column id is that dataset id plus
``.`` and the field name (``namespace/name.column``). ``load`` keeps every parsed object and
counts blank lines and broken lines (invalid JSON, or JSON that is not an object). ``summary``
and ``edges`` accept either a list of events or that ``load`` result.
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path: str | Path) -> dict:
    """Read NDJSON. Blank lines and broken lines are skipped and counted, never raised."""
    events: list[dict] = []
    blank = broken = 0
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            blank += 1
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            broken += 1
            continue
        if not isinstance(item, dict):
            broken += 1
            continue
        events.append(item)
    return {"events": events, "blank": blank, "broken": broken}


def _iter(events) -> list[dict]:
    if isinstance(events, dict) and isinstance(events.get("events"), list) and "blank" in events:
        return events["events"]
    return list(events)


def _dataset_id(ds: dict) -> str | None:
    ns, name = ds.get("namespace"), ds.get("name")
    if isinstance(ns, str) and isinstance(name, str):
        return f"{ns}/{name}"
    return None


def _facet_names(obj: dict) -> list[str]:
    facets = obj.get("facets") if isinstance(obj, dict) else None
    if not isinstance(facets, dict):
        return []
    return [k for k in facets if isinstance(k, str)]


def summary(events) -> dict:
    """Counts over the events: runs, jobs, datasets, event types, facet names, column-lineage outputs."""
    items = _iter(events)
    runs: set[str] = set()
    jobs: set[str] = set()
    datasets: set[str] = set()
    event_types: dict[str, int] = {}
    facets: dict[str, int] = {}
    column_lineage_outputs = 0
    for ev in items:
        kind = str(ev.get("eventType"))
        event_types[kind] = event_types.get(kind, 0) + 1
        run_id = (ev.get("run") or {}).get("runId") if isinstance(ev.get("run"), dict) else None
        if isinstance(run_id, str):
            runs.add(run_id)
        job = ev.get("job") if isinstance(ev.get("job"), dict) else {}
        if isinstance(job.get("namespace"), str) and isinstance(job.get("name"), str):
            jobs.add(f"{job['namespace']}/{job['name']}")
        for bucket in (ev.get("inputs") or []), (ev.get("outputs") or []):
            if not isinstance(bucket, list):
                continue
            for ds in bucket:
                if not isinstance(ds, dict):
                    continue
                did = _dataset_id(ds)
                if did:
                    datasets.add(did)
        for name in _facet_names(ev.get("run") or {}) + _facet_names(ev.get("job") or {}):
            facets[name] = facets.get(name, 0) + 1
        for key in ("inputs", "outputs"):
            bucket = ev.get(key) or []
            if not isinstance(bucket, list):
                continue
            for ds in bucket:
                if not isinstance(ds, dict):
                    continue
                for name in _facet_names(ds):
                    facets[name] = facets.get(name, 0) + 1
                extra = ds.get("inputFacets") if key == "inputs" else ds.get("outputFacets")
                if isinstance(extra, dict):
                    for name in extra:
                        if isinstance(name, str):
                            facets[name] = facets.get(name, 0) + 1
                if key == "outputs" and isinstance((ds.get("facets") or {}).get("columnLineage"), dict):
                    column_lineage_outputs += 1
    return {
        "events": len(items),
        "runs": len(runs),
        "jobs": len(jobs),
        "datasets": len(datasets),
        "event_types": event_types,
        "facets": facets,
        "column_lineage_outputs": column_lineage_outputs,
    }


def _column_pairs(output: dict) -> list[list[str]]:
    out_id = _dataset_id(output)
    facet = (output.get("facets") or {}).get("columnLineage") if isinstance(output.get("facets"), dict) else None
    fields = facet.get("fields") if isinstance(facet, dict) else None
    if not out_id or not isinstance(fields, dict):
        return []
    pairs: list[list[str]] = []
    for out_col, spec in fields.items():
        if not isinstance(out_col, str) or not isinstance(spec, dict):
            continue
        for inp in spec.get("inputFields") or []:
            if not isinstance(inp, dict):
                continue
            ns, name, field = inp.get("namespace"), inp.get("name"), inp.get("field")
            if isinstance(ns, str) and isinstance(name, str) and isinstance(field, str):
                pairs.append([f"{ns}/{name}.{field}", f"{out_id}.{out_col}"])
    return pairs


def _dedupe(pairs: list[list[str]]) -> list[list[str]]:
    seen: set[tuple[str, str]] = set()
    out: list[list[str]] = []
    for pair in pairs:
        key = (pair[0], pair[1])
        if key not in seen:
            seen.add(key)
            out.append(pair)
    return out


def edges(events) -> dict:
    """Table and column edges from COMPLETE events only. Other event types contribute nothing."""
    table: list[list[str]] = []
    column: list[list[str]] = []
    for ev in _iter(events):
        if ev.get("eventType") != "COMPLETE":
            continue
        inputs = [ds for ds in (ev.get("inputs") or []) if isinstance(ds, dict)]
        outputs = [ds for ds in (ev.get("outputs") or []) if isinstance(ds, dict)]
        in_ids = [i for i in (_dataset_id(ds) for ds in inputs) if i]
        out_ids = [i for i in (_dataset_id(ds) for ds in outputs) if i]
        table.extend([src, dst] for src in in_ids for dst in out_ids)
        for output in outputs:
            column.extend(_column_pairs(output))
    return {"table": _dedupe(table), "column": _dedupe(column)}
