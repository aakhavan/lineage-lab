"""Three views of lineage over the same dbt models, compared.

    python -m lineagelab.compare report

Views:
  manifest      ``depends_on`` of every model in ``work/olist-dbt/target/manifest.json``; sources are the
                ``raw`` tables. The reference for table edges. dbt's manifest has no column lineage.
  openmetadata  ``om.upstream`` of every ``kpi_*`` table in ``shop_testbed.shop.dev_governor``.
  openlineage   ``olevents.edges`` of ``artifacts/openlineage/events.ndjson`` (COMPLETE events).

Normalisation (``normalise(name, view)``), one rule per view. The result is ``<schema>.<table>`` or
``<schema>.<table>.<column>``; anything else returns None and is counted and listed as unmatched:
  manifest      ``<database>.<schema>.<table>``                 -> drop the database (3 parts only)
  openmetadata  ``<service>.<database>.<schema>.<table>[.<col>]`` -> drop service and database (4 or 5 parts)
  openlineage   ``<namespace>/<database>.<schema>.<table>[.<col>]`` -> drop the namespace (up to the first
                ``/`` after an optional ``scheme://``) and the database (3 or 4 parts)
Empty parts, a missing namespace or another part count do not match. Names are lower-cased (Postgres folds
unquoted identifiers). Metadata only: names and counts, never data values.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from lineagelab import olevents

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "work" / "olist-dbt" / "target" / "manifest.json"
EVENTS = ROOT / "artifacts" / "openlineage" / "events.ndjson"
REPORT = ROOT / "docs" / "lineage-compare.md"
SCHEMA_FQN = "shop_testbed.shop.dev_governor"
DEPTH = 6  # kpi -> int -> stg -> raw is 3 hops; 6 leaves room, om.upstream steps by 3

VIEWS = ("manifest", "openmetadata", "openlineage")
_PARTS = {"manifest": (3,), "openmetadata": (4, 5), "openlineage": (3, 4)}
_OL = re.compile(r"^((?:[A-Za-z][\w+.-]*://)?[^/]*)/(.+)$")


# ---- pure ---------------------------------------------------------------------------------------

def normalise(name: str, view: str) -> str | None:
    """Map one view's table or column name to ``schema.table[.column]``; None when no rule matches."""
    if view not in _PARTS:
        raise ValueError(f"unknown view: {view}")
    if not isinstance(name, str):
        return None
    if view == "openlineage":
        m = _OL.match(name)
        if not m or not m.group(1):
            return None
        name = m.group(2)
    parts = name.lower().split(".")
    if len(parts) not in _PARTS[view] or not all(parts):
        return None
    drop = 2 if view == "openmetadata" else 1
    return ".".join(parts[drop:])


def normalise_edges(pairs, view: str) -> dict:
    """Normalise [from, to] pairs. An edge with an unmapped end is not compared; its names are listed."""
    edges: set[tuple[str, str]] = set()
    unmatched: list[str] = []
    for src, dst in pairs:
        a, b = normalise(src, view), normalise(dst, view)
        for raw, got in ((src, a), (dst, b)):
            if got is None and raw not in unmatched:
                unmatched.append(raw)
        if a is not None and b is not None:
            edges.add((a, b))
    return {"edges": edges, "unmatched": unmatched}


def score(reference, other) -> dict:
    """Missing (in reference only), extra (in other only), precision and recall of other against reference.

    precision = shared / |other|, recall = shared / |reference|; an empty side gives 0.0 (both empty: 1.0).
    """
    ref, oth = set(map(tuple, reference)), set(map(tuple, other))
    shared = ref & oth
    if not ref and not oth:
        p = r = 1.0
    else:
        p = len(shared) / len(oth) if oth else 0.0
        r = len(shared) / len(ref) if ref else 0.0
    return {"shared": len(shared), "missing": sorted(ref - oth), "extra": sorted(oth - ref),
            "precision": round(p, 4), "recall": round(r, 4)}


def manifest_edges(manifest: dict) -> list[list[str]]:
    """``[from, to]`` table edges from ``depends_on.nodes`` of every model, as ``database.schema.table``.

    Parents are models, seeds, snapshots or sources (sources are the ``raw`` tables). Tests are not models.
    """
    rel: dict[str, str] = {}
    for uid, node in {**(manifest.get("nodes") or {}), **(manifest.get("sources") or {})}.items():
        ident = node.get("identifier") or node.get("alias") or node.get("name")
        if node.get("database") and node.get("schema") and ident:
            rel[uid] = f"{node['database']}.{node['schema']}.{ident}"
    out: list[list[str]] = []
    for uid, node in (manifest.get("nodes") or {}).items():
        if node.get("resource_type") != "model" or uid not in rel:
            continue
        for parent in (node.get("depends_on") or {}).get("nodes") or []:
            if parent in rel and [rel[parent], rel[uid]] not in out:
                out.append([rel[parent], rel[uid]])
    return sorted(out)


