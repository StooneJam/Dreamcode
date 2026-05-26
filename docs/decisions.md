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

## D-016 · Schema 设计：通用骨架 + 动态维度 + 证据驱动 + state/schema 分文件
**Status**: Accepted · **Date**: 2026-05-22
**Implements**: D-004 (config 化可扩展) · D-014 (forced/unreviewed) · D-015 (动态任务管理)

**Context**：Timeline 5.22 要求"办公软件竞品专属 Schema"，但若把办公软件字段写死会破坏 D-004 的扩展性承诺。需要在领域深度与扩展性间找到工程上的平衡。

**Decision**：

1. **通用骨架 + 动态维度** —— Schema 本身赛道无关
   - `Dimension(name, category, facts)` —— name 和 category 都是开放字符串
   - `ProductProfile.dimensions: list[Dimension]` —— 维度由 PM/Agent 运行时发现
   - 领域知识在 `domain_seeds/{vertical}.yaml` + prompts，**不在 Pydantic 类**

2. **证据驱动** —— 每条事实必须可溯源
   - `Fact.evidence: list[Evidence] = Field(min_length=1)` —— 至少一条证据
   - `Evidence(source_url, snippet, fetched_at)` —— URL + 原文 + 时间戳
   - `SWOTPoint.supporting_fact_statements: Field(min_length=1)` —— SWOT 必须引用已有 facts
   - **答辩亮点**：杜绝 LLM 无依据生成结论

3. **约束分层**（与 100% strict 讨论的结论）
   - 闭合状态机 → 严格 `Literal[...]`（report_status / ReviewUnit.status / .agent）
   - 已知分类可扩展 → `Literal[..., "other"]` 兜底（pricing_model / platform）
   - 真开放发现 → `str`（Dimension.name / .category / product_type / target_users）
   - 不全局加 `extra="forbid"`，保留 agent 扩展字段的空间

4. **state 与 schema 分文件**
   - `src/cca/schema.py` —— Pydantic `BaseModel`（领域）
   - `src/cca/state.py` —— TypedDict + reducer（LangGraph 状态）
   - 避免 `Annotated/add/TypedDict` 等 import 污染领域模型文件

5. **ReviewUnit 三件套兑现 D-014 + D-015**
   - `ReviewStatus = Literal["passed", "needs_retry", "forced"]`
   - `ReviewUnit(agent, product_name, status, retry_count, qa_flags, pm_note, reviewed_at)`
   - `agent` 范围限定 `["collector", "insight", "analyst"]` —— **不含 report**，因为 report 归 Doubao 终审走 `qa_results`，与 PM inline QA 解耦
   - `CCAState.review_state: Annotated[list[dict], add]` —— 累加每轮评审，retry 状态从 list 推导而非单一 int

**Alternatives 考虑过**：
- 硬编码垂直字段（方案 A）：换垂直 = 重写 schema，违背 D-004
- 完全继承体系（方案 B）：每个垂直一个子类，工程量大
- 运行时 `pydantic.create_model()` 动态 schema（方案 C）：开发期无静态类型，17 天承担不起
- 通用骨架 + 逃生舱 `domain_specific: dict[str, Any]`（方案 D 初版）：最终未加，因 `Dimension.facts` 已足够灵活

**Trade-offs**：
- `UserSentiment.appstore_cn_*` 半固化中国 AppStore，是办公软件首发的合理 trade-off；同文件 `appstore_region` 字段保留通用化迹象，v2 重构
- `PricingTier` 已通用化（`price_per_user_monthly` + `currency` 字段）
- 没有 `domain_specific` 逃生舱意味着塞不进 dimensions 的极端字段无处放，**接受**（按 YAGNI，遇到再加）

**Known issues**：
- `qa_results` vs `ReviewUnit` 职责相邻：前者是 Doubao 终审 / 后者是 PM inline；注释里已明示区分，开发时需注意不要混用

---

## D-017 · 跨家族最终 QA 从节点变 skill（call_report_reviewer）
**Status**: Accepted · **Date**: 2026-05-22
**Supersedes**: 架构 v2 中"Doubao 作为独立 QA 节点"的设计

**Context**：v2 架构原把 Doubao 终审做成 LangGraph 独立节点（QA #3）。实际审查只做一致性校对，工作量远低于一个完整 agent；做成节点带来不必要的图结构复杂度。

**Decision**：
- Doubao 终审封装为 **`call_report_reviewer` skill**（LangGraph subgraph）
- Reporter agent 生成 MD 后**主动调用**该 skill
- skill 仅返审查结论（`QAResult`），不修改 MD；Reporter 根据 result 决定是否重写
- 是否调用由 `ReportTask.invoke_call_report_reviewer: bool` 显式开关控制（默认 true）

**Why**：
- 一致性校对的认知负荷 << 完整 agent，skill 颗粒度更合适
- 与 `questionnaire` skill 对称，架构连贯
- Reporter 作为单一触点拥有完整报告生命周期（生成 + 审 + 修订）

