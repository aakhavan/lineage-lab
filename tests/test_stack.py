"""Offline tests for the stack files and the status line (no Docker, no network)."""
import re
from pathlib import Path

import yaml

from lineagelab import stack

ROOT = Path(__file__).resolve().parents[1]


def _images(compose_path: Path) -> set[str]:
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    return {s["image"] for s in data["services"].values() if "image" in s}


def test_status_line_shape():
    line = stack.status_line({"up": True, "version": "2.0.5", "url": "http://localhost:8585"},
                             {"up": False, "url": "http://localhost:5000"})
    assert line == {"openmetadata": {"up": True, "version": "2.0.5", "url": "http://localhost:8585"},
                    "marquez": {"up": False, "url": "http://localhost:5000"}}
    down = stack.status_line({"up": False, "version": None, "url": "u"}, {"up": False, "url": "m"})
    assert down["openmetadata"]["version"] is None and down["openmetadata"]["up"] is False


def test_compose_files_name_their_projects():
    v = stack.load_versions()["stacks"]
    assert v["om"]["compose_project"] == "lineagelab_om"
    assert v["marquez"]["compose_project"] == "lineagelab_marquez"
    # the OpenMetadata file is the release file unchanged, so its project name is passed with -p
    om_args = stack.compose_args(v["om"])
    assert om_args[om_args.index("-p") + 1] == "lineagelab_om"
    om_text = (ROOT / v["om"]["compose_file"]).read_text(encoding="utf-8")
    assert "releases/download/2.0.5-release/docker-compose-postgres.yml" in om_text.splitlines()[0]
    mq = yaml.safe_load((ROOT / v["marquez"]["compose_file"]).read_text(encoding="utf-8"))
    assert mq["name"] == "lineagelab_marquez"
    assert stack.compose_args(v["marquez"])[3] == "lineagelab_marquez"


def test_versions_file_lists_every_image_in_the_compose_files():
    v = stack.load_versions()["stacks"]
    for key in ("om", "marquez"):
        in_compose = _images(ROOT / v[key]["compose_file"])
        assert in_compose, key
        assert in_compose == set(v[key]["images"]), key
        for img in in_compose:
            assert re.search(r":[\w.-]+$", img) and not img.endswith(":latest"), img
