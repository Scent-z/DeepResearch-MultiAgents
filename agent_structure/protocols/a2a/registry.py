class AgentRegistry:
    """基于官方 a2a-sdk 库的 Agent 注册中心（概念性实现）"""

    def __init__(self, name: str = "Agent Registry", description: str = "Central agent registry"):
        """
        初始化 Agent 注册中心

        Args:
            name: 注册中心名称
            description: 注册中心描述
        """
        self.name = name
        self.description = description
        self.registered_agents = {}

    # ✅️
    def register_agent(self, agent_name: str, agent_url: str, metadata: Optional[Dict[str, Any]] = None):
        """注册 Agent"""
        self.registered_agents[agent_name] = {
            "url": agent_url,
            "metadata": metadata or {},
            "registered_at": __import__("datetime").datetime.now().isoformat()
        }

    # ✅️
    def unregister_agent(self, agent_name: str):
        """注销 Agent"""
        if agent_name in self.registered_agents:
            del self.registered_agents[agent_name]

    # ✅️
    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有注册的 Agent"""
        return [
            {"name": name, **info}
            for name, info in self.registered_agents.items()
        ]

    # ✅️
    def find_agent(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """查找特定 Agent"""
        return self.registered_agents.get(agent_name)

    # ✅️
    def get_info(self) -> Dict[str, Any]:
        """获取注册中心信息"""
        return {
            "name": self.name,
            "description": self.description,
            "protocol": "A2A",
            "type": "registry",
            "registered_agents": len(self.registered_agents)
        }