**Trade-offs**：
- LangGraph 节点图里 Doubao 跨家族审不再独立可见 → **修法**：在架构图里画 Reporter 调用 skill subgraph 的虚线（与 questionnaire 视觉对称），保住答辩可视化卖点
- `ReviewUnit.agent` 范围因此**不含 report**（仅 collector / insight / analyst），Doubao 审查记录走独立的 `qa_results` 字段（D-016 已明示）

**Implementation**：
- `src/cca/skills/call_report_reviewer.py`（v1 占位）
- 接口：`def call_report_reviewer(report_md: str, profiles: dict[str, dict]) -> QAResult` —— 单一职责，仅返审查结论
- 失败语义：QAResult.passed=false 时 Reporter 重写；retry_count > 2 进入 forced（沿用 D-014 规则）

---

## D-018 · PM 分阶段任务下发（AnalystTask + ReportTask 后置）
**Status**: Accepted · **Date**: 2026-05-22
**Implements**: D-011 (supervisor pattern) + D-015 (动态任务管理) + D-016 (schema 设计)

**Context**：早期 TaskPlan 仅含 `collect_tasks` + `insight_tasks`，下游 Analyst / Report 没有任务定义。若 PM 在开局就一次性下发全部任务（Pattern X），Analyst 的 `focus_dimensions` 只能盲填或留空，因为此时 Collector 还未发现真实 dimensions —— **信息流逆向**。

**Decision**：PM 分 3 阶段下发任务，每阶段基于上一阶段真实产出生成。

```
PM 阶段一 → TaskPlan(collect_tasks + insight_tasks)
   ↓
Collector + Insight 并行 → PM QA pass
   ↓
PM 阶段二 → AnalystTask（focus_dimensions 用 Collector 实际填的高频维度）
   ↓
Analyst → PM QA pass
   ↓
PM 阶段三 → ReportTask（sections 由 SWOT 高亮项指定）
   ↓
Reporter（内部调用 call_report_reviewer skill，D-017）→ END
```

**Alternatives**：
- **Pattern X 开局一次性出全部任务**：信息流逆向（Analyst 拿到 task 时还没有真实 dimensions），驳回
- **完全静态 dispatch（无 AnalystTask/ReportTask）**：Analyst/Report 直接读 state.profiles 自行决策，PM 不下发 → 失去 PM 作为 supervisor 的价值，驳回

**Why**：
- 每阶段任务定义基于上一阶段真实产出 → 信息流正向
- 强化 PM 的 supervisor 角色，每个 QA pass 后都有"再规划"动作 → 体现 D-011 supervisor pattern
- 兑现 D-015 动态任务管理（task 真正动态，不是开局静态）

**Implementation**：
- `schema.py`：新增 `AnalystTask` + `ReportTask`（独立 Pydantic 类，不嵌入 TaskPlan）
- `state.py`：`CCAState` 加 `analyst_task: dict | None` + `report_task: dict | None`
- TaskPlan 保持只含 collect + insight tasks，**不增长字段**

**Trade-offs**：
- PM 多 2 次 LLM 调用（阶段二、三），token 成本上升 → 接受，因 Doubao 终审是 skill 不占独立节点（D-017），整体调用次数相比 v2 原设计无显著增加
- TaskPlan 与 AnalystTask / ReportTask 字段同源问题：如 `target_products` 在两处都有 → 设计上 PM 必须保持一致，开发期靠 audit_log 检测

---

## D-019 · Tools 全部 `@tool` 化（Level 1 agent 自治）
**Status**: Accepted · **Date**: 2026-05-23

**Context**：原 plain function tool 设计被 push back —— "套着 LLM 壳子做后端开发"，是伪 agent。

**Decision**：所有暴露给 agent 的工具用 `langchain_core.tools.tool` 装饰。LLM 通过 `bind_tools` / `create_react_agent` 自主决定调用时机与参数。

**Why**：Level 1 工具自治是 multi-agent 的最低门槛。docstring 直接成为 LLM 的 tool description，需为 LLM 友好。

**Implementation**：
- `src/cca/tools/search.py` ✓ 已落地
- 后续 `tools/fetcher.py` / `pdf_reader.py` / `pii_guard.py` 同样模式
- 测试用 `tool.invoke({...})` 调用 + 验证 `isinstance(tool, BaseTool)`

---

## D-020 · 半步 multi-agent 架构（v3）
**Status**: Accepted · **Date**: 2026-05-23 (Meeting3)
**Supersedes**: D-011 部分（PM 中心化但完全 deterministic 的版本），D-018 三阶段静态 dispatch 的部分语义

**Context**：外部 review 指出 v2 仍是"带智能路由的 Pipeline"，agent 间无交互、PM 自审无审。完全去中心化 multi-agent (debate / mesh) 工期不可达。需要中间方案。

**Decision**：**半步 multi-agent** —— PM 与下游 agent 通过**跨家族 debate** 双向收敛 task_plan，但最终 dispatch 仍走 PM（保留 supervisor 单点可观测）。

