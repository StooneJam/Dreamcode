"""
Day 1 (5.20) Hello World —— 跑通最小 LangGraph 图。

目标：验证 LangGraph + DeepSeek + OpenAI + 结构化输出 四件套连通。

用法：
    conda activate multi-agent
    python scripts/hello_world.py          # 默认分析"飞书"
    python scripts/hello_world.py 钉钉
"""

import sys
import os
from typing import TypedDict, List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field

# override=True：强制用 .env 覆盖系统/conda 里可能残留的旧环境变量
load_dotenv(override=True)

# ── 1. LLM 客户端 ─────────────────────────────────────────────────────────────

deepseek_llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.5,
)

openai_llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.3,
)

# ── 2. 结构化输出 Schema ──────────────────────────────────────────────────────


class AnalysisDimension(BaseModel):
    """Agent 自主发现并选择的单个分析维度"""

    name: str = Field(description="维度名称，如「定价策略」「生态绑定」「核心用户画像」")
    finding: str = Field(description="该维度下的核心发现，2-3 句，有观点有依据")
    score: Optional[float] = Field(
        None, description="0-10 分评分（可量化时给出，否则为 null）"
    )


class ProductAnalysis(BaseModel):
    """DeepSeek 对产品的结构化深度分析（Agent 自主决定分析哪些维度）"""

    product_name: str
    positioning: str = Field(description="一句话市场定位")
    dimensions: List[AnalysisDimension] = Field(
        description=(
            "Agent 自主选择的分析维度，至少 5 个，不限于固定框架，"
            "可覆盖功能、用户、定价、增长、生态、技术壁垒等任意角度"
        )
    )
    core_strength: str = Field(description="最核心的竞争优势，1 句")
    core_weakness: str = Field(description="最致命的短板或风险，1 句")


class CompetitiveEdge(BaseModel):
    """OpenAI 对竞争格局的独立判断"""

    vs_competitors: List[str] = Field(
        description="与主要竞品的关键差异，每条对应一个竞品，格式：「vs XX：差异点」"
    )
    strategic_recommendation: str = Field(
        description="如果你是产品负责人，当前最优先要做的一件事"
    )
    threat_level: str = Field(description="当前市场威胁等级：低 / 中 / 高")


# ── 3. Graph State ────────────────────────────────────────────────────────────


class HelloState(TypedDict):
    product_name: str
    product_analysis: dict   # ProductAnalysis.model_dump() 后存入
    competitive_edge: dict   # CompetitiveEdge.model_dump() 后存入


# ── 4. 节点函数 ───────────────────────────────────────────────────────────────


def deepseek_node(state: HelloState) -> dict:
    product = state["product_name"]
    print(f"\n[DeepSeek ▶] 自主探索分析维度：{product}")

    # deepseek-reasoner 既不支持 json_schema 也不支持 tool_choice，
    # 只能用 json_mode + prompt 里显式声明字段名，让模型按结构输出
    structured_llm = deepseek_llm.with_structured_output(ProductAnalysis, method="json_mode")
    result: ProductAnalysis = structured_llm.invoke(
        f"你是竞品分析专家，专注办公协作软件领域。\n"
        f"请对产品【{product}】进行深度分析，自主选择最有价值的分析维度（至少5个，不限于固定框架）。\n\n"
        f"必须严格按以下 JSON 结构输出，字段名不可更改：\n"
        f'{{\n'
        f'  "product_name": "{product}",\n'
        f'  "positioning": "一句话市场定位",\n'
        f'  "dimensions": [\n'
        f'    {{\n'
        f'      "name": "维度名称（如定价策略、目标用户、生态绑定等）",\n'
        f'      "finding": "该维度下的核心发现，2-3句",\n'
        f'      "score": 8.5\n'
        f'    }}\n'
        f'  ],\n'
        f'  "core_strength": "最核心的竞争优势，1句",\n'
        f'  "core_weakness": "最致命的短板，1句"\n'
        f"}}"
    )

    print(f"[DeepSeek ✓] 发现 {len(result.dimensions)} 个分析维度")
    for d in result.dimensions:
        score_str = f" [{d.score}/10]" if d.score is not None else ""
        print(f"   • {d.name}{score_str}")

    return {"product_analysis": result.model_dump()}


def openai_node(state: HelloState) -> dict:
    print(f"\n[OpenAI  ▶] 生成竞争格局判断")

    analysis = state["product_analysis"]
    dimension_summary = [
        f"{d['name']}: {d['finding']}" for d in analysis["dimensions"]
    ]

    structured_llm = openai_llm.with_structured_output(CompetitiveEdge)
    result: CompetitiveEdge = structured_llm.invoke(
        f"基于以下产品分析，给出竞争格局的独立判断：\n\n"
        f"产品：{analysis['product_name']}\n"
        f"定位：{analysis['positioning']}\n"
        f"核心优势：{analysis['core_strength']}\n"
        f"核心短板：{analysis['core_weakness']}\n"
        f"分析维度：\n" + "\n".join(f"- {s}" for s in dimension_summary)
    )

    print(f"[OpenAI  ✓] 威胁等级：{result.threat_level}")
    return {"competitive_edge": result.model_dump()}


# ── 5. 构建图 ─────────────────────────────────────────────────────────────────


def build_graph():
    graph = StateGraph(HelloState)

    graph.add_node("deepseek", deepseek_node)
    graph.add_node("openai", openai_node)

    graph.add_edge(START, "deepseek")
    graph.add_edge("deepseek", "openai")
    graph.add_edge("openai", END)

    return graph.compile()


# ── 6. 入口 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    product = sys.argv[1] if len(sys.argv) > 1 else "飞书"

    print("=" * 55)
    print(f"  竞品分析 Hello World  |  目标产品：{product}")
    print("=" * 55)

    app = build_graph()
    result = app.invoke({
        "product_name": product,
        "product_analysis": {},
        "competitive_edge": {},
    })

    analysis = result["product_analysis"]
    edge = result["competitive_edge"]

    print("\n" + "=" * 55)
    print(f"【{analysis['product_name']}】竞品分析结构化输出")
    print("=" * 55)
    print(f"\n定位：{analysis['positioning']}")
    print(f"核心优势：{analysis['core_strength']}")
    print(f"核心短板：{analysis['core_weakness']}")

    print(f"\n── 分析维度（DeepSeek 自主探索）{'─' * 15}")
    for d in analysis["dimensions"]:
        score_str = f"  [{d['score']}/10]" if d.get("score") is not None else ""
        print(f"  ▪ {d['name']}{score_str}")
        print(f"    {d['finding']}")

    print(f"\n── 竞争格局（OpenAI 独立判断）{'─' * 16}")
    print(f"  威胁等级：{edge['threat_level']}")
    for item in edge["vs_competitors"]:
        print(f"  • {item}")
    print(f"\n  战略建议：{edge['strategic_recommendation']}")

    print("\n两个模型均已连通，LangGraph 图跑通！")
