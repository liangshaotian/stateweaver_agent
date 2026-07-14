from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from typing import Any


class OptionalLLMClient:
    """Small OpenAI-compatible chat client with deterministic fallback."""

    def __init__(self, config: dict[str, Any]) -> None:
        llm_cfg = config.get("llm", {}) or {}
        self.enabled = bool(llm_cfg.get("enabled") or os.getenv("STATEWEAVER_LLM_URL"))
        self.base_url = (llm_cfg.get("base_url") or os.getenv("STATEWEAVER_LLM_URL") or "").rstrip("/")
        self.model = llm_cfg.get("model") or os.getenv("STATEWEAVER_LLM_MODEL") or "local-model"
        self.api_key = llm_cfg.get("api_key") or os.getenv("STATEWEAVER_LLM_API_KEY") or ""
        self.timeout = float(llm_cfg.get("timeout", 8))

    def generate(self, prompt: str) -> dict[str, Any]:
        if not self.enabled or not self.base_url:
            return {
                "mode": "rule_fallback",
                "used": False,
                "reason": "未配置本地 LLM 地址，使用规则分析器完成报告。",
                "content": "",
                "elapsed_sec": 0.0,
            }

        start = time.time()
        url = self.base_url
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个严谨的项目诊断 Agent，请输出中文、可执行、基于证据的分析。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 900,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            return {
                "mode": "llm",
                "used": True,
                "reason": f"已调用 {self.model}",
                "content": content.strip(),
                "elapsed_sec": round(time.time() - start, 3),
            }
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            return {
                "mode": "rule_fallback",
                "used": False,
                "reason": f"LLM 调用失败，已自动降级：{exc}",
                "content": "",
                "elapsed_sec": round(time.time() - start, 3),
            }


