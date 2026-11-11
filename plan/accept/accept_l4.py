"""L4 acceptance: OpenLineage events saved and in Marquez; the forward experiment is written up."""
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


def static():
    path = ROOT / "artifacts/openlineage/events.ndjson"
    if not check("events file exists", path.is_file(), str(path)):
        return
    types: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        types[str(ev.get("eventType"))] = types.get(str(ev.get("eventType")), 0) + 1
    check("the file holds COMPLETE events", types.get("COMPLETE", 0) >= 5, str(types))
    d, err = py_json("import json\nfrom lineagelab import olevents\n"
                     "ev = olevents.load('artifacts/openlineage/events.ndjson')\n"
                     "s = olevents.summary(ev); e = olevents.edges(ev)\n"
                     "print(json.dumps({'jobs': s['jobs'], 'datasets': s['datasets'], 'table': len(e['table']), 'column': len(e['column'])}))")
    if check("olevents reads the saved events", d is not None, err):
        check("events name jobs and datasets", d["jobs"] >= 5 and d["datasets"] >= 5, str(d))
        check("table edges can be built from the events", d["table"] >= 5, str(d))
    f = ROOT / "docs/findings/openlineage-to-openmetadata.md"
    text = f.read_text(encoding="utf-8") if f.is_file() else ""
    check("the findings file exists (15 to 120 lines)", 15 <= len(text.splitlines()) <= 120, f"{len(text.splitlines())} lines")
    check("the findings say what resolved and what did not", "resolv" in text.lower(), "")
    no_secrets()


def live():
    st = stacks_up()
    url = str((st.get("marquez") or {}).get("url") or "").rstrip("/")
    try:
        with urllib.request.urlopen(url + "/api/v1/namespaces/lineagelab/jobs?limit=200", timeout=30) as resp:
            jobs = json.loads(resp.read().decode("utf-8")).get("jobs", [])
        check("Marquez holds the dbt jobs in namespace lineagelab", len(jobs) >= 5, f"{len(jobs)} jobs")
    except Exception as exc:  # noqa: BLE001
        check("Marquez holds the dbt jobs in namespace lineagelab", False, f"{type(exc).__name__}: {exc}")


guarded("static", static)
guarded("live", live)
pytest_check("tests", required=["test_summary_counts_runs_jobs_datasets_and_facets", "test_edges_come_from_complete_events_only",
                                "test_column_edges_come_from_the_column_lineage_facet",
                                "test_load_skips_blank_and_broken_lines_and_counts_them"])
finish("L4")
