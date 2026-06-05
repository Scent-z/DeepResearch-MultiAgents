# ✅️
class A2AClient:
    """A2A 客户端（通过 HTTP 与 A2AServer 通信）"""

    def __init__(self, server_url: str):
        """
        初始化 A2A 客户端

        Args:
            server_url: 服务器 URL（例如：http://localhost:5000）
        """
        self.server_url = server_url.rstrip('/')

    # ✅️
    def ask(self, question: str) -> str:
        """
        向 Agent 提问（通用接口）

        Args:
            question: 问题文本

        Returns:
            Agent 的回答
        """
        try:
            import requests
            response = requests.post(
                f"{self.server_url}/ask",
                json={"question": question},
                timeout=30
            )
            response.raise_for_status()  # 用于 检查 HTTP 响应状态码 ，如果请求失败则抛出异常
            return response.json().get("answer", "No response")
        except Exception as e:
            return f"Error communicating with agent: {str(e)}"

    # ✅️
    def execute_skill(self, skill_name: str, text: str = "") -> Dict[str, Any]:
        """
        执行指定技能

        Args:
            skill_name: 技能名称
            text: 输入文本

        Returns:
            执行结果
        """
        try:
            import requests
            response = requests.post(
                f"{self.server_url}/execute/{skill_name}",
                json={"text": text},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"Failed to execute skill: {str(e)}", "status": "error"}

    # ✅️
    def get_info(self) -> Dict[str, Any]:
        """获取 Agent 信息"""
        try:
            import requests
            response = requests.get(f"{self.server_url}/info", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": f"Failed to get agent info: {str(e)}"}

    # ✅️
    def list_skills(self) -> List[str]:
        """列出 Agent 的技能"""
        try:
            import requests
            response = requests.get(f"{self.server_url}/skills", timeout=10)
            response.raise_for_status()
            return response.json().get("skills", [])
        except Exception as e:
            return []