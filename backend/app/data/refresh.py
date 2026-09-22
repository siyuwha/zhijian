from pydantic import BaseModel, Field

class RefreshPolicy(BaseModel):
    """
    数据刷新策略配置
    遵守原则：刷新频率可配置，必须遵守实际 Provider 的速率限制
    """
    capability: str
    provider: str
    interval_seconds: int = Field(default=60, description="常规刷新间隔(秒)")
    min_interval_seconds: int = Field(default=5, description="最小调用保护间隔(秒)")
    max_retries: int = Field(default=3, description="单次降级重试次数")
    enabled: bool = Field(default=True, description="是否启用自动化定时抓取")
