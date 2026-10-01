"""
Hypothesis JCS Fingerprint & Set Hash Engine (Phase 2A Step 4)
上位依据：
1. RFC 8785 JSON Canonicalization Scheme
2. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL
"""

from ..jcs import hash_jcs
from .contracts import MarketHypothesisDefinition, HypothesisSetProjection


def compute_hypothesis_hash(hypo: MarketHypothesisDefinition) -> str:
    """计算单个假说定义投影的 RFC 8785 JCS SHA-256 哈希"""
    return hash_jcs(hypo.to_canonical_dict())


def compute_hypothesis_set_hash(hypo_set: HypothesisSetProjection) -> str:
    """计算整套假说集合定义投影的聚合哈希 (对应 CognitionRecord.hypothesis_set_hash)"""
    return hash_jcs(hypo_set.to_canonical_dict())


def verify_hypothesis_hash(hypo: MarketHypothesisDefinition) -> bool:
    """验真单个假说定义哈希，任一字段变动立即返回 False"""
    if not hypo.hypothesis_hash:
        return False
    expected = compute_hypothesis_hash(hypo)
    return hypo.hypothesis_hash == expected


def verify_hypothesis_set_hash(hypo_set: HypothesisSetProjection) -> bool:
    """验真假说集合整体哈希"""
    if not hypo_set.hypothesis_set_hash:
        return False
    expected = compute_hypothesis_set_hash(hypo_set)
    return hypo_set.hypothesis_set_hash == expected
