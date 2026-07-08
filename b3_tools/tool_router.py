from __future__ import annotations


def route_tools(user_input: str, stage: str) -> list[str]:
    text = (user_input + " " + stage).lower()
    selected = {"file_reader", "format_converter", "evidence_checker"}
    if any(k in text for k in ["csv", "tsv", "table", "budget", "staff"]):
        selected.add("table_analyzer")
    if any(k in text for k in ["search", "evidence", "find", "requirements", "risk"]):
        selected.add("local_file_search")
    if any(k in text for k in ["calculate", "sum", "total", "mean", "budget"]):
        selected.add("calculator")
    return sorted(selected)
