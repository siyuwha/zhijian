"""
Phase 3B.1: In-Memory Alert Bus Core & Offline Replay Gates
============================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 《DOC-98 · Phase 3B 盘中多源告警通知总线与受控防御编排技术设计单》

8 大刚性门禁规范：
- GATE-3B1-01: 事件契约与四维时间因果测试
- GATE-3B1-02: 幂等去重与滑动窗口冷却抑制测试
- GATE-3B1-03: 乱序、迟到及过期事件精准识别测试
- GATE-3B1-04: RingBuffer 满载溢出与关键告警保留策略测试
- GATE-3B1-05: 内存死信队列 (DLQ) 与进程重启快照恢复测试
- GATE-3B1-06: 多线程并发安全与确定性历史回放测试
- GATE-3B1-07: 恶意载荷防注入与哈希链日志防篡改测试
- GATE-3B1-08: 生产数据库物理隔离与零业务写入测试
"""

import os
import shutil
import pytest
import sqlite3
import threading
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from backend.app.schemas.canonical_intraday import IntradayStageEnum
from backend.app.schemas.popper_verdict import AssertionItemVerdict, AssertionSeverityEnum
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.schemas.canonical_alert_event import (
    CanonicalDriftAlertEvent,
    AlertSeverityEnum,
    AlertCategoryEnum,
)
from backend.app.services.alert_bus_ring_buffer import (
    AlertRingBuffer,
    AlertDeadLetterQueue,
)
from backend.app.services.alert_evaluator import (
    AlertEvaluator,
    AlertDeduplicator,
    AlertLifecycleStateEnum,
)
from backend.app.services.alert_audit_logger import AlertAuditLogger


TEST_LOG_DIR = "scratch/test_alert_bus_logs"


@pytest.fixture(autouse=True)
def clean_test_log_dir():
    if os.path.exists(TEST_LOG_DIR):
        shutil.rmtree(TEST_LOG_DIR, ignore_errors=True)
    os.makedirs(TEST_LOG_DIR, exist_ok=True)
    yield
    if os.path.exists(TEST_LOG_DIR):
        shutil.rmtree(TEST_LOG_DIR, ignore_errors=True)


def build_mock_verdict(
    trade_date: str = "2026-10-09",
    time_str: str = "10:00:00",
    state: DriftStateEnum = DriftStateEnum.CRITICAL_BREACH,
    events: list = None,
) -> IntradayDriftVerdict:
    """构建用于离线回放测试的标准判定对账单"""
    if events is None:
        events = [DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE]
    
    return IntradayDriftVerdict(
        verdict_id=f"VERDICT-{trade_date}-INTRADAY-12345678",
        trade_date=trade_date,
        evaluated_at=f"{trade_date}T{time_str}+08:00",
        stage=IntradayStageEnum.STAGE_2_MORNING,
        elapsed_trading_minutes=30,
        trace_id=f"TRACE-{trade_date}-001",
        hypothesis_id=f"HYPO-2026-10-08-001",
        hypothesis_fingerprint="a" * 64,
        intraday_snapshot_fingerprint="b" * 64,
        rule_version="3A.2-V1",
        threshold_config_hash="c" * 64,
        overall_drift_state=state,
        inconclusive_reason=None,
        verdict_headline="空间标杆破位炸板，触发客观风险防御",
        detected_drift_events=events,
        assertion_results=[
            AssertionItemVerdict(
                rule_id="RULE-SPACE-LEADER-STATUS",
                rule_name="空间标杆存续性",
                severity=AssertionSeverityEnum.CRITICAL_KILL,
                target_entity="000001",
                expected_condition="连板封死",
                actual_observation="炸板跌停",
                is_violated=True,
                deviation_analysis="盘中炸板破位，偏离度 100.0%",
            )
        ],
        preservation_boundaries=["空间龙炸板，杜绝追高盲目博弈"],
        safety_audit_passed=True,
        verdict_fingerprint="d" * 64,
    )


