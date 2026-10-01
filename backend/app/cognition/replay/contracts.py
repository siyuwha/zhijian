"""
Cognition Replay Contracts (Phase 2B Runtime)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第6.1节)
2. 《开发文档/49-Phase-2B-实施规划与科学实验对撞引擎技术设计单.md》

核心不变量：
- 【INV-WORM】：衍生认知记录通过 parent_cognition_id 追溯，绝对不原地覆写父记录
- 【INV-DETERMINISTIC】：严格区分四级确定性等级 (BIT_EXACT / SEMANTIC_EQUAL / STOCHASTIC_DRIFT / OFFLINE_FALLBACK)
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.cognition.hypothesis.contracts import (
    HypothesisSetProjection,
)


class DeterministicLevel(str, Enum):
    """
    确定性等级刚性分层枚举
    坚决摒弃“temperature=0 即等于绝对确定”的技术盲从
    """
    BIT_EXACT = "BIT_EXACT"              # 原始响应文本与历史文本 SHA-256 二进制级 100% 吻合
    SEMANTIC_EQUAL = "SEMANTIC_EQUAL"    # 文本标点或格式微调，但结构化假说与断言 100% 等价
    STOCHASTIC_DRIFT = "STOCHASTIC_DRIFT"# 相同配置下模型因 MoE 路由或随机性产生推演漂移
    OFFLINE_FALLBACK = "OFFLINE_FALLBACK"# 历史模型已下线，采用指定替代模型进行近似推演


class ReplayType(str, Enum):
    """重放实验类型"""
    EXACT_REPLAY = "EXACT_REPLAY"        # 历史同配置可复现性检验
    DIFF_SHADOW = "DIFF_SHADOW"          # 控制变量反事实对照实验 (换 Prompt / 换模型)


class InferenceConfig(BaseModel):
    """重放推理参数配置不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    seed: Optional[int] = 42
    temperature: float = 0.0
    top_p: Optional[float] = 1.0
    model_name: str = "mock-reasoning-model-v1"
    provider: str = "sandbox-mock"


class ReplayRequest(BaseModel):
    """认知重放请求不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    replay_id: str
    parent_cognition_id: str
    replay_type: ReplayType = ReplayType.EXACT_REPLAY
    target_prompt_id: Optional[str] = None
    target_prompt_version: Optional[str] = None
    target_prompt_template: Optional[str] = None
    target_inference_config: InferenceConfig = Field(default_factory=InferenceConfig)
    is_offline_fallback: bool = False


class DerivedCognitionRecord(BaseModel):
    """
    衍生认知记录不可变值对象 (Derived Cognition Record)
    严格遵循 WORM 存储不变量，通过 parent_cognition_id 挂载至历史父记录
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    cognition_id: str                          # 衍生记录唯一 ID (e.g. cog_rep_...)
    parent_cognition_id: str                   # 严格指向父记录，严禁悬空
    replay_id: str                             # 本次重放任务批次 ID
    replay_type: ReplayType                    # 重放类型
    deterministic_level: DeterministicLevel    # 经严格判别后的确定性等级
    snapshot_id: str                           # 保持控制变量一致的事实快照 ID
    raw_response: str                          # 重放生成的原始文本响应
    response_hash: str                         # 文本 SHA-256 指纹
    hypothesis_set: HypothesisSetProjection    # 提取出的假说集合
    hypothesis_set_hash: str                   # 假说集合根哈希
    replayed_at: str                           # 重放执行完成时间戳
    drift_details: Optional[str] = None        # 漂移或降级细节说明

    def to_canonical_dict(self) -> Dict[str, Any]:
        """构建 RFC 8785 规范化审计载荷"""
        return {
            "cognition_id": self.cognition_id,
            "deterministic_level": self.deterministic_level.value,
            "drift_details": self.drift_details,
            "hypothesis_set_hash": self.hypothesis_set_hash,
            "parent_cognition_id": self.parent_cognition_id,
            "replay_id": self.replay_id,
            "replay_type": self.replay_type.value,
            "replayed_at": self.replayed_at,
            "response_hash": self.response_hash,
            "snapshot_id": self.snapshot_id,
        }
