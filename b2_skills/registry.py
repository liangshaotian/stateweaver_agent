from __future__ import annotations

from .calculator import calculator
from .evidence_checker import evidence_checker
from .file_reader import file_reader
from .format_converter import format_converter
from .local_file_search import local_file_search
from .skill_spec import SkillSpec
from .table_analyzer import table_analyzer


SKILLS = {
    "calculator": SkillSpec(
        "calculator", "Safely evaluate arithmetic expressions.",
        {"expression": "Arithmetic expression string."}, ["math", "compute"], "low", calculator,
    ),
    "file_reader": SkillSpec(
        "file_reader", "Read a local UTF-8 text file under the project directory.",
        {"path": "Relative file path."}, ["file", "read", "text"], "low", file_reader,
    ),
    "local_file_search": SkillSpec(
        "local_file_search", "Search keywords in local files.",
        {"paths": "List of relative paths.", "query": "Keyword query."}, ["file", "search"], "low", local_file_search,
    ),
    "table_analyzer": SkillSpec(
        "table_analyzer", "Analyze CSV/TSV numeric columns and row counts.",
        {"path": "Relative CSV/TSV path."}, ["table", "csv", "tsv", "stats"], "low", table_analyzer,
    ),
    "format_converter": SkillSpec(
        "format_converter", "Write Markdown and JSON outputs.",
        {"markdown_path": "Output md path.", "json_path": "Output json path.", "payload": "Report payload."},
        ["format", "markdown", "json"], "low", format_converter,
    ),
    "evidence_checker": SkillSpec(
        "evidence_checker", "Check whether required report sections have evidence strings.",
        {"report": "Report text.", "evidence": "Evidence mapping."}, ["evidence", "verify"], "medium", evidence_checker,
    ),
}


def list_skills() -> list[SkillSpec]:
    return list(SKILLS.values())


def get_skill(name: str) -> SkillSpec:
    return SKILLS[name]
