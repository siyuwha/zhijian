from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from ..capabilities import DataQuality, DataResult, Freshness, ProviderResponse

class BaseProvider(ABC):
    """
    数据源适配器基类
    包含 P2 五维生产准入验证元数据：
    1. implementation_status (已接入 / 部分接入 / 未接入)
    2. connectivity_verified (已验证 / 待验证 / 连通受限)
    3. schema_verified (已验证 / 待验证 / 存在漂移)
    4. semantic_verified (已验证 / 待验证 / 存在失真)
    5. production_eligible (准入 / 仅作备用 / 暂不准入 / 待验证)
    """

    def __init__(
        self,
        name: str,
        implementation_status: str = "已接入",
        connectivity_verified: str = "待验证",
        schema_verified: str = "待验证",
        semantic_verified: str = "待验证",
        production_eligible: str = "待验证",
    ):
        self.name = name
        self.implementation_status = implementation_status
        self.connectivity_verified = connectivity_verified
        self.schema_verified = schema_verified
        self.semantic_verified = semantic_verified
        self.production_eligible = production_eligible

    @abstractmethod
    async def is_available(self) -> bool:
        """检查该 Provider 物理服务可用性"""
        return True

    def get_admission_metadata(self) -> Dict[str, Any]:
        """获取 Provider 准入验证五维元数据"""
        return {
            "provider": self.name,
            "implementation_status": self.implementation_status,
            "connectivity_verified": self.connectivity_verified,
            "schema_verified": self.schema_verified,
            "semantic_verified": self.semantic_verified,
            "production_eligible": self.production_eligible,
        }

    def is_production_ready(self) -> bool:
        """是否具备生产主力或备用准入资格"""
        return self.production_eligible in ("准入", "仅作备用")
