"""Copy governor's dbt project to work/olist-dbt/ (the source is only read).

    python -m lineagelab.workcopy

The source is ../olist-dbt (env LAB_DBT_PROJECT overrides it). The top-level `target/`, `logs/` and `.git`
are skipped; an older copy is replaced. Prints one JSON line: {"source", "dest", "files_copied"}.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "work" / "olist-dbt"
SKIP_TOP = {"target", "logs", ".git"}


def source_dir() -> Path:
    return Path(os.environ.get("LAB_DBT_PROJECT") or (ROOT.parent / "olist-dbt")).resolve()


def _force_remove(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)  # Windows: read-only files (e.g. from git) block rmtree
    func(path)


def make_copy(src: Path, dest: Path) -> int:
    """Replace dest with a copy of src minus the top-level target/, logs/ and .git. Returns files copied."""
    src, dest = Path(src).resolve(), Path(dest).resolve()
    if not (src / "dbt_project.yml").is_file():
        raise FileNotFoundError(f"no dbt_project.yml in {src}")
    if dest == src or src in dest.parents:
        raise ValueError("destination must not be inside the source project")
    if dest.exists():
        shutil.rmtree(dest, onexc=_force_remove)

    def ignore(d: str, names: list[str]) -> set[str]:
        return SKIP_TOP & set(names) if Path(d).resolve() == src else set()

    shutil.copytree(src, dest, ignore=ignore)
    return sum(1 for p in dest.rglob("*") if p.is_file())


def main() -> int:
    src = source_dir()
    n = make_copy(src, DEST)
    print(json.dumps({"source": str(src), "dest": str(DEST.relative_to(ROOT)).replace("\\", "/"), "files_copied": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
