# StateWeaver Agent

StateWeaver 是一个面向自然语言处理实训项目的本地工具调用型 Agent 系统。项目以“状态驱动”为核心思想，将任务配置、计划生成、动态工具调用、结果验证、运行轨迹、断点状态和长期记忆组织成一条可追踪的执行链路。

本仓库对应东北大学人工智能 2023 级自然语言处理实训第 16 组项目代码，选题方向为 B 方向 Agent 系统实践。

## 项目概述

普通 LLM Agent 往往依赖隐式消息历史推进任务，容易出现重复调用、提前结束、工具参数错误、运行过程不可追踪等问题。StateWeaver 将 Agent 运行过程拆成明确的状态阶段，并把每一步工具调用、验证结果和记忆写回保存为结构化文件，使系统不仅能“生成结果”，也能解释结果是如何产生的。

默认示例任务会读取本地需求文档、会议记录、预算表和人员工时表，自动完成：

- 本地 Markdown 文档读取与摘要
- CSV / TSV 表格统计分析
- 需求、预算、风险和人员安排证据检索
- Markdown 报告生成
- JSON 摘要生成
- Trace 执行轨迹记录
- Checkpoint 状态快照保存
- Memory 长期记忆检索与写回
- Web 控制台交互式运行与结果查看

默认运行结果会生成：

- 预算统计结果：`4800.0`
- 人员工时统计结果：`122.0`
- 风险等级：`中等`
- 输出报告：`outputs/demo_001/report.md`
- 结构化摘要：`outputs/demo_001/summary.json`
- 执行轨迹：`traces/demo_001.jsonl`
- 运行快照：`checkpoints/demo_001.json`
- 记忆文件：`configs/memory.json`

## 核心特性

### 1. 状态驱动 Runtime

系统使用显式状态阶段组织完整任务生命周期：

```text
INIT -> RETRIEVE_MEMORY -> PLAN -> TOOL_CALL
     -> WRITE_OUTPUTS -> VERIFY -> SAVE_MEMORY -> DONE
```

每个阶段都会写入 Trace，并同步保存 Checkpoint，便于检查运行过程、定位失败位置和复现实验结果。

### 2. 可组合 Skill 工具系统

所有工具都通过统一的 `SkillSpec` 和 `SkillResult` 封装。工具函数不直接暴露给 Runtime，而是先注册到 Skill Registry，再由 B3 工具层动态编译和调用。

已实现的工具包括：

- `calculator`：安全计算器
- `file_reader`：本地文件读取
- `local_file_search`：本地文本证据搜索
- `table_analyzer`：CSV / TSV 表格统计
- `format_converter`：Markdown 与 JSON 输出生成
- `evidence_checker`：报告证据覆盖检查

### 3. 动态 Tool Schema 与执行桥接

B3 工具层根据任务文本和当前阶段动态选择工具，避免一次性向模型或决策层注入全部工具。工具调用前会校验函数签名，调用后会记录工具名、参数、状态、结果和耗时。

### 4. 本地决策、分析与规则降级

B4 决策模块包含 Planner、Analyst 和 Verifier。默认情况下，系统使用可复现的本地规则 Planner + Analyst 生成计划和诊断报告；如果配置了 OpenAI-compatible 本地模型服务，则 Analyst 会调用本地 LLM 生成补充洞察。报告中的 `decision_mode` 会明确标注当前是 `llm` 还是 `rule_fallback`，避免把规则降级结果误认为真实大模型输出。

### 5. 可信长期记忆

B5 Memory 使用本地 JSON 文件保存情景记忆。每条记忆包含内容、标签、置信度、来源 Trace 和创建时间。任务开始前检索相关记忆，任务完成后写回新的经验记录。

### 6. Web 控制台

项目提供一个无需前端构建步骤的 Web Console。启动后可以在浏览器中查看任务配置、运行 Agent、查看报告、摘要、Trace、Checkpoint 和 Memory。

## 目录结构

