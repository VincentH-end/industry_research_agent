# 行业洞察 Multi-Agent

方法知识先行、行业事实后置的多 Agent 行业研究应用。它提供 FastAPI REST/SSE 接口与有独立 URL、固定导航的报告子页。

## 核心流程

```text
用户指定行业/地区/周期
  → KnowledgeAcquisitionAgent：获取行业研究方法知识（M- 来源）
  → TaskPlanningAgent：按方法原则设计任务、证据要求和依赖
  → SourceCollector：按锚定网站获取具体行业事实（S- 来源）
  → 四个 AnalysisSubAgent 并行：发展阶段、市场竞争、商业模式、驱动风险
  → MainAgent 汇总结论；ChartSubAgent 根据分析后的指标制图
  → ReportEvaluator 评测；REST/SSE 返回；多子页呈现
```

这里的“蒸馏”指把专业资料中的分析原则提炼成 Agent 的任务设计知识，不是对具体行业网页做摘要，也不是训练小模型。方法知识指导“要问什么、按什么顺序问、需要什么证据”，不能替代具体行业的数据或事实引用。

## 方法知识获取

默认目录使用四类已核对的原始来源：

- `M1`：[Michael E. Porter, *The Five Competitive Forces That Shape Strategy*](https://hbr.org/2008/01/the-five-competitive-forces-that-shape-strategy)：竞争结构分析；该文章可能需要访问权限，目录仅保留我们自己写的用途摘要，不复制正文。
- `M2`：[OECD/Eurostat, *Oslo Manual 2018*](https://www.oecd.org/en/publications/oslo-manual-2018_9789264304604-en.html)：创新、采用和扩散的指标设计。
- `M3`：[OECD Structural Analysis Database](https://www.oecd.org/en/data/datasets/structural-analysis-database.html)：行业分类、产出、增加值、劳动力和生产率口径。
- `M4`：[World Bank Enterprise Surveys](https://microdata.worldbank.org/collections/enterprise_surveys)：企业层面的竞争、融资、基础设施与经营表现问题。

演示模式使用目录及用途摘要，标记 `acquisition=catalog`。配置模型后，知识 Agent 会尝试抓取上述公开页面，再标记成功页面为 `retrieved`，并让模型据此生成 `MethodologyGuide`。同时配置 Tavily 时，它还会在受限的 OECD、世界银行和 HBR 域名中发现与所问行业相关的报告或研究方法页面，用其方法部分指导任务设计。可通过 `.env` 的 `METHODOLOGY_URLS` 增加公开方法资料完整 URL；可访问且抓取成功的页面会进入方法目录。请仅加入有权访问、允许抓取的资料，书籍或付费报告不能凭标题假装已读取全文。

具体行业材料始终另外采集为 `S-` 来源。模型输出的 `M-` 引用不得进入行业结论或指标，未验证的行业断言会被隐藏并降为低置信度；没有来源的非估算数字不会被制图。

## 安装与启动

要求 Python 3.10+：

```powershell
cd industry_research_agent
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python run.py
```

启动器默认使用 `127.0.0.1:8010`，端口占用时自动尝试后续端口，并打印实际访问地址。打开打印出的地址，接口文档在 `/docs`。Windows 默认关闭 Uvicorn 自动重载，以规避部分环境中的 `WinError 10013`。

演示模式无需密钥，但不产生可信的行业事实。实时分析需填写：

```dotenv
LLM_API_KEY=your-model-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
TAVILY_API_KEY=your-search-key
ANCHOR_DOMAINS=stats.gov.cn,worldbank.org,oecd.org
```

`TAVILY_API_KEY` 用于在锚定域名内发现行业页面。也可在首页直接输入具体页面 URL；只填域名且没有搜索服务时，不会盲目爬完整网站。若有模型但没有取得任何行业事实，仍会降级为演示报告。

## 页面与接口

首页 `/` 用于创建报告。报告有八个独立子页和固定侧边导航：

| URL 后缀 | 内容 |
|---|---|
| `/overview` | 核心判断、行业边界与栏目速览 |
| `/methodology` | 方法来源、原则、任务设计与依赖 |
| `/lifecycle` | 发展阶段与图表 |
| `/market` | 市场竞争与图表 |
| `/business_model` | 商业模式与图表 |
| `/drivers_risks` | 驱动风险与图表 |
| `/sources` | 具体行业来源和分析边界 |
| `/evaluation` | 质量门禁和改进建议 |

完整路径形式为 `/reports/{report_id}/{page}`。页面使用固定模板；方法 Agent 不负责网页栏目或导航设计。前端通过 `sessionStorage` 缓存当前标签页报告；启用 RAG 的报告还存入 SQLite，跨标签页或服务重启后仍可通过后端读取。生产环境如启用 API Key，前端当前会在同一浏览器标签页的 `sessionStorage` 保存密钥以支持子页切换；高安全部署应改为服务端会话或 HttpOnly Cookie。

API：

- `POST /api/reports`：一次性生成结构化报告。
- `POST /api/reports/stream`：`text/event-stream`；包含 `knowledge.acquired`、`plan.ready`、`sources.collected`、各 Agent 事件和最终 `report`。
- `GET /api/reports/{id}`：读取自己的报告，先查进程缓存再查持久化存档。
- `GET /api/reports/{id}/evaluation`：读取自动评测。
- `GET /api/health`：健康状态。

## 权限、安全与日志

开发环境未配置密钥时允许匿名调用。生产环境示例：

```dotenv
APP_ENV=prod
API_KEYS=writer-key:writer:reports:read|reports:write|evals:read,viewer-key:viewer:reports:read|evals:read
```

请求头为 `X-API-Key`；Scope 为 `reports:write`、`reports:read`、`evals:read`。采集器限制锚定域名、HTTP(S)、私网地址和每次重定向。每个响应返回 `X-Trace-ID`；Agent 名、耗时和状态写入轮转 JSON 日志 `logs/industry-agent.jsonl`。日志不记录 API Key 原文。

自动评测覆盖行业引用、栏目结构、SubAgent 产出、图表、不确定性以及任务的方法来源有效性。演示模式永远不通过事实质量门禁。

## 测试

```powershell
cd industry_research_agent
python -m pytest -q
```

仅测试该子项目；仓库中其他示例项目具有各自独立依赖。当前测试覆盖方法先行的 SSE 顺序、M/S 来源隔离、多子页路由、REST/SSE、权限、锚定域名、评测和启动端口。

## 用例级 Agent 评测

在原有 `ReportEvaluator` 之外，`app/benchmarks.py` 提供“数据集 → 实际执行 → 输出评分 → 轨迹评分 → 结果归档”的评测闭环，设计参考 [LangSmith final response/trajectory evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent)。它不依赖 LangSmith 账号或服务。

`app/eval_cases.json` 包含 5 个用例，每个用例提供用户问题、预期回复质量、栏目关键概念和是否必须有事实证据：低空经济、工业机器人、企业 SaaS、动力电池数据口径冲突、完全缺少证据。预期标准不是固定长文答案，避免只奖励措辞一致。

运行方式：

```powershell
# 无密钥，合成来源和模型适配器驱动实际工作流，测试编排/评分器
python evaluate.py --mode fixture

# 无密钥，测试无证据时的安全降级
python evaluate.py --mode demo --case missing_evidence

# 真实行业 Agent（需要模型密钥和可用搜索/行业来源，会产生费用）
python evaluate.py --mode live --case industrial_robot

# 额外使用 EvaluationAgent 做语义质量评测
python evaluate.py --mode live --case industrial_robot --judge
```

`fixture` 的通过率只能证明合成回归场景通过，不能用于宣称真实模型的行业分析正确率。`demo` 运行需要事实证据的用例会失败，这是预期行为。真实用例默认使用 `.env` 中的搜索服务/锚定域名；没有取得行业材料时，证据门禁会失败，而不会把演示输出评为行业分析合格。

输出评分占 70%，检查栏目、方法关联、关键概念、引用合法性、指标来源、证据缺失处理、局限和延迟预算；轨迹评分占 30%，检查真实 Agent span 的成功状态、方法→计划→来源→分析→图表→汇总依赖，以及四个分析 span 是否实际重叠。演示模式不要求并行。引用造假、缺失必要证据或顺序违规不能被其他高分抵消。

可选 EvaluationAgent 检查相关性、事实支持、推理与不确定性，并给出说明；它不能覆盖确定性门禁，评分不达标也会让用例失败。当前关键概念检查属于关键词基线，引用 ID 合法也不代表内容被原文蕴含；严格事实一致性仍需评测 Agent、金标资料与人工复核。

结果保存在 `eval_results/{run_id}.json`，包含每个问题、预期质量、完整实际报告、分项失败、延迟和实际 span/LLM 追踪。每个 span 与服务 JSON 日志共享 `trace_id`、`span_id`、耗时和状态，可关联核查。评测环境隔离记忆，不污染用户研究会话。

新增接口：

- `GET /api/evaluations/cases`（`evals:read`）：读取问题集与预期标准。
- `POST /api/evaluations/run`（`evals:write`）：请求例如 `{"mode":"fixture","case_ids":["low_altitude"],"judge":false,"timeout_seconds":120}`。
- `GET /api/reports/{id}/trace`（`evals:read`）：读取自己的报告追踪，支持持久化存档恢复。

## 短期上下文与长期记忆

`app/context.py` 参考 [LangGraph 的短期/长期记忆区分](https://docs.langchain.com/oss/python/concepts/memory)和 [Anthropic 的上下文压缩、结构化笔记实践](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)，是独立的轻量上下文管理器，并非声称实现了某个统一强制标准。

- **短期记忆**：按调用主体和 `session_id` 存储请求、方法原则、计划、来源索引及最后报告的结构化工作笔记。按阶段覆盖旧笔记、按字符预算淘汰旧笔记，以 SQLite checkpoint 支持跨请求恢复。同一个会话 ID 继续研究时自动恢复。
- **长期记忆**：SQLite 持久化，支持 semantic、episodic、procedural、preference 四类。自动保留方法流程，以及实时报告的历史研究摘要；演示报告不写入长期行业结论。相同内容去重刷新有效期。
- **检索**：按主体、行业 topic 与最近更新时间选取；通用方法和偏好允许跨行业使用。当前不是向量语义检索。
- **安全边界**：长期笔记始终被标为历史/非当前证据，不能成为 S- 引用，注入内容被当作非可信数据。过期笔记不读取；默认 30 天 TTL，写入时清理过期项，每主体最多保留 100 条记忆/检查点。
- **预算**：`CONTEXT_MAX_CHARS` 默认 6000，仅控制注入笔记；`PROMPT_MAX_CHARS` 默认 50000，超大当前任务提示会报错而非静默截掉证据。字符预算不是精确 Token 计数，JSON Schema 与系统提示另计。

报告请求新增 `question`、`session_id`、`use_memory`；报告返回实际 `session_id` 和 `trace_id`。首页高级选项可输入问题、继续会话或关闭持久化记忆。开发匿名调用共享 `anonymous-dev` 主体；生产需不同 API Key/主体隔离，报告读取也限制为报告创建主体，Scope 不等于跨用户共享权限。

```json
{"industry":"工业机器人","question":"重点研究集成商收入模式","session_id":"robot-study-01","use_memory":true}
```

记忆管理接口：

- `GET /api/memory`（`memory:read`）：读取自己的最近长期笔记。
- `POST /api/memory`（`memory:write`）：写入自己的笔记，例如 `{"kind":"preference","topic":"global","content":"偏好中文、强调证据不足","ttl_days":30}`。
- `DELETE /api/memory/{id}`（`memory:write`）：删除自己的长期笔记。
- `GET /api/context/{session_id}`（`memory:read`）：读取自己的短期检查点。
- `DELETE /api/context/{session_id}`（`memory:write`）：清除自己的会话检查点。

`.env` 可配置 `MEMORY_DB`、`MEMORY_TTL_DAYS`、`CONTEXT_MAX_CHARS`、`PROMPT_MAX_CHARS`、`EVAL_ARTIFACT_DIR`。现有生产 API Key 需显式补充新 Scope，如 `evals:write|memory:read|memory:write`。SQLite 默认未加密，敏感部署应限制目录权限、加密备份并接入合适的密钥管理。同一会话的并发写入目前采用最后检查点覆盖，不提供多分支事务合并；建议每个并发研究使用独立 session。

## 生产化边界（补充）

- 已增加 SQLite 报告存档，多个本机 Worker 可读取同一存档；多机高并发部署应迁移到 PostgreSQL/向量库等共享服务。
- 对 PDF、动态页面与需要授权的文献增加合规解析器；不可绕过付费墙。
- 对模型结构化输出增加重试、超时和成本监控。
- 用真实金标案例、来源质量判断和人工抽检补足目前的确定性评测。
- 当前方法目录是可审计的起点，不代表四份资料适用于每个行业；任务计划应披露不适用部分。

## 行业报告 RAG 与直接复用

`app/rag.py` 实现报告存档、分栏切片、检索增强和完整报告缓存。它与记忆模块不同：记忆保存短工作笔记/偏好，而 RAG 保留完整报告、图表、来源和执行追踪，并提供可引用的历史资料片段。

```text
新请求
  → 按主体和研究范围查报告存档
      ├─ 完整匹配且未过期 → 直接返回已有报告，不调用模型
      └─ 未匹配/强制刷新 → 检索相关行业片段
          → 方法获取和任务设计 → 当前行业网页采集
          → 将 S- 当前资料与 R- 历史片段传给专业 Agent
          → 分析、制图、汇总 → 报告和可引用片段存入 SQLite
```

完整匹配使用规范化行业、地区、周期、具体问题和锚定来源的指纹；会话 ID 不影响匹配。例如相同“芯片”研究重复提交会返回已有报告；“芯片行业”的规范化名称也可匹配。不同地区、不同问题或不同来源不会误返回旧问题答案。`generated_at` 和 `report_id` 保持原值，响应增加 `reused=true`；当前请求拥有新 `trace_id`，`origin_trace_id` 保留原始报告的 Trace ID。SSE 会发送 `report.reused` 后正常输出 `report`/`done`。

相关检索采用中文双字词片段、英文词匹配以及显式行业关系加权，不需要 Embedding 密钥，**不是向量语义检索**。关系表包括计算机↔芯片/半导体、动力电池↔新能源汽车/储能、工业机器人↔制造业/自动化等，可在 `RELATIONS` 中扩展。检索按主体、地区、报告新鲜度过滤，并限制每份报告最多两个片段，避免上下文被单份报告占满。

例如先完成芯片真实行业研究，再研究计算机，芯片报告中有可追溯引用的结论会进入计算机 Agent 的参考上下文。`related_reports` 返回 R- 片段 ID、报告 ID、行业、日期、原始网页 URL 和匹配分数，前端证据子页提供跳转。

安全/质量规则：

- 完整报告默认保存到 `data/reports.sqlite3`，报告归属于创建主体，其他主体无权复用或检索。
- 演示报告可存档，并在未配置模型时复用为演示报告；不进入真实行业 RAG 参考索引。合成 fixture 评测不入库。
- 仅有可回溯引用的真实报告结论进入片段索引；未验证断言不索引。引用 ID 有效仍不保证原文支持结论，重要事实需人工复核。
- R- 历史片段只能作为带日期的背景/推断，不能冒充当前 S- 网页事实；仅依赖 R- 的结论降为低置信度，R- 不能直接支持数值指标。
- 未获取新网页但有历史参考时，可以运行历史资料驱动的分析，报告会明确披露缺乏新证据。原始网页及报告时效仍需核查。
- 默认 30 天内的报告才自动复用/检索；过期报告仍可按 ID 手动读取。已引用的历史报告日期也参与新鲜度检查，避免通过衍生报告绕过时效。
- 评测强制关闭 RAG 复用，避免测试只读缓存、不测实际 Agent。

请求控制：

```json
{"industry":"计算机","use_rag":true,"force_refresh":false}
```

`use_rag=false` 同时关闭本次缓存复用、相关检索和报告入库；`force_refresh=true` 只跳过完整报告缓存，仍允许使用历史片段辅助重新分析。首页高级设置提供相应勾选项。

配置：`RAG_DB`、`RAG_MAX_AGE_DAYS`、`RAG_TOP_K`。接口：

- `GET /api/rag/reports`（`reports:read`）：自己的存档报告列表。
- `POST /api/rag/search`（`reports:read`）：传入行业请求，查看相关参考片段。
- 原 `GET /api/reports/{id}`、`/evaluation`、`/trace` 支持从 SQLite 恢复。

升级前仅在旧进程或浏览器中存在、未被存档的完整报告不能凭长期记忆摘要重建。新版本运行后生成的报告会自动持久化；历史未存档报告需重新分析。RAG 数据目录默认忽略 Git，备份与访问权限需要自行管理。
