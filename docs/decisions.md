# 决策日志（ADR）

按时间顺序记录所有架构 / 工程决策。每条 ADR 包含：背景、决策、备选、代价。

格式约定：
- **Status**: Accepted / Superseded by D-NNN
- **Date**: YYYY-MM-DD
- **Why** 段落写"做这个决定的硬约束/动机"
- **Trade-offs** 段落写"承认放弃了什么"

---

## D-001 · 项目目标与工期
**Status**: Accepted · **Date**: 2026-05-19

**Context**：17 天（5.20 – 6.5）打造业务场景级多 Agent 竞品分析系统，答辩演示形式提交。

**Decision**：
- 工期分 3 段：0.5 周架构（5.20-23）+ 1 周单体（5.24-30）+ 1 周联调（5.31-6.5）
- 业务场景级，非生产可用；评估标准含答辩演示效果与设计可解释性

**Trade-offs**：放弃完整生产级测试覆盖与多垂直支持。

---

## D-002 · Agent 角色划分定型为 5 角色
**Status**: Accepted · **Date**: 2026-05-20 (Meeting1)
**Supersedes**: 早期 6 角色草案

**Context**：业界经验显示 agent 数 > 4 后协调成本超过分工收益；但题目建议要 5 角色。

**Decision**：5 角色 = PM / Collector / Insight / Analyst / Report。其中 Insight 独立是差异化亮点。

**Alternatives**：
- 4 角色（Insight 并入 Collector）—— 砍掉差异化
- 6 角色（拆出 Industry Researcher）—— 协调成本太高

**Trade-offs**：5 角色 token / 复杂度处于可接受边缘，需要严格 prompt 管控防止职责漂移。

---

## D-003 · LLM 栈 = 3 模型家族
**Status**: Accepted · **Date**: 2026-05-20

**Context**：题目建议 GPT-5 + DeepSeek，但仅两家无法形成完整跨家族审。

**Decision**：
- GPT-5：PM + Report + Collector 多模态分支
- DeepSeek V4：Insight / Analyst / Collector 文本分支
- Doubao（火山方舟，多模态）：最终跨模型 QA

**Why**：self-preference bias 缓解的核心是"审者与被审异家族"。两家不够形成完整对抗 chain，三家覆盖关键 QA checkpoint。

**Trade-offs**：3 套 SDK + 3 套 API key + 3 套 base_url，工程复杂度上升；LangSmith trace 跨家族但仍统一可见。

---

## D-004 · 首发垂直 = 办公软件，config 化抽离支持扩展
**Status**: Accepted · **Date**: 2026-05-20

**Context**：题目要求互联网产品。聚焦能讲深，但要保留扩展能力。

**Decision**：
- 写死办公软件领域 prompt（飞书/钉钉/腾讯会议/Zoom）
- `config.yaml` 抽离垂直名、对比维度种子、URL 白名单
- 换垂直 = 改 config + 可选 domain_seed yaml，不改代码

**Alternatives**：完全通用框架 + RAG 喂领域知识（17 天做不深，每个垂直都浅）。

**Trade-offs**：领域 prompt 偏办公软件，跨垂直时报告语气可能需要微调。

---

## D-005 · 数据合规边界 + 一手数据做成 skill 不真采集
**Status**: Accepted · **Date**: 2026-05-20

**Context**：合规是答辩硬要求；真做问卷采集 17 天放不下。

**Decision**：
- 外部数据严格遵守 robots.txt + ToS，仅公开源 + 官方 API + RSS
- 一手数据封装为 `questionnaire` skill（LangGraph subgraph），demo 时用 LLM 合成 persona 模拟应答
- 主流程默认 `use_questionnaire_skill: false`

**Why 合成而非预置**：合成可坦白说"cold-start synthetic data"，预置数据假装真采集会被评委追问穿。

**Trade-offs**：v1 不真做问卷，question 设计 / 分发渠道仅占位。

---

## D-006 · 答辩 demo = 现场实时 + 必须有 cached 兜底
**Status**: Accepted · **Date**: 2026-05-20

**Context**：现场跑实时 demo 风险大（网络 / API 抖动 / 模型 404）。

**Decision**：
- 前端 Streamlit，必须支持 `--mode=live` 和 `--mode=cached` 两条路径
- LangGraph 启用 SQLite checkpointer，断点续跑
- 关键长步骤必须 streaming 输出

**Trade-offs**：需要双模式工程量，约多 1 天工作。

---

## D-007 · Skill 抽象 = LangGraph subgraph
**Status**: Accepted · **Date**: 2026-05-20

**Context**：v1 不深做 skill，但接口必须先定。

**Decision**：每个 skill 实现为独立 LangGraph subgraph，主图通过节点调用。

**Why**：与主图编排一致 + 可视化连贯（评委看到主图嵌套子图，体现架构层次）。

**Alternatives**：LangChain Tool（更轻量，但难以表现"内部多步流程"）/ Claude Code skill（runtime 绑定不适用）。

---

## D-008 · 报告输出 = Markdown + PDF（保留 PDF）
**Status**: Accepted · **Date**: 2026-05-20

**Context**：评审审报告需要 PDF 形态；纯 markdown 不够正式。

**Decision**：默认 markdown，同时输出 PDF。
- md → html：`markdown-it-py`
- html → pdf：`weasyprint`（Windows 装失败时 fallback `xhtml2pdf`）