class DecisionAnalyst:
    def __init__(self, runtime_input: dict[str, Any]) -> None:
        self.runtime_input = runtime_input
        self.llm = OptionalLLMClient(runtime_input)

    def analyze(self, docs: dict[str, str], tables: dict[str, dict], evidence: dict, memory: list[dict]) -> dict[str, Any]:
        start = time.time()
        doc_facts = self._extract_doc_facts(docs)
        table_diagnosis = self._diagnose_tables(tables)
        recommendations = self._recommend(table_diagnosis, doc_facts, evidence, memory)
        llm_result = self.llm.generate(self._build_llm_prompt(doc_facts, table_diagnosis, recommendations))
        if llm_result["content"]:
            recommendations["llm_insights"] = llm_result["content"].splitlines()[:12]

        return {
            "decision_mode": llm_result["mode"],
            "llm": llm_result,
            "analysis_elapsed_sec": round(time.time() - start, 3),
            "doc_facts": doc_facts,
            "table_diagnosis": table_diagnosis,
            "recommendations": recommendations,
        }

    def _extract_doc_facts(self, docs: dict[str, str]) -> dict[str, Any]:
        requirement_terms = ("must", "required", "requires", "deliverable", "output", "需要", "必须", "要求", "提交", "报告")
        risk_terms = ("risk", "unstable", "unavailable", "fail", "error", "冲突", "失败", "风险", "不可用", "不稳定")
        preference_terms = ("prefer", "expected", "should", "希望", "建议", "更容易", "中文", "界面")
        facts = {"requirements": [], "risks": [], "preferences": [], "headings": []}
        for path, text in docs.items():
            for line_no, raw in enumerate(text.splitlines(), 1):
                line = raw.strip()
                if not line:
                    continue
                clean = line.strip("#- *").strip()
                low = clean.lower()
                item = {"path": path, "line": line_no, "text": clean[:240]}
                if raw.lstrip().startswith("#"):
                    facts["headings"].append(item)
                if any(term in low or term in clean for term in requirement_terms):
                    facts["requirements"].append(item)
                if any(term in low or term in clean for term in risk_terms):
                    facts["risks"].append(item)
                if any(term in low or term in clean for term in preference_terms):
                    facts["preferences"].append(item)
        for key in facts:
            facts[key] = facts[key][:12]
        return facts

    def _diagnose_tables(self, tables: dict[str, dict]) -> dict[str, Any]:
        budget_rows = []
        staff_rows = []
        progress_rows = []
        tool_rows = []
        incident_rows = []
        duplicates = defaultdict(list)

        for path, table in tables.items():
            basename = re.sub(r"_[0-9]+(?=\.)", "", path.split("/")[-1])
            duplicates[basename].append(path)
            for row in table.get("records", []):
                enriched = {"_path": path, **row}
                if "cost" in row:
                    budget_rows.append(enriched)
                if "hours" in row:
                    staff_rows.append(enriched)
                if "completion_percent" in row:
                    progress_rows.append(enriched)
                if {"calls", "successes"}.issubset(row):
                    tool_rows.append(enriched)
                if "severity" in row and "status" in row:
                    incident_rows.append(enriched)

        return {
            "budget": self._budget_diagnosis(budget_rows),
            "staffing": self._staff_diagnosis(staff_rows),
            "progress": self._progress_diagnosis(progress_rows),
            "tools": self._tool_diagnosis(tool_rows),
            "incidents": self._incident_diagnosis(incident_rows),
            "duplicate_uploads": {name: paths for name, paths in duplicates.items() if len(paths) > 1},
        }

    def _budget_diagnosis(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        total = sum(self._num(row.get("cost")) for row in rows)
        by_category = defaultdict(float)
        by_owner = defaultdict(float)
        by_stage = defaultdict(float)
        for row in rows:
            cost = self._num(row.get("cost"))
            by_category[row.get("category", "unknown")] += cost
            by_owner[row.get("owner", "unknown")] += cost
            by_stage[row.get("stage", "unknown")] += cost
        top_items = sorted(rows, key=lambda row: self._num(row.get("cost")), reverse=True)[:5]
        return {
            "total": total,
            "rows": len(rows),
            "by_category": dict(sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)),
            "by_owner": dict(sorted(by_owner.items(), key=lambda kv: kv[1], reverse=True)),
            "by_stage": dict(sorted(by_stage.items(), key=lambda kv: kv[1], reverse=True)),
            "top_items": top_items,
        }

    def _staff_diagnosis(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        total = sum(self._num(row.get("hours")) for row in rows)
        by_name = defaultdict(float)
        by_role = defaultdict(float)
        for row in rows:
            by_name[row.get("name") or row.get("owner") or "unknown"] += self._num(row.get("hours"))
            by_role[row.get("role", "unknown")] += self._num(row.get("hours"))
        overloaded = [{"name": name, "hours": hours} for name, hours in by_name.items() if hours >= 35]
        return {
            "total": total,
            "rows": len(rows),
            "by_name": dict(sorted(by_name.items(), key=lambda kv: kv[1], reverse=True)),
            "by_role": dict(sorted(by_role.items(), key=lambda kv: kv[1], reverse=True)),
            "overloaded": overloaded,
        }

    def _progress_diagnosis(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        if not rows:
            return {"rows": 0, "average_completion": 0, "lowest": [], "blocked": []}
        avg = sum(self._num(row.get("completion_percent")) for row in rows) / len(rows)
        lowest = sorted(rows, key=lambda row: self._num(row.get("completion_percent")))[:3]
        blocked = [row for row in rows if row.get("blocked_by")]
        return {
            "rows": len(rows),
            "average_completion": round(avg, 2),
            "lowest": lowest,
            "blocked": blocked,
        }

    def _tool_diagnosis(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        tool_items = []
        total_calls = 0
        total_success = 0
        for row in rows:
            calls = self._num(row.get("calls"))
            successes = self._num(row.get("successes"))
            total_calls += calls
            total_success += successes
            tool_items.append({
                "tool": row.get("tool", "unknown"),
                "calls": calls,
                "successes": successes,
                "success_rate": round(successes / calls * 100, 2) if calls else 0,
                "avg_latency_ms": self._num(row.get("avg_latency_ms")),
                "main_use": row.get("main_use", ""),
            })
        return {
            "total_calls": total_calls,
            "total_successes": total_success,
            "overall_success_rate": round(total_success / total_calls * 100, 2) if total_calls else 0,
            "items": sorted(tool_items, key=lambda row: row["avg_latency_ms"], reverse=True),
        }

    def _incident_diagnosis(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        severity = Counter(row.get("severity", "unknown") for row in rows)
        status = Counter(row.get("status", "unknown") for row in rows)
        open_items = [row for row in rows if row.get("status") not in {"closed", "done", "mitigated"}]
        return {
            "rows": len(rows),
            "severity": dict(severity),
            "status": dict(status),
            "open_items": open_items,
        }

    def _recommend(self, table: dict[str, Any], doc: dict[str, Any], evidence: dict, memory: list[dict]) -> dict[str, Any]:
        recs = []
        budget = table["budget"]
        progress = table["progress"]
        tools = table["tools"]
        incidents = table["incidents"]
        if budget["top_items"]:
            top = budget["top_items"][0]
            recs.append(f"优先复核最高成本项 `{top.get('item', 'unknown')}`，金额 {self._fmt(self._num(top.get('cost')))}，避免预算被单项资源拖高。")
        if progress["blocked"]:
            names = "、".join(row.get("module", "unknown") for row in progress["blocked"][:3])
            recs.append(f"当前存在被阻塞模块：{names}，应先处理 blocked_by 字段对应的问题，再继续扩展功能。")
        if tools["items"]:
            slow = tools["items"][0]
            recs.append(f"工具层最慢的是 `{slow['tool']}`，平均 {self._fmt(slow['avg_latency_ms'])} ms，适合加入缓存或结果复用。")
        if incidents["open_items"]:
            names = "、".join(row.get("issue_id", "unknown") for row in incidents["open_items"][:3])
            recs.append(f"仍需关注未关闭事件：{names}，这些问题应体现在验收前检查清单中。")
        if table["duplicate_uploads"]:
            recs.append("检测到同名文件多次上传，建议在正式演示前清理重复版本，避免重复统计导致预算和工时翻倍。")
        if not recs:
            recs.append("当前数据没有发现明显阻塞项，可继续完善报告表达、演示流程和边界案例。")
        return {
            "action_items": recs,
            "evidence_coverage": {key: len(vals) for key, vals in evidence.items()},
            "memory_count": len(memory),
        }

    def _build_llm_prompt(self, doc_facts: dict[str, Any], table: dict[str, Any], recs: dict[str, Any]) -> str:
        compact = {
            "doc_facts": doc_facts,
            "table_diagnosis": table,
            "rule_recommendations": recs,
        }
        return (
            "请基于以下结构化材料，生成 5 条项目诊断洞察。要求：中文；不要编造不存在的数据；"
            "每条包含问题、依据和建议。\n\n"
            + json.dumps(compact, ensure_ascii=False)[:6000]
        )

    def _num(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _fmt(self, value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(round(value, 2))
