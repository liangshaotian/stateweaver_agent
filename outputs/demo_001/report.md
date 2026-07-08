# StateWeaver Agent 中文运行报告

## 1. 项目需求概述
本项目需要构建一个可本地运行、可复现、可追踪的文档与数据分析 Agent。系统需要读取本地需求文档、会议记录和数据表格，并生成带证据来源的结构化输出。

## 2. 预算统计结果
- 预算总额：4800.0
- 预算表记录数：5
- 统计方式：由表格分析工具读取 data/budget.csv，并对 cost 字段求和。

## 3. 人员工时统计
- 计划总工时：122.0
- 人员表记录数：4
- 统计方式：由表格分析工具读取 data/staff.tsv，并对 hours 字段求和。

## 4. 关键风险与建议
- 综合风险等级：中等
- 本地小模型的工具调用格式可能不稳定，需要保留规则降级和解析重试机制。
- GPU 或模型服务可能临时不可用，因此系统需要支持离线规则 Planner。
- 文件路径、表头或数据格式可能不一致，需要通过路径检查和表格字段校验降低失败概率。

## 5. 证据来源
### requirements
- docs/bid_requirements.md:3 The project requires a local document and data analysis assistant. The system must read local files, summarize requirements, analyze budget tables, and generate traceable reports.
- docs/bid_requirements.md:13 - The workflow should run locally.
- docs/bid_requirements.md:5 Mandatory deliverables:
### budget
- docs/bid_requirements.md:8 - A JSON summary containing total budget, expected cost and risk level.
- data/budget.csv:1 item,category,cost
- docs/bid_requirements.md:3 The project requires a local document and data analysis assistant. The system must read local files, summarize requirements, analyze budget tables, and generate traceable reports.
### risks
- data/budget.csv:3 gpu_hours,compute,1800
- docs/bid_requirements.md:7 - A Markdown report with project requirements, budget summary, risks and staffing suggestions.
- docs/meeting_notes.md:13 Risks:
### staffing
- docs/meeting_notes.md:3 The group decided to implement five modules: runtime orchestration, skill functions, tool schema and router, local model decision, and memory management.
- data/staff.tsv:2 Liang Shaotian	leader-runtime-integration	42
- data/staff.tsv:5 Wang Xuanhao	memory-storage-retrieval	26

## 6. 召回记忆
- procedural: For CSV analysis tasks, inspect headers first, then compute totals and averages, then validate JSON fields.
- preference: User prefers concise Markdown reports with a table first and bullet-point risks.
- episodic: Completed local document and table analysis with traceable outputs.
- episodic: Completed local document and table analysis with traceable outputs.
- episodic: Completed local document and table analysis with traceable outputs.
