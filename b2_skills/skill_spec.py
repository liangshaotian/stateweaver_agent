from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SkillResult:
    status: str
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    state_changes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
            "state_changes": self.state_changes,
        }


@dataclass
class SkillSpec:
    name: str
    description: str
    parameters: dict[str, str]
    tags: list[str]
    risk_level: str
    func: Callable[..., SkillResult]
