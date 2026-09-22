from abc import ABC, abstractmethod
from typing import Any
from ..capabilities import DataResult

class BaseProvider(ABC):
    """数据源适配器基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def is_available(self) -> bool:
        """检查该 Provider 服务可用性"""
        return True
