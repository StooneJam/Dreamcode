"""Regenerate report charts using the fixed chart renderer.

Run after updating src/cca/tools/chart.py to apply layout fixes to existing charts.

The radar chart data is reconstructed from the ranked scores in the report.
For the dual_axis (App Store) chart, re-run the full demo to get exact scraped values.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cca.tools.chart import _render_chart_impl


def regen_radar() -> None:
    # Data reconstructed from report section 4.1 dimension rankings (n=3 products):
    # 视频会议: 飞书1st(3), 企业微信2nd(2), 钉钉3rd(1)
    # AI能力:   飞书1st(3), 钉钉2nd(2), 企业微信3rd(1)
    # 平台支持: 钉钉1st(3), 飞书2nd(2), 企业微信3rd(1)
    data = json.dumps({
        "labels": ["视频会议", "AI能力", "平台支持"],
        "series": {
            "飞书": [3, 3, 2],
            "钉钉": [1, 2, 3],
            "企业微信": [2, 1, 1],
        },
        "max_value": 3,
    }, ensure_ascii=False)
    result = _render_chart_impl(
        "radar",
        "各维度竞争力对比（排名转换得分，满分 3 分）",
        data,
        "radar_competitiveness_3dims",
    )
    print(f"radar chart regenerated: {result}")


if __name__ == "__main__":
    regen_radar()
    print(
        "\nNote: the dual_axis App Store chart (dual_axis_reviews_ratings.png) requires "
        "the actual scraped review counts. Re-run the demo to regenerate it with correct data."
    )
