"""Report Agent 图表渲染工具。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_core.tools import tool

# Windows：numpy/torch 带入 Intel OpenMP (libiomp5md.dll)，matplotlib 带入 LLVM OpenMP
# (libomp.dll)，两者在同一进程内均初始化会导致 OMP Error #15 / exit code 3。
# setdefault 仅在未设置时写入，不覆盖用户的显式配置。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

_CHART_DIR = Path("output/charts")
_PALETTE = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#44BBA4", "#E94F37", "#5C4B8A"]
_CJK_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _fmt_num(v: float) -> str:
    """Format a number for chart labels without scientific notation."""
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _plot_value(v: float | None) -> float:
    """缺失值 → nan，让 matplotlib 自然留缺口（柱不画、折线断开），不伪装成 0。"""
    return float("nan") if v is None else float(v)


def _apply_style() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    # 动态注册 CJK 字体并获取实际注册名，避免名字匹配失败导致回退到 DejaVu Sans
    detected: list[str] = []
    for p in _CJK_FONT_CANDIDATES:
        if Path(p).exists():
            fm.fontManager.addfont(p)
            detected = list({f.name for f in fm.fontManager.ttflist if f.fname == p})
            break

    plt.rcParams.update({
        "font.sans-serif": detected + ["Noto Sans CJK SC", "Noto Sans SC", "Microsoft YaHei", "SimHei", "DejaVu Sans"],
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
    stem = filename.removesuffix(".png")
    output_path = _CHART_DIR / f"{stem}.png"

    dispatch = {
        "bar": _bar,
        "horizontal_bar": _horizontal_bar,
        "grouped_bar": _grouped_bar,
        "dual_axis_bar": _dual_axis_bar,
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
    - "dual_axis_bar"  双轴柱状图，左轴大量级（如评论量），右轴小量级（如评分）
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
    - dual_axis_bar:
      {"labels": ["飞书","钉钉","企业微信"],
       "left":  {"name": "评论量（条）", "values": [85000, 210000, 95000]},
       "right": {"name": "App Store 评分", "values": [4.6, 4.4, 4.2]}}
    - radar:
      {"labels": ["功能","生态","定价","易用","稳定"],
       "series": {"钉钉": [4,5,3,4,4], "企业微信": [3,4,5,4,3]},
       "max_value": 5}

    Returns:
        Markdown 图片嵌入字符串，可直接粘贴到报告正文。
    """
    return _render_chart_impl(chart_type, title, data_json, filename)


def _cjk_font_path() -> str | None:
    """词云渲染中文必须显式给字体；按优先级找系统 CJK 字体。"""
    candidates = ["msyh.ttc", "simhei.ttf", "simsun.ttc"]
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in candidates:
        path = fonts_dir / name
        if path.exists():
            return str(path)
    return None


