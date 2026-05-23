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
    target: str,                  # 被审对象类型 (pm_taskplan / analyst_swot / report)
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

## 待决（Pending）

- **DP-001**：domain_seed yaml 与 long-term `semantic_patterns` 命中策略
- **DP-002**：weasyprint 在 Windows 装失败时的 fallback 触发条件
- **DP-003**：答辩 demo 时长（影响 streaming 节奏）
- **DP-004**：Doubao 具体 model id / endpoint
- **DP-005**：debate 不收敛率 > 阈值时是否打断流程（v1 走 forced，v2 可加 alert）