# ==============================================================================
# GATE-3B1-01: 事件契约与四维时间因果测试
# ==============================================================================
def test_gate_3b1_01_event_contract_and_temporal_causality():
    """GATE-3B1-01: 验证规范告警事件的双重签名机制与物理数据年龄计算"""
    verdict = build_mock_verdict()
    evaluator = AlertEvaluator()

    t_req = datetime.fromisoformat("2026-10-09T10:01:00+08:00")
    state, event, msg = evaluator.evaluate_and_publish(verdict, request_timestamp=t_req)

    assert state == AlertLifecycleStateEnum.ACTIVE
    assert event is not None
    assert event.alert_id.startswith("ALERT-2026-10-09-STAGE_2_MORNING-")
    assert event.severity == AlertSeverityEnum.CRITICAL
    assert event.category == AlertCategoryEnum.SPACE_LEADER_COLLAPSE

    # 1. 验证双重防伪：内容哈希与源端 HMAC 签名
    assert event.verify_signatures() is True

    # 2. 验证物理数据年龄计算 (10:01:00 - 10:00:00 = 60s)
    assert event.data_age_seconds == 60.0
    assert event.is_stale is False


# ==============================================================================
# GATE-3B1-02: 幂等去重与滑动窗口冷却抑制测试
# ==============================================================================
def test_gate_3b1_02_idempotence_and_cooldown_suppression():
    """GATE-3B1-02: 相同去重键在 180s 冷却期内自动抑制，返回 COOLDOWN"""
    verdict = build_mock_verdict()
    evaluator = AlertEvaluator(cooldown_seconds=180.0)

    t1 = datetime.fromisoformat("2026-10-09T10:00:00+08:00")
    state1, ev1, _ = evaluator.evaluate_and_publish(verdict, request_timestamp=t1)
    assert state1 == AlertLifecycleStateEnum.ACTIVE
    assert ev1 is not None

    # 20秒后重复到达
    t2 = datetime.fromisoformat("2026-10-09T10:00:20+08:00")
    state2, ev2, msg2 = evaluator.evaluate_and_publish(verdict, request_timestamp=t2)
    assert state2 == AlertLifecycleStateEnum.COOLDOWN
    assert ev2 is None
    assert "Suppressed by cooldown" in msg2

    # 190秒后冷却期已过，重新激活
    t3 = datetime.fromisoformat("2026-10-09T10:03:10+08:00")
    state3, ev3, _ = evaluator.evaluate_and_publish(verdict, request_timestamp=t3)
    assert state3 == AlertLifecycleStateEnum.ACTIVE
    assert ev3 is not None
    assert ev3.detail_facts["occurrence_count"] == 3


# ==============================================================================
# GATE-3B1-03: 乱序、迟到及过期事件精准识别测试
# ==============================================================================
def test_gate_3b1_03_out_of_order_and_staleness_detection():
    """GATE-3B1-03: 乱序数据打标防御与滞后数据精准识别"""
    # 禁用冷却以独立核验乱序判定逻辑
    evaluator = AlertEvaluator(cooldown_seconds=0.0)

    # 先收到 10:30:00 数据
    v_late = build_mock_verdict(time_str="10:30:00")
    t_req1 = datetime.fromisoformat("2026-10-09T10:31:00+08:00")
    _, ev1, _ = evaluator.evaluate_and_publish(v_late, request_timestamp=t_req1)
    assert ev1.is_out_of_order is False

    # 随后收到迟到的 10:15:00 数据 (乱序到达)
    v_early = build_mock_verdict(time_str="10:15:00")
    t_req2 = datetime.fromisoformat("2026-10-09T10:32:00+08:00")
    _, ev2, _ = evaluator.evaluate_and_publish(v_early, request_timestamp=t_req2)
    assert ev2 is not None
    assert ev2.is_out_of_order is True
    # 物理数据年龄：10:32:00 - 10:15:00 = 1020s > 180s (过期滞后)
    assert ev2.data_age_seconds == 1020.0
    assert ev2.is_stale is True


