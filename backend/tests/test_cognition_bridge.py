import json
import pytest
from datetime import datetime
from sqlalchemy import select, text
from app.core.database import async_session
from app.models.market import MarketDailySnapshot
from app.models.report import DailyReview
from app.models.cognition_v2 import CognitionRecord, CognitionChainState
from app.cognition.bridge import CognitionBridge
from app.cognition.hash_chain import verify_chain_integrity, verify_single_record
from app.cognition.clock import DeterministicClock
from app.services.daily_review import DailyReviewService


def make_valid_indices(base_price=3300.0, base_pct=1.0):
    return [
        {"code": "s_sh000001", "name": "上证指数", "price": base_price, "pct_change": base_pct, "amount_wan": 450000.0},
        {"code": "s_sz399001", "name": "深证成指", "price": 10500.0, "pct_change": base_pct * 0.8, "amount_wan": 550000.0},
        {"code": "s_sz399006", "name": "创业板指", "price": 2100.0, "pct_change": base_pct * 1.2, "amount_wan": 250000.0},
        {"code": "s_sh000688", "name": "科创50", "price": 980.0, "pct_change": base_pct * 0.9, "amount_wan": 150000.0},
    ]


def make_valid_breadth():
    return {"up_count": 3200, "down_count": 1500, "total_amount": 12000.0}


@pytest.mark.asyncio
async def test_bridge_records_daily_review_and_advances_chain():
    """验证最小认知桥梁：合规 M1 复盘成功通过准入并写入不可变账本"""
    async with async_session() as session:
        bridge = CognitionBridge(session)
        test_date = "2026-10-01"

        indices_data = make_valid_indices(3300.0, 1.2)
        breadth_data = make_valid_breadth()
        limit_up_data = {"limit_up_count": 58, "broken_ratio": 0.15, "max_height": 5}
        dimensions_data = {
            "label": "BALANCED",
            "composite_score": 62.5,
            "D1": {"score": 65.0},
            "D2": {"score": 60.0},
            "D6": {"score": 62.0}
        }

        snapshot = MarketDailySnapshot(
            date=test_date,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps(indices_data, ensure_ascii=False),
            breadth_snapshot=json.dumps(breadth_data, ensure_ascii=False),
            limit_up_snapshot=json.dumps(limit_up_data, ensure_ascii=False),
            market_state_snapshot=json.dumps(dimensions_data, ensure_ascii=False),
            data_quality="FULL"
        )
        session.add(snapshot)

        review = DailyReview(
            date=test_date,
            market_overview=json.dumps(indices_data, ensure_ascii=False),
            limit_up_analysis=json.dumps(limit_up_data, ensure_ascii=False),
            report_content=json.dumps({"title": "复盘", "market_state": dimensions_data}, ensure_ascii=False),
            data_quality="FULL"
        )
        session.add(review)
        await session.commit()
        await session.refresh(snapshot)
        await session.refresh(review)

        # 驱动桥梁写入
        clk = DeterministicClock.frozen(datetime(2026, 10, 1, 15, 5, 0))
        rec = await bridge.record_daily_review(test_date, snapshot, review, clock=clk)

        assert rec is not None
        assert rec.date == test_date
        assert rec.stage == "POST_CLOSE"
        assert rec.sequence_id >= 1
        assert len(rec.record_hash) == 64
        assert len(rec.previous_record_hash) == 64

        # 验真单条记录哈希
        is_valid, err = verify_single_record(rec)
        assert is_valid is True, f"单记录验真失败: {err}"

        # 检查 chain_state 指针同步前进
        chain_stmt = select(CognitionChainState).where(CognitionChainState.chain_id == "MAIN_LEDGER")
        state = (await session.execute(chain_stmt)).scalar_one()
        assert state.tail_sequence_id == rec.sequence_id
        assert state.tail_record_hash == rec.record_hash


@pytest.mark.asyncio
async def test_bridge_sequential_chain_integrity():
    """验证最小认知桥梁：多交易日跨日推演满足单调自增、无空洞与链式严格前驱闭合"""
    async with async_session() as session:
        bridge = CognitionBridge(session)

        # 写入相邻两日数据，保证多交易日链条严格闭合
        day_a = "2026-10-11"
        day_b = "2026-10-12"

        snap_a = MarketDailySnapshot(
            date=day_a,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps(make_valid_indices(3310.0, 0.3), ensure_ascii=False),
            breadth_snapshot=json.dumps(make_valid_breadth(), ensure_ascii=False),
            market_state_snapshot=json.dumps({"label": "BALANCED", "composite_score": 60.0}),
            data_quality="FULL"
        )
        snap_b = MarketDailySnapshot(
            date=day_b,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps(make_valid_indices(3330.0, 0.6), ensure_ascii=False),
            breadth_snapshot=json.dumps(make_valid_breadth(), ensure_ascii=False),
            market_state_snapshot=json.dumps({"label": "OVERHEATED", "composite_score": 75.0}),
            data_quality="FULL"
        )
        session.add_all([snap_a, snap_b])
        await session.commit()
        await session.refresh(snap_a)
        await session.refresh(snap_b)

        clk_a = DeterministicClock.frozen(datetime(2026, 10, 11, 15, 5, 0))
        clk_b = DeterministicClock.frozen(datetime(2026, 10, 12, 15, 5, 0))

        rec_a = await bridge.record_daily_review(day_a, snap_a, clock=clk_a)
        rec_b = await bridge.record_daily_review(day_b, snap_b, clock=clk_b)

        assert rec_a is not None
        assert rec_b is not None
        assert rec_b.sequence_id == rec_a.sequence_id + 1
        assert rec_b.previous_record_hash == rec_a.record_hash

        # 查询全量历史账本
        stmt = select(CognitionRecord).order_by(CognitionRecord.sequence_id.asc())
        records = list((await session.execute(stmt)).scalars().all())
        assert len(records) >= 2

        # 运行全链完整性验真器
        chain_valid, chain_err = verify_chain_integrity(records)
        assert chain_valid is True, f"全链完整性检验失败: {chain_err}"