```text
stateweaver_agent_20236533/
├── b1_runtime/              # B1 状态驱动 Runtime
│   └── runtime.py
├── b2_skills/               # B2 Skill 工具函数模块
│   ├── calculator.py
│   ├── file_reader.py
│   ├── local_file_search.py
│   ├── table_analyzer.py
│   ├── format_converter.py
│   ├── evidence_checker.py
│   ├── registry.py
│   └── skill_spec.py
├── b3_tools/                # B3 Tool Schema 与工具执行层
│   ├── schema_compiler.py
│   ├── tool_router.py
│   └── executor.py
├── b4_decision/             # B4 Planner / Analyst / Verifier 决策模块
│   ├── analyst.py
│   ├── planner.py
│   └── verifier.py
├── b5_memory/               # B5 长期记忆模块
│   └── memory_store.py
├── configs/                 # 任务配置、工具配置、记忆文件
├── data/                    # 示例 CSV / TSV 数据
├── docs/                    # 示例需求文档和会议记录
├── outputs/                 # 运行后生成的报告与摘要
├── traces/                  # JSONL 执行轨迹
├── checkpoints/             # 运行状态快照
├── tests/                   # 冒烟测试
├── scripts/                 # benchmark 脚本
├── web/                     # Web Console 前端页面
├── main.py                  # 命令行入口
├── web_server.py            # Web 服务入口
└── README.md
```

## 环境要求

推荐环境：

- Python 3.10+
- Windows / Linux 均可运行
- 默认版本不依赖 GPU
- 默认版本不强制依赖外部大模型服务

