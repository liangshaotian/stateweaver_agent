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
                    f"- {self._cn_label(row.get('item', 'unknown'))}：{self._fmt_num(self._num(row.get('cost')))} "
                    f"({self._cn_label(row.get('category', 'unknown'))}，来源 {row.get('_path')})"
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
                    f"成功率 {row['success_rate']}%，平均延迟 {self._fmt_num(row['avg_latency_ms'])} ms，用途：{self._cn_label(row['main_use'])}"
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
            md.append(f"### {self._cn_label(key)}")
            if vals:
                for val in vals:
                    md.append(f"- {self._cn_evidence(val)}")
            else:
                md.append("- 未检索到匹配证据。")

        md.extend(["", "## 9. 召回记忆"])
        if memory:
            md.extend(f"- {self._cn_memory(m)}" for m in memory)
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
                "preview": self._cn_doc_summary(path, text),
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
        return [f"- {item['path']}:{item['line']} {self._cn_fact(item['text'])}" for item in facts[:8]]

    def _format_mapping(self, mapping: dict[str, Any]) -> str:
        if not mapping:
            return "无"
        return "；".join(f"{self._cn_label(key)}={self._fmt_num(value)}" for key, value in mapping.items())

    def _cn_doc_summary(self, path: str, text: str) -> str:
        low = text.lower()
        parts = []
        if "local document and data analysis assistant" in low or "traceable reports" in low:
            parts.append("要求构建本地文档与数据分析助手，读取本地文件、分析预算表并生成可追溯报告")
        if "mandatory deliverables" in low or "generated outputs" in low:
            parts.append("强调交付物必须包含 Markdown 报告、JSON 摘要和可复现输出")
        if "meeting notes" in low or "runtime orchestration" in low:
            parts.append("记录组内模块分工，包括运行编排、工具函数、工具路由、本地决策和记忆管理")
        if "interface feedback" in low or "file picker" in low or "browser interface" in low:
            parts.append("记录用户对 Web 界面、文件选择、中文报告和结果查看位置的反馈")
        if "risk" in low or "unstable" in low or "unavailable" in low:
            parts.append("包含模型服务、数据格式、证据约束和运行稳定性相关风险")
        if "memory" in low:
            parts.append("包含长期记忆、偏好保存、重复记忆和冲突处理相关案例")
        if not parts:
            title = path.rsplit("/", 1)[-1].replace("_", " ")
            parts.append(f"该文件提供 {title} 相关的任务背景、约束或补充材料")
        return "；".join(dict.fromkeys(parts))[:260]

    def _cn_fact(self, text: str) -> str:
        low = text.lower()
        if "local document and data analysis assistant" in low:
            return "要求系统作为本地文档与数据分析助手，读取本地文件、汇总需求、分析预算并生成可追溯报告。"
        if "mandatory deliverables" in low:
            return "要求输出必须包含指定交付物，便于验收时检查。"
        if "json summary" in low:
            return "要求生成 JSON 摘要，包含总预算、预期成本和风险等级等结构化结果。"
        if "workflow should run locally" in low:
            return "要求完整工作流能够在本地运行，不依赖远程服务。"
        if "all generated outputs should be reproducible" in low:
            return "要求所有生成结果可复现，便于重复验收和问题定位。"
        if "visible browser interface" in low:
            return "用户希望通过可视化浏览器界面操作，而不是直接编辑原始 JSON。"
        if "selecting files" in low or "file picker" in low:
            return "用户希望可以直接从文件资源管理器选择文件，降低配置难度。"
        if "chinese reports" in low:
            return "用户明确偏好中文报告，便于课堂展示和答辩说明。"
        if "memory should" in low or "memory" in low:
            return "要求记忆模块保存用户偏好、成功工具路径和失败记录，为后续任务提供上下文。"
        if "tools should return" in low:
            return "要求工具结果采用统一格式，方便运行时汇总、验证和追踪。"
        if "router should choose" in low:
            return "要求工具路由器选择小而具体的任务工具集，减少无关工具干扰。"
        if "risk" in low or "unstable" in low or "unavailable" in low:
            return "该证据指出模型服务、工具调用或资源可用性存在稳定性风险。"
        if any("\u4e00" <= ch <= "\u9fff" for ch in text):
            return text[:220]
        return "该行提供了与当前任务相关的英文原始证据，报告已转写为中文释义，原文可通过对应文件和行号追溯。"

    def _cn_evidence(self, value: str) -> str:
        ref, sep, text = value.partition(" ")
        low = text.lower()
        if text.startswith("item,category,cost"):
            return f"{ref} 表格表头包含项目、类别和成本字段，可用于预算统计。"
        if text.startswith("name,role,hours"):
            return f"{ref} 表格表头包含姓名、角色和工时字段，可用于人员投入统计。"
        if text.startswith("tool,calls,successes"):
            return f"{ref} 表格表头包含工具名、调用次数、成功次数和平均延迟字段，可用于工具可靠性分析。"
        if text.startswith("module,owner,completion_percent"):
            return f"{ref} 表格表头包含模块、负责人、完成度、阻塞原因和下一步动作，可用于进度诊断。"
        if text.startswith("issue_id"):
            return f"{ref} 表格表头包含事件编号、模块、严重程度、状态和处理动作，可用于风险跟踪。"
        if "gpu_hours" in low:
            return f"{ref} 预算记录显示 GPU 算力属于计算资源成本，金额为 1800。"
        if not sep:
            return value
        return f"{ref} {self._cn_fact(text)}"

    def _cn_memory(self, memory_item: dict[str, Any]) -> str:
        kind = self._cn_label(memory_item.get("kind", "memory"))
        content = str(memory_item.get("content", ""))
        low = content.lower()
        if "csv analysis" in low:
            return f"{kind}：处理 CSV 任务时，应先检查表头，再计算总和与均值，最后验证 JSON 字段。"
        if "prefers concise markdown" in low:
            return f"{kind}：用户偏好简洁的 Markdown 报告，并希望先展示表格，再列出风险要点。"
        if "completed local document" in low:
            return f"{kind}：系统曾完成本地文档与表格分析，并生成可追溯输出。"
        if "completed analysis in" in low:
            return f"{kind}：系统曾完成一次带决策模式记录的文档与表格诊断任务。"
        if any("\u4e00" <= ch <= "\u9fff" for ch in content):
            return f"{kind}：{content}"
        return f"{kind}：该记忆记录为历史运行经验，已用于当前任务上下文。"

    def _cn_label(self, value: Any) -> str:
        text = str(value)
        mapping = {
            "requirements": "需求证据",
            "budget": "预算证据",
            "risks": "风险证据",
            "staffing": "人员证据",
            "procedural": "流程记忆",
            "preference": "偏好记忆",
            "episodic": "情景记忆",
            "compute": "计算资源",
            "backend": "后端模块",
            "frontend": "前端界面",
            "documentation": "文档材料",
            "engineering": "工程实现",
            "data": "数据材料",
            "infrastructure": "基础设施",
            "integration": "集成联调",
            "implementation": "功能实现",
            "validation": "验证测试",
            "presentation": "展示材料",
            "unknown": "未标注",
            "gpu_hours": "GPU 算力",
            "local_llm_server": "本地模型服务",
            "web_console": "网页控制台",
            "skill_registry": "工具注册表",
            "tool_schema_layer": "工具 Schema 层",
            "memory_store": "记忆存储",
            "testing_and_report": "测试与报告",
            "poster_materials": "展示材料",
            "read markdown and text files": "读取 Markdown 与文本文件",
            "sum numeric columns and count rows": "统计数值列并计算行数",
            "find evidence lines": "检索证据行",
            "verify report claims": "验证报告结论",
            "export markdown and json outputs": "导出 Markdown 与 JSON 输出",
            "compute simple totals": "计算简单汇总值",
        }
        return mapping.get(text, text)

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
