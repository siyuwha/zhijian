import json
import pytest
from datetime import datetime
from sqlalchemy import select
from app.core.database import async_session
from app.models.market import MarketDailySnapshot
from app.models.cognition_v2 import CognitionRecord, CognitionChainState
from app.cognition.bridge import CognitionBridge
from app.cognition.guard import CognitionAdmissionGuard, CognitionAdmissionError
from app.cognition.health import ChainHealthService
from app.cognition.observation.contracts import (
    ObservationSnapshot,
    ObservationWindow,
    CognitionStage,
    SourceCredential,
    QualityLevel,
    FactType,
    FactStatus,
    Freshness,
    FactItem,
    FourDimensionalTime,
    Provenance,
)
from app.cognition.clock import DeterministicClock


def _build_dummy_fact(
    fact_key: str,
    fact_type: FactType,
    status: FactStatus = FactStatus.AVAILABLE,
    event_time: str = "2026-10-02T15:00:00.000+08:00",
    observed_time: str = "2026-10-02T15:00:05.000+08:00",
) -> FactItem:
    return FactItem(
        fact_id=f"f_{fact_key}",
        fact_key=fact_key,
        fact_type=fact_type,
        time_context=FourDimensionalTime(
            event_time=event_time,
            observed_time=observed_time,
            ingestion_time=observed_time,
            effective_time=event_time,
        ),
        status=status,
        freshness=Freshness.REALTIME,
        source="mock_test",
        source_record_id="rec_1",
        payload={"score": 100},
        provenance=Provenance(primary_source="mock_test", trace_id="tr_1"),
        fact_fingerprint="fp_dummy",
    )


def _build_dummy_snapshot(
    quality: QualityLevel = QualityLevel.FULL,
    facts: list = None,
) -> ObservationSnapshot:
    if facts is None:
        facts = [
            _build_dummy_fact("index.sh000001", FactType.INDEX_QUOTE),
            _build_dummy_fact("breadth.market", FactType.MARKET_BREADTH),
        ]
    return ObservationSnapshot(
        snapshot_id="obs_test_001",
        schema_version="1.0.0",
        market_date="2026-10-02",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(
            window_start="2026-10-02T09:15:00.000+08:00",
            window_end="2026-10-02T15:00:00.000+08:00",
        ),
        snapshot_time="2026-10-02T15:05:00.000+08:00",
        overall_quality=quality,
        fact_items=facts,
        degraded_fields=[],
        source_manifest=[
            SourceCredential(
                source_name="mock_test",
                fetch_status="SUCCESS",
                latency_ms=1.0,
                records_count=len(facts),
            )
        ],
        snapshot_fingerprint="snap_fp_dummy",
    )


def test_guard_passes_valid_snapshot():
    """验证合规快照正常通过准入守卫"""
    snap = _build_dummy_snapshot()
    # 应当静默通过无异常
    CognitionAdmissionGuard.validate_snapshot(snap)


def test_guard_rejects_invalid_quality():
    """验证硬阻断规则 1：INVALID 数据拒绝"""
    snap = _build_dummy_snapshot(quality=QualityLevel.INVALID)
    with pytest.raises(CognitionAdmissionError) as exc_info:
        CognitionAdmissionGuard.validate_snapshot(snap)
    assert exc_info.value.rule_name == "REJECT_INVALID_QUALITY"
    assert "INVALID" in exc_info.value.reason


def test_guard_rejects_missing_critical_fact():
    """验证硬阻断规则 2：关键事实类型缺失拒绝"""
    # 仅提供指数行情，缺失市场广度
    only_index = [_build_dummy_fact("index.sh000001", FactType.INDEX_QUOTE)]
    snap = _build_dummy_snapshot(facts=only_index)
    with pytest.raises(CognitionAdmissionError) as exc_info:
        CognitionAdmissionGuard.validate_snapshot(snap)
    assert exc_info.value.rule_name == "REJECT_MISSING_CRITICAL_FACT"
    assert "MARKET_BREADTH" in exc_info.value.reason