**职责重新切分**：
- **PM (GPT-5, 无工具)**：仅用训练知识起草 initial task_plan，通过 debate 与下游协商精化；分阶段 dispatch + 验收
- **Collector (DeepSeek + ReAct + 工具)**：联网发现真实竞品、产品赛道、分析维度（**接管原 PM 的外部认知**）+ 抓取数据
- **Insight (DeepSeek + ReAct + 工具)**：联网发现评论平台 + 抓评论 + 情感分析
- **Analyst (DeepSeek + ReAct)**：SWOT 推理，与 PM debate 验证
- **Report (GPT-5)**：撰写 + 调 call_report_reviewer skill (debate-based)

**信息流**：
```
PM 起草 → Collector/Insight 实地探索 → 跨家族 debate 收敛 task_plan
       → PM 接受 → Analyst 推理 → PM debate 收敛 SWOT
       → PM 接受 → Report 撰写 → Doubao+DeepSeek debate 终审 → END
```

**Why**：
- 学术 multi-agent (mesh/debate) 工期 8-10 周，不可达
- 业界生产 supervisor pattern 又被 reviewer 指为"伪 agent"
- 半步是工程妥协：保留 PM 编排 + 引入跨家族 debate + 重新切分职责让 agent 真有自主探索权

**Trade-offs**：
- PM 失去外部信息源 → 信任 Collector 的实地探索 + 用 debate 拒绝错误的 hallucination
- 每个关键 checkpoint 多 5x token（debate 4 阶段）→ 总 cost 2-3x
- Demo 时间增加（debate 是串行）→ 用 streaming 让评委看辩论展开

---

## D-021 · domain_seeds/ 定位为用户可上传内容
**Status**: Accepted · **Date**: 2026-05-23

**Context**：曾考虑把 domain_seeds 简化合并进 config.yaml，被用户 push back 指出 domain_seeds 是**面向用户的可上传内容**，与开发者管理的 config 性质不同。

**Decision**：保留 `src/cca/domain_seeds/` 作为独立目录。`settings.load_domain_seed()` **不缓存**（用户可运行时上传新 yaml）。

**类比**：config.yaml 像 Nginx config（开发者管理），domain_seeds 像 WordPress 插件目录（用户管理）。

**v1 内置**：`office_software.yaml` 演示完整能力。v2 加上传 UI。

---

## D-022 · PM TaskPlan 跨家族 debate 精化（合并 self-audit gap fix）
**Status**: Accepted · **Date**: 2026-05-23
**Implements**: D-020 半步 multi-agent；修复外部 review 的 #2 PM self-audit critique

**Context**：v2 中 PM 自审 TaskPlan 是关键漏洞 —— PM 幻觉竞品或漏维度无人发现。

**Decision**：PM 起草 initial task_plan → 由 Collector/Insight 在 ReAct 执行后**反向 debate** PM 的假设 → 跨家族仲裁产出 refined task_plan。

**4 阶段实现**（D-024 debate skill）：
1. Position：PM 给 initial task_plan，Collector/Insight 各自给实地证据
2. Critique：两方互相挑刺（"PM 漏了 XX 竞品"/"Collector 找的 XX 在国内份额 <1%"）
3. Refine：双方修订
4. Judge：Doubao 仲裁，产出 refined task_plan

**Why**：PM (GPT-5) 与 Collector/Insight (DeepSeek) 异家族 + Doubao 仲裁三家族无重叠 → bias 隔离链条完整。

**Trade-offs**：每个产品的 task_plan 精化要 5x token，但只跑一次/一产品 → 整体可控。

---

## D-023 · Agent → PM 反向 signal 通道
**Status**: Accepted · **Date**: 2026-05-23
**Implements**: 修复外部 review 的 #1 (pipeline 感) + #3 (Collector 太薄) critique

**Context**：要在 supervisor 架构内让 agent 有"主动反馈权"，避免 reviewer 的 "agent 是被动函数" 评判。

**Decision**：state 加 `agent_signals: Annotated[list[dict], add]` 字段。Agent 可主动 publish：
- `data_gap`：发现数据缺口请求重派
- `pm_challenge`：质疑 PM 的 task_plan 某假设
- `insight_lead`：发现一个高价值线索建议追加任务

PM 每轮扫这个列表决定是否短路径响应。**事实性 signal 走普通响应，主观判断 signal 触发 debate**。

**消费去重**：`AgentSignal.signal_id`（UUID）+ `state.consumed_signal_ids: Annotated[list[str], add]`。
PM 节点处理完一条信号后把其 `signal_id` append 进 `consumed_signal_ids`，下次扫描 `agent_signals` 时跳过这些 id。信号本体永不删除，保留在 `agent_signals` 内供回溯（看历史挑战）；debate 内容存于 `debate_results`，PM 决策存于 `audit_log`，三条审计链分离。

**Why**：让 Collector / Insight / Analyst 不是被动接受 task，而是可发起 push-back —— 是"半步 multi-agent" 双向通讯的具体实现。

**Trade-offs**：可能 signal 过多 → 加 rate limit + 优先级。

---

## D-024 · 跨家族 4 阶段 debate skill
**Status**: Accepted · **Date**: 2026-05-23
**Used by**: D-022, D-017 (修订), Analyst SWOT 校验

**Context**：单家族 LLM 审同家族 LLM 输出有 bias。需要可复用的多家族对抗机制。

**Decision**：实现 `src/cca/skills/debate.py` 公共组件。

