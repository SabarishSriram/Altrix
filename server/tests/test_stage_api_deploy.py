"""scripts/stage_api_deploy.py builds a self-contained API folder for Vercel. Offline."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.scanner_ui import SNAPSHOT_NAME

from .app.test_scanner_ui import make_world

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("stage_api_deploy", ROOT / "scripts" / "stage_api_deploy.py")
stage_api_deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage_api_deploy)


@pytest.fixture
def staged(tmp_path):
    processed, raw = make_world(tmp_path)
    out = tmp_path / "out"
    counts = stage_api_deploy.stage(out, processed, raw)
    return out, counts


def test_stages_runtime_files_only(staged):
    out, counts = staged
    assert counts["symbols"] == 5
    for path in ["index.py", "requirements.txt", "vercel.json", ".python-version", "api/main.py",
                 "src/strategy/baseline.py", "src/backtest/engine.py", "app/__init__.py", "app/dashboard.py",
                 "app/scanner_ui.py", "data/processed/BUYCO.NS.parquet", f"data/raw/{SNAPSHOT_NAME}"]:
        assert (out / path).is_file(), path
    for path in ["app/streamlit_app.py", "app/views", "tests", "web", "scripts"]:
        assert not (out / path).exists(), path
    assert not list(out.rglob("__pycache__"))


def test_staged_folder_runs_on_its_own(staged):
    out, _ = staged
    probe = """
import json
from fastapi.testclient import TestClient
import api, index
c = TestClient(index.app)
health = c.get("/health").json()
print(json.dumps({
    "api_file": api.__file__,
    "health": health,
    "scanner_status": c.get("/api/scanner").status_code,
    "download_status": c.post("/api/refresh?download=true").status_code,
}))
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ALTRIX_") and k != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, "-c", probe], cwd=out, env=env, capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert Path(result["api_file"]).resolve().is_relative_to(out.resolve())  # the staged copy, not the repo
    assert result["health"]["stored_symbols"] == 5
    assert result["health"]["offline_mode"] is True and result["health"]["downloads_enabled"] is False
    assert result["scanner_status"] == 200
    assert result["download_status"] == 403


def test_replaces_a_previous_stage(staged, tmp_path):
    out, _ = staged
    (out / "stale.txt").write_text("old", encoding="utf-8")
    stage_api_deploy.stage(out, tmp_path / "processed", tmp_path / "raw")
    assert not (out / "stale.txt").exists() and (out / "index.py").exists()


def test_refuses_a_folder_it_did_not_create(tmp_path):
    processed, raw = make_world(tmp_path)
    out = tmp_path / "mine"
    out.mkdir()
    (out / "keep.txt").write_text("important", encoding="utf-8")
    with pytest.raises(stage_api_deploy.StageError, match="refusing"):
        stage_api_deploy.stage(out, processed, raw)
    assert (out / "keep.txt").read_text(encoding="utf-8") == "important"


def test_requires_data_and_snapshot(tmp_path):
    processed, raw = make_world(tmp_path)
    with pytest.raises(stage_api_deploy.StageError, match="no Parquet files"):
        stage_api_deploy.stage(tmp_path / "out", tmp_path / "empty", raw)
    (raw / SNAPSHOT_NAME).unlink()
    with pytest.raises(stage_api_deploy.StageError, match="no constituent snapshot"):
        stage_api_deploy.stage(tmp_path / "out", processed, raw)


def test_stages_deliverables_when_present(tmp_path):
    from src.data.deliverables import DeliverableStore

    processed, raw = make_world(tmp_path)
    store = DeliverableStore(tmp_path / "deliverables")
    store.append(pd.DataFrame({"date": [pd.Timestamp("2026-08-24")], "symbol": ["BUYCO.NS"],
                               "deliv_qty": [1.0], "deliv_per": [60.0]}))
    counts = stage_api_deploy.stage(tmp_path / "out", processed, raw, tmp_path / "deliverables")
    assert counts["deliverables"] is True
    assert (tmp_path / "out" / "data" / "deliverables" / "deliverables.parquet").is_file()

    counts = stage_api_deploy.stage(tmp_path / "out", processed, raw, tmp_path / "nothing-here")
    assert counts["deliverables"] is False
