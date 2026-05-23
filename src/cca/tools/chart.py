"""Report Agent 图表渲染工具。"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool

_CHART_DIR = Path("output/charts")
_PALETTE = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#44BBA4", "#E94F37", "#5C4B8A"]


def _apply_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "figure.facecolor": "white",
        "axes.facecolor": "#f8f9fa",
        "axes.grid": True,
        "grid.color": "white",
        "grid.linewidth": 1.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.titlepad": 16,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.labelsize": 11,
    })


def _save(fig: "plt.Figure", output_path: Path, title: str) -> str:
    import matplotlib.pyplot as plt
    fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"![{title}]({output_path.as_posix()})"


def _render_chart_impl(chart_type: str, title: str, data_json: str, filename: str) -> str:
    _apply_style()
    data = json.loads(data_json)
    _CHART_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _CHART_DIR / f"{filename}.png"

    dispatch = {
        "bar": _bar,
        "horizontal_bar": _horizontal_bar,
        "grouped_bar": _grouped_bar,
        "line": _line,
        "area": _area,
        "pie": _pie,
        "radar": _radar,
    }
    fig = dispatch.get(chart_type, _bar)(title, data)
    return _save(fig, output_path, title)


@tool
def render_chart(chart_type: str, title: str, data_json: str, filename: str) -> str:
    """生成专业图表，返回 Markdown 图片引用字符串。

    chart_type 可选值：
    - "bar"            单系列垂直柱状图
    - "horizontal_bar" 水平柱状图，适合标签较长的对比
    - "grouped_bar"    多系列分组柱状图，适合多产品多维度横向对比
    - "line"           折线图，适合趋势展示
    - "area"           面积图，适合趋势+量级对比
    - "pie"            饼图，适合市场占比展示
    - "radar"          雷达图，强烈推荐用于竞品多维度能力对比

    data_json 格式（JSON 字符串）：
    - bar / horizontal_bar / line / area / pie:
      {"labels": ["钉钉","企业微信"], "values": [4.2, 3.9]}
    - grouped_bar:
      {"labels": ["功能","定价","易用性"],
       "series": {"钉钉": [4,3,4], "企业微信": [3,5,4]}}
    - radar:
      {"labels": ["功能","生态","定价","易用","稳定"],
       "series": {"钉钉": [4,5,3,4,4], "企业微信": [3,4,5,4,3]},
       "max_value": 5}

    Returns:
        Markdown 图片嵌入字符串，可直接粘贴到报告正文。
    """
    return _render_chart_impl(chart_type, title, data_json, filename)


@tool
def render_bar_chart(title: str, categories: str, values: str, filename: str) -> str:
    """生成柱状图，返回可直接嵌入 Markdown 的图片引用字符串。

    在需要跨竞品对比数值型指标时调用，例如 AppStore 评分对比、定价对比。

    Args:
        title: 图表标题。
        categories: JSON 数组字符串，每个元素对应一根柱子的标签。
        values: JSON 数组字符串，数值与 categories 一一对应。
        filename: 输出文件名，不含扩展名。

    Returns:
        Markdown 图片嵌入字符串。
    """
    data_json = json.dumps({"labels": json.loads(categories), "values": json.loads(values)})
    return _render_chart_impl("bar", title, data_json, filename)


def _bar(title: str, data: dict) -> "plt.Figure":
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    values: list[float] = data["values"]

    fig, ax = plt.subplots(figsize=(max(7, len(labels) * 1.4), 5))
    bars = ax.bar(labels, values, color=_PALETTE[:len(labels)],
                  edgecolor="white", linewidth=1.5, width=0.6)
    ax.bar_label(bars, fmt="%.2g", padding=5, fontsize=10, fontweight="bold")
    ax.set_title(title)
    ax.set_ylim(0, max(values) * 1.28)
    if max(len(str(l)) for l in labels) > 4:
        ax.tick_params(axis="x", labelrotation=20)
    plt.tight_layout()
    return fig


def _horizontal_bar(title: str, data: dict) -> "plt.Figure":
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    values: list[float] = data["values"]

    fig, ax = plt.subplots(figsize=(9, max(4, len(labels) * 0.65)))
    bars = ax.barh(labels, values, color=_PALETTE[:len(labels)],
                   edgecolor="white", linewidth=1.5, height=0.6)
    ax.bar_label(bars, fmt="%.2g", padding=5, fontsize=10, fontweight="bold")
    ax.set_title(title)
    ax.set_xlim(0, max(values) * 1.28)
    ax.invert_yaxis()
    plt.tight_layout()
    return fig


def _grouped_bar(title: str, data: dict) -> "plt.Figure":
    import numpy as np
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    series: dict[str, list[float]] = data["series"]
    n_series = len(series)
    width = 0.7 / n_series
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.5), 5))
    for i, (name, vals) in enumerate(series.items()):
        offset = (i - n_series / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width * 0.9, label=name,
                      color=_PALETTE[i % len(_PALETTE)], edgecolor="white")
        ax.bar_label(bars, fmt="%.2g", padding=3, fontsize=9)

    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_ylim(0, max(v for vals in series.values() for v in vals) * 1.32)
    plt.tight_layout()
    return fig


def _line(title: str, data: dict) -> "plt.Figure":
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    fig, ax = plt.subplots(figsize=(9, 5))

    if "series" in data:
        for i, (name, vals) in enumerate(data["series"].items()):
            ax.plot(labels, vals, marker="o", linewidth=2.5, markersize=7,
                    color=_PALETTE[i % len(_PALETTE)], label=name)
        ax.legend(loc="best", framealpha=0.9)
    else:
        values: list[float] = data["values"]
        ax.plot(labels, values, marker="o", linewidth=2.5, markersize=7, color=_PALETTE[0])
        for x, y in zip(labels, values):
            ax.annotate(f"{y:.2g}", (x, y), textcoords="offset points",
                        xytext=(0, 9), ha="center", fontsize=9, fontweight="bold")
    ax.set_title(title)
    plt.tight_layout()
    return fig


def _area(title: str, data: dict) -> "plt.Figure":
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    xs = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(9, 5))

    if "series" in data:
        for i, (name, vals) in enumerate(data["series"].items()):
            color = _PALETTE[i % len(_PALETTE)]
            ax.fill_between(xs, vals, alpha=0.2, color=color)
            ax.plot(xs, vals, marker="o", linewidth=2.5, color=color, label=name)
        ax.legend(loc="best", framealpha=0.9)
    else:
        values: list[float] = data["values"]
        ax.fill_between(xs, values, alpha=0.25, color=_PALETTE[0])
        ax.plot(xs, values, marker="o", linewidth=2.5, color=_PALETTE[0])

    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    plt.tight_layout()
    return fig


def _pie(title: str, data: dict) -> "plt.Figure":
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    values: list[float] = data["values"]

    fig, ax = plt.subplots(figsize=(7, 6))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=_PALETTE[:len(values)], startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
        pctdistance=0.8,
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_fontweight("bold")
    ax.set_title(title, pad=20)
    plt.tight_layout()
    return fig


def _radar(title: str, data: dict) -> "plt.Figure":
    import numpy as np
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    series: dict[str, list[float]] = data["series"]
    max_val: float = float(data.get("max_value", 5))
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"polar": True})
    ax.set_facecolor("#f8f9fa")
    for i, (name, vals) in enumerate(series.items()):
        closed = list(vals) + [vals[0]]
        color = _PALETTE[i % len(_PALETTE)]
        ax.fill(angles, closed, alpha=0.15, color=color)
        ax.plot(angles, closed, linewidth=2.5, color=color, label=name, marker="o", markersize=5)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, max_val)
    ticks = np.linspace(0, max_val, 6)[1:]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{v:.2g}" for v in ticks], fontsize=8)
    ax.grid(color="white", linewidth=1.5)
    ax.set_title(title, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15), framealpha=0.9)
    plt.tight_layout()
    return fig