**接口**：
```python
def run_debate(
    target: str,                  # 被审对象类型 (pm_taskplan / analyst_task / report)
    target_content: dict,
    families: list[str] = ["deepseek", "doubao"],
    judge: str = "gpt-5",         # 第三家族仲裁
    max_rounds: int = 2,
) -> DebateResult
```

**4 阶段**：Position → Critique → Refine → Judge（详见 [[project-debate-design]]）。

**应用 checkpoint**：
- PM TaskPlan 精化（D-022）
- Analyst SWOT 推理
- Report 终审（D-017 升级）

**不用 debate**：Collector 结构化字段、Insight 情感分类等单审够。

**Trade-offs**：debate 比单审多 5x token；3-4 个 checkpoint × 5x ≈ 总 cost 2-3x。

---

## D-017 修订 · call_report_reviewer 升级为 debate 实现
**Status**: Revised · **Date**: 2026-05-23
**Revises**: 原 D-017（Doubao 独审）

**变更**：call_report_reviewer skill 内部不再是 Doubao 独审，而是 **Doubao + DeepSeek 双辩 → GPT-5 仲裁**（跨三家族）。

**Why**：单 Doubao 仍是同模型审同模型（虽跨家族但单方）。debate 引入对抗强化判断。

**Implementation**：sklls/call_report_reviewer.py 内部调用 `run_debate(target="report", ...)`。

---

## D-025 · DecisionRecord + decision_log：PM 决策可溯源
**Status**: Accepted · **Date**: 2026-05-25
**Implements**: 离线 Q&A 用户"为什么这么决定" + 修复 debate defense 空壳

**Context**：用户产品诉求是"看报告时能问 PM 为什么选这几家竞品 / 为什么强调这些维度"。原本 `TaskPlan.rationale` 是可选 str，PM 经常不填；debate 时 `_read_defense` 只能字面拼字段值当 claim，evidence 等于 claim，是空壳。根因：**PM 在产出 task 时根本没把决策过程写下来**——不是存储问题，是产出环节缺记录。

**Decision**：加 `DecisionRecord(decision_id, phase, decision_type, chosen, alternatives_considered, rationale, inputs_used, ts)` schema。state 加 `decision_log: Annotated[list[dict], add]`。PM 4 个阶段节点用新增的 `InitialBriefOutput / TaskPlanOutput / AnalystTaskOutput / ReportTaskOutput` 联合输出类型，同一次 LLM 调用同时返回 task 主体 + `decision_records: list[DecisionRecord]`（min_length=1 强制）。删除 `InitialBrief.rationale` 与 `TaskPlan.rationale`（被 DecisionRecord.rationale 完全覆盖）。

**Why not 黑板模式**：`Annotated[list, add]` state 字段本身就是黑板的最小实现；引入独立 zone / 检索层 / 持久化层对单会话 demo 是负收益，违反"简洁优于完备"。`decision_log` 只是又一个分区，跟 `debate_results` / `audit_log` 对称。

**Why decision_type 不用 Literal**：枚举固化太早。description 里列建议值（`competitor_selection` / `dimension_priority` / `task_allocation` / `analyst_focus` / `report_structure` / `audience_choice` / `other`）让 LLM 倾向用，自由 str 字段保扩展性。

**Implementation 细节**：
- `phase` 由代码端 `_stamp_decisions` 强制覆盖（防 LLM 自报错值，同 debate `_phase_judge` 覆盖 judge_family 的模式）
- `ts` schema 端 default_factory 兜底
- `confidence` 字段砍掉——LLM 自评 confidence 不可信，留个 None 不如不留

**Trade-offs**：每个 PM 节点 LLM 输出 token 增加 ~30%，换来完整决策审计链；下游可在报告段落里嵌 `[D-XX]` 脚注供用户回溯（3d 阶段做）。

---

## D-026 · AgentSignal 强类型 ChallengePayload + signal_id 消费去重
**Status**: Accepted · **Date**: 2026-05-25
**Implements**: 修复 #3（challenge 空壳）+ 防 handle_signal_node 重复触发

**Context**：原 `AgentSignal.payload: dict` 任意结构，约定俗成塞 `{"reason": str}`。`_handle_debate_signal` 把 reason 字符串同时灌进 challenge 的 claim 和 evidence——双倍 claim 当 evidence，等于零证据挑战。同时 `agent_signals: Annotated[list, add]` 永不删，PM 节点二次激活会重复处理同一信号，可触发死循环。

**Decision**：
- 加 `ChallengePayload(claim, evidence: list[str] min_length=1, observed_data, suggested_fix)`，把 `AgentSignal.payload` 改为强类型 `ChallengePayload`。事实性 / 主观信号共用同一形态——reroute LLM 与 debate skill 都能直接读结构化字段。evidence 强约束 ≥1 条，让"零证据挑战"在 Pydantic 层就被拒。
- 加 `AgentSignal.signal_id: str = Field(default_factory=lambda: str(uuid4()))` + state 加 `consumed_signal_ids: Annotated[list[str], add]`。`handle_signal_node` 处理前过滤已消费 id，处理后把本次 id 写回。信号本体永留 `agent_signals` 供回溯。