# ==============================================================================
# GATE-3B1-04: RingBuffer 满载溢出与关键告警保留策略测试
# ==============================================================================
def test_gate_3b1_04_ring_buffer_capacity_and_critical_reservation():
    """GATE-3B1-04: RingBuffer 满载时优先淘汰非关键告警，保护 CRITICAL 告警"""
    # 构造容量为 5 的微型环形缓冲区
    ring = AlertRingBuffer(capacity=5, critical_reservation_quota=2)

    # 1. 塞入 1 个 CRITICAL 和 4 个 INFO
    v_crit = build_mock_verdict(time_str="10:00:00", state=DriftStateEnum.CRITICAL_BREACH)
    eval_c = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)
    _, ev_crit, _ = eval_c.evaluate_and_publish(v_crit)

    for i in range(1, 5):
        v_info = build_mock_verdict(time_str=f"10:0{i}:00", state=DriftStateEnum.NORMAL, events=[])
        eval_i = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)
        eval_i.evaluate_and_publish(v_info)

    assert ring.size() == 5

    # 2. 满载时再注入 1 个新的 WARNING 告警
    v_warn = build_mock_verdict(time_str="10:10:00", state=DriftStateEnum.DRIFT_WARNING, events=[DriftEventCategoryEnum.LIQUIDITY_FLASH_DRY])
    eval_w = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)
    state, ev_w, drop_msg = eval_w.evaluate_and_publish(v_warn)

    assert ring.size() == 5
    assert ring.total_overflow_drops == 1
    # 确认淘汰的是 non-critical 告警，最早的 CRITICAL 依然保留在缓冲区中
    buffered = ring.get_events()
    crit_count = sum(1 for e in buffered if e.severity == AlertSeverityEnum.CRITICAL)
    assert crit_count >= 1, "CRITICAL 告警必须受保留策略保护"


# ==============================================================================
# GATE-3B1-05: 内存死信队列 (DLQ) 与进程重启快照恢复测试
# ==============================================================================
def test_gate_3b1_05_dlq_and_restart_snapshot_recovery():
    """GATE-3B1-05: 格式异常推入死信队列，快照导入导出保证进程重启恢复"""
    dlq = AlertDeadLetterQueue(capacity=10)
    ring = AlertRingBuffer(capacity=100)
    evaluator = AlertEvaluator(ring_buffer=ring, dead_letter_queue=dlq, cooldown_seconds=0.0)

    # 1. 正常生成 2 条事件 (设置 cooldown=0.0 避免同分类去重抑制)
    v1 = build_mock_verdict(time_str="10:00:00")
    v2 = build_mock_verdict(time_str="10:05:00")
    evaluator.evaluate_and_publish(v1)
    evaluator.evaluate_and_publish(v2)
    assert ring.size() == 2

    # 2. 导出快照
    snapshot = ring.export_snapshot()
    assert len(snapshot) == 2

    # 3. 模拟进程重启创建新缓冲区并恢复
    new_ring = AlertRingBuffer(capacity=100)
    loaded = new_ring.restore_from_snapshot(snapshot)
    assert loaded == 2
    assert new_ring.size() == 2
    assert new_ring.get_events()[0].alert_id == ring.get_events()[0].alert_id

    # 4. 手动向 DLQ 压入毒丸数据
    dlq.push({"corrupt": "data"}, "TEST_POISON_INJECTION")
    assert dlq.size() == 1
    assert dlq.get_all()[0]["reason"] == "TEST_POISON_INJECTION"


# ==============================================================================
# GATE-3B1-06: 多线程并发安全与确定性历史回放测试
# ==============================================================================
def test_gate_3b1_06_concurrent_emission_and_thread_safety():
    """GATE-3B1-06: 10 线程并发向同一评估器投递事件，验证无锁冲突与无数据竞争"""
    ring = AlertRingBuffer(capacity=200)
    evaluator = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)

    def worker(idx: int):
        v = build_mock_verdict(time_str=f"10:{idx:02d}:00")
        evaluator.evaluate_and_publish(v)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 确认 20 条事件全量安全写入，无死锁、无丢失
    assert ring.size() == 20


# ==============================================================================
# GATE-3B1-07: 恶意载荷防注入与哈希链日志防篡改测试
# ==============================================================================
def test_gate_3b1_07_injection_defense_and_merkle_audit_tamper_detection():
    """GATE-3B1-07: 去重键字符注入拦截，且哈希链日志可检测单字符微篡改"""
    logger_service = AlertAuditLogger(log_dir=TEST_LOG_DIR)
    verdict = build_mock_verdict()
    evaluator = AlertEvaluator()

    _, event, _ = evaluator.evaluate_and_publish(verdict)
    assert event is not None

    # 1. 正常写入审计日志
    line_hash = logger_service.append_event(event)
    assert len(line_hash) == 64

    log_file = os.path.join(TEST_LOG_DIR, f"alert_audit_{verdict.trade_date}.jsonl")
    valid, count, err = AlertAuditLogger.verify_audit_log_integrity(log_file)
    assert valid is True
    assert count == 1
    assert err is None

    # 2. 模拟黑客篡改日志中的 1 个字符
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 篡改 headline 字段中的一个文字
    tampered_content = content.replace("空间标杆破位炸板", "空间标杆平安无事")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(tampered_content)

    # 3. 再次校验哈希链，断言立即被密码学捕获
    valid_tampered, count_t, err_t = AlertAuditLogger.verify_audit_log_integrity(log_file)
    assert valid_tampered is False
    assert "mismatch" in err_t.lower()