**Trade-offs**：weasyprint 在 Windows 上偶尔装坑；预留 fallback 路径。

---

## D-009 · Memory 精简到 2 模块
**Status**: Accepted · **Date**: 2026-05-20

**Context**：原设计 4 个独立 memory 模块（episodic/semantic/source_quality/checkpointer），17 天工期承担不起。

**Decision**：
- `working.py`：State 操作辅助
- `store.py`：统一 LangGraph BaseStore，用 namespace 区分 (`patterns/`, `competitors/`, `source_quality/`)
- Checkpointer 直接用 `langgraph.checkpoint.sqlite.SqliteSaver`，不再封装

**Trade-offs**：v2 若需细分再拆。

---

## D-010 · 测试基建前置 + CI/pre-commit
**Status**: Accepted · **Date**: 2026-05-20

**Context**：Timeline 把单体测试放在 5.29（D10），但 agent 与测试应同日开发。

**Decision**：
- `tests/conftest.py` 提供 `FakeLLM` fixture（绝不调真 API）
- 每写一个 agent / skill / tool，同日补 `tests/test_xxx.py`
- `ruff` 一体 lint+format，`pre-commit` 本地拦，`.github/workflows/ci.yml` push 时跑

**Trade-offs**：开发期多 5% 时间成本，换联调日不出格式 bug。

---

## D-011 · Supervisor pattern（PM 是 bottleneck）
**Status**: Accepted · **Date**: 2026-05-20 (Meeting2 sync)

**Context**：v1 设计 agent 之间松耦合互调；改 v2 后所有 agent 输出汇到 PM 做内联 QA + 路由。

**Decision**：采用 supervisor pattern，PM 作为单点汇聚 + 任务编排 + 内联 QA。

**Alternatives**：
- 松耦合 agent-to-agent —— 无单点 bottleneck，但调试难，跨 agent 状态分散
- Team-of-equals + 独立 QA agent —— 接近原 v1，但失去 PM 的动态规划亮点

**Trade-offs**：
- PM token 成本 ≈ 其他 agent 总和（接受）
- 单点故障：PM 失败整链卡死（用重试 + checkpointer 缓解）
- 调试集中：只看 PM 日志可定位绝大多数问题（**核心收益**）

---

## D-012 · Collector + Insight 并行 fan-out
**Status**: Accepted · **Date**: 2026-05-20

**Context**：原 v2 设计是串行经 PM；评估发现 Collector 和 Insight 互不依赖。

**Decision**：PM 拆解任务后同时 dispatch Collector 与 Insight，LangGraph 原生 fan-out + 自动 fan-in 到 Analyst。

**Why**：现场 demo 节省一半采集时间；答辩可点"用上 LangGraph 并发能力"。

**Trade-offs**：QA 失败时两条线都可能要回退，retry 逻辑稍复杂。

---

## D-013 · PM Agent = GPT-5（终定）
**Status**: Accepted · **Date**: 2026-05-20

**Context**：曾考虑 PM = DeepSeek 以避免 PM 审 Report（同 GPT-5）；但 v2 终审落到 Doubao，PM 不再审 Report。

**Decision**：PM = GPT-5。

**Why**：
- PM 不直接审 Report（Doubao 终审）→ 没有同家族冲突
- GPT-5 的复杂任务规划 / TaskRegistry 状态机管理能力更强
- PM 审的 Collector / Insight / Analyst 全为 DeepSeek → 完全跨家族

**Known trade-off**：PM 审 Collector 多模态分支（也是 GPT-5）时存在同家族风险，但只在 PDF/图像输入时触发，Doubao 终审兜底。

---

## D-014 · 可信度规则：retry > 2 即 forced/unreviewed
**Status**: Accepted · **Date**: 2026-05-20

**Context**：报告需要标注哪些信息"可信度低"，但不能让 LLM 主观打分。

**Decision**：QA 失败 retry_count > 2 即将 task 标 `status=forced`，并写入 state 的 `unreviewed` 列表。报告自动生成"未经充分审核"段落。

**Why**：客观规则可解释（答辩说"我们用客观重试上限而非 LLM 主观置信度"），不依赖 LLM 自评。

**Alternatives**：
- LLM self-rating —— 已知过度自信
- 源多样性打分 —— 复杂，未来 v2 考虑
- 时间新鲜度 —— 与质量弱相关

---

## D-015 · 动态任务管理：TaskRegistry
**Status**: Accepted · **Date**: 2026-05-20

**Context**：每个 agent 的 T1/T2/T3 在 QA loop 中状态变化，需追踪。

**Decision**：State 引入 `task_registry: dict[str, TaskRecord]`，记录每个 task 的：
```
task_id / agent / description / status (pending|running|passed|failed|forced) / retry_count / output
```

**Why**：
- PM 路由决策依据 = 看 registry 状态
- 调试 / 答辩可直接展示完整任务生命周期
- 是 D-014 "forced" 标记的载体

**Trade-offs**：State 复杂度上升，单元测试要覆盖状态机转换。

---

## 待决（Pending）

- **DP-001**：domain_seed yaml 与 long-term `semantic_patterns` 命中策略（命中后是跳过 web 还是合并）
- **DP-002**：weasyprint 在 Windows 装失败时的 fallback 触发条件
- **DP-003**：答辩 demo 时长（影响 streaming 节奏）
- **DP-004**：Doubao 具体 model id（用户拿到 endpoint 后填）