**三审计链分离**：`agent_signals`（原始信号）+ `consumed_signal_ids`（去重指针）+ `debate_results`（辩论内容）+ `audit_log`（PM 决策事件）。任意时刻可按 signal_id 追溯整条链。

**Why not in-place 标记 consumed**：list 是 add reducer，修改 = 追加新版本污染历史。独立指针字段 = 清爽的"已读"语义，类比邮箱"已读"标记不删邮件。

**配套改动**：`_read_defense` 从字段字面拼装改为按 phase 聚合 `decision_log`（依赖 D-025 已落盘的决策档案）。`qa_report.reject_report_task` 工具签名从 `(reason, ...)` 改为 `(claim, evidence, ...)` 强制结构化产出。

---

## D-027 · PM handle_signal_node 多信号正确性 + reroute 上下文瘦身
**Status**: Accepted · **Date**: 2026-05-25
**Implements**: 修复 #1（dict.update 覆盖）+ #10（rejected 无恢复）+ #11（reroute context 膨胀）+ #12（apply_reroute 死参）

**Context**：`handle_signal_node` 单次调用收多个信号时，`updates.update(...)` 同 key 覆盖——LangGraph add reducer 只在节点之间累加，**节点内自己合并 dict 不会触发 reducer**。第二个 debate 信号的 `debate_results: [r2]` 把第一个的整键吞掉。`apply_reroute` 全量 state JSON 化送 LLM，profiles 累积后 prompt 无界增长。`rejected` verdict 只记 log，被否决的 task 维持错误状态，下游基于脏数据继续跑。

**Decision**：
1. **节点内 list 本地累加** `debate_results` / `audit_log` 用本地 list，循环结束一次性返回；标量字段保留"后写覆盖先写"语义
2. **信号处理顺序固定**：reroute（事实性纠错优先清理脏数据）先处理，debate（主观分歧基于清理后的状态再裁决）后处理
3. **rejected verdict 清空对应 task 字段**（`task_plan` / `analyst_task` / `report_task` = None），触发上游路由重派该阶段；落地 `_DEBATE_TARGET_TO_TASK_FIELD` 共用 dispatch 表
4. **reroute context 瘦身**：新加 `_build_reroute_context` 只送 `exploration_result / task_plan / analyst_task / report_task / review_state / competitor_names`，剔除 profiles / audit_log / debate_results / decision_log 等大对象
5. **`apply_reroute` 删 state 死参**：从未读取过

**Trade-offs**：节点内手动 list 拼接看起来不如 reducer 优雅，但 LangGraph 的设计就是跨节点累加；理解后这是正确用法不是 hack。

---

## D-028 · debate skill 一致性修复：target rename + revised_output schema 校验
**Status**: Accepted · **Date**: 2026-05-25
**Implements**: 修复 #4（target 语义错位）+ #5（revised_output 静默数据丢失）
**Revises**: D-024 接口

**Context**：
- **#4**：signal target `analyst_task` 被映射到 debate target `"analyst_swot"`，但 `target_content = state["analyst_task"]` 取的是 PM 下发的任务包（focus_dimensions / product_names），不是 Analyst 产出的 SWOT。**标签在欺骗内容**——下游若按 target 类型分发会误判。
- **#5**：`_phase_finalize_converged` 收敛路径用裸 `json.loads(raw.strip().removeprefix("```json").removesuffix("```"))` 解析 LLM 输出，没 schema 校验。若 LLM 漏写 `competitor_names`，`_apply_debate_result` 里 `updates["competitor_names"] = result.revised_output.get("competitor_names", [])` 把整张竞品列表静默清空——最难 debug 的失败模式。

**Decision**：
1. `DebateTarget` / `DebateResult.target` Literal: `analyst_swot` → `analyst_task`（"analyst SWOT 终审"由 `call_report_reviewer` skill 独立 owner，不归入本表）
2. 加 `_REVISED_OUTPUT_SCHEMA: dict[DebateTarget, type[BaseModel]]` dispatch（`TaskPlan` / `AnalystTask` / `ReportTask`）
3. `_phase_finalize_converged` 改用 `get_llm(winner).with_structured_output(schema, method="json_mode")`：LLM 漏 required 字段 → Pydantic ValidationError 直接抛，loud failure 替代 silent data loss

**显式不修**：
- **#6**（双方都让步时 winner 任意按 families 元组顺序选）：边角 case，且 demo 真跑出来过，但优先级低
- **#7/#8**（refinement 不带新 evidence / critique 看不到对方 refinement）：双 LLM 并行的设计权衡，文档化为已知限制

---

## D-029 · 多家族 LLM 跑通的兼容性约束
**Status**: Accepted · **Date**: 2026-05-25
**Context**：D-025/D-026/D-028 设计跑 dry-run 全过，切真 LLM 后一连串踩坑，最后归纳出 3 类必须的兼容性约束。

