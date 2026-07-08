from __future__ import annotations

import inspect
import time
from typing import Any

from b2_skills import get_skill


class ToolExecutor:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        start = time.time()
        try:
            spec = get_skill(tool_name)
            sig = inspect.signature(spec.func)
            sig.bind(**arguments)
            result = spec.func(**arguments)
            rec = {
                "tool": tool_name,
                "arguments": arguments,
                "status": result.status,
                "result": result.to_dict(),
                "elapsed_sec": round(time.time() - start, 4),
            }
        except Exception as exc:
            rec = {
                "tool": tool_name,
                "arguments": arguments,
                "status": "error",
                "result": {"status": "error", "error": str(exc), "output": None},
                "elapsed_sec": round(time.time() - start, 4),
            }
        self.records.append(rec)
        return rec
