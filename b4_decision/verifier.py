from __future__ import annotations

from pathlib import Path


class Verifier:
    def verify_outputs(self, project_root: Path, markdown_path: str, json_path: str) -> dict:
        md = project_root / markdown_path
        js = project_root / json_path
        checks = {
            "markdown_exists": md.exists(),
            "json_exists": js.exists(),
            "markdown_nonempty": md.exists() and md.stat().st_size > 100,
            "json_nonempty": js.exists() and js.stat().st_size > 50,
        }
        return {"passed": all(checks.values()), "checks": checks}
