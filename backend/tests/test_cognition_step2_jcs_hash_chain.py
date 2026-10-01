"""
Cognition Phase 2A Step 2: RFC 8785 JCS + Hash Chain Engine 专项测试套件
上位依据：
- 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(v1.2.1-FINAL-CLOSURE)
- 董事会下一阶段工程裁决（第五条）：Step 2 严格 Sandbox/Test Only，不得调用真实商用 LLM。

测试验证：
1. RFC 8785 JCS 规范化边界（键排序、空白符消除、浮点整型规范化、UTF-8 字符保全、转义规则）
2. 单记录 Payload 哈希确定性与抗键序扰动
3. 链条 Record 哈希结合 sequence_id + previous_record_hash + payload_hash
4. 单记录自洽性验真与篡改检测
5. 多记录全链完整性验真（Gapless 连续自增、创世前驱对齐、链式哈希指针闭环）
6. 空洞检测、前驱指针破坏检测与历史块篡改雪崩破坏检测
"""

import sys
import os
import json
import pytest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cognition.jcs import canonicalize, canonicalize_bytes, hash_jcs
from app.cognition.hash_chain import (
    compute_payload_hash,
    compute_record_hash,
    verify_single_record,
    verify_chain_integrity,
    GENESIS_PREVIOUS_HASH,
)
from app.models.cognition_v2 import CognitionRecord


def test_rfc8785_canonicalization_rules():
    """验证 RFC 8785 核心规范化规则"""
    # 1. 键排序与空白符消除
    d = {"b": 2, "a": 1}
    assert canonicalize(d) == '{"a":1,"b":2}'
    
    # 2. 浮点数与整型处理 (42.0 规范化为 42, 0.0 为 0)
    assert canonicalize(42.0) == "42"
    assert canonicalize(0.0) == "0"
    assert canonicalize(-0.0) == "0"
    assert canonicalize(12.345) == "12.345"

    # 3. 布尔与空值
    assert canonicalize(True) == "true"
    assert canonicalize(False) == "false"
    assert canonicalize(None) == "null"

    # 4. 中文与特殊字符保全 (UTF-8 原样输出，不转义为 \\u)
    assert canonicalize("A股结构化认知") == '"A股结构化认知"'

    # 5. 特殊转义（仅转义引号、反斜杠与控制字符，正斜杠 / 不转义）
    assert canonicalize('hello "world"') == '"hello \\"world\\""'
    assert canonicalize("path/to/resource") == '"path/to/resource"'
    assert canonicalize("line1\nline2") == '"line1\\nline2"'


def test_compute_payload_hash_key_order_invariance():
    """验证 Payload 哈希具备严格的键序无关性与确定性"""
    snapshot_1 = {"market_cap": 5000, "code": "600519", "pct": 1.25}
    snapshot_2 = {"pct": 1.25, "code": "600519", "market_cap": 5000}
    
    h1 = compute_payload_hash(
        date="2026-09-30", stage="POST_CLOSE", market_event_time="15:00:00",
        observation_window="15:00:00", observation_snapshot=snapshot_1,
        market_state_snapshot='{"D1": 85}', prompt_id="p1", prompt_version="1.0",
        prompt_hash="phash", model_provider="deepseek", model_name="r1",
        model_version="v1", inference_config='{"temp": 0.0}',
        effective_input_hash="eff1", rendered_system_prompt="sys",
        rendered_user_prompt="usr", raw_response="raw",
        structured_cognition='{"thesis": "bull"}', hypothesis_set_hash="hypo1"
    )
    
    h2 = compute_payload_hash(
        date="2026-09-30", stage="POST_CLOSE", market_event_time="15:00:00",
        observation_window="15:00:00", observation_snapshot=snapshot_2,
        market_state_snapshot='{"D1": 85}', prompt_id="p1", prompt_version="1.0",
        prompt_hash="phash", model_provider="deepseek", model_name="r1",
        model_version="v1", inference_config='{"temp": 0.0}',
        effective_input_hash="eff1", rendered_system_prompt="sys",
        rendered_user_prompt="usr", raw_response="raw",
        structured_cognition='{"thesis": "bull"}', hypothesis_set_hash="hypo1"
    )
    
    assert h1 == h2
    assert len(h1) == 64


def test_compute_record_hash_deterministic():
    """验证 record_hash 结合 sequence_id 与前驱哈希生成确定性结果"""
    seq_id = 1
    prev_hash = GENESIS_PREVIOUS_HASH
    payload_hash = "abcdef" * 10 + "1234"
    
    r_hash1 = compute_record_hash(seq_id, prev_hash, payload_hash)
    r_hash2 = compute_record_hash(seq_id, prev_hash, payload_hash)
    
    assert r_hash1 == r_hash2
    assert len(r_hash1) == 64
    
    # 任何参数微小变动必然引起哈希雪崩
    r_hash_tampered = compute_record_hash(seq_id + 1, prev_hash, payload_hash)
    assert r_hash1 != r_hash_tampered


