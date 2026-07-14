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
        self.config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
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
                    rec = self.executor.execute(
                        "local_file_search",
                        {"paths": self.config["allowed_files"], "query": query},
                    )
                    self._record_tool(rec)
                    if rec["status"] == "ok":
                        evidence[key] = [f'{h["path"]}:{h["line"]} {h["text"]}' for h in rec["result"]["output"]["hits"][:3]]

        payload = self._build_report_payload(docs, tables, evidence, selected_memory)
        out_req = self.config["output_requirements"]
        rec = self.executor.execute(
            "format_converter",
            {
                "markdown_path": out_req["markdown_path"],
                "json_path": out_req["json_path"],
                "payload": payload,
            },
        )
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
        input_files = self.config.get("allowed_files", [])
        generated_at = datetime.now().isoformat(timespec="seconds")
        doc_summaries = self._summarize_docs(docs)
        table_stats = self._summarize_tables(tables)
        total_cost = sum(
            table["numeric"]["cost"]["sum"]
            for table in table_stats.values()
            if "cost" in table["numeric"]
        )
        total_hours = sum(
            table["numeric"]["hours"]["sum"]
            for table in table_stats.values()
            if "hours" in table["numeric"]
        )
        budget_rows = sum(table["rows"] for table in table_stats.values() if "cost" in table["numeric"])
        staff_rows = sum(table["rows"] for table in table_stats.values() if "hours" in table["numeric"])
        risk_level = "中等" if total_cost and total_cost < 6000 else "较高"
        if not total_cost and evidence.get("risks"):
            risk_level = "中等"

        md = [
            "# StateWeaver Agent 中文运行报告",
            "",
            f"> 生成时间：{generated_at}  ",
            f"> 会话编号：{self.cid}",
            "",
            "## 0. 本次实际输入文件",
            *[f"- {path}" for path in input_files],
            "",
            "## 1. 项目需求概述",
            f"本次任务共读取 {len(docs)} 个文档文件、分析 {len(tables)} 个表格文件。系统根据当前配置中的 `allowed_files` 动态选择文件，不再固定只读取默认示例文件。",
            "",
            "### 文档摘要",
        ]
        if doc_summaries:
            for path, item in doc_summaries.items():
                md.append(f"- **{path}**：{item['preview']}（约 {item['chars']} 字符）")
        else:
            md.append("- 未读取到 Markdown 或文本类文档。")

        md.extend(
            [
                "",
                "## 2. 预算统计结果",
                f"- 预算总额：{self._fmt_num(total_cost)}",
                f"- 预算相关记录数：{budget_rows}",
                "- 统计方式：扫描本次读取的所有 CSV/TSV 表格，对包含 `cost` 字段的表格求和。",
                "",
                "## 3. 人员工时统计",
                f"- 计划总工时：{self._fmt_num(total_hours)}",
                f"- 工时相关记录数：{staff_rows}",
                "- 统计方式：扫描本次读取的所有 CSV/TSV 表格，对包含 `hours` 字段的表格求和。",
                "",
                "## 4. 表格明细统计",
            ]
        )
        if table_stats:
            for path, table in table_stats.items():
                md.append(f"### {path}")
                md.append(f"- 行数：{table['rows']}")
                md.append(f"- 字段：{', '.join(table['columns'])}")
                if table["numeric"]:
                    for field, stats in table["numeric"].items():
                        md.append(
                            f"- 数值字段 `{field}`：sum={self._fmt_num(stats['sum'])}, "
                            f"mean={round(stats['mean'], 2)}, min={self._fmt_num(stats['min'])}, max={self._fmt_num(stats['max'])}"
                        )
                else:
                    md.append("- 未检测到可统计的数值字段。")
        else:
            md.append("- 未读取到 CSV 或 TSV 表格。")

        md.extend(
            [
                "",
                "## 5. 关键风险与建议",
                f"- 综合风险等级：{risk_level}",
                "- 本地小模型的工具调用格式可能不稳定，需要保留规则降级和解析重试机制。",
                "- GPU 或模型服务可能临时不可用，因此系统需要支持离线规则 Planner。",
                "- 文件路径、表头或数据格式可能不一致，需要通过路径检查和表格字段校验降低失败概率。",
                "",
                "## 6. 证据来源",
            ]
        )
        for key, vals in evidence.items():
            md.append(f"### {key}")
            if vals:
                for val in vals:
                    md.append(f"- {val}")
            else:
                md.append("- 未检索到匹配证据。")

        md.extend(["", "## 7. 召回记忆"])
        if memory:
            md.extend(f"- {m.get('kind')}: {m.get('content')}" for m in memory)
        else:
            md.append("- 本次未召回相关记忆。")

        summary = {
            "conversation_id": self.cid,
            "generated_at": generated_at,
            "input_files": input_files,
            "doc_count": len(docs),
            "table_count": len(tables),
            "doc_summaries": doc_summaries,
            "total_budget_cost": total_cost,
            "total_staff_hours": total_hours,
            "risk_level": risk_level,
            "evidence_counts": {k: len(v) for k, v in evidence.items()},
            "table_stats": table_stats,
            "tables": tables,
        }
        return {"markdown": "\n".join(md) + "\n", "summary": summary}

    def _summarize_docs(self, docs: dict[str, str]) -> dict[str, dict[str, Any]]:
        summaries = {}
        for path, text in docs.items():
            lines = [line.strip(" #") for line in text.splitlines() if line.strip()]
            summaries[path] = {
                "chars": len(text),
                "preview": "；".join(lines[:3])[:220],
            }
        return summaries

    def _summarize_tables(self, tables: dict[str, dict]) -> dict[str, dict[str, Any]]:
        stats = {}
        for path, table in tables.items():
            stats[path] = {
                "rows": table.get("rows", 0),
                "columns": table.get("columns", []),
                "numeric": table.get("numeric", {}),
            }
        return stats

    def _fmt_num(self, value: float) -> str:
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
