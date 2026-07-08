from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from b3_tools.executor import ToolExecutor
from b3_tools.schema_compiler import compile_schema
from b3_tools.tool_router import route_tools
from b4_decision.planner import Planner
from b4_decision.verifier import Verifier
from b5_memory import MemoryStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentRuntime:
    def __init__(self, config_path: Path) -> None:
        self.project_root = PROJECT_ROOT
        self.config_path = (PROJECT_ROOT / config_path).resolve() if not config_path.is_absolute() else config_path
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.cid = self.config["conversation_id"]
        self.trace_path = PROJECT_ROOT / "traces" / f"{self.cid}.jsonl"
        self.checkpoint_path = PROJECT_ROOT / "checkpoints" / f"{self.cid}.json"
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.executor = ToolExecutor()
        self.planner = Planner()
        self.verifier = Verifier()
        self.memory = MemoryStore(PROJECT_ROOT / "configs" / "memory.json")
        self.state: dict[str, Any] = {
            "conversation_id": self.cid,
            "stage": "INIT",
            "messages": [],
            "tool_calls": [],
            "errors": [],
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }

    def event(self, stage: str, payload: dict[str, Any]) -> None:
        self.state["stage"] = stage
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "stage": stage, **payload}
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.checkpoint()

    def checkpoint(self) -> None:
        self.checkpoint_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def run(self) -> dict[str, Any]:
        start = time.time()
        user_input = self.config["user_input"]
        selected_tools = route_tools(user_input, "INIT")
        schema = compile_schema(selected_tools)
        self.event("INIT", {"selected_tools": selected_tools, "schema_size": len(schema)})

        selected_memory = self.memory.retrieve(user_input)
        self.state["selected_memory"] = selected_memory
        self.event("RETRIEVE_MEMORY", {"memory_count": len(selected_memory)})

        plan = self.planner.plan(self.config, selected_memory)
        self.state["plan"] = plan
        self.event("PLAN", {"plan_steps": [p["id"] for p in plan]})

        docs: dict[str, str] = {}
        tables: dict[str, dict] = {}
        evidence: dict[str, list[str]] = {"requirements": [], "budget": [], "risks": [], "staffing": []}

        for step in plan:
            if step["id"] == "read_docs":
                for path in step["targets"]:
                    rec = self.executor.execute("file_reader", {"path": path})
                    self._record_tool(rec)
                    if rec["status"] == "ok":
                        docs[path] = rec["result"]["output"]["text"]
            elif step["id"] == "analyze_tables":
                for path in step["targets"]:
                    rec = self.executor.execute("table_analyzer", {"path": path})
                    self._record_tool(rec)
                    if rec["status"] == "ok":
                        tables[path] = rec["result"]["output"]
            elif step["id"] == "search_evidence":
                queries = {
                    "requirements": "requires deliverables workflow local",
                    "budget": "budget cost",
                    "risks": "risks unstable gpu",
                    "staffing": "modules runtime memory tools",
                }
                for key, query in queries.items():
                    rec = self.executor.execute("local_file_search", {"paths": self.config["allowed_files"], "query": query})
                    self._record_tool(rec)
                    if rec["status"] == "ok":
                        evidence[key] = [f'{h["path"]}:{h["line"]} {h["text"]}' for h in rec["result"]["output"]["hits"][:3]]

        payload = self._build_report_payload(docs, tables, evidence, selected_memory)
        out_req = self.config["output_requirements"]
        rec = self.executor.execute("format_converter", {
            "markdown_path": out_req["markdown_path"],
            "json_path": out_req["json_path"],
            "payload": payload,
        })
        self._record_tool(rec)
        self.event("WRITE_OUTPUTS", {"markdown_path": out_req["markdown_path"], "json_path": out_req["json_path"]})

        evidence_rec = self.executor.execute("evidence_checker", {"report": payload["markdown"], "evidence": evidence})
        self._record_tool(evidence_rec)
        verify = self.verifier.verify_outputs(PROJECT_ROOT, out_req["markdown_path"], out_req["json_path"])
        self.state["verification"] = verify
        self.event("VERIFY", {"passed": verify["passed"], "checks": verify["checks"], "evidence_status": evidence_rec["status"]})

        memory_rec = self.memory.write_back(
            self.cid,
            "Completed local document and table analysis with traceable outputs.",
            ["demo", "document", "table", "trace"],
        )
        self.event("SAVE_MEMORY", {"memory_id": memory_rec["id"]})

        status = "success" if verify["passed"] and evidence_rec["status"] == "ok" else "partial"
        self.state["status"] = status
        self.state["elapsed_sec"] = round(time.time() - start, 3)
        self.event("DONE", {"status": status, "elapsed_sec": self.state["elapsed_sec"]})
        return {
            "conversation_id": self.cid,
            "status": status,
            "report_path": out_req["markdown_path"],
            "summary_path": out_req["json_path"],
            "trace_path": str(self.trace_path.relative_to(PROJECT_ROOT)),
        }

    def _record_tool(self, rec: dict[str, Any]) -> None:
        self.state["tool_calls"].append(rec)
        self.event("TOOL_CALL", {"tool": rec["tool"], "status": rec["status"], "elapsed_sec": rec["elapsed_sec"]})

    def _build_report_payload(self, docs: dict[str, str], tables: dict[str, dict], evidence: dict, memory: list[dict]) -> dict:
        budget = tables.get("data/budget.csv", {})
        staff = tables.get("data/staff.tsv", {})
        total_cost = budget.get("numeric", {}).get("cost", {}).get("sum", 0)
        total_hours = staff.get("numeric", {}).get("hours", {}).get("sum", 0)
        risk_level = "中等" if total_cost and total_cost < 6000 else "较高"
        md = [
            "# StateWeaver Agent 中文运行报告",
            "",
            "## 1. 项目需求概述",
            "本项目需要构建一个可本地运行、可复现、可追踪的文档与数据分析 Agent。系统需要读取本地需求文档、会议记录和数据表格，并生成带证据来源的结构化输出。",
            "",
            "## 2. 预算统计结果",
            f"- 预算总额：{total_cost}",
            f"- 预算表记录数：{budget.get('rows', 0)}",
            "- 统计方式：由表格分析工具读取 data/budget.csv，并对 cost 字段求和。",
            "",
            "## 3. 人员工时统计",
            f"- 计划总工时：{total_hours}",
            f"- 人员表记录数：{staff.get('rows', 0)}",
            "- 统计方式：由表格分析工具读取 data/staff.tsv，并对 hours 字段求和。",
            "",
            "## 4. 关键风险与建议",
            f"- 综合风险等级：{risk_level}",
            "- 本地小模型的工具调用格式可能不稳定，需要保留规则降级和解析重试机制。",
            "- GPU 或模型服务可能临时不可用，因此系统需要支持离线规则 Planner。",
            "- 文件路径、表头或数据格式可能不一致，需要通过路径检查和表格字段校验降低失败概率。",
            "",
            "## 5. 证据来源",
        ]
        for key, vals in evidence.items():
            md.append(f"### {key}")
            for val in vals:
                md.append(f"- {val}")
        md.extend([
            "",
            "## 6. 召回记忆",
            *[f"- {m.get('kind')}: {m.get('content')}" for m in memory],
        ])
        summary = {
            "conversation_id": self.cid,
            "total_budget_cost": total_cost,
            "total_staff_hours": total_hours,
            "risk_level": risk_level,
            "evidence_counts": {k: len(v) for k, v in evidence.items()},
            "tables": tables,
        }
        return {"markdown": "\n".join(md) + "\n", "summary": summary}