def overlap(a, b) -> dict:
    """Pairwise overlap of two edge sets (column level: OpenMetadata vs OpenLineage)."""
    a, b = set(map(tuple, a)), set(map(tuple, b))
    union = a | b
    return {"both": len(a & b), "only_a": sorted(a - b), "only_b": sorted(b - a),
            "jaccard": round(len(a & b) / len(union), 4) if union else 1.0}


def disagreements(om_cols, ol_cols, n: int = 5) -> list[dict]:
    """Up to n column edges seen by one view only, grouped by target column so both sides show."""
    om_set, ol_set = set(map(tuple, om_cols)), set(map(tuple, ol_cols))
    targets = sorted({d for _, d in om_set ^ ol_set})
    out = []
    for t in targets[:n]:
        out.append({"column": t,
                    "openmetadata": sorted(s for s, d in om_set if d == t),
                    "openlineage": sorted(s for s, d in ol_set if d == t)})
    return out


def build(manifest_pairs, om_view: dict, ol_view: dict) -> dict:
    """All numbers of the report from the raw (unnormalised) edges of the three views."""
    man = normalise_edges(manifest_pairs, "manifest")
    omt = normalise_edges(om_view["table"], "openmetadata")
    omc = normalise_edges(om_view["column"], "openmetadata")
    olt = normalise_edges(ol_view["table"], "openlineage")
    olc = normalise_edges(ol_view["column"], "openlineage")
    unmatched = {"manifest": man["unmatched"], "openmetadata": omt["unmatched"] + [x for x in omc["unmatched"] if x not in omt["unmatched"]],
                 "openlineage": olt["unmatched"] + [x for x in olc["unmatched"] if x not in olt["unmatched"]]}
    return {
        "manifest": {"table_edges": len(man["edges"]), "edges": sorted(man["edges"])},
        "openmetadata": {"table_edges": len(omt["edges"]), "column_edges": len(omc["edges"]),
                         **score(man["edges"], omt["edges"]), "sources": om_view.get("sources") or {}},
        "openlineage": {"table_edges": len(olt["edges"]), "column_edges": len(olc["edges"]),
                        **score(man["edges"], olt["edges"])},
        "om_vs_ol_tables": overlap(omt["edges"], olt["edges"]),
        "columns": overlap(omc["edges"], olc["edges"]),
        "examples": disagreements(omc["edges"], olc["edges"]),
        "unmatched": unmatched,
    }


def json_line(r: dict) -> dict:
    def view(k):
        v = r[k]
        return {"table_edges": v["table_edges"], "column_edges": v["column_edges"],
                "precision": v["precision"], "recall": v["recall"]}
    return {"manifest": {"table_edges": r["manifest"]["table_edges"]}, "openmetadata": view("openmetadata"),
            "openlineage": view("openlineage"), "unmatched": sum(len(v) for v in r["unmatched"].values())}


def _edge(e) -> str:
    return f"`{e[0]}` -> `{e[1]}`"


