from __future__ import annotations


class Planner:
    def plan(self, runtime_input: dict, selected_memory: list[dict]) -> list[dict]:
        files = runtime_input.get("allowed_files", [])
        doc_files = [p for p in files if p.endswith((".md", ".txt"))]
        table_files = [p for p in files if p.endswith((".csv", ".tsv"))]
        return [
            {"id": "read_docs", "tool": "file_reader", "targets": doc_files, "purpose": "collect requirements and risks"},
            {"id": "analyze_tables", "tool": "table_analyzer", "targets": table_files, "purpose": "compute budget and staff statistics"},
            {"id": "search_evidence", "tool": "local_file_search", "targets": files, "purpose": "find evidence lines"},
            {"id": "write_outputs", "tool": "format_converter", "targets": [], "purpose": "generate markdown and json"},
            {"id": "verify_evidence", "tool": "evidence_checker", "targets": [], "purpose": "check evidence coverage"},
        ]
