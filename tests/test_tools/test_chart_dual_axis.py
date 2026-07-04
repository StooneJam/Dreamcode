"""dual_axis_bar: missing values (None) render as a gap, not a misleading 0."""
from __future__ import annotations

import json
import math
from pathlib import Path

from cca.tools.chart import _plot_value, render_chart


class TestPlotValue:
    def test_none_becomes_nan(self):
        assert math.isnan(_plot_value(None))

    def test_number_passthrough(self):
        assert _plot_value(4.5) == 4.5
        assert _plot_value(0) == 0.0


class TestDualAxisMissing:
    def test_none_values_render_without_crash(self):
        # Mixue/Gu Ming's ratings are missing, Auntea Jenny has data: missing shouldn't render as a 0 bar
        data = {
            "labels": ["蜜雪冰城", "古茗", "沪上阿姨"],
            "left": {"name": "评论量（条）", "values": [None, None, 89000]},
            "right": {"name": "口碑评分", "values": [None, 4.2, 4.9]},
        }
        out = render_chart.invoke({
            "chart_type": "dual_axis_bar",
            "title": "用户口碑评分与评论量",
            "data_json": json.dumps(data, ensure_ascii=False),
            "filename": "test_dual_axis_missing",
        })
        assert "test_dual_axis_missing" in out
        assert Path("output/charts/test_dual_axis_missing.png").exists()

    def test_all_missing_does_not_crash(self):
        data = {
            "labels": ["A", "B"],
            "left": {"name": "评论量", "values": [None, None]},
            "right": {"name": "评分", "values": [None, None]},
        }
        out = render_chart.invoke({
            "chart_type": "dual_axis_bar",
            "title": "全缺失",
            "data_json": json.dumps(data, ensure_ascii=False),
            "filename": "test_dual_axis_all_missing",
        })
        assert "test_dual_axis_all_missing" in out
