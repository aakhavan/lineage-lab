"""L3 acceptance: dbt descriptions, tests and lineage are in OpenMetadata."""
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


def live():
    stacks_up()
    code = ("import json\nfrom lineagelab import om\nom.client()\n"
            f"k = om.table('{SERVICE}.dev_governor.kpi_gmv') or {{}}\n"
            f"s = om.table('{SERVICE}.dev_governor.stg_orders') or {{}}\n"
            f"u = om.upstream('{SERVICE}.dev_governor.kpi_gmv', 4)\n"
            "print(json.dumps({'kpi_desc': bool((k.get('description') or '').strip()),\n"
            "                  'stg_col_desc': sum(1 for c in s.get('columns', []) if (c.get('description') or '').strip()),\n"
            "                  'stg_tests': int(s.get('tests') or 0), 'nodes': u.get('nodes', []), 'edges': len(u.get('edges', []))}))")
    d, err = py_json(code, timeout=180)
    if not check("kpi_gmv and stg_orders can be read", d is not None, err):
        return
    check("kpi_gmv has its dbt description", d["kpi_desc"], "")
    check("stg_orders has column descriptions", d["stg_col_desc"] >= 1, str(d["stg_col_desc"]))
    check("stg_orders has dbt tests", d["stg_tests"] >= 1, str(d["stg_tests"]))
    nodes = [str(n).lower() for n in d["nodes"]]
    check("kpi_gmv lineage reaches a silver model", any(".stg_" in n or ".int_" in n for n in nodes), ", ".join(nodes)[:200])
    check("kpi_gmv lineage reaches a raw table", any(".raw." in n for n in nodes), ", ".join(nodes)[:200])
    check("kpi_gmv has at least two upstream edges", d["edges"] >= 2, str(d["edges"]))


guarded("static", no_secrets)
guarded("live", live)
pytest_check("tests", required=["test_dbt_workflow_yaml_points_at_the_three_artifacts", "test_dbt_workflow_yaml_names_the_service"])
finish("L3")