def render(r: dict) -> str:
    m, o, l, c = r["manifest"], r["openmetadata"], r["openlineage"], r["columns"]
    t = r["om_vs_ol_tables"]
    L = ["# Three views of lineage compared", "",
         "Written by `python -m lineagelab.compare report`. Metadata only: table and column names, counts.",
         "Names are normalised to `<schema>.<table>` and `<schema>.<table>.<column>` by",
         "`lineagelab.compare.normalise` (rules in its module docstring).", "",
         "- **manifest**: `depends_on` of every dbt model in `manifest.json`, sources as `raw` tables. The reference.",
         f"- **openmetadata**: `om.upstream` (depth {DEPTH}) of every `kpi_*` table in `{SCHEMA_FQN}`.",
         "- **openlineage**: `olevents.edges` of the saved dbt-ol events (COMPLETE events only).", "",
         "## Edge counts", "",
         "| view | table edges | column edges |", "|---|---:|---:|",
         f"| manifest | {m['table_edges']} | n/a (dbt has no column lineage) |",
         f"| openmetadata | {o['table_edges']} | {o['column_edges']} |",
         f"| openlineage | {l['table_edges']} | {l['column_edges']} |", "",
         "## Table edges against the manifest", "",
         "| view | shared | missing | extra | precision | recall |", "|---|---:|---:|---:|---:|---:|"]
    for k in ("openmetadata", "openlineage"):
        v = r[k]
        L.append(f"| {k} | {v['shared']} | {len(v['missing'])} | {len(v['extra'])} | {v['precision']} | {v['recall']} |")
    for k in ("openmetadata", "openlineage"):
        v = r[k]
        L += ["", f"Missing from {k} ({len(v['missing'])}):"]
        L += [f"- {_edge(e)}" for e in v["missing"]] or ["- none"]
        L += ["", f"Extra in {k} ({len(v['extra'])}):"]
        L += [f"- {_edge(e)}" for e in v["extra"]] or ["- none"]
    L += ["", "### Where OpenMetadata's table edges came from", "",
          "OpenMetadata 2.0.5 keeps one edge per pair of tables, with one `lineageDetails.source`. The dbt",
          "workflow (L3) and the OpenLineage endpoint (L4 forward) both write to that same edge. Without",
          "`overrideLineage` in the dbt workflow, a later dbt run merges its column lineage into the edge and",
          "keeps the source label that is already there. So the label tells you who wrote the edge first after",
          "it was created or overridden, and the column list on the edge is the union of both writers.", "",
          "| source | edges |", "|---|---:|"]
    L += [f"| {s} | {n} |" for s, n in sorted(o["sources"].items())] or ["| none | 0 |"]
    L += ["", f"OpenMetadata and OpenLineage table edges: {t['both']} in both, {len(t['only_a'])} only in OpenMetadata, "
          f"{len(t['only_b'])} only in OpenLineage (Jaccard {t['jaccard']}).", "",
          "## Column edges: OpenMetadata against OpenLineage", "",
          "| in both | only OpenMetadata | only OpenLineage | Jaccard |", "|---:|---:|---:|---:|",
          f"| {c['both']} | {len(c['only_a'])} | {len(c['only_b'])} | {c['jaccard']} |", "",
          "### Five example disagreements", "",
          "Target columns whose upstream columns differ between the two views.", ""]
    for ex in r["examples"]:
        L.append(f"- `{ex['column']}`: OpenMetadata from {', '.join(f'`{x}`' for x in ex['openmetadata']) or 'nothing'};"
                 f" OpenLineage from {', '.join(f'`{x}`' for x in ex['openlineage']) or 'nothing'}.")
    if not r["examples"]:
        L.append("- none: the two column edge sets are equal.")
    total = sum(len(v) for v in r["unmatched"].values())
    L += ["", "## Unmatched names", "", f"Names no rule could map: {total}. Edges with an unmatched end are left out of the",
          "comparison above and listed here, never dropped silently.", ""]
    for k in VIEWS:
        names = r["unmatched"][k]
        L.append(f"- {k}: {len(names)}" + (": " + ", ".join(f"`{x}`" for x in names[:20]) if names else ""))
        if len(names) > 20:
            L.append(f"  ({len(names) - 20} more)")
    if any((m := _OL.match(x)) and m.group(2).count(".") == 1 for x in r["unmatched"]["openlineage"]):
        L += ["", "An OpenLineage name with only two parts (`<name>.<column>` with no database or schema) is a",
              "CTE or subquery alias that dbt-ol's SQL parser reported as an input dataset. No table has that",
              "name, so it cannot be mapped, and OpenMetadata cannot resolve it either."]
    return "\n".join(L) + "\n"


# ---- live readers -------------------------------------------------------------------------------

def openmetadata_edges() -> dict:
    """Table and column edges upstream of every ``kpi_*`` table, plus a tally of edge sources."""
    from lineagelab import om
    page = om.get("/v1/tables", databaseSchema=SCHEMA_FQN, limit=1000)
    kpis = sorted(t["fullyQualifiedName"] for t in page.get("data") or [] if t.get("name", "").startswith("kpi_"))
    table: list[list[str]] = []
    column: list[list[str]] = []
    for fqn in kpis:
        up = om.upstream(fqn, depth=DEPTH)
        table += [e for e in up["edges"] if e not in table]
        column += [e for e in up["column_edges"] if e not in column]
    sources: dict[str, int] = {}
    for dst in sorted({d for _, d in table}):
        p = om.get(f"/v1/lineage/table/name/{quote(dst, safe='')}", upstreamDepth=1, downstreamDepth=0)
        by_id = {n["id"]: n.get("fullyQualifiedName") for n in [p.get("entity") or {}, *(p.get("nodes") or [])] if n.get("id")}
        for e in p.get("upstreamEdges") or []:
            if [by_id.get(e.get("fromEntity")), by_id.get(e.get("toEntity"))] in table:
                s = str((e.get("lineageDetails") or {}).get("source") or "unknown")
                sources[s] = sources.get(s, 0) + 1
    return {"kpis": kpis, "table": table, "column": column, "sources": sources}


def openlineage_edges(events) -> dict:
    return olevents.edges(events)


def report() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    r = build(manifest_edges(manifest), openmetadata_edges(), openlineage_edges(olevents.load(EVENTS)))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render(r), encoding="utf-8")
    return json_line(r)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["report"]:
        print("usage: python -m lineagelab.compare report", file=sys.stderr)
        return 2
    print(json.dumps(report()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
