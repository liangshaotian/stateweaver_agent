from __future__ import annotations

from .file_reader import file_reader
from .skill_spec import SkillResult


def local_file_search(paths: list[str], query: str) -> SkillResult:
    terms = [t.lower() for t in query.split() if t.strip()]
    hits = []
    for path in paths:
        res = file_reader(path)
        if res.status != "ok":
            continue
        text = res.output["text"]
        lines = text.splitlines()
        for idx, line in enumerate(lines, 1):
            low = line.lower()
            score = sum(1 for term in terms if term in low)
            if score:
                hits.append({"path": path, "line": idx, "text": line, "score": score})
    hits.sort(key=lambda x: x["score"], reverse=True)
    return SkillResult("ok", {"query": query, "hits": hits[:20], "count": len(hits)})
