"""
Day 1 (5.20) Hello World —— 跑通最小 LangGraph 图。

目标：验证 LangGraph + DeepSeek + GPT-5 三件套连通。
跑通后，本文件保留作为后续骨架参考。

用法：
    conda activate multi-agent
    python scripts/hello_world.py

TODO（下一步会填充）：
    1. 加载 .env
    2. 用 ChatOpenAI 配置两个客户端（gpt-5 / deepseek 兼容接口）
    3. 定义最小 State（TypedDict）
    4. 3 节点 LangGraph：input -> deepseek_node -> gpt5_node -> END
    5. 调用 graph.invoke({...}) 并打印结果
"""

if __name__ == "__main__":
    print("hello_world placeholder — waiting for fill-in")