**Decision**：
1. **PM 4 节点必须 `method="function_calling"`**——OpenAI strict mode 拒绝任何含 `dict` 字段的 schema（要求每个 object 显式 `additionalProperties: false`）。`DecisionRecord.chosen: dict` 是结构灵活的设计本意，不能为兼容 strict 而改成 typed schema。function_calling 是 OpenAI 兼容 API 的通用解。
2. **debate 4 个 prompt 显式含 "JSON" 字样**——OpenAI / DeepSeek 的 `response_format=json_object` 强制 prompt 内出现 "json"（case-insensitive），否则 400。`_phase_critique` / `_phase_refine` / `_phase_judge` / `_phase_finalize_converged` 全部在 system prompt 末尾加 "以 JSON 输出"。
3. **schema 字段名贴合 LLM 自然倾向 + 显式约束基本类型**：`_Critique.text` → `_Critique.critique`，`_Refinement.text` → `_Refinement.refinement`——DeepSeek 在 json_mode 下倾向语义命名（看到"批驳"就用 `critique` key 而非 schema 指定的 `text`）。同时 prompt 要明确"必须是单一字符串，不要数组/对象"，否则 DeepSeek 会自作主张返回结构化数组。

**Trade-offs**：prompt 啰嗦些（多 1-2 句），换来 GPT-5 / DeepSeek / Doubao 三家族同时跑通。

---

## D-030 · PM agent demo 脚本作为后续 agent 开发范本
**Status**: Accepted · **Date**: 2026-05-25
**Used by**: 后续 Collector / Insight / Analyst agent 开发

**Context**：D-025～D-029 落地后需要端到端验证，但完整 graph 尚未拼起，且单元测试无法验证多 LLM 串联的真实行为。

**Decision**：写 `scripts/run_pm_demo.py`，直接调用 PM 内部节点函数（不接 LangGraph），上游产出（exploration_result / profiles / review_state）硬编码 mock。提供：
- `--dry-run` 模式：patch `pm.gpt` 和 `debate.get_llm` 为预制 fake，验证 plumbing 不烧 token
- 3 种 debate 场景：`accept`（合理挑战，预期 accepted_with_revision）/ `reject`（站不住脚的挑战，预期 rejected → task 清空）/ `none`（跳过 signal）
- `--skip-report` 隔离 ReAct 工具循环复杂度（report agent 单独跑）
- Verbose 输出：每阶段 task 全字段 JSON + DecisionRecord + debate 每轮 positions/critiques/refinements/verdict

**Why**：单元测试覆盖控制流，demo 脚本覆盖**多 LLM 串联的语义级行为**——D-029 的兼容性问题就是 demo 跑出来才发现的。后续 Collector / Insight / Analyst 沿用同一模式：`scripts/run_<agent>_demo.py` + dry-run/live 双模式。

**意外验证**：demo 真 LLM 跑出来时撞到 D-028 #6（双方让步 winner 按 families 顺序选）的边角 case，revised_output 没移除腾讯会议——确认了"显式不修"的取舍代价可见，未来若数据观察发现问题再回头修。

---

## D-031 · state 写权架构：producer-owns + PM 通过 debate 事后校验
**Status**: Accepted · **Date**: 2026-05-25
**Used by**: 所有非 PM agent 节点（Collector / Insight / Analyst / Report）

**Context**：Step 2 写 `collector.exploration_node` 前，讨论一个架构原则——"state 是否应由 PM 独占维护"。这关系到所有 agent 节点的返回值约定、是否需要 PM commit 中间层、demo 答辩的叙事框架。

**评估了 3 个方案**：
- **A 极严**：非 PM 节点只能通过 `agent_signals` 投递数据（signal-as-message-bus）。PM 消费 signal 提交到 state
- **B 中等**：state 加 `pending_*` 待审字段；非 PM 节点写 pending，PM 加 `commit_*` 节点搬运到权威字段
- **C 软约束**：state 字段按 **producer owns** 划分；PM 通过现有 debate / reroute 在分歧点事后修正

**Decision**：选 **C**。具体写权划分：

| 字段 | Owner |
|---|---|
| `task_plan` / `analyst_task` / `report_task` | PM |
| `decision_log` / `debate_results` / `review_state` / `consumed_signal_ids` / `competitor_names` | PM |
| `exploration_result` | Collector |
| `profiles[*].dimensions/pricing/sources/website` | Collector |
| `profiles[*].sentiment` | Insight |
| `profiles[*].swot` | Analyst |
| `report_md` / `report_pdf_path` / `report_status` / `qa_results` | Report |
| `agent_signals` / `audit_log` / `qa_notes` | 任何 agent（add reducer 累加无冲突）|

**纠错通道仍由 PM 把持**：
- Collector 写脏 `exploration_result` → PM 阶段二 `task_plan_node` 消费时可发起 debate；或下游 agent 通过 `AgentSignal` 反向挑战
- Analyst 写脏 SWOT → Report 阶段通过 `call_report_reviewer` 跨家族审核
- 任何主观分歧 → `agent_signals` + `handle_signal_node` debate 仲裁
- `rejected` verdict 清空被否决的 task（D-028），触发上游路由重派

**Why not A**：所有数据走 signal 通道会让 signal 语义混乱（signal 原本是 event/challenge，被迫承担数据交付角色）；现有 `report_node` 等需大改；plumbing 成本 ~3x。

