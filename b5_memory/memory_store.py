from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('{"records":[]}', encoding="utf-8")

    def _load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        terms = set(query.lower().split())
        records = self._load().get("records", [])
        scored = []
        for rec in records:
            text = (rec.get("content", "") + " " + " ".join(rec.get("tags", []))).lower()
            score = sum(1 for term in terms if term in text) + float(rec.get("confidence", 0))
            if score > 0:
                item = dict(rec)
                item["score"] = round(score, 3)
                scored.append(item)
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    def write_back(self, conversation_id: str, summary: str, tags: list[str]) -> dict:
        data = self._load()
        rec = {
            "id": f"episodic_{conversation_id}_{len(data.get('records', [])) + 1}",
            "kind": "episodic",
            "content": summary,
            "tags": tags,
            "confidence": 0.76,
            "source_trace": conversation_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        data.setdefault("records", []).append(rec)
        self._save(data)
        return rec
