"""Assemble a self-contained folder for deploying the API to Vercel.

Usage:
    python scripts/stage_api_deploy.py OUT_DIR
    npx vercel deploy --prod --cwd OUT_DIR

OUT_DIR gets only what the API needs at runtime: api/, src/, the two app/
modules the API reuses, the stored Parquet files, the constituent snapshot,
and deploy/vercel-api/ (entrypoint, pinned requirements, Vercel config).
Streamlit, tests, the frontend and the dev requirements stay out, which keeps
the Python bundle under Vercel's size limit.

Reads ALTRIX_DATA_DIR / ALTRIX_RAW_DIR like the app. Never downloads anything:
run scripts/download_data.py first. Used by .github/workflows/deploy-api.yml.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.dashboard import processed_dir  # noqa: E402
from app.scanner_ui import SNAPSHOT_NAME, raw_dir  # noqa: E402

DEPLOY_DIR = Path("deploy") / "vercel-api"
PACKAGES = ["api", "src"]
APP_MODULES = ["app/__init__.py", "app/dashboard.py", "app/scanner_ui.py"]
MARKER = ".altrix-stage"  # marks a folder this script created, so it is safe to replace


class StageError(Exception):
    """The inputs are missing or OUT_DIR is not safe to replace."""


def stage(out: Path, data_dir: Path, raw: Path) -> dict:
    """Build `out` from scratch. Returns counts for the summary line."""
    out = Path(out)
    parquet = sorted(Path(data_dir).glob("*.parquet"))
    snapshot = Path(raw) / SNAPSHOT_NAME
    if not parquet:
        raise StageError(f"no Parquet files in {data_dir}; run: python scripts/download_data.py")
    if not snapshot.exists():
        raise StageError(f"no constituent snapshot at {snapshot}; run: python scripts/download_data.py")
    if out.exists() and any(out.iterdir()):
        if not (out / MARKER).exists():
            raise StageError(f"{out} is not empty and was not created by this script; refusing to replace it")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("created by scripts/stage_api_deploy.py\n", encoding="utf-8")

    code = [p for pkg in PACKAGES for p in (ROOT / pkg).rglob("*.py") if "__pycache__" not in p.parts]
    code += [ROOT / m for m in APP_MODULES]
    for src in code:
        _copy(src, out / src.relative_to(ROOT))
    for src in (ROOT / DEPLOY_DIR).iterdir():
        _copy(src, out / src.name)
    for src in parquet:
        _copy(src, out / "data" / "processed" / src.name)
    _copy(snapshot, out / "data" / "raw" / SNAPSHOT_NAME)
    return {"code_files": len(code), "symbols": len(parquet)}


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, help="folder to create (replaced if a previous run created it)")
    args = parser.parse_args()
    try:
        counts = stage(args.out, processed_dir(), raw_dir())
    except StageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Staged {counts['code_files']} code files and {counts['symbols']} symbols in {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
