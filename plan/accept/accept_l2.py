"""L2 acceptance: work copy with dbt artifacts; the shop database is in OpenMetadata."""
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
    target = ROOT / "work/olist-dbt/target"
    for name in ("manifest.json", "catalog.json", "run_results.json"):
        check(f"work copy has target/{name}", (target / name).is_file(), "")
    check("the work copy has no .git", not (ROOT / "work/olist-dbt/.git").exists(), "")
    tracked = run(["git", "ls-files", "work", "artifacts", "logs"]).stdout.strip()
    check("work/, artifacts/ and logs/ are not tracked", tracked == "", tracked[:200])
    no_secrets()


def live():
    stacks_up()
    code = ("import json\nfrom lineagelab import om\nom.client()\nout = {}\n"
            f"for t in ('dev_governor.stg_orders', 'dev_governor.kpi_gmv', 'analytics.kpi_gmv'):\n"
            f"    x = om.table('{SERVICE}.' + t)\n"
            "    out[t] = len(x['columns']) if x else -1\n"
            "print(json.dumps(out))")
    d, err = py_json(code, timeout=180)
    check("tables can be read from OpenMetadata", d is not None, err)
    for t, n in (d or {}).items():
        check(f"{t} is in OpenMetadata with its columns", n >= 2, f"{n} columns")


guarded("static", static)
guarded("live", live)
pytest_check("tests", required=["test_workcopy_skips_target_logs_and_git",
                                "test_database_workflow_yaml_has_only_the_three_schemas",
                                "test_database_workflow_yaml_turns_sample_data_off",
                                "test_rendered_yaml_in_tests_holds_no_real_credentials",
                                "test_missing_compose_file_is_downloaded_from_the_recorded_url"])
finish("L2")
