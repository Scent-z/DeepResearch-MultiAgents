try:
    from a2a.client import A2AClient
    from a2a.types import Message
    A2A_AVAILABLE = True
except ImportError:
    A2A_AVAILABLE = False
    A2AClient = None
    Message = None

class AgentNetwork:
    """基于官方 a2a-sdk 库的 Agent 网络（概念性实现）"""

    def __init__(self, name: str = "Agent Network"):
        """
        初始化 Agent 网络

        Args:
            name: 网络名称
        """
        self.name = name
        self.agents = {}  # agent_name -> agent_url

    # ✅️
    def add_agent(self, agent_name: str, agent_url: str):
        """
        添加 Agent 到网络

        Args:
            agent_name: Agent 名称
            agent_url: Agent URL
        """
        self.agents[agent_name] = agent_url

    # ✅️
    def get_agent(self, agent_name: str) -> A2AClient:
        """
        获取网络中的 Agent

        Args:
            agent_name: Agent 名称

        Returns:
            A2A 客户端实例
        """
        if agent_name not in self.agents:
            raise ValueError(f"Agent '{agent_name}' not found in network")

        return A2AClient(self.agents[agent_name])

    # ✅️
    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent"""
        return [
            {"name": name, "url": url}
            for name, url in self.agents.items()
        ]

    # ✅️
    def discover_agents(self, urls: List[str]) -> int:
        """
        从 URL 列表中发现 Agent

        Args:
            urls: URL 列表

        Returns:
            发现的 Agent 数量
        """
        discovered = 0
        for url in urls:
            try:
                client = A2AClient(url)
                info = client.get_info()
                if "name" in info and "error" not in info:
                    self.add_agent(info["name"], url)
                    discovered += 1
            except Exception:
                continue
        return discovered