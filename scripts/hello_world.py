"""Day 1 Hello World — LangGraph + DeepSeek + OpenAI + Doubao 三家族联通验证。

DeepSeek 探维度 → OpenAI 给竞争格局 → Doubao 跨家族审一致性。

用法:
    python scripts/hello_world.py           # 默认分析"飞书"
    python scripts/hello_world.py 钉钉
"""
from __future__ import annotations

import os
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

# override=True 防止 .env 被系统/conda 残留变量覆盖
load_dotenv(override=True)


deepseek_llm = ChatOpenAI(
    model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.5,
    timeout=30,
)

openai_llm = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0.3,
    timeout=30,
)

# Doubao 走火山方舟 Ark OpenAI 兼容协议
doubao_llm = ChatOpenAI(
    model=os.getenv("DOUBAO_MODEL", "Doubao-Seed-2.0-lite"),
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    temperature=0.2,
    timeout=30,
)


class AnalysisDimension(BaseModel):
    name: str = Field(description="维度名称，如「定价策略」「生态绑定」「核心用户画像」")
    finding: str = Field(description="该维度下的核心发现，2-3 句，有观点有依据")
    score: float | None = Field(None, description="0-10 分评分（可量化时给出，否则 null）")


class ProductAnalysis(BaseModel):
    product_name: str
    positioning: str = Field(description="一句话市场定位")
    dimensions: list[AnalysisDimension] = Field(
        description=(
            "Agent 自主选择的分析维度，至少 5 个，不限于固定框架，"
            "可覆盖功能、用户、定价、增长、生态、技术壁垒等任意角度"
        )
    )
    core_strength: str = Field(description="最核心的竞争优势，1 句")
    core_weakness: str = Field(description="最致命的短板或风险，1 句")


class CompetitiveEdge(BaseModel):
    vs_competitors: list[str] = Field(
        description="与主要竞品的关键差异，每条对应一个竞品，格式：「vs XX：差异点」"
    )
    strategic_recommendation: str = Field(description="如果你是产品负责人，当前最优先要做的一件事")
    threat_level: str = Field(description="当前市场威胁等级：低 / 中 / 高")


class ReviewVerdict(BaseModel):
    """Doubao 跨家族审查产出。"""
    consistent: bool = Field(description="DeepSeek 维度与 OpenAI 战略判断是否自洽")
    contradictions: list[str] = Field(
        default_factory=list,
        description="发现的矛盾点；自洽时为空列表"
    )
    overall_note: str = Field(description="一句话总评")


class HelloState(TypedDict):
    product_name: str
    product_analysis: dict
    competitive_edge: dict
    review_verdict: dict


def deepseek_node(state: HelloState) -> dict:
    """自主探索分析维度，输出 ProductAnalysis 结构化结果。"""
    product = state["product_name"]
    # deepseek-chat 走 json_mode：不支持 json_schema/tool_choice，需 prompt 显式声明字段
    structured = deepseek_llm.with_structured_output(ProductAnalysis, method="json_mode")
    result: ProductAnalysis = structured.invoke(
        f"你是竞品分析专家，专注办公协作软件领域。\n"
        f"请对产品【{product}】进行深度分析，自主选择最有价值的分析维度（至少5个，不限于固定框架）。\n\n"
        f"必须严格按以下 JSON 结构输出，字段名不可更改：\n"
        f'{{\n'
        f'  "product_name": "{product}",\n'
        f'  "positioning": "一句话市场定位",\n'
        f'  "dimensions": [\n'
        f'    {{"name": "维度名", "finding": "2-3句发现", "score": 8.5}}\n'
        f'  ],\n'
        f'  "core_strength": "最核心优势，1句",\n'
        f'  "core_weakness": "最致命短板，1句"\n'
        f"}}"
    )
    return {"product_analysis": result.model_dump()}


def openai_node(state: HelloState) -> dict:
    """基于产品分析输出 CompetitiveEdge 竞争格局判断。"""
    analysis = state["product_analysis"]
    dim_summary = "\n".join(f"- {d['name']}: {d['finding']}" for d in analysis["dimensions"])
    structured = openai_llm.with_structured_output(CompetitiveEdge)
    result: CompetitiveEdge = structured.invoke(
        f"基于以下产品分析，给出竞争格局的独立判断：\n\n"
        f"产品：{analysis['product_name']}\n"
        f"定位：{analysis['positioning']}\n"
        f"核心优势：{analysis['core_strength']}\n"
        f"核心短板：{analysis['core_weakness']}\n"
        f"分析维度：\n{dim_summary}"
    )
    return {"competitive_edge": result.model_dump()}


def doubao_node(state: HelloState) -> dict:
    """Doubao 跨家族审查：检查 DeepSeek 维度与 OpenAI 战略是否自洽。"""
    analysis = state["product_analysis"]
    edge = state["competitive_edge"]
    dim_list = "、".join(d["name"] for d in analysis["dimensions"])
    structured = doubao_llm.with_structured_output(ReviewVerdict, method="json_mode")
    result: ReviewVerdict = structured.invoke(
        f"你是独立审查员，与生成者不同家族，不预设立场。\n"
        f"请审查以下竞品分析的内部自洽性：\n\n"
        f"产品：{analysis['product_name']}\n"
        f"定位：{analysis['positioning']}\n"
        f"OpenAI 威胁等级：{edge['threat_level']}\n"
        f"OpenAI 战略建议：{edge['strategic_recommendation']}\n\n"
        f"判断维度集合与战略判断是否自洽，列出任何矛盾点。\n"
        f"严格按以下 JSON 输出：\n"
        f'{{"consistent": true, "contradictions": [], "overall_note": "一句话总评"}}'
    )
    return {"review_verdict": result.model_dump()}


def build_graph():
    g = StateGraph(HelloState)
    g.add_node("deepseek", deepseek_node)
    g.add_node("openai", openai_node)
    g.add_node("doubao", doubao_node)
    g.add_edge(START, "deepseek")
    g.add_edge("deepseek", "openai")
    g.add_edge("openai", "doubao")
    g.add_edge("doubao", END)
    return g.compile()


app = build_graph()


def main() -> None:
    product = sys.argv[1] if len(sys.argv) > 1 else "飞书"
    result = app.invoke({
        "product_name": product,
        "product_analysis": {},
        "competitive_edge": {},
        "review_verdict": {},
    })
    analysis = result["product_analysis"]
    edge = result["competitive_edge"]
    verdict = result["review_verdict"]

    print(f"产品: {analysis['product_name']}")
    print(f"定位: {analysis['positioning']}")
    print(f"核心优势: {analysis['core_strength']}")
    print(f"核心短板: {analysis['core_weakness']}")
    print(f"\n分析维度（{len(analysis['dimensions'])}）:")
    for d in analysis["dimensions"]:
        score = f" [{d['score']}/10]" if d.get("score") is not None else ""
        print(f"  {d['name']}{score}")
        print(f"    {d['finding']}")
    print(f"\n威胁等级: {edge['threat_level']}")
    for item in edge["vs_competitors"]:
        print(f"  {item}")
    print(f"\n战略建议: {edge['strategic_recommendation']}")
    print(f"\nDoubao 审查: 自洽={verdict['consistent']}")
    if verdict["contradictions"]:
        print("矛盾点:")
        for c in verdict["contradictions"]:
            print(f"  {c}")
    print(f"总评: {verdict['overall_note']}")


if __name__ == "__main__":
    main()