@pytest.mark.asyncio
async def test_bridge_idempotency_prevents_forks():
    """验证最小认知桥梁幂等性：重复写入同一天同一阶段不会产生重复记录或导致链条分叉"""
    async with async_session() as session:
        bridge = CognitionBridge(session)
        day = "2026-10-13"

        snap = MarketDailySnapshot(
            date=day,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps(make_valid_indices(3340.0, 0.4), ensure_ascii=False),
            breadth_snapshot=json.dumps(make_valid_breadth(), ensure_ascii=False),
            market_state_snapshot=json.dumps({"label": "BALANCED", "composite_score": 58.0}),
            data_quality="FULL"
        )
        session.add(snap)
        await session.commit()
        await session.refresh(snap)

        # 首次调用桥接器
        rec1 = await bridge.record_daily_review(day, snap)
        assert rec1 is not None

        # 第二次调用桥接器
        rec2 = await bridge.record_daily_review(day, snap)
        assert rec2.id == rec1.id
        assert rec2.record_hash == rec1.record_hash

        # 数据库中该日期该阶段记录总数依然严格为 1
        stmt = select(CognitionRecord).where(
            CognitionRecord.date == day,
            CognitionRecord.stage == "POST_CLOSE",
            CognitionRecord.replay_type == "ORIGINAL"
        )
        recs = list((await session.execute(stmt)).scalars().all())
        assert len(recs) == 1


@pytest.mark.asyncio
async def test_worm_trigger_guards_bridged_records():
    """验证最小认知桥梁产出的记录受物理 WORM 触发器刚性保护，禁止篡改与删除"""
    async with async_session() as session:
        # 获取或生成记录
        stmt = select(CognitionRecord).order_by(CognitionRecord.sequence_id.desc()).limit(1)
        rec = (await session.execute(stmt)).scalars().first()
        if not rec:
            bridge = CognitionBridge(session)
            snap = MarketDailySnapshot(
                date="2026-10-14",
                snapshot_type="EOD_CLOSE",
                indices_snapshot=json.dumps(make_valid_indices(3300.0, 0.5), ensure_ascii=False),
                breadth_snapshot=json.dumps(make_valid_breadth(), ensure_ascii=False),
                data_quality="FULL"
            )
            session.add(snap)
            await session.commit()
            rec = await bridge.record_daily_review("2026-10-14", snap)
        rec_id = rec.id

    # 1. 直接 SQL 篡改攻击：必须被 WORM 触发器拦截
    async with async_session() as session_upd:
        with pytest.raises(Exception) as exc_info:
            await session_upd.execute(
                text(f"UPDATE cognition_record SET stage = 'TAMPERED' WHERE id = '{rec_id}'")
            )
            await session_upd.commit()
        assert "WORM Violation" in str(exc_info.value) or "prohibited" in str(exc_info.value)

    # 2. 直接 SQL 删除攻击：必须被 WORM 触发器拦截
    async with async_session() as session_del:
        with pytest.raises(Exception) as exc_info_del:
            await session_del.execute(
                text(f"DELETE FROM cognition_record WHERE id = '{rec_id}'")
            )
            await session_del.commit()
        assert "WORM Violation" in str(exc_info_del.value) or "prohibited" in str(exc_info_del.value)


@pytest.mark.asyncio
async def test_daily_review_service_e2e_triggers_cognition_bridge():
    """验证端到端：DailyReviewService.generate_review 自动触发 CognitionBridge 写入不可变账本"""
    async with async_session() as session:
        today = "2026-10-20"
        # 预设基础快照，使复盘服务直接基于快照生成，保证离线隔离与毫秒级速度
        snap = MarketDailySnapshot(
            date=today,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps(make_valid_indices(3350.0, 0.5), ensure_ascii=False),
            breadth_snapshot=json.dumps(make_valid_breadth(), ensure_ascii=False),
            limit_up_snapshot=json.dumps({"limit_up_count": 50, "broken_ratio": 0.12, "max_height": 4}),
            market_state_snapshot=json.dumps({"label": "BALANCED", "composite_score": 60.0}),
            data_quality="FULL"
        )
        session.add(snap)
        await session.commit()

        review_service = DailyReviewService(session)
        review = await review_service.generate_review(today)
        assert review is not None
        assert review.date == today

        # 验证 CognitionRecord 已被桥梁自动接入
        stmt = select(CognitionRecord).where(
            CognitionRecord.date == today,
            CognitionRecord.stage == "POST_CLOSE"
        )
        cog_rec = (await session.execute(stmt)).scalars().first()
        assert cog_rec is not None
        assert cog_rec.stage == "POST_CLOSE"
        assert cog_rec.sequence_id >= 1
        assert len(cog_rec.record_hash) == 64

        # 验真单条记录与账本指针
        valid, err = verify_single_record(cog_rec)
        assert valid is True, f"端到端记录哈希验真失败: {err}"