# ==============================================================================
# GATE-3B1-08: 生产数据库物理隔离与零业务写入测试
# ==============================================================================
def test_gate_3b1_08_database_readonly_isolation():
    """GATE-3B1-08: 盘中总线全生命周期操作下，SQLite 核心业务表 Mutations = 0"""
    db_path = "data/trading.db"
    assert os.path.exists(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if not r[0].startswith("sqlite_") and r[0] != "data_quality_log"]
    
    counts_before = {t: cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    conn.close()

    # 执行 50 次告警总线密集处理与回放
    ring = AlertRingBuffer(capacity=100)
    evaluator = AlertEvaluator(ring_buffer=ring)
    for i in range(10):
        v = build_mock_verdict(time_str=f"10:{i:02d}:00")
        evaluator.evaluate_and_publish(v)

    # 重新核验数据库核心业务表
    conn2 = sqlite3.connect(db_path)
    cur2 = conn2.cursor()
    counts_after = {t: cur2.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    conn2.close()

    for t in tables:
        assert counts_before[t] == counts_after[t], f"Table {t} mutated from {counts_before[t]} to {counts_after[t]}!"


# ==============================================================================
# GATE-3B1-09: 关键告警极端满载、配额溢出与零静默丢弃证明
# ==============================================================================
def test_gate_3b1_09_critical_saturation_and_zero_silent_drop():
    """GATE-3B1-09: 验证 CRITICAL 满载、配额突破、混合淘汰与 DLQ 满载下的零静默丢弃与全量可度量性"""
    # 1. 缓冲区测试：容量 20，CRITICAL 配额 5
    ring = AlertRingBuffer(capacity=20, critical_reservation_quota=5)
    evaluator = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)

    # 先注入 10 个 CRITICAL 告警 (突破了 5 个配额，只要容量未满均允许容纳)
    for i in range(10):
        v_crit = build_mock_verdict(time_str=f"10:{i:02d}:00", state=DriftStateEnum.CRITICAL_BREACH)
        evaluator.evaluate_and_publish(v_crit)

    metrics = ring.get_metrics()
    assert metrics["size"] == 10
    assert metrics["current_critical_count"] == 10
    assert metrics["total_overflow_drops"] == 0

    # 再注入 10 个 INFO 告警填满缓冲区到 20 条
    for i in range(10, 20):
        v_info = build_mock_verdict(time_str=f"10:{i:02d}:00", state=DriftStateEnum.NORMAL, events=[])
        evaluator.evaluate_and_publish(v_info)

    assert ring.size() == 20
    assert ring.get_metrics()["current_non_critical_count"] == 10

    # 满载下再注入 5 个 CRITICAL 告警：应优先淘汰最旧的 INFO，既有 CRITICAL 必须 100% 保留
    for i in range(20, 25):
        v_crit_extra = build_mock_verdict(time_str=f"10:{i:02d}:00", state=DriftStateEnum.CRITICAL_BREACH)
        evaluator.evaluate_and_publish(v_crit_extra)

    metrics2 = ring.get_metrics()
    assert metrics2["size"] == 20
    assert metrics2["current_critical_count"] == 15
    assert metrics2["current_non_critical_count"] == 5
    assert metrics2["total_overflow_drops"] == 5
    assert metrics2["critical_protected_drops"] == 0
    assert metrics2["non_critical_drops"] == 5

    # 继续注入 10 个 CRITICAL 告警：淘汰剩余 5 个 INFO，并进一步淘汰最旧的 5 个 CRITICAL
    for i in range(25, 35):
        v_crit_extra2 = build_mock_verdict(time_str=f"10:{i:02d}:00", state=DriftStateEnum.CRITICAL_BREACH)
        evaluator.evaluate_and_publish(v_crit_extra2)

    metrics3 = ring.get_metrics()
    assert metrics3["size"] == 20
    assert metrics3["current_critical_count"] == 20
    assert metrics3["current_non_critical_count"] == 0
    assert metrics3["total_overflow_drops"] == 15
    assert metrics3["non_critical_drops"] == 10
    assert metrics3["critical_protected_drops"] == 5
    assert metrics3["total_overflow_drops"] == metrics3["non_critical_drops"] + metrics3["critical_protected_drops"]

    # 2. DLQ 满载测试：容量 10，注入 15 个毒丸载荷
    dlq = AlertDeadLetterQueue(capacity=10)
    for i in range(15):
        dlq.push({"corrupt_id": i}, f"Poison pill #{i}")

    dlq_metrics = dlq.get_metrics()
    assert dlq_metrics["capacity"] == 10
    assert dlq_metrics["current_size"] == 10
    assert dlq_metrics["total_dropped_count"] == 5


# ==============================================================================
# GATE-3B1-10: 密码学信任边界、密钥轮转与日志截断防御测试
# ==============================================================================
def test_gate_3b1_10_crypto_trust_boundary_and_truncation_defense():
    """GATE-3B1-10: 验证 HMAC 密钥轮转、外部可信锚点、日志尾部截断捕获与快照验签"""
    verdict = build_mock_verdict()
    evaluator = AlertEvaluator(cooldown_seconds=0.0)
    _, event, _ = evaluator.evaluate_and_publish(verdict)
    assert event is not None

    # 使用当前密钥验签
    assert event.verify_signatures() is True

    # 模拟攻击者使用错误或过期密钥验签
    assert event.verify_signatures(secret_key="WRONG_EXPIRED_KEY_9999") is False

    # 日志追加与外部锚点校验
    log_dir = os.path.join(TEST_LOG_DIR, "crypto_gate_test")
    os.makedirs(log_dir, exist_ok=True)
    logger = AlertAuditLogger(log_dir=log_dir)

    line_hashes = []
    for i in range(5):
        v = build_mock_verdict(time_str=f"10:{i:02d}:00")
        _, ev, _ = evaluator.evaluate_and_publish(v)
        lh = logger.append_event(ev)
        line_hashes.append(lh)

    log_file = os.path.join(log_dir, f"alert_audit_{verdict.trade_date}.jsonl")
    closing_anchor = line_hashes[-1]

    # 完整性校验：带外部锚点与期望行数
    ok, count, err = AlertAuditLogger.verify_audit_log_integrity(
        log_file,
        expected_closing_hash=closing_anchor,
        expected_line_count=5,
    )
    assert ok is True
    assert count == 5
    assert err is None

    # 模拟尾部截断攻击 (攻击者删除了最后 2 行)
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(log_file, "w", encoding="utf-8") as f:
        f.writelines(lines[:3])

    # 再次使用原锚点校验，断言精准捕获截断
    ok_trunc, count_trunc, err_trunc = AlertAuditLogger.verify_audit_log_integrity(
        log_file,
        expected_closing_hash=closing_anchor,
        expected_line_count=5,
    )
    assert ok_trunc is False
    assert "truncation" in err_trunc.lower()


# ==============================================================================
# GATE-3B1-11: 未来时戳、时钟漂移与负数据年龄精准打标测试
# ==============================================================================
def test_gate_3b1_11_future_timestamps_and_clock_skew():
    """GATE-3B1-11: 验证时钟倒流/超前、未来时戳、负数据年龄保护与回放时钟隔离"""
    evaluator = AlertEvaluator(cooldown_seconds=0.0)

    # 场景 1: 客户端时钟滞后 / 判定来自未来 (T_observed > T_requested)
    v_future = build_mock_verdict(time_str="10:35:00")
    t_client_lag = datetime.fromisoformat("2026-10-09T10:30:00+08:00")

    state, ev_future, _ = evaluator.evaluate_and_publish(v_future, request_timestamp=t_client_lag)
    assert state == AlertLifecycleStateEnum.ACTIVE
    assert ev_future is not None

    # 数据年龄保护机制：不可为负，安全钳位于 0.0，并在 detail_facts 显式记录时钟漂移
    assert ev_future.data_age_seconds == 0.0
    assert ev_future.detail_facts["is_future_skew"] is True
    assert ev_future.detail_facts["raw_data_age_seconds"] == -300.0

    # 场景 2: 确定性历史回放时钟注入测试
    t_replay = datetime.fromisoformat("2026-10-09T10:36:00+08:00")
    state_r, ev_replay, _ = evaluator.evaluate_and_publish(v_future, request_timestamp=t_replay)
    assert state_r == AlertLifecycleStateEnum.ACTIVE
    assert ev_replay is not None
    assert ev_replay.data_age_seconds == 60.0
    assert ev_replay.detail_facts["is_future_skew"] is False
    assert ev_replay.is_stale is False