**Why not B**：commit 节点引入 1 跳延迟；commit 内若不调 LLM 校验则只是搬运（B 的卖点等于零），若调 LLM 校验则每次交付都烧 token（debate 通道本就在分歧点才烧）。事后校验已经覆盖核心场景。

**Why C 贴 D-020 半步 multi-agent 叙事**：D-020 已选"agent 有自主权但 PM 有最终否决权"。C 是这条线的自然延伸——agent 在自己的域内自治写，PM 在分歧点通过 debate / reroute 行使否决权。强行套 A/B 反而和 D-020 精神冲突。

**答辩叙事可这么讲**：
> PM 是 **planning 字段**的唯一 owner（task_plan / decision_log / review_state / debate_results）；数据产出归各自 owner agent。PM 通过跨家族 debate 在分歧点 push back 修正——这是半步 multi-agent 的核心：agent 有自主权但 PM 有最终否决权。

**Trade-offs**：失去"PM 是唯一 state owner"这条干净叙事；但答辩可改用上面的"planning vs data 域划分 + debate 否决权"叙事，更贴架构实际。

**回头改为 B 的触发条件**（边界值）：
- 出现两个 agent 同时往同一字段写（目前无重叠，未来若有冲突再加 reducer 或上 B）
- 下游 agent 因 bug 反复写脏数据且 debate 识别率 < 70%（先尝试加 schema 校验或 prompt 强化）
- 答辩评委明确质疑 "为什么 Report agent 能改 state"（用上面叙事回答，撑不住再上 B）

---

## D-032 · 用户文档处理架构：domain_seed_node 蒸馏写 state，删除 dimension_discovery skill
**Status**: Accepted · **Date**: 2026-05-25
**Used by**: Collector exploration_node、未来 Insight / Analyst 的 focus dimensions
**Replaces**: V1 占位骨架 `cca/skills/dimension_discovery/`（**删除**，详见下方"取消 skill 抽象"段）

**Context**：实现 `dimension_discovery` skill 前讨论了一个根本架构选择——**用户上传的文档**（PDF / Word / 市场调研报告）如何被多个 agent 消费？讨论中提出了几个候选：

1. **PM phase 1 自己读文档**：违反 D-020 "PM 纯规划无工具"
2. **每个 agent 各自读**：重复 LLM 抽取，token 浪费
3. **塞全文到 state**：state 膨胀（30 页 PDF ~50k 字，checkpoint 序列化拖慢）+ 下游每次读 state 都重复消费同一段原文
4. **经典 RAG**（chunks + embedding + 向量库）：跟项目零 RAG 基础不对齐，加 chromadb / sentence-transformers 等依赖，起步 ~1.5 天工程成本
5. **蒸馏式预处理**：pdf_reader 抽全文 → 一次 LLM 蒸馏成结构化 hint dict 写 state.domain_seed → 多 agent 共享

**Decision**：选 **方案 5（蒸馏写 state）**。

具体设计：
- 新增独立节点 `domain_seed_node`，位于 PM phase 1 **之前**
- 用 `pdf_reader` / `docx_reader` 抽全文 → DeepSeek 单次蒸馏 → 写 `state.domain_seed` 结构化字段
- 状态 dict 形态：
  ```python
  state.domain_seed: dict | None = {
      "source_files": ["uploads/market_report.pdf"],   # 路径，留 lazy 重读通道
      "extracted_at": "ISO 8601",
      "dimension_candidates": list[str],                # ≤ 20 项
      "competitor_mentions": list[str],                 # ≤ 10 项
      "product_type_hint": str,                         # 1 句
      "terminology": dict[str, str],                    # ≤ 30 条键值对
  }
  ```
- **不存原文 / 不存 raw_excerpt 字段**——state 控制在 ~2KB
- 用户未上传文件时 `state.domain_seed = None`，下游 skill 走 `from_web` 兜底链
- 现有 V1 骨架 `dimension_discovery/from_memory.py` **删除**——依赖训练知识违反用户"减少幻觉"诉求

**Why not 经典 RAG**：

| 维度 | RAG 评估 |
|---|---|
| **时间预算** | 17 天项目，今天 day 6，剩 11 天还要做 collect_node / analyst_node / graph 集成 / 前端 / 演示。RAG 起步 ~1.5 天，挤掉 collect_node 的工作量 |
| **依赖面** | 项目目前零向量库 / 零 embedding 代码。加 chromadb（或 faiss）+ embedding 供应商（OpenAI / BGE 本地）= 多 1 套部署坑 |
| **问题预设性** | dimension_discovery 要回答的问题是**固定的**（dimension 候选 / competitor mentions / product_type / terminology）。RAG 的核心优势"应对未预设查询"在这里用不上 |
| **与 V1 命名对齐** | 现有 `from_seed.py` / `from_web.py` / `from_memory.py` 命名暗示"按 source 提取 hint"的蒸馏路径，不是 chunk + retrieve 路径 |
| **D-020 半步 multi-agent** | RAG 更适合一个集中的 retriever agent 调，跟"半步去中心化"的精神冲突；蒸馏式让 hint 成为 producer-shared 的世界事实，跟 `exploration_result` / `profiles` 同等地位 |
| **demo 场景** | 评估用户一般上传 1-2 个文档，且 DeepSeek 128k 上下文单文档塞得下 |

