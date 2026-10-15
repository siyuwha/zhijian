"""
System LLM Configuration & OpenAI-Compatible Relay Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional


class LLMConfigResponse(BaseModel):
    provider_type: str = Field(
        default="openai_compatible",
        description="Provider 类型: openai_compatible (中转站), deepseek, openai, custom",
    )
    base_url: str = Field(
        default="https://api.deepseek.com/v1",
        description="API 基础端点地址 (如 https://api.your-relay.com/v1)",
    )
    model: str = Field(
        default="deepseek-chat",
        description="模型名称 (如 gpt-4o, deepseek-chat, claude-3-5-sonnet 等)",
    )
    api_key_masked: str = Field(
        default="",
        description="脱敏后的 API Key (用于前端展示)",
    )
    has_api_key: bool = Field(
        default=False,
        description="是否已配置有效 API Key",
    )
    temperature: float = Field(
        default=0.2,
        description="采样温度 (0.0~1.0, 推荐 0.2 严格严谨模式)",
    )
    max_tokens: int = Field(
        default=4000,
        description="最大生成 Token 数",
    )
    timeout_seconds: float = Field(
        default=60.0,
        description="请求超时秒数",
    )
    is_customized: bool = Field(
        default=False,
        description="是否已使用用户自定义配置 (True) 或环境变量默认值 (False)",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="最后更新时间 (ISO 8601)",
    )


class LLMConfigUpdateRequest(BaseModel):
    provider_type: Optional[str] = Field(
        default="openai_compatible",
        description="Provider 类型",
    )
    base_url: str = Field(
        ...,
        description="API 基础端点地址",
    )
    model: str = Field(
        ...,
        description="模型名称",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="新 API Key (若传空或保持 null 则保留原已有密钥)",
    )
    temperature: Optional[float] = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="采样温度",
    )
    max_tokens: Optional[int] = Field(
        default=4000,
        ge=100,
        le=32000,
        description="最大 Token 数",
    )
    timeout_seconds: Optional[float] = Field(
        default=60.0,
        ge=5.0,
        le=300.0,
        description="超时秒数",
    )


class LLMTestConnectionRequest(BaseModel):
    base_url: str = Field(
        ...,
        description="待测试的 API 端点",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="待测试的 API Key (若为空则尝试使用系统当前已保存的 Key)",
    )
    model: str = Field(
        default="deepseek-chat",
        description="待测试的模型名称",
    )
    timeout_seconds: Optional[float] = Field(
        default=20.0,
        description="测试超时时间",
    )


class LLMTestConnectionResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    success: bool = Field(..., description="测试是否连通成功")
    latency_ms: int = Field(..., description="请求往返延迟毫秒数")
    message: str = Field(..., description="诊断结果说明")
    model_used: Optional[str] = Field(default=None, description="测试所用模型")
    reply_preview: Optional[str] = Field(default=None, description="模型返回的测试问答片段")
    error: Optional[str] = Field(default=None, description="错误详情 (若失败)")
