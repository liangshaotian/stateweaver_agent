from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    proc = subprocess.run([sys.executable, "main.py", "--config", "configs/runtime_input.json"], cwd=ROOT, text=True, capture_output=True)
    print(proc.stdout)
    if proc.returncode:
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    summary = json.loads((ROOT / "outputs/demo_001/summary.json").read_text(encoding="utf-8"))
    print("budget=", summary["total_budget_cost"])
    print("hours=", summary["total_staff_hours"])
    print("risk=", summary["risk_level"])


if __name__ == "__main__":
    main()
