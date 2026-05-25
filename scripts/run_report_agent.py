"""手动测试脚本 —— 用虚拟数据驱动 Report Agent 生成完整竞品分析报告。

用法：
    python scripts/run_report_agent.py
    python scripts/run_report_agent.py --reviewer   # 同时开启豆包终审

生成的文件保存在：
    output/report_飞书.pdf    （PDF 报告）
    output/charts/            （图表图片）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows 控制台强制 UTF-8 输出，防止中文乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))    # 让 `cca` 包可被 import（无需 pip install -e .）
sys.path.insert(0, str(_root / "tests"))  # 让 fixtures 可被 import

import os
os.chdir(_root)

from fixtures.mock_state import make_mock_state
from cca.agents.qa_report import report_node


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Agent 手动测试")
    parser.add_argument("--reviewer", action="store_true", help="开启豆包终审")
    args = parser.parse_args()

    print("正在构造虚拟数据（竞品：钉钉、企业微信）...")
    state = make_mock_state(invoke_reviewer=args.reviewer)

    print("正在调用 Report Agent（会消耗真实 API token）...")
    result = report_node(state)

    print("\n========== 执行结果 ==========")
    print(f"报告状态：{result['report_status']}")
    print(f"PDF 路径：{result['report_pdf_path']}")
    print(f"QA 结果：{result['qa_results']}")

    print("\n========== 报告正文（前 500 字）==========")
    md = result["report_md"] or ""
    print(md[:500])
    if len(md) > 500:
        print(f"\n... （共 {len(md)} 字，完整内容见 PDF）")

    if result["report_pdf_path"]:
        print(f"\n完整报告已保存至：{result['report_pdf_path']}")


if __name__ == "__main__":
    main()
