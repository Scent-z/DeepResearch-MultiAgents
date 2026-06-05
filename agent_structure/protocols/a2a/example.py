"""
基于官方 a2a-sdk 库的 A2A 协议实现

使用官方 a2a-sdk 库实现 Agent-to-Agent Protocol 功能。
官方仓库: https://github.com/a2aproject/a2a-python
安装: pip install a2a-sdk
"""
# ✅️

from typing import Dict, Any, List, Optional
from network import A2A_AVAILABLE
from server import A2AServer

# ✅️
# 示例：创建一个简单的 A2A Agent
def create_example_agent() -> A2AServer:
    """创建一个示例 A2A Agent"""
    if not A2A_AVAILABLE:
        raise ImportError(
            "Cannot create example agent: a2a-sdk library not available. "
            "Install it with: pip install a2a-sdk"
        )

    server = A2AServer(
        name="Example A2A Agent",
        description="A simple example A2A agent",
        version="1.0.0",
        capabilities={"chat": True, "calculation": True}
    )

    # 添加计算技能
    def calculator_skill(text: str) -> str:
        """计算数学表达式"""
        # 从文本中提取表达式
        import re
        match = re.search(r'calculate\s+(.+)', text, re.IGNORECASE)
        if match:
            expression = match.group(1).strip()
            try:
                # 安全的表达式求值（仅支持基本运算）
                allowed_chars = set("0123456789+-*/() .")
                if not all(c in allowed_chars for c in expression):
                    return "Error: Invalid characters in expression"
                result = eval(expression)
                return f"The result is: {result}"
            except Exception as e:
                return f"Calculation error: {str(e)}"
        return "Please provide an expression to calculate"

    server.add_skill("calculate", calculator_skill)

    # 添加问候技能
    def greeting_skill(text: str) -> str:
        """生成问候语"""
        import re
        match = re.search(r'hello|hi|greet', text, re.IGNORECASE)
        if match:
            return "Hello! I'm an A2A agent. How can I help you today?"
        return "Hi there!"

    server.add_skill("greet", greeting_skill)

    return server


if __name__ == "__main__":
    try:
        # 创建并运行示例 Agent
        agent = create_example_agent()
        print(f"🚀 Starting {agent.name}...")
        print(f"📝 {agent.description}")
        print(f"🔌 Protocol: A2A")
        print(f"📡 Version: {agent.version}")
        print(f"🛠️ Skills: {list(agent.skills.keys())}")
        print()
        agent.run(host="0.0.0.0", port=5000)
    except ImportError as e:
        print(f"❌ {e}")
        print("💡 Install the A2A SDK: pip install a2a-sdk")
        print("📖 Official repository: https://github.com/a2aproject/a2a-python")

