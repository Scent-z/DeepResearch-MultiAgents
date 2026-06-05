"""
基于 agent-connect 库的 ANP 协议实现

使用 agent-connect 库 (v0.3.7) 实现 Agent Network Protocol 功能。

注意：agent-connect 是一个底层的网络协议库，提供了加密、认证等功能。
这里我们创建一个简化的包装器，使其更易于使用。
"""

# 由于 agent-connect 的 API 比较底层，我们创建一个简化的实现
# 实际使用时可以根据需要调用 agent-connect 的具体模块
# 示例：创建一个简单的 ANP 网络
def create_example_network() -> ANPNetwork:
    """创建一个示例 ANP 网络"""
    network = ANPNetwork(network_id="example_network")
    
    # 添加节点
    network.add_node("node1", "http://localhost:8001", {"type": "agent", "role": "coordinator"})
    network.add_node("node2", "http://localhost:8002", {"type": "agent", "role": "worker"})
    network.add_node("node3", "http://localhost:8003", {"type": "agent", "role": "worker"})
    
    # 连接节点
    network.connect_nodes("node1", "node2")
    network.connect_nodes("node1", "node3")
    network.connect_nodes("node2", "node3")
    
    return network


if __name__ == "__main__":
    # 创建示例网络
    network = create_example_network()
    print(f"🌐 ANP Network: {network.network_id}")
    print(f"📊 Network Stats:")
    stats = network.get_network_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print()
    
    # 测试路由
    print("🔀 Testing message routing:")
    path = network.route_message("node1", "node2", {"type": "test", "content": "Hello"})
    print(f"   Route from node1 to node2: {' -> '.join(path) if path else 'No route found'}")
    
    # 测试广播
    print("\n📢 Testing broadcast:")
    recipients = network.broadcast_message("node1", {"type": "broadcast", "content": "Hello all"})
    print(f"   Broadcast from node1 to: {', '.join(recipients)}")