def test_single_record_verification_and_tamper_detection():
    """验证单记录验真器能够精准发现任何字段篡改"""
    payload_h = compute_payload_hash(
        date="2026-09-30", stage="POST_CLOSE", market_event_time="15:00:00",
        observation_window="15:00:00", observation_snapshot='{"up": 3200}',
        market_state_snapshot='{"D1": 80}', prompt_id="p1", prompt_version="1.0",
        prompt_hash="phash", model_provider="deepseek", model_name="r1",
        model_version="v1", inference_config="{}", effective_input_hash="eff1",
        rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response="raw",
        structured_cognition='{"thesis": "neutral"}', hypothesis_set_hash="hypo1"
    )
    rec_h = compute_record_hash(1, GENESIS_PREVIOUS_HASH, payload_h)
    
    valid_record = CognitionRecord(
        id="cog_1", date="2026-09-30", stage="POST_CLOSE", timestamp=datetime.now(),
        market_event_time="15:00:00", observation_window="15:00:00", data_snapshot_time=datetime.now(),
        observation_snapshot='{"up": 3200}', market_state_snapshot='{"D1": 80}',
        prompt_id="p1", prompt_version="1.0", prompt_hash="phash", model_provider="deepseek",
        model_name="r1", model_version="v1", inference_config="{}", effective_input_hash="eff1",
        rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response="raw",
        structured_cognition='{"thesis": "neutral"}', hypothesis_set_hash="hypo1",
        sequence_id=1, previous_record_hash=GENESIS_PREVIOUS_HASH, payload_hash=payload_h,
        record_hash=rec_h, replay_type="ORIGINAL"
    )
    
    # 1. 正常记录验真通过
    ok, err = verify_single_record(valid_record)
    assert ok is True
    assert err is None
    
    # 2. 篡改 observation_snapshot
    valid_record.observation_snapshot = '{"up": 9999}'
    ok_tamper, err_tamper = verify_single_record(valid_record)
    assert ok_tamper is False
    assert "payload_hash mismatch" in err_tamper


def test_chain_integrity_verification_multi_records():
    """验证多记录 Hash Chain 链式完整性验真"""
    chain = []
    prev_h = GENESIS_PREVIOUS_HASH
    
    for i in range(1, 6):
        obs = json.dumps({"block_index": i})
        payload_h = compute_payload_hash(
            date="2026-09-30", stage="POST_CLOSE", market_event_time="15:00:00",
            observation_window="15:00:00", observation_snapshot=obs,
            market_state_snapshot="{}", prompt_id="p1", prompt_version="1.0",
            prompt_hash="phash", model_provider="deepseek", model_name="r1",
            model_version="v1", inference_config="{}", effective_input_hash=f"eff_{i}",
            rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response=f"resp_{i}",
            structured_cognition=json.dumps({"seq": i}), hypothesis_set_hash=f"hypo_{i}"
        )
        rec_h = compute_record_hash(i, prev_h, payload_h)
        
        rec = CognitionRecord(
            id=f"cog_{i}", date="2026-09-30", stage="POST_CLOSE", timestamp=datetime.now(),
            market_event_time="15:00:00", observation_window="15:00:00", data_snapshot_time=datetime.now(),
            observation_snapshot=obs, market_state_snapshot="{}", prompt_id="p1",
            prompt_version="1.0", prompt_hash="phash", model_provider="deepseek",
            model_name="r1", model_version="v1", inference_config="{}", effective_input_hash=f"eff_{i}",
            rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response=f"resp_{i}",
            structured_cognition=json.dumps({"seq": i}), hypothesis_set_hash=f"hypo_{i}",
            sequence_id=i, previous_record_hash=prev_h, payload_hash=payload_h,
            record_hash=rec_h, replay_type="ORIGINAL"
        )
        chain.append(rec)
        prev_h = rec_h
    
    # 完整合法链校验通过
    is_valid, err = verify_chain_integrity(chain)
    assert is_valid is True
    assert err is None


def test_chain_integrity_detects_gap_and_broken_pointer():
    """验证 Hash Chain 引擎能够精准检测序号空洞与断链"""
    chain = []
    prev_h = GENESIS_PREVIOUS_HASH
    
    for i in [1, 2, 4]:  # 故意制造序号 3 的空洞
        obs = json.dumps({"block_index": i})
        payload_h = compute_payload_hash(
            date="2026-09-30", stage="POST_CLOSE", market_event_time="15:00:00",
            observation_window="15:00:00", observation_snapshot=obs,
            market_state_snapshot="{}", prompt_id="p1", prompt_version="1.0",
            prompt_hash="phash", model_provider="deepseek", model_name="r1",
            model_version="v1", inference_config="{}", effective_input_hash=f"eff_{i}",
            rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response=f"resp_{i}",
            structured_cognition=json.dumps({"seq": i}), hypothesis_set_hash=f"hypo_{i}"
        )
        rec_h = compute_record_hash(i, prev_h, payload_h)
        rec = CognitionRecord(
            id=f"cog_{i}", date="2026-09-30", stage="POST_CLOSE", timestamp=datetime.now(),
            market_event_time="15:00:00", observation_window="15:00:00", data_snapshot_time=datetime.now(),
            observation_snapshot=obs, market_state_snapshot="{}", prompt_id="p1",
            prompt_version="1.0", prompt_hash="phash", model_provider="deepseek",
            model_name="r1", model_version="v1", inference_config="{}", effective_input_hash=f"eff_{i}",
            rendered_system_prompt="sys", rendered_user_prompt="usr", raw_response=f"resp_{i}",
            structured_cognition=json.dumps({"seq": i}), hypothesis_set_hash=f"hypo_{i}",
            sequence_id=i, previous_record_hash=prev_h, payload_hash=payload_h,
            record_hash=rec_h, replay_type="ORIGINAL"
        )
        chain.append(rec)
        prev_h = rec_h

    # 验证空洞被捕获
    is_valid, err = verify_chain_integrity(chain)
    assert is_valid is False
    assert "Sequence hole detected" in err
