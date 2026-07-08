from __future__ import annotations

from .skill_spec import SkillResult


def evidence_checker(report: str, evidence: dict[str, list[str]]) -> SkillResult:
    missing = []
    for section in ["requirements", "budget", "risks", "staffing"]:
        if not evidence.get(section):
            missing.append(section)
    has_report = len(report.strip()) > 100
    status = "ok" if has_report and not missing else "error"
    return SkillResult(status, {
        "valid": status == "ok",
        "missing_evidence": missing,
        "checked_sections": list(evidence.keys()),
    }, error=None if status == "ok" else "Missing evidence or report too short")
