from __future__ import annotations

import json
import subprocess
import sys
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def expected_totals(config: dict) -> tuple[float, float]:
    total_cost = 0.0
    total_hours = 0.0
    for rel in config.get("allowed_files", []):
        path = ROOT / rel
        if path.suffix.lower() not in {".csv", ".tsv"} or not path.exists():
            continue
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter=delimiter):
                try:
                    total_cost += float(row.get("cost", 0) or 0)
                except ValueError:
                    pass
                try:
                    total_hours += float(row.get("hours", 0) or 0)
                except ValueError:
                    pass
    return total_cost, total_hours


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
    cfg = json.loads((ROOT / "configs/runtime_input.json").read_text(encoding="utf-8-sig"))
    expected_cost, expected_hours = expected_totals(cfg)
    assert data["total_budget_cost"] == expected_cost
    assert data["total_staff_hours"] == expected_hours
    assert data["decision_mode"] in {"llm", "rule_fallback"}