当前实现主要使用 Python 标准库，默认 Demo 不需要额外安装复杂依赖。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/liangshaotian/stateweaver_agent.git
cd stateweaver_agent
```

### 2. 命令行运行默认 Agent

```bash
python main.py --config configs/runtime_input.json
```

运行成功后终端会输出类似信息：

```text
StateWeaver run finished
conversation_id=demo_001
status=success
report=outputs/demo_001/report.md
summary=outputs/demo_001/summary.json
trace=traces/demo_001.jsonl
```

### 3. 查看输出结果

```bash
cat outputs/demo_001/report.md
cat outputs/demo_001/summary.json
cat traces/demo_001.jsonl
```

Windows CMD 或 PowerShell 可以使用：

```powershell
Get-Content outputs/demo_001/report.md
Get-Content outputs/demo_001/summary.json
Get-Content traces/demo_001.jsonl
```

### 4. 启动 Web 控制台

```bash
python web_server.py
```

然后在浏览器打开：

```text
http://127.0.0.1:8066/
```

Web 控制台支持：

- 查看和编辑任务配置
- 从文件资源管理器选择文件并上传到 `uploads/`，自动加入读取白名单
- 一键运行 Agent
- 查看 Markdown 报告
- 查看 JSON Summary
- 查看 Trace 运行轨迹
- 查看 Checkpoint
- 查看 Memory 记忆状态

## 任务配置说明

默认任务配置位于：

```text
configs/runtime_input.json
```

核心字段示例：

```json
{
  "conversation_id": "demo_001",
  "user_input": "Read docs/bid_requirements.md, docs/meeting_notes.md, data/budget.csv and data/staff.tsv. Generate a Markdown report and a JSON summary.",
  "allowed_files": [
    "data/budget.csv",
    "data/staff.tsv",
    "docs/bid_requirements.md",
    "docs/meeting_notes.md"
  ],
  "output_requirements": {
    "formats": ["markdown", "json"],
    "markdown_path": "outputs/demo_001/report.md",
    "json_path": "outputs/demo_001/summary.json"
  }
}
```

修改 `user_input`、`allowed_files` 和 `output_requirements` 后，可以让 Agent 处理新的本地文档和表格任务。Web 控制台也支持直接选择本地文件，文件会被复制到项目内 `uploads/` 目录，并自动写入 `allowed_files`。

### 可选：接入真实本地 LLM

默认版本为了保证离线可运行，会使用 `rule_fallback` 决策模式。如果已经启动了 vLLM、Qwen 或其他 OpenAI-compatible 服务，可以通过环境变量启用真实 LLM 分析：

```powershell
$env:STATEWEAVER_LLM_URL="http://127.0.0.1:8016/v1"
$env:STATEWEAVER_LLM_MODEL="Qwen3-1.7B"
python web_server.py
```

启用后，报告中的决策模式会显示为 `llm`，并记录 LLM 调用耗时；如果模型服务不可用，系统会自动降级为 `rule_fallback` 并在报告里写明原因。

本仓库也提供了一个应急本地模型服务脚本，可直接用 Anaconda 中的 `torch + transformers` 启动小型 Qwen 模型：

```powershell
cd D:\1自然语言处理实训\stateweaver_agent_20236533
C:\Users\lenovo\anaconda3\python.exe local_llm_server.py --model Qwen/Qwen2.5-0.5B-Instruct --host 127.0.0.1 --port 8016
```

另开一个终端启动 Web Console：

```powershell
$env:STATEWEAVER_LLM_URL="http://127.0.0.1:8016/v1"
$env:STATEWEAVER_LLM_MODEL="Qwen/Qwen2.5-0.5B-Instruct"
$env:STATEWEAVER_LLM_TIMEOUT="120"
$env:STATEWEAVER_LLM_MAX_TOKENS="220"
C:\Users\lenovo\anaconda3\python.exe web_server.py
```

这一路线不依赖校园网和远程服务器。首次启动会从 HuggingFace 下载模型权重，之后会使用本机缓存。

## 输出文件说明

| 文件 | 作用 |
| :--- | :--- |
| `outputs/demo_001/report.md` | Agent 生成的 Markdown 中文运行报告 |
| `outputs/demo_001/summary.json` | 结构化摘要，包含预算、工时、风险、证据数量和表格统计 |
| `traces/demo_001.jsonl` | 逐行 JSON 运行轨迹，每一行对应一个状态事件 |
| `checkpoints/demo_001.json` | 当前 RuntimeState 快照，可用于检查中间状态 |
| `configs/memory.json` | 长期记忆记录，保存任务经验和来源 Trace |

## 测试与验证

运行冒烟测试：

```bash
python -m pytest tests/smoke_test.py
```

如果当前环境没有安装 `pytest`，也可以直接运行 benchmark 脚本：

```bash
python scripts/benchmark.py
```

期望输出中应包含：

```text
budget= 4800.0
hours= 122.0
risk= 中等
```

## Web API

启动 `web_server.py` 后，本地会提供基础 API。

普通 Web 控制台接口：

- `GET /api/status`：查看项目状态
- `GET /api/config`：读取任务配置
- `POST /api/config`：保存任务配置
- `POST /api/upload`：上传本地文件到 `uploads/` 并返回可读取的相对路径
- `POST /api/run`：运行 Agent
- `GET /api/file?path=...`：读取输出文件

面向外部工具或 GPT Actions 的接口：

- `GET /openapi.json`：获取 OpenAPI 描述
- `GET /api/agent/status`：获取 Agent 状态
- `POST /api/agent/run`：运行 Agent
- `GET /api/agent/read_file?path=...`：读取文件内容

外部工具接口需要 Bearer Token：

```text
Authorization: Bearer stateweaver-20236533
```

注意：当前 Token 仅用于课程 Demo。实际公网部署时应改为环境变量或更安全的认证方式。

## B1-B5 模块说明

### B1 状态驱动 Agent Runtime

位置：`b1_runtime/runtime.py`

负责：

- 读取任务配置
- 初始化运行状态
- 控制状态机流转
- 调用 B5 检索记忆
- 调用 B4 生成计划
- 调用 B3 执行工具
- 写入 Trace
- 保存 Checkpoint
- 触发验证和记忆写回

B1 是系统的唯一编排者，保证每一步都有明确状态和可追踪记录。

### B2 可组合 Skill 工具系统

位置：`b2_skills/`

负责：

- 定义 `SkillSpec`
- 定义 `SkillResult`
- 注册工具函数
- 提供真实本地执行能力

B2 不负责全局规划，只提供稳定、可复用、可封装的工具能力。

### B3 动态 Tool Schema 与执行层

位置：`b3_tools/`

负责：

- 根据任务动态筛选工具
- 将 Skill 编译为 Tool Schema
- 校验工具调用参数
- 执行具体工具函数
- 记录调用结果和耗时
- 将异常转换为结构化错误

B3 是模型意图到真实工具执行之间的桥接层。

### B4 本地决策模块

位置：`b4_decision/`

负责：

- 根据任务配置生成计划
- 定义执行步骤
- 对文档、表格、风险、人员、进度和工具可靠性进行诊断分析
- 可选调用 OpenAI-compatible 本地 LLM 生成补充洞察
- 验证输出文件是否存在
- 判断运行结果是否满足要求

当前默认实现为本地规则 Planner + Analyst，便于离线可复现运行。配置 `STATEWEAVER_LLM_URL` 后，Analyst 会尝试调用本地 LLM；调用失败时自动降级，并将失败原因写入 Summary 和报告。

### B5 可信长期记忆系统

位置：`b5_memory/memory_store.py`

负责：

- 读取本地记忆文件
- 根据查询文本召回相关记忆
- 基于关键词和置信度排序
- 在任务完成后写回情景记忆
- 保存来源 Trace 和创建时间

B5 让 Agent 具备跨任务复用经验的能力。

## 默认 Demo 数据

项目内置了一个可复现的本地分析任务：

| 类型 | 文件 |
| :--- | :--- |
| 需求文档 | `docs/bid_requirements.md` |
| 会议记录 | `docs/meeting_notes.md` |
| 预算表 | `data/budget.csv` |
| 人员工时表 | `data/staff.tsv` |

Agent 会读取这些文件，生成带证据来源的项目分析报告。

## 设计亮点

1. **显式状态机替代隐式消息推进**  
   每个运行阶段都有清晰名称和结构化记录，避免 Agent 过程不可见。

2. **工具能力标准化封装**  
   工具统一注册、统一参数说明、统一返回结果，便于扩展和调试。

3. **动态工具注入**  
   根据任务筛选工具，减少工具选择负担，提高本地小模型可用性。

4. **证据约束输出**  
   报告中的关键结论绑定到文档行、表格字段和统计结果，降低幻觉风险。

5. **Trace + Checkpoint 可追踪**  
   不只保留最终答案，也保留完整运行路径和中间状态。

6. **本地长期记忆**  
   通过 JSON 记忆库保存任务经验，为后续相似任务提供上下文。

7. **可交互 Web Console**  
   不需要复杂前端构建即可运行，方便演示、验收和调试。

## 常见问题

### 运行后没有看到新结果怎么办？

确认当前目录是项目根目录，并执行：

```bash
python main.py --config configs/runtime_input.json
```

然后查看：

```text
outputs/demo_001/
traces/demo_001.jsonl
checkpoints/demo_001.json
```

### Web 页面打不开怎么办？

先确认服务已经启动：

```bash
python web_server.py
```

终端应显示：

```text
StateWeaver web UI: http://127.0.0.1:8066
```

如果端口被占用，可以修改 `web_server.py` 中的 `PORT`。

### 可以接入真实本地大模型吗？

可以。B4 Analyst 已经预留 OpenAI-compatible 调用。设置 `STATEWEAVER_LLM_URL` 和 `STATEWEAVER_LLM_MODEL` 后重新启动 `web_server.py` 即可。如果没有设置这些变量，系统会显示 `rule_fallback`，运行会非常快，这是规则分析器在工作，不是大模型在思考。

### 是否需要 GPU？

默认版本不需要 GPU。只有接入真实本地大模型服务时，才可能需要 GPU。

## 团队分工

| 成员 | 学号 | 主要工作 |
| :--- | :--- | :--- |
| 梁少天 | 20236533 | 总体架构、B1-B5 核心实现、Verification、Recovery、Web Console 与集成 |
| 刘广阔 | 20236507 | B2 Skill 工具函数模块 |
| 杨金鑫 | 20216424 | B3 工具说明生成与工具调用模块 |
| 王渲淏 | 20236512 | B5 记忆文档存储与查找模块 |

## 版本说明

当前版本为课程项目最终展示版，重点保证：

- 默认 Demo 可直接运行
- 运行过程可追踪
- 输出结果可检查
- Web UI 可交互
- 代码结构清晰，便于答辩展示

## License

本项目用于课程实训与学习展示，未设置开源许可证。未经作者许可，不建议直接用于商业用途。
