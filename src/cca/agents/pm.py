"""
PM Agent 主要职责：

    分析用户输入，明确输入产品信息

    结合输入产品，联网获取产品赛道与竞品名单

    分析产品赛道和yaml配置, 明确产品分析维度

    整合信息, 制定Collector与Insighter的task_plan

    Review Collector, Insighter和Analyst的输出, 更新 QAResult 并制定新的task_plan/AnalystTask

    Collector与Insighter输出通过后, 根据分析结果和yaml配置, 制定 Analyst 的任务AnalystTask

    Analyst 输出通过后, 根据分析结果和yaml配置, 制定ReportTask并发送给Reporter
"""

