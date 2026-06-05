"""Agent基类"""

from abc import ABC, abstractmethod
from typing import Optional
from .message import Message
from .llm import LLM
from .config import Config

class Agent(ABC):
    """Agent基类, 定义了一个智能体应该具备的通用行为和属性，但并不关心具体的实现方式, 通过 Python 的 abc(抽象基类) 模块来实现它，这强制所有具体的智能体实现都必须遵循同一个接口"""
    
    def __init__(
        self,
        name: str,
        llm: LLM,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or Config()
        self._history: list[Message] = []
    
    @abstractmethod
    def run(self, input_text: str, **kwargs) -> str:
        """运行Agent"""
        pass
    
    def add_message(self, message: Message):
        """添加消息到历史记录"""
        self._history.append(message)
    
    def clear_history(self):
        """清空历史记录"""
        self._history.clear()
    
    def get_history(self) -> list[Message]:
        """获取历史记录"""
        return self._history.copy()
    
    def __str__(self) -> str:
        return f"Agent(name={self.name}, provider={self.llm.provider})"
    
    def __repr__(self) -> str:
        return self.__str__()