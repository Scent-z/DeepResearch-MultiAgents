# 服务发现中心, 用于注册和查询网络中的智能体服务
# ✅️
class ANPDiscovery:
    """基于 agent-connect 的服务发现实现"""
    
    def __init__(self):
        """初始化服务发现"""
        self._services: Dict[str, ServiceInfo] = {}
        
    def register_service(self, service: ServiceInfo) -> bool:
        """
        注册服务
        
        Args:
            service: 服务信息
            
        Returns:
            是否注册成功
        """
        self._services[service.service_id] = service
        return True
        
    def unregister_service(self, service_id: str) -> bool:
        """
        注销服务
        
        Args:
            service_id: 服务 ID
            
        Returns:
            是否注销成功
        """
        if service_id in self._services:
            del self._services[service_id]
            return True
        return False
        
    def discover_services(
        self,
        service_type: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ServiceInfo]:
        """
        发现服务
        
        Args:
            service_type: 服务类型（可选）
            filters: 过滤条件（可选）
            
        Returns:
            服务列表
        """
        services = list(self._services.values())
        
        # 按类型过滤
        if service_type:
            services = [s for s in services if s.service_type == service_type]
            
        # 按元数据过滤
        if filters:
            def matches_filters(service: ServiceInfo) -> bool:
                for key, value in filters.items():
                    if service.metadata.get(key) != value:
                        return False
                return True
            services = [s for s in services if matches_filters(s)]
            
        return services
        
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """
        获取服务信息
        
        Args:
            service_id: 服务 ID
            
        Returns:
            服务信息，如果不存在则返回 None
        """
        return self._services.get(service_id)
        
    def list_all_services(self) -> List[ServiceInfo]:
        """列出所有服务"""
        return list(self._services.values())