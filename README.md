# Dreamcode — 多Agent竞品分析系统

Bytedance project · 业务场景级 vibecoding 

## 项目目标

模拟数字调研小组，自动完成 **公开信息采集 → 结构化竞品报告输出** 的全链路工作流。
首发垂直：**办公软件**，架构支持 config 切换其他赛道。

## Agents 分工

| 角色 | 职责 | 默认模型 |
|---|---|---|
| 项目经理 PM | 任务拆解、动态分配 | DeepSeek V4 |
| 数据采集 | 抓官网/AppStore/RSS（合规） | DeepSeek V4 / GPT-5 多模态分支 |
| 用户洞察 | 评论/情感分析（差异化亮点） | DeepSeek V4 |
| 分析师 | Schema 填充 / 打分 / SWOT | DeepSeek V4 |
| QA + 报告 | 校验 + 报告输出 + 溯源 | GPT-5（多模态） |

跨家族模型对抗校验缓解 self-preference bias。

## 记忆体系

两层Memory体系配合 LangGraph 原生能力：

| 层 | 实现 | 用途 |
|---|---|---|
| Working memory | `State` (TypedDict) → `src/cca/memory/working.py` | 单次运行内 agent 间数据传递 |
| Long-term store | LangGraph BaseStore + SQLite → `src/cca/memory/store.py` | 跨 session 沉淀（用 namespace 区分维度模板/历史报告/源质量） |

短期 checkpointer 直接用 `langgraph.checkpoint.sqlite.SqliteSaver`，

## Skills

| Skill | 用途 | v1 状态 |
|---|---|---|
| `dimension_discovery` | 自动发现竞品对比维度（web + 可选 seed yaml） | 占位 |
| `questionnaire` | 一手数据 cold-start 合成（LLM 模拟 persona） | 占位 |

两个 skill 都作为 LangGraph **subgraph** 实现，与主图编排一致。

## 报告输出

- 默认 **Markdown**
- 同时输出 **PDF**：`markdown-it-py` (md→html) → `weasyprint` (html→pdf)
- 答辩演示需要 PDF 形态

## 测试与质量

- `tests/conftest.py` 提供 `FakeLLM` fixture，避免单元测试调真 API
- 阶段二（5.24-5.30）每开一个 agent 同日补它的测试，**不集中堆到联调日**
- `ruff` lint + format
- `pre-commit` 在每次 commit 前自动跑 ruff
- GitHub Actions CI：`ruff check` + `pytest`

## 快速开始

```powershell
conda env create -f environment.yml
conda activate multi-agent
python -m spacy download zh_core_web_sm
pre-commit install
Copy-Item .env.example .env       # 填入你的 API key
python scripts/hello_world.py     # 验证 LangGraph + 双模型联通
```

## 目录结构

```
Dreamcode/
├── config/               # 仅运行时参数（不放领域知识）
├── src/cca/              # 核心包
│   ├── agents/           # 5 个 agent
│   ├── skills/           # 2 个 skill 子图（v1 占位）
│   ├── memory/           # working.py + store.py（精简版）
│   ├── tools/            # search / fetcher / pdf / pii_guard
│   ├── prompts/          # md 文件
│   ├── llm/              # 跨家族模型路由
│   ├── observability/    # loguru + langsmith
│   └── graph.py          # 主图装配
├── app/                  # Streamlit 前端
├── scripts/              # CLI 入口 + hello_world
├── tests/                # 与 src/ 镜像，含 fixtures/golden
├── data/                 # raw/cache/private/memory（gitignored）
├── reports/              # 输出（gitignored）
├── docs/                 # 架构图 + 决策日志
└── .github/workflows/    # CI
```

## v2 / Stretch Roadmap

| 项 | v1 状态 | v2 计划 |
|---|---|---|
| Memory 分层 | 1 store（namespace 区分） | 拆 episodic / semantic / source_quality 独立库 |
| Skills | 占位 | 真接入 dimension_discovery 与 questionnaire |
| PII 脱敏 | 正则兜底 | presidio + 中文 NER |
| 报告渲染 | md + weasyprint | 加 PPT / HTML 交互版 |
| 多垂直 | 办公软件 | 加 SaaS / 电商 / 知识工具 |

## 文档

- `Meeting1 + Timeline.md` — 17 天工期细则
- `docs/architecture.html` — LangGraph 架构图
- `docs/decisions.md` — 决策日志
