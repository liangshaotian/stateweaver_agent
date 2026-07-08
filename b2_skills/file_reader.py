from __future__ import annotations

from pathlib import Path

from .skill_spec import SkillResult


ROOT = Path(__file__).resolve().parents[1]


def safe_path(path: str) -> Path:
    target = (ROOT / path).resolve()
    if ROOT not in target.parents and target != ROOT:
        raise ValueError("Path escapes project root")
    if not target.exists():
        raise FileNotFoundError(path)
    return target


def file_reader(path: str) -> SkillResult:
    try:
        target = safe_path(path)
        text = target.read_text(encoding="utf-8")
        return SkillResult("ok", {"path": path, "text": text, "chars": len(text)})
    except Exception as exc:
        return SkillResult("error", error=str(exc), metadata={"path": path})
