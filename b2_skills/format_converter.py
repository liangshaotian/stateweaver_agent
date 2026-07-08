from __future__ import annotations

import json
from pathlib import Path

from .file_reader import ROOT
from .skill_spec import SkillResult


def _safe_output(path: str) -> Path:
    target = (ROOT / path).resolve()
    if ROOT not in target.parents:
        raise ValueError("Output path escapes project root")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def format_converter(markdown_path: str, json_path: str, payload: dict) -> SkillResult:
    try:
        md_target = _safe_output(markdown_path)
        json_target = _safe_output(json_path)
        md_target.write_text(payload["markdown"], encoding="utf-8")
        json_target.write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
        return SkillResult("ok", {
            "markdown_path": markdown_path,
            "json_path": json_path,
            "markdown_chars": len(payload["markdown"]),
        }, state_changes=[
            {"type": "file_created", "path": markdown_path},
            {"type": "file_created", "path": json_path},
        ])
    except Exception as exc:
        return SkillResult("error", error=str(exc))