@tool
def render_wordcloud(title: str, word_freq_json: str, filename: str) -> str:
    """生成词云 PNG，返回 Markdown 图片引用字符串。

    用于可视化用户评论高频词，比柱状图更直观地呈现口碑焦点。

    Args:
        title: 词云标题，如 "钉钉用户好评词云"。
        word_freq_json: JSON 对象字符串 {"词": 权重}，直接取自 profile 的
            sentiment.positive_word_freq 或 negative_word_freq，不要自己编词频。
        filename: 输出文件名，不含扩展名。

    Returns:
        Markdown 图片嵌入字符串；词频为空时返回提示文本（不出图）。
    """
    freq = json.loads(word_freq_json)
    if not freq:
        return "词频为空（样本不足或未做情感分组），跳过词云渲染。"

    font_path = _cjk_font_path()
    if font_path is None:
        return "系统缺少中文字体，无法渲染词云；请改用柱状图呈现高频词。"

    from wordcloud import WordCloud

    _CHART_DIR.mkdir(parents=True, exist_ok=True)
    stem = filename.removesuffix(".png")
    output_path = _CHART_DIR / f"{stem}.png"

    wc = WordCloud(
        font_path=font_path, width=900, height=500,
        background_color="white", colormap="viridis",
        max_words=60, prefer_horizontal=0.9,
    ).generate_from_frequencies(freq)
    wc.to_file(str(output_path))
    return f"![{title}]({output_path.as_posix()})"


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
    ax.bar_label(bars, labels=[_fmt_num(v) for v in values], padding=5, fontsize=10, fontweight="bold")
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
    ax.bar_label(bars, labels=[_fmt_num(v) for v in values], padding=5, fontsize=10, fontweight="bold")
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
        ax.bar_label(bars, labels=[_fmt_num(v) for v in vals], padding=3, fontsize=9)

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
            ax.annotate(_fmt_num(y), (x, y), textcoords="offset points",
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


def _dual_axis_bar(title: str, data: dict) -> "plt.Figure":
    """左轴柱状（大量级），右轴折线+点（小量级）。"""
    import numpy as np
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    left: dict = data["left"]
    right: dict = data["right"]
    x = np.arange(len(labels))
    width = 0.5

    fig, ax1 = plt.subplots(figsize=(max(7, len(labels) * 1.8), 5))
    ax2 = ax1.twinx()
    # ax2 is transparent so ax1's background shows through without double-grid strips
    ax2.set_facecolor("none")
    ax2.grid(False)

    left_vals = [_plot_value(v) for v in left["values"]]
    bars = ax1.bar(x, left_vals, width, color=_PALETTE[0],
                   edgecolor="white", linewidth=1.5, label=left["name"], alpha=0.85)
    # 缺失（None→nan）不画柱、不标 0；标签留空，缺口下面单独标「数据缺失」
    bar_labels = ["" if not np.isfinite(v) else f"{int(round(v))}" for v in left_vals]
    ax1.bar_label(bars, labels=bar_labels, padding=5, fontsize=9, fontweight="bold")
    ax1.set_ylabel(left["name"], color=_PALETTE[0], fontsize=11)
    ax1.tick_params(axis="y", labelcolor=_PALETTE[0])
    finite_left = [v for v in left_vals if np.isfinite(v)]
    top = (max(finite_left) if finite_left else 1) * 1.3
    ax1.set_ylim(0, top)
    ax1.spines["top"].set_visible(False)

    right_vals = [_plot_value(v) for v in right["values"]]
    ax2.plot(x, right_vals, color=_PALETTE[1], marker="o",
             linewidth=2.5, markersize=8, label=right["name"], zorder=5)
    for xi, yi in zip(x, right_vals):
        if not np.isfinite(yi):
            continue
        ax2.annotate(_fmt_num(yi), (xi, yi), textcoords="offset points",
                     xytext=(0, 10), ha="center", fontsize=9, fontweight="bold",
                     color=_PALETTE[1])
    ax2.set_ylabel(right["name"], color=_PALETTE[1], fontsize=11)
    ax2.tick_params(axis="y", labelcolor=_PALETTE[1])
    finite_right = [v for v in right_vals if np.isfinite(v)]
    if finite_right:
        rmin, rmax = min(finite_right), max(finite_right)
        margin = (rmax - rmin) * 0.5 or 0.5
        ax2.set_ylim(max(0, rmin - margin), rmax + margin)
    ax2.spines["top"].set_visible(False)

    # 评分与评论量都缺的类目在基线标「数据缺失」，替代误导性的 0 柱
    for xi, lv, rv in zip(x, left_vals, right_vals):
        if not np.isfinite(lv) and not np.isfinite(rv):
            ax1.annotate("数据缺失", (xi, top * 0.02), ha="center", va="bottom",
                         fontsize=8, color="#999999")

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=11)
    ax1.set_title(title)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.9)

    plt.tight_layout()
    return fig


def _radar(title: str, data: dict) -> "plt.Figure":
    import numpy as np
    import matplotlib.pyplot as plt
    labels: list[str] = data["labels"]
    series: dict[str, list[float]] = data["series"]
    max_val: float = float(data.get("max_value", 5))
    n = len(labels)
    n_series = len(series)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})
    ax.set_facecolor("#f8f9fa")
    for i, (name, vals) in enumerate(series.items()):
        closed = list(vals) + [vals[0]]
        color = _PALETTE[i % len(_PALETTE)]
        ax.fill(angles, closed, alpha=0.15, color=color)
        ax.plot(angles, closed, linewidth=2.5, color=color, label=name, marker="o", markersize=5)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11)
    # Push dimension labels outside the radar ring so they don't overlap the plot area
    ax.tick_params(axis="x", pad=20)
    ax.set_ylim(0, max_val)
    ticks = np.linspace(0, max_val, 6)[1:]
    ax.set_yticks(ticks)
    ax.set_yticklabels([_fmt_num(v) for v in ticks], fontsize=8)
    ax.grid(color="white", linewidth=1.5)
    ax.set_title(title, pad=30)
    # Place legend below the chart (fig-level) to avoid overlapping the polar area
    handles, leg_labels = ax.get_legend_handles_labels()
    fig.legend(handles, leg_labels, loc="lower center", ncol=n_series,
               framealpha=0.9, fontsize=10, bbox_to_anchor=(0.5, 0.01))
    plt.tight_layout(rect=[0, 0.1, 1, 1])
    return fig