def test_guard_rejects_fatal_critical_fact_status():
    """验证硬阻断规则 2 延伸：关键事实出现致命故障（TIMEOUT/ERROR）拒绝"""
    broken_facts = [
        _build_dummy_fact("index.sh000001", FactType.INDEX_QUOTE, status=FactStatus.TIMEOUT),
        _build_dummy_fact("breadth.market", FactType.MARKET_BREADTH),
    ]
    snap = _build_dummy_snapshot(facts=broken_facts)
    with pytest.raises(CognitionAdmissionError) as exc_info:
        CognitionAdmissionGuard.validate_snapshot(snap)
    assert exc_info.value.rule_name == "REJECT_FATAL_CRITICAL_FACT_STATUS"
    assert "TIMEOUT" in exc_info.value.reason


def test_guard_rejects_time_inversion():
    """验证硬阻断规则 3：时间倒挂/未来时钟拒绝"""
    inverted_facts = [
        _build_dummy_fact("index.sh000001", FactType.INDEX_QUOTE),
        _build_dummy_fact(
            "breadth.market",
            FactType.MARKET_BREADTH,
            event_time="2026-10-02T16:00:00.000+08:00",  # 比 observed 晚 1 小时
            observed_time="2026-10-02T15:00:00.000+08:00",
        ),
    ]
    snap = _build_dummy_snapshot(facts=inverted_facts)
    with pytest.raises(CognitionAdmissionError) as exc_info:
        CognitionAdmissionGuard.validate_snapshot(snap)
    assert exc_info.value.rule_name == "REJECT_TIME_INVERSION"
    assert "倒挂" in exc_info.value.reason or "inversion" in exc_info.value.reason.lower()


@pytest.mark.asyncio
async def test_bridge_aborts_on_admission_error_without_polluting_chain():
    """验证集成防护：上游快照数据损坏触发准入拦截时，桥梁立即终止，绝不推进链指针亦不污染不可变账本"""
    async with async_session() as session:
        bridge = CognitionBridge(session)
        health_svc = ChainHealthService(session)

        initial_status = await health_svc.get_chain_status()
        initial_seq = initial_status["tail_sequence_id"]

        # 构造一个损坏的 snapshot (缺少任何行情，指数快照为不可解析的空结构)
        broken_snap = MarketDailySnapshot(
            date="2026-10-25",
            snapshot_type="EOD_CLOSE",
            indices_snapshot=None,  # 严重损坏，缺少关键事实
            breadth_snapshot=None,
            market_state_snapshot=None,
            data_quality="INVALID",
        )

        with pytest.raises(CognitionAdmissionError):
            await bridge.record_daily_review("2026-10-25", broken_snap)

        # 验证防御效果：链指针完全未变动
        post_status = await health_svc.get_chain_status()
        assert post_status["tail_sequence_id"] == initial_seq

        # 验证该日期记录在不可变账本中为 0
        rec_stmt = select(CognitionRecord).where(CognitionRecord.date == "2026-10-25")
        recs = list((await session.execute(rec_stmt)).scalars().all())
        assert len(recs) == 0


@pytest.mark.asyncio
async def test_chain_health_observability_status_and_audit():
    """验证链健康可观察性：只读状态查询与全链哈希闭合自验正常工作"""
    async with async_session() as session:
        health_svc = ChainHealthService(session)

        # 1. 验证 get_chain_status
        status = await health_svc.get_chain_status()
        assert status["chain_id"] == "MAIN_LEDGER"
        assert status["is_initialized"] is True
        assert status["status"] in ("HEALTHY", "OUT_OF_SYNC")
        assert "tail_sequence_id" in status
        assert "tail_record_hash" in status

        # 2. 验证 audit_chain_health
        audit = await health_svc.audit_chain_health()
        assert audit["healthy"] is True
        assert audit["error"] is None
        assert audit["status"]["is_state_synced"] is True
