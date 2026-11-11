"""L5 acceptance: the three views of lineage are compared and written up."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, check, finish, grep, guarded, py_json, pytest_check, run  # noqa: E402

SERVICE = "shop_testbed.shop"


def status():
    r = run([sys.executable, "-m", "lineagelab.stack", "status"], timeout=120)
    for line in reversed((r.stdout or "").strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {}


def stacks_up():
    st = status()
    om, mq = st.get("openmetadata") or {}, st.get("marquez") or {}
    check("OpenMetadata is up", bool(om.get("up")), str(om)[:200])
    check("Marquez is up", bool(mq.get("up")), str(mq)[:200])
    return st


def no_secrets():
    hits = grep(["src", "stack", "docs", "tests", "README.md"], r"(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,})")
    check("no token in the repo files", not hits, "; ".join(hits[:3]))


def report():
    stacks_up()
    r = run([sys.executable, "-m", "lineagelab.compare", "report"], timeout=600)
    d = None
    for line in reversed((r.stdout or "").strip().splitlines()):
        if line.strip().startswith("{"):
            try:
                d = json.loads(line)
            except ValueError:
                pass
            break
    if not check("compare report prints its JSON line", isinstance(d, dict), (r.stderr or r.stdout)[-200:]):
        return
    m = (d.get("manifest") or {}).get("table_edges")
    check("the manifest gives the reference table edges", isinstance(m, int) and m >= 10, str(m))
    for view in ("openmetadata", "openlineage"):
        v = d.get(view) or {}
        ok = all(isinstance(v.get(k), (int, float)) for k in ("table_edges", "column_edges", "precision", "recall"))
        check(f"{view} has edge counts, precision and recall", ok and 0 <= v.get("precision", -1) <= 1 and 0 <= v.get("recall", -1) <= 1, str(v)[:200])
    check("unmatched names are counted", isinstance(d.get("unmatched"), int), str(d.get("unmatched")))
    doc = ROOT / "docs/lineage-compare.md"
    text = doc.read_text(encoding="utf-8") if doc.is_file() else ""
    check("docs/lineage-compare.md exists", len(text.splitlines()) >= 20, f"{len(text.splitlines())} lines")
    check("the report shows the manifest edge count", str(m) in text, "")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for word in ("lineagelab.stack up", "lineagelab.ingest database", "lineagelab.ingest dbt", "lineagelab.olrun", "lineagelab.compare report"):
        check(f"README has the command {word}", word in readme, "")
    no_secrets()


guarded("report", report)
pytest_check("tests", required=["test_normalise_maps_each_view_to_schema_table", "test_unmatched_names_are_counted_not_dropped",
                                "test_score_precision_and_recall", "test_manifest_edges_include_sources"])
finish("L5")
