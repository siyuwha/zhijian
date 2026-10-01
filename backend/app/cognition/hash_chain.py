"""
RFC 8785 JCS + SHA-256 Hash Chain 链式验真引擎 (Phase 2A Step 2: Sandbox / Test Only)
上位依据：
- 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(v1.2.1-FINAL-CLOSURE, Section 8.3)
- 《开发文档/29-Cognition-Phase2A架构与数据契约冻结决议与实施约束单.md》(INV-05, INV-07)
- 董事会下一阶段工程裁决（第五条）：Step 2 严格 Sandbox/Test，不调用真实商用 LLM，不接入真实交易链。

核心功能：
1. compute_payload_hash: 计算单记录全要素 JCS 规范化哈希
2. compute_record_hash: 链式结合 sequence_id、previous_record_hash 与 payload_hash 计算 record_hash
3. verify_single_record: 单记录自洽性验真
4. verify_chain_integrity: 全链单调自增、前驱哈希链式衔接与零空洞验真
"""

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from .jcs import canonicalize, hash_jcs
from ..models.cognition_v2 import CognitionRecord

GENESIS_PREVIOUS_HASH = "0" * 64


def _normalize_sub_element(val: Any) -> Any:
    """若传入字符串格式的 JSON，安全解析为原生结构以便 JCS 递归规范化"""
    if isinstance(val, str):
        val_str = val.strip()
        if (val_str.startswith("{") and val_str.endswith("}")) or (val_str.startswith("[") and val_str.endswith("]")):
            try:
                return json.loads(val_str)
            except Exception:
                return val
    return val


def compute_payload_hash(
    date: str,
    stage: str,
    market_event_time: str,
    observation_window: str,
    observation_snapshot: Union[str, dict],
    market_state_snapshot: Union[str, dict],
    prompt_id: str,
    prompt_version: str,
    prompt_hash: str,
    model_provider: str,
    model_name: str,
    model_version: str,
    inference_config: Union[str, dict],
    effective_input_hash: str,
    rendered_system_prompt: str,
    rendered_user_prompt: str,
    raw_response: str,
    structured_cognition: Union[str, dict],
    hypothesis_set_hash: str,
) -> str:
    """
    计算 CognitionRecord 全要素 Canonical Payload 哈希 (RFC 8785 JCS + SHA-256)
    """
    canonical_payload_dict = {
        "date": date,
        "stage": stage,
        "market_event_time": market_event_time,
        "observation_window": observation_window,
        "observation_snapshot": _normalize_sub_element(observation_snapshot),
        "market_state_snapshot": _normalize_sub_element(market_state_snapshot),
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "model_provider": model_provider,
        "model_name": model_name,
        "model_version": model_version,
        "inference_config": _normalize_sub_element(inference_config),
        "effective_input_hash": effective_input_hash,
        "rendered_system_prompt": rendered_system_prompt,
        "rendered_user_prompt": rendered_user_prompt,
        "raw_response": raw_response,
        "structured_cognition": _normalize_sub_element(structured_cognition),
        "hypothesis_set_hash": hypothesis_set_hash,
    }
    return hash_jcs(canonical_payload_dict)


def compute_record_hash(
    sequence_id: int,
    previous_record_hash: str,
    payload_hash: str,
) -> str:
    """
    计算链条记录哈希 (C-04 核心公式):
    record_hash = SHA256(JCS({
        "sequence_id": sequence_id,
        "previous_record_hash": previous_record_hash,
        "payload_hash": payload_hash
    }))
    """
    chain_link_dict = {
        "sequence_id": sequence_id,
        "previous_record_hash": previous_record_hash,
        "payload_hash": payload_hash,
    }
    return hash_jcs(chain_link_dict)


def verify_single_record(record: CognitionRecord) -> Tuple[bool, Optional[str]]:
    """
    单记录验真器：
    1. 重新计算 payload_hash 并比对
    2. 重新计算 record_hash 并比对
    """
    try:
        expected_payload_hash = compute_payload_hash(
            date=record.date,
            stage=record.stage,
            market_event_time=record.market_event_time,
            observation_window=record.observation_window,
            observation_snapshot=record.observation_snapshot,
            market_state_snapshot=record.market_state_snapshot,
            prompt_id=record.prompt_id,
            prompt_version=record.prompt_version,
            prompt_hash=record.prompt_hash,
            model_provider=record.model_provider,
            model_name=record.model_name,
            model_version=record.model_version,
            inference_config=record.inference_config,
            effective_input_hash=record.effective_input_hash,
            rendered_system_prompt=record.rendered_system_prompt,
            rendered_user_prompt=record.rendered_user_prompt,
            raw_response=record.raw_response,
            structured_cognition=record.structured_cognition,
            hypothesis_set_hash=record.hypothesis_set_hash,
        )
        if expected_payload_hash != record.payload_hash:
            return False, (
                f"Record {record.id} payload_hash mismatch: "
                f"expected {expected_payload_hash}, got {record.payload_hash}"
            )

        expected_record_hash = compute_record_hash(
            sequence_id=record.sequence_id,
            previous_record_hash=record.previous_record_hash,
            payload_hash=record.payload_hash,
        )
        if expected_record_hash != record.record_hash:
            return False, (
                f"Record {record.id} record_hash mismatch: "
                f"expected {expected_record_hash}, got {record.record_hash}"
            )

        return True, None
    except Exception as e:
        return False, f"Verification failed with exception: {e}"


def verify_chain_integrity(
    records: List[CognitionRecord],
    genesis_previous_hash: str = GENESIS_PREVIOUS_HASH,
) -> Tuple[bool, Optional[str]]:
    """
    全链完整性验真器：
    1. 验证序号严格自增且连续单调无空洞 (sequence_id == prev + 1)
    2. 验证首条记录前驱哈希满足创世约定
    3. 验证后续每条记录的 previous_record_hash == 上一条记录的 record_hash
    4. 逐条执行单记录 payload 与 record_hash 验真
    """
    if not records:
        return True, None

    for i, rec in enumerate(records):
        # 1. 验证单记录哈希正确性
        is_valid, err = verify_single_record(rec)
        if not is_valid:
            return False, f"Chain broken at index {i} (seq={rec.sequence_id}): {err}"

        # 2. 验证创世或前驱链条衔接
        if i == 0:
            if rec.sequence_id == 1 and rec.previous_record_hash != genesis_previous_hash:
                return False, (
                    f"Genesis record seq=1 previous_record_hash must be {genesis_previous_hash}, "
                    f"got {rec.previous_record_hash}"
                )
        else:
            prev_rec = records[i - 1]
            if rec.sequence_id != prev_rec.sequence_id + 1:
                return False, (
                    f"Sequence hole detected: index {i} seq={rec.sequence_id} "
                    f"does not follow prev seq={prev_rec.sequence_id}"
                )
            if rec.previous_record_hash != prev_rec.record_hash:
                return False, (
                    f"Chain pointer broken at index {i} (seq={rec.sequence_id}): "
                    f"previous_record_hash {rec.previous_record_hash} != {prev_rec.record_hash}"
                )

    return True, None
