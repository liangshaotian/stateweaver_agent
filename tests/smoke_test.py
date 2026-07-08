from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_smoke() -> None:
    proc = subprocess.run([sys.executable, "main.py", "--config", "configs/runtime_input.json"], cwd=ROOT, text=True)
    assert proc.returncode == 0
    summary = ROOT / "outputs/demo_001/summary.json"
    report = ROOT / "outputs/demo_001/report.md"
    trace = ROOT / "traces/demo_001.jsonl"
    assert summary.exists()
    assert report.exists()
    assert trace.exists()
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["total_budget_cost"] == 4800.0
    assert data["total_staff_hours"] == 122.0