**Why not 塞全文到 state**：
- 30 页 PDF ~50k 字塞 state，checkpoint 写 sqlite 时序列化拖慢
- 每个读 state 的 agent 都付一次输入 token 成本，重复消费同一段原文
- state 应该是 agent **产出**的世界，不是输入资料的容器
- 下游 agent 实际不需要原文：PM 只要 hint，Collector 只要 dimension 候选，Analyst 只要 focus 维度

**Why not 每个 agent 各自读**：
- 同一文档被 4-5 次 LLM 蒸馏（每个 agent 一次），token 成本 ~5x
- 各 agent 可能抽出不一致的 hint（同一 PDF，PM 抽出"企业协作"，Collector 抽出"协同办公"）
- 缺乏审计入口

**答辩叙事**：

> 我们评估过经典 RAG，对**单文档 + 预设查询**场景判定为过度设计。我们用了 lightweight 蒸馏：pdf_reader 抽全文 → 单次 LLM 提取结构化 hint 写 state.domain_seed，原文路径保留供 lazy 重读。这是"无向量库的 RAG 思路"——retrieval 等于蒸馏阶段的指令式抽取，generation 等于后续 agent 用 hint。

**Trade-offs / 已知限制**：
- 蒸馏阶段未提取的字段，下游就丢了。当前预设 4 个 hint 字段够覆盖 dimension_discovery 需求，但未来若 Insight 想问"用户文档里提到了哪些用户画像？" 答不上来
- 不是标准 RAG 叙事；评委如果坚持"为什么不用向量库"需要用上面答辩稿回应
- 蒸馏 1 次失败影响全局（vs RAG 每次查询独立）；通过严格 schema 校验 + retry 1 次缓解

**升级到经典 RAG 的触发条件**：
- 实际 demo 用户上传 > 5 个文档（蒸馏的预设字段顶不住跨文档信息聚合）
- 出现需要 ad-hoc 查询的 agent（如未来加一个"答疑 agent" 让用户对报告追问）
- 答辩明确要求 "vector store" 关键词

**与 D-031 producer-owns 的关系**：`domain_seed_node` 是 `state.domain_seed` 的 producer-owner，跟 Collector / Insight / Analyst 各自拥有自己产出字段同构。pre-processing 不破坏 D-031 半步 multi-agent 原则。

**source_files 路径字段的意义**：留 lazy 重读通道。任何 agent 想看原文 → `pdf_reader.read(path)` 直接读文件，不走 state。这给"按需查询"留了口子，没引入向量库。

**取消 skill 抽象**：V1 在 `cca/skills/dimension_discovery/` 设计了 `from_seed.py` / `from_web.py` / `from_memory.py` / `subgraph.py` 四源 fallback subgraph，本决策一并**删除整个 skill 目录**。理由：

跟踪 dimension 在系统里的实际生命周期 → 没有任何调用方需要"运行时按需调用一个 dimension_discovery skill"：

| 阶段 | dimension 来源 | 实现方式 |
|---|---|---|
| domain_seed_node | 用户上传文档蒸馏 | 节点内部 LLM 调用，**不需要 skill** |
| Collector exploration_node | 联网搜索 | ReAct 用 web_search + fetch_url 工具，**不需要 skill** |
| PM TaskPlan / AnalystTask / ReportTask | 综合 domain_seed + exploration_result | PM 读 state 决策，**不需要 skill** |
| Collector phase 2 / Insight / Analyst | 接收 PM 下发的 priority_dimensions | 用现成的，**不需要 skill** |

skill 抽象的核心价值是"被多个调用方复用"。这里**没有多个调用方**——domain_seed_node（文档源）和 Collector exploration（网页源）是两个完全不同的数据通道，没法共用 skill 实现。`from_memory` 已确认删（依赖训练知识违反"减少幻觉"诉求）。剩下 `from_seed` 是节点而非 skill，`from_web` 是工具调用而非 skill，subgraph 三选一融合的设计在实际使用中没人调。

整个文件夹是 V1 命名残留，删除符合 CLAUDE.md "简洁优于完备"。

同步删除：
- `src/cca/skills/dimension_discovery/`（含 5 个空 .py 文件）
- `tests/test_skills/test_dimension_discovery.py`（占位 skip）
- `schema.py:Dimension` docstring 引用更新为"由 domain_seed_node 蒸馏或 Collector 联网发现"
- `domain_seeds/README.md` 引用更新为 `domain_seed_node`
- `tests/fixtures/feishu_seed.yaml` notes 更新

---

## 待决（Pending）

- **DP-001**：domain_seed yaml 与 long-term `semantic_patterns` 命中策略
- **DP-002**：weasyprint 在 Windows 装失败时的 fallback 触发条件
- **DP-003**：答辩 demo 时长（影响 streaming 节奏）
- **DP-004**：Doubao 具体 model id / endpoint
- **DP-005**：debate 不收敛率 > 阈值时是否打断流程（v1 走 forced，v2 可加 alert）
