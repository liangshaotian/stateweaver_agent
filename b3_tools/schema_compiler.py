from __future__ import annotations

from b2_skills import list_skills


def compile_schema(skill_names: list[str] | None = None) -> list[dict]:
    schemas = []
    for spec in list_skills():
        if skill_names and spec.name not in skill_names:
            continue
        schemas.append({
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "tags": spec.tags,
            "risk_level": spec.risk_level,
        })
    return schemas
