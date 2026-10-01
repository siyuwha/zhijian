"""
JCS 规范化指纹与哈希引擎（Observation Fingerprint & Input Hash Engine）
上位依据：
1. RFC 8785 JSON Canonicalization Scheme
2. BOARD-APPROVAL-20260930-STEP3
"""

from typing import Any
from ..jcs import hash_jcs, canonicalize
from .contracts import FactItem, ObservationSnapshot, EffectiveInferenceInput


def compute_fact_fingerprint(fact: FactItem) -> str:
    """计算单个 FactItem 的 RFC 8785 JCS SHA-256 规范化指纹"""
    return hash_jcs(fact.canonical_dict())


def compute_snapshot_fingerprint(snapshot: ObservationSnapshot) -> str:
    """计算 ObservationSnapshot 全要素规范化指纹"""
    return hash_jcs(snapshot.canonical_dict())


def compute_effective_input_hash(input_obj: EffectiveInferenceInput) -> str:
    """计算 EffectiveInferenceInput 的有效推理输入哈希 (effective_input_hash)"""
    return hash_jcs(input_obj.canonical_dict())


def verify_fact_fingerprint(fact: FactItem) -> bool:
    """验真单个事实指纹，任一字段被篡改立即返回 False"""
    if not fact.fact_fingerprint:
        return False
    expected = compute_fact_fingerprint(fact)
    return fact.fact_fingerprint == expected


def verify_snapshot_fingerprint(snapshot: ObservationSnapshot) -> bool:
    """验真快照整体指纹，任一事实项或元数据变动立即返回 False"""
    if not snapshot.snapshot_fingerprint:
        return False
    expected = compute_snapshot_fingerprint(snapshot)
    return snapshot.snapshot_fingerprint == expected


def verify_effective_input_hash(input_obj: EffectiveInferenceInput) -> bool:
    """验真生效推理输入哈希，任一 prompt、事实或配置变动立即返回 False"""
    if not input_obj.effective_input_hash:
        return False
    expected = compute_effective_input_hash(input_obj)
    return input_obj.effective_input_hash == expected
