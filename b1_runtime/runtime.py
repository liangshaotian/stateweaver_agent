from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from b3_tools.executor import ToolExecutor
from b3_tools.schema_compiler import compile_schema
from b3_tools.tool_router import route_tools
from b4_decision.analyst import DecisionAnalyst
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
        self.analyst = DecisionAnalyst(self.config)
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
                    "requirements": "requires deliverables workflow local 需要 必须 要求 提交",
                    "budget": "budget cost 预算 成本 金额",
                    "risks": "risks unstable gpu unavailable 风险 不稳定 失败 不可用",
                    "staffing": "modules runtime memory tools hours 人员 工时 模块",
                }
                for key, query in queries.items():
                    rec = self.executor.execute(
                        "local_file_search",
                        {"paths": self.config["allowed_files"], "query": query},
                    )
                    self._record_tool(rec)
                    if rec["status"] == "ok":
                        evidence[key] = [f'{h["path"]}:{h["line"]} {h["text"]}' for h in rec["result"]["output"]["hits"][:5]]

        analysis = self.analyst.analyze(docs, tables, evidence, selected_memory)
        self.state["analysis"] = analysis
        self.event(
            "ANALYZE",
            {
                "decision_mode": analysis["decision_mode"],
                "llm_used": analysis["llm"]["used"],
                "llm_reason": analysis["llm"]["reason"],
                "analysis_elapsed_sec": analysis["analysis_elapsed_sec"],
            },
        )

        payload = self._build_report_payload(docs, tables, evidence, selected_memory, analysis)
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
            f"Completed analysis in {analysis['decision_mode']} mode with {len(docs)} docs and {len(tables)} tables.",
            ["demo", "document", "table", "trace", analysis["decision_mode"]],
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

    def _build_report_payload(
        self,
        docs: dict[str, str],
        tables: dict[str, dict],
        evidence: dict,
        memory: list[dict],
        analysis: dict[str, Any],
    ) -> dict:
        input_files = self.config.get("allowed_files", [])
        generated_at = datetime.now().isoformat(timespec="seconds")
        doc_summaries = self._summarize_docs(docs)
        table_stats = self._summarize_tables(tables)
        diagnosis = analysis["table_diagnosis"]
        budget = diagnosis["budget"]
        staffing = diagnosis["staffing"]
        progress = diagnosis["progress"]
        tools = diagnosis["tools"]
        incidents = diagnosis["incidents"]
        duplicate_uploads = diagnosis["duplicate_uploads"]
        risk_level = self._risk_level(budget, progress, incidents, duplicate_uploads)

        md = [
            "# StateWeaver Agent 中文运行报告",
            "",
            f"> 生成时间：{generated_at}  ",
            f"> 会话编号：{self.cid}  ",
            f"> 决策模式：{analysis['decision_mode']}；{analysis['llm']['reason']}  ",
            f"> 分析耗时：{analysis['analysis_elapsed_sec']} 秒；LLM 耗时：{analysis['llm']['elapsed_sec']} 秒",
            "",
            "## 0. 本次实际输入文件",
            *[f"- {path}" for path in input_files],
            "",
            "## 1. 执行摘要",
            f"- 本次共读取 {len(docs)} 个文档文件、分析 {len(tables)} 个表格文件，并生成带证据来源的 Markdown 与 JSON 输出。",
            f"- 预算总额为 {self._fmt_num(budget['total'])}，工时总量为 {self._fmt_num(staffing['total'])}，综合风险等级评估为 **{risk_level}**。",
            f"- 工具调用统计显示：共 {self._fmt_num(tools['total_calls'])} 次历史/输入工具调用记录，整体成功率 {tools['overall_success_rate']}%。",
            "- 如果决策模式为 `rule_fallback`，说明当前环境没有配置可用本地 LLM，系统使用可复现规则分析器完成诊断；这不是伪装成大模型输出。",
            "",
            "## 2. 需求与约束归纳",
        ]
        md.extend(self._fact_lines(analysis["doc_facts"]["requirements"], "未在文档中抽取到明确需求句。"))
        md.extend(["", "### 用户偏好与演示要求"])
        md.extend(self._fact_lines(analysis["doc_facts"]["preferences"], "未在文档中抽取到明确偏好。"))
        md.extend(["", "### 文档摘要"])
        if doc_summaries:
            for path, item in doc_summaries.items():
                md.append(f"- **{path}**：{item['preview']}（约 {item['chars']} 字符）")
        else:
            md.append("- 未读取到 Markdown 或文本类文档。")

        md.extend(
            [
                "",
                "## 3. 预算结构诊断",
                f"- 预算总额：{self._fmt_num(budget['total'])}",
                f"- 成本记录数：{budget['rows']}",
                f"- 成本分类：{self._format_mapping(budget['by_category'])}",
                f"- 成本归属：{self._format_mapping(budget['by_owner'])}",
                f"- 实施阶段成本：{self._format_mapping(budget['by_stage'])}",
                "### 最高成本项",
            ]
        )
        if budget["top_items"]:
            for row in budget["top_items"]:
                md.append(
                    f"- {row.get('item', 'unknown')}：{self._fmt_num(self._num(row.get('cost')))} "
                    f"({row.get('category', 'unknown')}，来源 {row.get('_path')})"
                )
        else:
            md.append("- 没有检测到 `cost` 字段，无法形成预算诊断。")

        md.extend(
            [
                "",
                "## 4. 人员与进度诊断",
                f"- 总工时：{self._fmt_num(staffing['total'])}",
                f"- 人员负载：{self._format_mapping(staffing['by_name'])}",
                f"- 角色分布：{self._format_mapping(staffing['by_role'])}",
                f"- 平均完成度：{progress['average_completion']}%",
            ]
        )
        if staffing["overloaded"]:
            md.append("- 高负载人员：" + "；".join(f"{x['name']} {self._fmt_num(x['hours'])}h" for x in staffing["overloaded"]))
        if progress["lowest"]:
            md.append("### 完成度最低的模块")
            for row in progress["lowest"]:
                md.append(
                    f"- {row.get('module', 'unknown')}：{row.get('completion_percent')}%，"
                    f"负责人 {row.get('owner', 'unknown')}，下一步 {row.get('next_action', '未填写')}"
                )
        if progress["blocked"]:
            md.append("### 阻塞项")
            for row in progress["blocked"]:
                md.append(f"- {row.get('module', 'unknown')} 被 `{row.get('blocked_by')}` 阻塞，应优先处理。")

        md.extend(
            [
                "",
                "## 5. 工具可靠性与事故诊断",
                f"- 工具总体成功率：{tools['overall_success_rate']}%",
                f"- 事故等级分布：{self._format_mapping(incidents['severity'])}",
                f"- 事故状态分布：{self._format_mapping(incidents['status'])}",
            ]
        )
        if tools["items"]:
            md.append("### 工具表现")
            for row in tools["items"][:6]:
                md.append(
                    f"- `{row['tool']}`：调用 {self._fmt_num(row['calls'])} 次，"
                    f"成功率 {row['success_rate']}%，平均延迟 {self._fmt_num(row['avg_latency_ms'])} ms，用途：{row['main_use']}"
                )
        if incidents["open_items"]:
            md.append("### 未关闭事件")
            for row in incidents["open_items"]:
                md.append(f"- {row.get('issue_id')}：{row.get('module')} / {row.get('severity')} / {row.get('action')}")

        md.extend(
            [
                "",
                "## 6. 数据质量与重复上传检查",
            ]
        )
        if duplicate_uploads:
            md.append("- 检测到以下文件存在重复上传版本，可能导致重复统计：")
            for name, paths in duplicate_uploads.items():
                md.append(f"  - {name}: {', '.join(paths)}")
        else:
            md.append("- 未发现明显重复上传文件。")
        md.append("- 建议正式演示前只保留需要分析的一份数据，避免预算、工时和工具调用记录被重复累计。")

        md.extend(["", "## 7. 可执行建议"])
        for item in analysis["recommendations"]["action_items"]:
            md.append(f"- {item}")
        if analysis["recommendations"].get("llm_insights"):
            md.extend(["", "### LLM 补充洞察"])
            for item in analysis["recommendations"]["llm_insights"]:
                if item.strip():
                    md.append(f"- {item.strip('- ')}")

        md.extend(["", "## 8. 证据来源"])
        for key, vals in evidence.items():
            md.append(f"### {key}")
            if vals:
                for val in vals:
                    md.append(f"- {val}")
            else:
                md.append("- 未检索到匹配证据。")

        md.extend(["", "## 9. 召回记忆"])
        if memory:
            md.extend(f"- {m.get('kind')}: {m.get('content')}" for m in memory)
        else:
            md.append("- 本次未召回相关记忆。")

        summary = {
            "conversation_id": self.cid,
            "generated_at": generated_at,
            "decision_mode": analysis["decision_mode"],
            "llm": analysis["llm"],
            "input_files": input_files,
            "doc_count": len(docs),
            "table_count": len(tables),
            "doc_summaries": doc_summaries,
            "total_budget_cost": budget["total"],
            "total_staff_hours": staffing["total"],
            "risk_level": risk_level,
            "evidence_counts": {k: len(v) for k, v in evidence.items()},
            "table_stats": table_stats,
            "diagnosis": diagnosis,
            "recommendations": analysis["recommendations"],
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

    def _fact_lines(self, facts: list[dict[str, Any]], empty_text: str) -> list[str]:
        if not facts:
            return [f"- {empty_text}"]
        return [f"- {item['path']}:{item['line']} {item['text']}" for item in facts[:8]]

    def _format_mapping(self, mapping: dict[str, Any]) -> str:
        if not mapping:
            return "无"
        return "；".join(f"{key}={self._fmt_num(value)}" for key, value in mapping.items())

    def _risk_level(self, budget: dict, progress: dict, incidents: dict, duplicate_uploads: dict) -> str:
        score = 0
        if budget["total"] >= 12000:
            score += 2
        elif budget["total"] >= 6000:
            score += 1
        if progress["blocked"]:
            score += 1
        if incidents["open_items"]:
            score += 1
        if duplicate_uploads:
            score += 1
        if score >= 4:
            return "较高"
        if score >= 2:
            return "中等"
        return "较低"

    def _num(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _fmt_num(self, value: Any) -> str:
        num = self._num(value)
        return str(int(num)) if num.is_integer() else str(round(num, 2))
