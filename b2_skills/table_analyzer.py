from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean

from .file_reader import safe_path
from .skill_spec import SkillResult


def _dialect(path: Path):
    return "\t" if path.suffix.lower() == ".tsv" else ","


def table_analyzer(path: str) -> SkillResult:
    try:
        target = safe_path(path)
        with target.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=_dialect(target))
            rows = list(reader)
        numeric = {}
        for field in reader.fieldnames or []:
            vals = []
            for row in rows:
                try:
                    vals.append(float(row[field]))
                except Exception:
                    pass
            if vals:
                numeric[field] = {
                    "count": len(vals),
                    "sum": sum(vals),
                    "mean": mean(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
        return SkillResult("ok", {
            "path": path,
            "rows": len(rows),
            "columns": reader.fieldnames or [],
            "numeric": numeric,
            "sample": rows[:3],
        })
    except Exception as exc:
        return SkillResult("error", error=str(exc), metadata={"path": path})
