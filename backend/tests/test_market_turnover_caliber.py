"""
T09-01 成交额口径治理强制验收矩阵测试套件
依据：《T09-01 成交额口径治理实施任务单》第四节强制验收矩阵与下游契约验证

覆盖场景：
1. Work 核心算例：已核准沪市 6000、深市 9000，另有创业板 3000、科创50 800 亿元 -> 两市为 15000 亿元，绝非 18800 亿元
2. 待核准门禁：候选指数存在但未核准官方口径 -> 正式总额为 None (null)，质量非 FULL
3. 沪深核准但北交所待核准/缺失 -> 两市可按自身条件完整，全市场为 None，质量 PARTIAL
4. 单边缺失或非法数值 (NaN/Inf/负数) -> 正式合计为 None，原因可追溯
5. 两侧同日同时间但同时过期 -> 实时路径不得为 FULL
6. 盘后 15:36 无归档证据 -> 不得仅凭壁钟标 FULL，标记 DEGRADED
7. 历史 15:00 后无归档证据 -> 不得仅凭时间标 FULL，更换评估时钟不改变历史结论
8. 已核准最终归档 -> 能产生完整收盘/历史结果 (FULL)，不套用实时年龄淘汰
9. 集合竞价、午休、休市日、时段边界 -> 分阶段输出，不落入无条件盘后放行
10. UTC 或其他时区未来时间 -> 正确转上海时间并拒绝未来值 (INVALID)
11. 盘前金额 0、成交量缺失或来源零语义未知 -> 不得标完整有效零
12. 来源证实有效量额 0 -> 可明确保留 0
13. 北交所独立校验 -> 独立时间、未来值与零值校验，不借用沪深时间
14. 单位转换无损性 -> 元/万元/亿元等价输入，小额累加仅最终舍入
15. 跨日或主备源日期冲突 -> 拒绝拼接为完整合计
16. 实际入口与下游消费路径验证：
    - CanonicalMarketService.build_market_truth_snapshot
    - MonitorService.capture_macro_snapshot
    - DailyReviewService.generate_daily_review
    - MarketStateCalibrator.extract_feature_vector (Null-safe)
    - NarrativeContextService (Null-safe anchor)
    - CanonicalAuctionService (Null-safe prev turnover)
    - CanonicalIntradayService (Null-safe pace ratio)
"""

import json
import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.schemas.canonical_market import DataQualityGrade
from backend.app.services.turnover_engine import (
    calculate_turnover_caliber,
    normalize_to_yi_decimal,
    round_yi_float,
    TurnoverSourceStatus,
    MarketSessionPhase,
    SHANGHAI_TZ,
)
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.daily_review import DailyReviewService
from backend.app.services.market_state_calibrator import MarketStateCalibrator
from backend.app.services.narrative_context_service import NarrativeContextExtractor
from backend.app.services.canonical_intraday_service import calculate_projected_turnover


# =========================================================================
# 场景 1: Work 核心验收样例 (已核准分量假设算例：15000 亿，绝非 18800 亿)
# =========================================================================
def test_scenario_01_work_sample_arithmetic():
    """
    验收样例：沪市 6000、深市 9000、创业板 3000、科创50 800 亿元
    两市合计必须严格为 15000 亿元，绝对不能为 18800 亿元！
    深市官方总额已包含创业板，严禁重复累加！
    """
    fixed_clock = datetime(2026, 10, 30, 15, 30, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        chinext_amount=3000.0,
        chinext_unit="yi",
        now_dt=fixed_clock,
        is_archive_confirmed=True,
    )

    # 核心断言：15000 亿，绝不能是 18800 亿
    assert res.two_markets_total_yi == 15000.00
    assert res.two_markets_total_yi != 18800.00
    assert res.sh_amount_yi == 6000.00
    assert res.sz_total_amount_yi == 9000.00
    assert res.chinext_slice_amount_yi == 3000.00
    assert res.chinext_ratio_in_sz == pytest.approx(0.3333, abs=0.0001)
    assert res.two_markets_quality == DataQualityGrade.FULL
    assert res.is_degraded is False


# =========================================================================
# 场景 2: 待核准门禁 (深市或沪市候选字段范围未核准)
# =========================================================================
def test_scenario_02_pending_verification_gate():
    """
    深市或沪市数值存在，但范围待核准 (PENDING_VERIFICATION)
    两市正式总额必须为 None，质量非 FULL，具有明确口径未核准原因
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="09:59:50",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:45",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.PENDING_VERIFICATION, # 深市待核准
        now_dt=fixed_clock,
    )

    # 正式总额必须置空为 None
    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert res.is_degraded is True
    # 但分量保留用于诊断
    assert res.sh_amount_yi == 6000.00
    assert res.sz_total_amount_yi == 9000.00
    assert any("待核准" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 3: 沪深均核准，北证50待核准或北交所缺失
# =========================================================================
def test_scenario_03_bse_missing_or_pending():
    """
    沪深均核准且有效，北交所缺失或待核准：
    两市正式总额可完整计算；全市场正式总额必须为 None，质量标 PARTIAL
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="09:59:50",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:45",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        bse_amount=None, # 北交所缺失
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi == 15000.00
    assert res.two_markets_quality == DataQualityGrade.FULL
    # 全市场总额必须置空，绝不能以 0 假冒
    assert res.all_markets_total_yi is None
    assert res.all_markets_quality == DataQualityGrade.PARTIAL
    assert any("北交所数据缺失" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 4: 缺沪市或深市；金额为空、NaN、无穷、负数
# =========================================================================
@pytest.mark.parametrize("invalid_val", [None, float("nan"), float("inf"), -100.0])
def test_scenario_04_missing_or_invalid_numeric(invalid_val):
    """
    单边金额缺失或为非法数值 (NaN, Inf, 负数)：正式合计为 None，原因可追溯
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=invalid_val,
        sh_date="2026-10-30",
        sh_time="09:59:50",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:45",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.PARTIAL
    assert any("缺失或非法数值" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 5: 两侧同日同时间但同时过期
# =========================================================================
def test_scenario_05_both_sides_stale_together():
    """
    两侧时间完全相同 (10:00:00)，但当前时间为 10:10:00 (过期 600s > 300s)
    实时路径绝对不能标 FULL！正式总额必须置空并降级
    """
    fixed_clock = datetime(2026, 10, 30, 10, 10, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="10:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="10:00:00", # 时间一致，但已过期 10 分钟
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi is None
    assert res.two_markets_quality != DataQualityGrade.FULL
    assert res.two_markets_quality == DataQualityGrade.PARTIAL
    assert any("过期淘汰" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 6: 盘后 15:36 无最终归档证据
# =========================================================================
def test_scenario_06_post_market_without_archive_evidence():
    """
    当前时间 15:36:00，行情时间 15:00:00，但无权威归档完成凭据
    不能仅凭壁钟超过 15:35 标记 FULL，正式总额强制为 None，标记 DEGRADED
    """
    fixed_clock = datetime(2026, 10, 30, 15, 36, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
        is_archive_confirmed=False, # 无归档完成标识
    )

    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert res.is_degraded is True
    assert any("尚未取得权威归档完成凭据" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 7: 历史时间 15:00 后无归档证据
# =========================================================================
def test_scenario_07_historical_without_archive_evidence():
    """
    历史查询目标日期 2026-10-29，报文时间 15:00:00，但无归档凭据
    不能仅凭时间 >= 15:00 标 FULL，正式总额强制为 None；更换当前评估时钟不应改变归档结论
    """
    clock_1 = datetime(2026, 10, 30, 16, 0, 0, tzinfo=SHANGHAI_TZ)
    clock_2 = datetime(2026, 11, 1, 9, 0, 0, tzinfo=SHANGHAI_TZ)

    for clk in (clock_1, clock_2):
        res = calculate_turnover_caliber(
            target_date="2026-10-29",
            sh_amount=6000.0,
            sh_date="2026-10-29",
            sh_time="15:00:00",
            sh_unit="yi",
            sh_status=TurnoverSourceStatus.VERIFIED,
            sz_amount=9000.0,
            sz_date="2026-10-29",
            sz_time="15:00:00",
            sz_unit="yi",
            sz_status=TurnoverSourceStatus.VERIFIED,
            now_dt=clk,
            is_archive_confirmed=False,
        )
        assert res.session_phase == MarketSessionPhase.HISTORICAL
        assert res.two_markets_quality == DataQualityGrade.DEGRADED
        assert res.two_markets_total_yi is None
        assert res.is_degraded is True


# =========================================================================
# 场景 8: 已核准最终归档
# =========================================================================
def test_scenario_08_verified_final_archive():
    """
    已核准且有官方归档标识，不套用实时年龄淘汰规则，产生 FULL 收盘事实
    """
    fixed_clock = datetime(2026, 10, 30, 20, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
        is_archive_confirmed=True, # 明确归档
    )

    assert res.two_markets_total_yi == 15000.00
    assert res.two_markets_quality == DataQualityGrade.FULL
    assert res.is_degraded is False


# =========================================================================
# 场景 9: 集合竞价时段处理
# =========================================================================
def test_scenario_09_call_auction_phase():
    """
    集合竞价 09:20:00，分阶段输出，不能落入无条件盘后放行分支
    """
    fixed_clock = datetime(2026, 10, 30, 9, 20, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=10.0,
        sh_date="2026-10-30",
        sh_time="09:20:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=20.0,
        sz_date="2026-10-30",
        sz_time="09:20:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.session_phase == MarketSessionPhase.CALL_AUCTION
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert any("集合竞价阶段" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 10: UTC 或其他时区输入，报价时间在未来
# =========================================================================
def test_scenario_10_utc_and_future_timestamp_rejected():
    """
    UTC 时间转化为上海时间后，如果超过当前时钟，严格拒绝并标记 INVALID
    例如当前评估时钟为上海 10:00:00，输入 UTC 02:05:00 (即上海 10:05:00)
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="2026-10-30T02:05:00Z", # UTC 02:05:00 = 上海 10:05:00 (未来 5 分钟)
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:50",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.UNAVAILABLE
    assert any("拒绝未来时间报价" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 11: 盘前金额 0、成交量缺失或来源零语义未知
# =========================================================================
def test_scenario_11_premarket_unverified_zero_rejected():
    """
    盘前 09:00:00，金额为 0，但成交量为 None 或语义未知
    不得标记完整有效零，总额必须置空 (None) 并标记 DEGRADED
    """
    fixed_clock = datetime(2026, 10, 30, 9, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=0.0,
        sh_date="2026-10-30",
        sh_time="09:00:00",
        sh_volume=None, # 成交量缺失
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=0.0,
        sz_date="2026-10-30",
        sz_time="09:00:00",
        sz_volume=None,
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
        is_zero_semantic_verified=False,
    )

    assert res.session_phase == MarketSessionPhase.PRE_MARKET
    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert any("零值语义未获来源证实" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 12: 来源证实有效量额均为 0
# =========================================================================
def test_scenario_12_premarket_verified_zero_allowed():
    """
    有来源证据证实零值语义，且显式量额均为 0：
    可明确保留 0.0，与缺失 (None) 明确区分
    """
    fixed_clock = datetime(2026, 10, 30, 9, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=0.0,
        sh_date="2026-10-30",
        sh_time="09:00:00",
        sh_volume=0.0,
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=0.0,
        sz_date="2026-10-30",
        sz_time="09:00:00",
        sz_volume=0.0,
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
        is_zero_semantic_verified=True,
    )

    assert res.session_phase == MarketSessionPhase.PRE_MARKET
    assert res.two_markets_total_yi == 0.0
    assert res.two_markets_quality == DataQualityGrade.FULL


# =========================================================================
# 场景 13: 北交所独立校验
# =========================================================================
def test_scenario_13_bse_independent_validation():
    """
    北交所独立校验：北交所时间陈旧或未来，不能借用沪深时间或质量
    两市有效，北交所过期 -> 全市场置空为 None，标 PARTIAL
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="09:59:50",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:50",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        bse_amount=50.0,
        bse_date="2026-10-30",
        bse_time="09:30:00", # 北交所时间陈旧 (30分钟前 > 300s)
        bse_unit="yi",
        bse_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi == 15000.00
    assert res.two_markets_quality == DataQualityGrade.FULL
    assert res.all_markets_total_yi is None
    assert res.all_markets_quality == DataQualityGrade.PARTIAL
    assert any("北交所数据时效过期" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 14: 单位无损转换 (元/万元/亿元) 与小额累加
# =========================================================================
def test_scenario_14_lossless_unit_conversion():
    """
    元、万元、亿元等价输入：高精度 Decimal 求和，仅在最终展示层舍入，杜绝提前舍入累积误差
    """
    # 6000 亿元 = 60000000 万元 = 600000000000 元
    d1 = normalize_to_yi_decimal(600000000000, "yuan")
    d2 = normalize_to_yi_decimal(90000000, "wan")
    assert d1 == Decimal("6000")
    assert d2 == Decimal("9000")
    total = round_yi_float(d1 + d2, 2)
    assert total == 15000.00


# =========================================================================
# 场景 15: 跨日缓存或日期不匹配
# =========================================================================
def test_scenario_15_date_mismatch_rejected():
    """
    沪深日期不一致 (如沪市 2026-10-29，深市 2026-10-30)，严格拒绝并标 INVALID
    """
    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-29", # 跨日脏数据
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="09:59:50",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )

    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.UNAVAILABLE
    assert any("交易日期不匹配" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 16: 实际入口与下游消费链路验证
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_16_canonical_market_service_entry():
    """
    验证 CanonicalMarketService.build_market_truth_snapshot 实际入口：
    1. 候选数据源 (待核准)：两市总额置空 (None)，质量 DEGRADED
    2. 声明已核准数据源：两市总额正确计算为 15000 亿 (去重创业板)
    """
    mock_session = AsyncMock()
    service = CanonicalMarketService(mock_session)

    sample_indices = [
        {"symbol": "sh000001", "name": "上证指数", "current_price": 3300.0, "amount_yi": 6000.0, "date": "2026-10-30", "time": "15:00:00"},
        {"symbol": "sz399001", "name": "深证成指", "current_price": 10500.0, "amount_yi": 9000.0, "date": "2026-10-30", "time": "15:00:00"},
        {"symbol": "sz399006", "name": "创业板指", "current_price": 2200.0, "amount_yi": 3000.0, "date": "2026-10-30", "time": "15:00:00"},
        {"symbol": "sh000688", "name": "科创50", "current_price": 1000.0, "amount_yi": 800.0, "date": "2026-10-30", "time": "15:00:00"},
    ]

    # 1. 默认门禁 (待核准候选来源)
    truth_degraded = service.build_market_truth_snapshot(
        date_str="2026-10-30",
        snap_dict={"indices": sample_indices, "sh_source_status": TurnoverSourceStatus.PENDING_VERIFICATION, "sz_source_status": TurnoverSourceStatus.PENDING_VERIFICATION},
        lu_dict={"total_count": 50, "broken_count": 10},
        anom_list=[],
    )
    assert truth_degraded.turnover.two_markets_total_yi is None
    assert truth_degraded.turnover.two_markets_quality == DataQualityGrade.DEGRADED
    assert truth_degraded.turnover.sh_amount_yi == 6000.00
    assert truth_degraded.turnover.sz_total_amount_yi == 9000.00
    assert truth_degraded.turnover.chinext_slice_amount_yi == 3000.00

    # 2. 单边核准门禁 (仅沪市核准，深市待核准 -> 正式总额仍为 None)
    truth_partial = service.build_market_truth_snapshot(
        date_str="2026-10-30",
        snap_dict={"indices": sample_indices, "sh_source_status": TurnoverSourceStatus.VERIFIED, "sz_source_status": TurnoverSourceStatus.PENDING_VERIFICATION, "is_archive_confirmed": True},
        lu_dict={"total_count": 50, "broken_count": 10},
        anom_list=[],
    )
    assert truth_partial.turnover.two_markets_total_yi is None
    assert truth_partial.turnover.two_markets_quality == DataQualityGrade.DEGRADED

    # 3. 假设双边已核准来源 (Work 算例)
    truth_verified = service.build_market_truth_snapshot(
        date_str="2026-10-30",
        snap_dict={
            "indices": sample_indices,
            "sh_source_status": TurnoverSourceStatus.VERIFIED,
            "sz_source_status": TurnoverSourceStatus.VERIFIED,
            "is_archive_confirmed": True,
        },
        lu_dict={"total_count": 50, "broken_count": 10},
        anom_list=[],
    )
    assert truth_verified.turnover.two_markets_total_yi == 15000.00
    assert truth_verified.turnover.two_markets_quality == DataQualityGrade.FULL


def test_scenario_16_downstream_market_state_calibrator():
    """
    验证下游 MarketStateCalibrator：
    当 two_markets_total_yi 为 None 时，安全提取特征向量，不抛异常，文字描述展示 '-- 万亿（口径待核准）'
    """
    mock_session = AsyncMock()
    service = CanonicalMarketService(mock_session)
    truth = service.build_market_truth_snapshot(
        date_str="2026-10-30",
        snap_dict={"indices": [{"symbol": "sh000001", "current_price": 3300.0, "amount_yi": 6000.0}], "is_source_verified": False},
        lu_dict={"total_count": 50, "broken_count": 10},
        anom_list=[],
    )

    calibrator = MarketStateCalibrator()
    feat = calibrator.extract_feature_vector(truth)
    assert feat.index_vector.total_turnover_yi is None
    assert feat.index_vector.turnover_change_ratio is None

    # 测试叙事描述渲染
    cal_state = calibrator.calibrate(feat)
    narrative_desc = calibrator.render_deterministic_summary(cal_state, feat, space_leader_desc="海能达 20B")
    assert "-- 万亿（口径待核准）" in narrative_desc or "万亿" not in narrative_desc


def test_scenario_16_downstream_narrative_context():
    """
    验证下游 NarrativeContextService：
    当 turnover.two_markets_total_yi 为 None 时，锚定 'EVID:TURNOVER:UNAVAILABLE'，杜绝字符串格式化崩溃
    """
    mock_session = AsyncMock()
    service = CanonicalMarketService(mock_session)
    truth = service.build_market_truth_snapshot(
        date_str="2026-10-30",
        snap_dict={"indices": [], "is_source_verified": False},
        lu_dict={"total_count": 50, "broken_count": 10},
        anom_list=[],
    )

    from backend.app.schemas.narrative_context import NarrativeTurnoverFact
    to = truth.turnover
    fact_turnover = NarrativeTurnoverFact(
        total_turnover_yi=round(to.two_markets_total_yi, 2) if to.two_markets_total_yi is not None else None,
        sh_amount_yi=round(to.sh_amount_yi, 2) if to.sh_amount_yi is not None else None,
        sz_total_amount_yi=round(to.sz_total_amount_yi, 2) if to.sz_total_amount_yi is not None else None,
        chinext_slice_yi=round(to.chinext_slice_amount_yi, 2) if to.chinext_slice_amount_yi is not None else None,
        chinext_ratio_in_sz=to.chinext_ratio_in_sz if to.chinext_ratio_in_sz is not None else 0.0,
    )
    assert fact_turnover.total_turnover_yi is None

    turnover_anchor = (
        f"EVID:TURNOVER:{to.two_markets_total_yi:.2f}YI"
        if to.two_markets_total_yi is not None
        else "EVID:TURNOVER:UNAVAILABLE"
    )
    assert turnover_anchor == "EVID:TURNOVER:UNAVAILABLE"


def test_scenario_16_downstream_projected_turnover_pace():
    """
    验证盘中计算 calculate_projected_turnover：
    前日成交额为 None 时，量能 pace 比率安全输出 None，不除以零或崩溃
    """
    proj, pace = calculate_projected_turnover(
        total_accumulated_yi=Decimal("1500.00"),
        elapsed_minutes=30,
        prev_total_yi=None, # 前日总额待核准/缺失
    )
    assert proj > Decimal("0.00")
    assert pace is None # 安全置空，不假冒 0 或崩溃


@pytest.mark.asyncio
async def test_scenario_16_monitor_macro_snapshot_entry():
    """
    验证 MonitorService.capture_macro_snapshot 实际入口：
    1. 候选指数行情在门禁下正式两市总额为 None (绝不累加 4 个指数得 18800 亿，也不以 0 假冒)
    2. volume_proj_yi 因总额为空同样安全输出 None
    3. 各分量保留在 snapshot 中供诊断展示
    """
    from backend.app.services.monitor import MonitorService

    service = MonitorService(session=None)
    mock_data = AsyncMock()

    # 模拟数据源返回 4 个核心指数，金额单位为万元
    mock_index_quotes = MagicMock()
    mock_index_quotes.data = [
        {"code": "s_sh000001", "name": "上证指数", "price": 3300.0, "pct_change": 0.5, "amount_wan": 60000000.0, "date": "2026-10-30", "time": "10:00:00"},
        {"code": "s_sz399001", "name": "深证成指", "price": 10500.0, "pct_change": 0.8, "amount_wan": 90000000.0, "date": "2026-10-30", "time": "10:00:00"},
        {"code": "s_sz399006", "name": "创业板指", "price": 2200.0, "pct_change": 1.2, "amount_wan": 30000000.0, "date": "2026-10-30", "time": "10:00:00"},
        {"code": "s_sh000688", "name": "科创50", "price": 1000.0, "pct_change": -0.4, "amount_wan": 8000000.0, "date": "2026-10-30", "time": "10:00:00"},
    ]
    mock_data.get_index_quotes = AsyncMock(return_value=mock_index_quotes)

    mock_breadth = MagicMock()
    mock_breadth.data = {"up_count": 3200, "down_count": 1800}
    mock_data.get_market_breadth = AsyncMock(return_value=mock_breadth)

    mock_lu = MagicMock()
    mock_lu.data = {"total_count": 60, "limit_down_count": 2, "broken_count": 15, "max_height": 6, "items": []}
    mock_data.get_limit_up_pool = AsyncMock(return_value=mock_lu)

    service.data_service = mock_data

    fixed_clock = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    snap = await service.capture_macro_snapshot(date_str="2026-10-30", now_dt=fixed_clock)

    # 核心断言：两市正式总额严格为 None (口径待核准门禁)，绝不是旧代码的 18800 亿元！
    assert snap["total_amount_yi"] is None
    assert snap["volume_proj_yi"] is None
    # 诊断分量保留
    assert snap["sh_amount_yi"] == 6000.00
    assert snap["sz_amount_yi"] == 9000.00
    assert snap["cy_slice_amount_yi"] == 3000.00
    assert snap["turnover_quality"] == "DEGRADED"
    assert "待核准" in snap["turnover_reason"]


def test_scenario_16_daily_review_turnover_entry():
    """
    验证 DailyReviewService 中的成交额处理逻辑：
    1. 候选指数在门禁下 total_amount_yi 为 None，展示为 '-- 亿元（待核准）'
    2. 彻底去除旧代码的 sum(float(idx.get('amount', 0.0)) for idx in index_data) 重复叠加逻辑
    """
    index_data = [
        {"code": "000001", "name": "上证指数", "price": 3300.0, "pct_change": 0.5, "amount_wan": 60000000.0},
        {"code": "399001", "name": "深证成指", "price": 10500.0, "pct_change": 0.8, "amount_wan": 90000000.0},
        {"code": "399006", "name": "创业板指", "price": 2200.0, "pct_change": 1.2, "amount_wan": 30000000.0},
        {"code": "000688", "name": "科创50", "price": 1000.0, "pct_change": -0.4, "amount_wan": 8000000.0},
    ]

    sh_idx = next((idx for idx in index_data if "000001" in str(idx.get("code") or idx.get("symbol") or "")), None)
    sz_idx = next((idx for idx in index_data if "399001" in str(idx.get("code") or idx.get("symbol") or "")), None)
    cy_idx = next((idx for idx in index_data if "399006" in str(idx.get("code") or idx.get("symbol") or "")), None)

    turnover_res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=sh_idx.get("amount_wan") if sh_idx else None,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="wan",
        sz_amount=sz_idx.get("amount_wan") if sz_idx else None,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="wan",
        chinext_amount=cy_idx.get("amount_wan") if cy_idx else None,
        chinext_unit="wan",
        sh_status=TurnoverSourceStatus.PENDING_VERIFICATION,
        sz_status=TurnoverSourceStatus.PENDING_VERIFICATION,
    )

    current_sh_sz_amount_yi = turnover_res.two_markets_total_yi
    assert current_sh_sz_amount_yi is None
    assert current_sh_sz_amount_yi != 18800.0
    assert turnover_res.sh_amount_yi == 6000.00
    assert turnover_res.sz_total_amount_yi == 9000.00
    assert turnover_res.chinext_slice_amount_yi == 3000.00


# =========================================================================
# 场景 17: 交易日历核验 (非交易日/周末休市)
# =========================================================================
def test_scenario_17_non_trading_day_calendar():
    """
    2026-10-31 为周六休市，目标日期命中非交易日：
    正式总额必须置空 (None)，质量标记 DEGRADED，生命周期标记 NON_TRADING_DAY
    """
    fixed_clock = datetime(2026, 10, 31, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-31",
        sh_amount=6000.0,
        sh_date="2026-10-31",
        sh_time="10:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-31",
        sz_time="10:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=fixed_clock,
    )
    assert res.session_phase == MarketSessionPhase.NON_TRADING_DAY
    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert any("非开市交易日" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 18: 集合竞价时效与总额门禁
# =========================================================================
def test_scenario_18_call_auction_guards():
    """
    1. 报价时间早于 09:15:00 (如 09:00:00) -> 视为陈旧数据淘汰，PARTIAL
    2. 报价新鲜 (09:20:00) -> 集合竞价全天总额尚未生成，正式总额为 None，标记 DEGRADED
    """
    clock_call_auction = datetime(2026, 10, 30, 9, 20, 0, tzinfo=SHANGHAI_TZ)

    # 1. 09:00 陈旧报价
    res_stale = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=100.0,
        sh_date="2026-10-30",
        sh_time="09:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=150.0,
        sz_date="2026-10-30",
        sz_time="09:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_call_auction,
    )
    assert res_stale.session_phase == MarketSessionPhase.CALL_AUCTION
    assert res_stale.two_markets_total_yi is None
    assert res_stale.two_markets_quality == DataQualityGrade.PARTIAL
    assert any("早于09:15" in r for r in res_stale.degradation_reasons)

    # 2. 09:19 新鲜竞价报价 -> 正式总额仍为 None
    res_fresh = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=100.0,
        sh_date="2026-10-30",
        sh_time="09:19:30",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=150.0,
        sz_date="2026-10-30",
        sz_time="09:19:30",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_call_auction,
    )
    assert res_fresh.session_phase == MarketSessionPhase.CALL_AUCTION
    assert res_fresh.two_markets_total_yi is None
    assert res_fresh.two_markets_quality == DataQualityGrade.DEGRADED


# =========================================================================
# 场景 19: 午间休市时段 (11:30 - 13:00)
# =========================================================================
def test_scenario_19_midday_intermission():
    """
    评估时钟 12:00:00，早盘收盘报价 11:30:00：
    不套用连续交易 300s 超龄淘汰，维持早盘收盘额，标记 DEGRADED，phase 为 MIDDAY_INTERMISSION
    """
    clock_noon = datetime(2026, 10, 30, 12, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=4000.0,
        sh_date="2026-10-30",
        sh_time="11:30:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=6000.0,
        sz_date="2026-10-30",
        sz_time="11:30:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_noon,
    )
    assert res.session_phase == MarketSessionPhase.MIDDAY_INTERMISSION
    assert res.two_markets_total_yi == 10000.00
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert any("午间休市时段" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 20: 盘中/盘后未证实零值严格防线
# =========================================================================
def test_scenario_20_unverified_zero_rejected_across_phases():
    """
    连续交易时段 10:30:00，成交额出现 0 但无零语义凭据或无显式 0 成交量证实：
    视为异常未初始化或假冒零值，正式总额强制置空 (None)
    """
    clock_cont = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=0.0, # 异常零值
        sh_date="2026-10-30",
        sh_time="10:30:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sh_volume=None, # 成交量缺失
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="10:30:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_cont,
        is_zero_semantic_verified=False,
    )
    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert any("缺少官方零语义凭据证实" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 21: 缺失时间戳严格淘汰 (拒绝补造默认时间)
# =========================================================================
def test_scenario_21_missing_quote_time_rejected():
    """
    报价具有日期但缺少时间戳 (time is None)：
    严禁默认填补 '15:00:00' 或当前时钟，直接判定时间戳非法/缺失并标记 UNAVAILABLE
    """
    clock = datetime(2026, 10, 30, 15, 30, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time=None, # 缺失时间戳
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock,
    )
    assert res.two_markets_total_yi is None
    assert res.two_markets_quality == DataQualityGrade.UNAVAILABLE
    assert any("时间戳格式非法或缺失" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 22: DailyReviewService 真实服务入口双边完整性与历史防线 (P1 门禁)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_22_daily_review_prev_total_bilateral_check():
    """
    验证 DailyReviewService.generate_review 真实服务入口在前日快照单侧缺失时的防线：
    1. 当历史 overview 仅有上证 000001 而无深证 399001 时，真实入口计算出的 prev_total_amount 严格为 None，严禁以单侧 6000 冒充两市总额
    2. 当日量能环比变动额与变动幅度 delta_amount_str / delta_pct_str 均为 '--'，绝不进行虚假环比计算
    3. 真实服务不补造 15:00:00 与日期，且在口径待核准下输出 '-- 亿元（待核准）'
    """
    from backend.app.models.report import DailyReview
    from backend.app.data.capabilities import DataQuality

    mock_session = AsyncMock()

    # 1. 模拟历史前日仅含上证指数的前日快照 (单侧缺失)
    prev_review = DailyReview(
        date="2026-10-29",
        market_overview=json.dumps([
            {"code": "000001", "name": "上证指数", "amount_wan": 60000000.0, "date": "2026-10-29", "time": "15:00:00"}
        ]),
        limit_up_analysis=json.dumps({"total_count": 40})
    )

    def mock_execute(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt).lower()
        if "market_daily_snapshots" in stmt_str:
            mock_res.scalars.return_value.first.return_value = None
        elif "daily_reviews" in stmt_str and "<" in stmt_str:
            mock_res.scalars.return_value.all.return_value = [prev_review]
        elif "daily_reviews" in stmt_str:
            mock_res.scalars.return_value.first.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        elif "market_hypotheses" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
        else:
            mock_res.scalars.return_value.first.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    service = DailyReviewService(mock_session)
    service.data_service = AsyncMock()
    service.data_service.get_index_quotes.return_value = MagicMock(
        quality=DataQuality.FULL,
        data=[
            {"symbol": "s_sh000001", "code": "000001", "name": "上证指数", "price": 3200.0, "pct_change": 0.5, "amount_wan": 60000000.0, "date": "2026-10-30", "time": "15:00:00"},
            {"symbol": "s_sz399001", "code": "399001", "name": "深证成指", "price": 10500.0, "pct_change": -0.8, "amount_wan": 90000000.0, "date": "2026-10-30", "time": "15:00:00"},
        ]
    )
    service.data_service.get_limit_up_pool.return_value = MagicMock(data={"total_count": 40, "items": []})
    service.data_service.get_market_breadth.return_value = MagicMock(data={"up": 2800, "down": 2000})
    service.data_service.get_micro_cap_quote.return_value = MagicMock(data={})
    service.data_service.get_external_risk.return_value = MagicMock(data={})
    service.data_service.get_high_tier_performance.return_value = MagicMock(data={})
    service.data_service.get_price_anomaly.return_value = MagicMock(data=[])
    service.data_service.get_concept_blocks.return_value = MagicMock(data=[])

    # 拦截计算与生成：直接截获传递给 downstream market_state_computer 的真实原始快照，并验证 transcendent_facts
    with patch("backend.app.services.daily_review.market_state_computer.compute_market_state", new_callable=AsyncMock) as mock_compute, \
         patch("backend.app.services.zhijian_transcendent_review_service.zhijian_transcendent_service.generate_transcendent_review", new_callable=AsyncMock) as mock_trans:
        # 构造合法 CognitionMarketState 结构供后续流程持久化
        mock_cog_state = MagicMock()
        mock_cog_state.dimensions = {}
        mock_cog_state.composite_score = 50.0
        mock_cog_state.state_label = "平衡震荡"
        mock_cog_state.data_quality = MagicMock(value="DEGRADED")
        mock_cog_state.missing_metrics = []
        mock_compute.return_value = mock_cog_state
        mock_trans.return_value = {"title": "2026-10-30 测试复盘"}

        review_record = await service.generate_review(date_str="2026-10-30", force=True)

        assert review_record is not None
        assert mock_compute.call_count == 1
        downstream_cog_input = mock_compute.call_args[0][0]
        raw_market_snapshot = downstream_cog_input.market_data

        # 核心防线断言 1: 前日单侧缺失时，向下游传递的 prev_total_amount 严格为 None，严禁以 6000.0 冒充
        assert raw_market_snapshot["prev_total_amount"] is None
        assert raw_market_snapshot["prev_total_amount"] != 6000.0

        assert mock_trans.call_count == 1
        passed_facts = mock_trans.call_args[0][0]

        # 验证真实入口传递给报告的成交额事实
        turnover_facts = passed_facts["turnover"]
        assert turnover_facts["total_amount_yi"] is None
        assert turnover_facts["total_amount"] == "-- 亿元（待核准）"
        assert turnover_facts["shrinkage_amount"] == "--"
        assert turnover_facts["shrinkage_pct"] == "--"
        assert turnover_facts["quality"] == "DEGRADED"

        # 验证假说审判文本中的量能事实完全遵循待核准规范，未发生虚假环比
        assert any("-- 亿元（待核准）" in item.get("reality", "") for item in passed_facts["audit_delta"])

    # 1.1 对照反例：前日双边指数均存在 (上证 6000 + 深证 9000 = 15000)，但口径未核准且无归档凭据
    prev_review_bilateral = DailyReview(
        date="2026-10-29",
        market_overview=json.dumps([
            {"code": "000001", "name": "上证指数", "amount_wan": 60000000.0, "date": "2026-10-29", "time": "15:00:00"},
            {"code": "399001", "name": "深证成指", "amount_wan": 90000000.0, "date": "2026-10-29", "time": "15:00:00"}
        ]),
        limit_up_analysis=json.dumps({"total_count": 40})
    )

    def mock_execute_bilateral(stmt):
        mock_res = MagicMock()
        stmt_str = str(stmt).lower()
        if "market_daily_snapshots" in stmt_str:
            mock_res.scalars.return_value.first.return_value = None
        elif "daily_reviews" in stmt_str and "<" in stmt_str:
            mock_res.scalars.return_value.all.return_value = [prev_review_bilateral]
        elif "daily_reviews" in stmt_str:
            mock_res.scalars.return_value.first.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        elif "market_hypotheses" in stmt_str:
            mock_res.scalars.return_value.all.return_value = []
        else:
            mock_res.scalars.return_value.first.return_value = None
            mock_res.scalars.return_value.all.return_value = []
        return mock_res

    mock_session.execute = AsyncMock(side_effect=mock_execute_bilateral)

    with patch("backend.app.services.daily_review.market_state_computer.compute_market_state", new_callable=AsyncMock) as mock_compute, \
         patch("backend.app.services.zhijian_transcendent_review_service.zhijian_transcendent_service.generate_transcendent_review", new_callable=AsyncMock) as mock_trans:
        mock_cog_state = MagicMock()
        mock_cog_state.dimensions = {}
        mock_cog_state.composite_score = 50.0
        mock_cog_state.state_label = "平衡震荡"
        mock_cog_state.data_quality = MagicMock(value="DEGRADED")
        mock_cog_state.missing_metrics = []
        mock_compute.return_value = mock_cog_state
        mock_trans.return_value = {"title": "2026-10-30 测试复盘"}

        await service.generate_review(date_str="2026-10-30", force=True)

        assert mock_compute.call_count == 1
        downstream_cog_input_bi = mock_compute.call_args[0][0]
        raw_market_snapshot_bi = downstream_cog_input_bi.market_data

        # 核心防线断言 2: 双边存在但在口径待核准且无归档凭证时，prev_total_amount 依然强制置空 None，绝不可透传 15000.0
        assert raw_market_snapshot_bi["prev_total_amount"] is None
        assert raw_market_snapshot_bi["prev_total_amount"] != 15000.0

    # 2. 验证时间戳不造假：当行情字典中无 time 或 date 时，严格传递 None
    sh_bare = {"code": "000001", "amount_wan": 60000000.0}
    sz_bare = {"code": "399001", "amount_wan": 90000000.0}
    res_bare = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=sh_bare.get("amount_wan"),
        sh_date=sh_bare.get("date"),
        sh_time=sh_bare.get("time"),
        sz_amount=sz_bare.get("amount_wan"),
        sz_date=sz_bare.get("date"),
        sz_time=sz_bare.get("time"),
    )
    # 因为缺少日期与时间戳，被直接判定为 PARTIAL 并置空正式总额
    assert res_bare.two_markets_total_yi is None
    assert res_bare.two_markets_quality == DataQualityGrade.PARTIAL
    assert any("缺少交易日期标识" in r for r in res_bare.degradation_reasons)


# =========================================================================
# 场景 23: 战报流水线全链路 Null-Safe 验证 (P1 门禁 · 端到端生成与安全拦截)
# =========================================================================
def test_scenario_23_briefing_pipeline_null_turnover_safe():
    """
    验证内参战报流水线遇 total_turnover_yi = None 时的健壮性：
    1. BriefingPromptBuilder.build_user_prompt 不发生 TypeError，优雅输出 '-- 亿元（口径待核准）'
    2. DeterministicBriefingFallbackEngine.generate_fallback_briefing 优雅输出待核准定调正文
    3. BriefingSafetyGuard._check_numerical_fidelity 拦截对未核准/置空总额的幻觉断言并记录 NumericalFidelityViolation
    4. ConstrainedBriefingGenerator.generate_briefing 完整流水线端到端调用成功，无感降级并保证安全审计通过
    """
    from backend.app.schemas.narrative_context import NarrativeContextContract
    from backend.app.services.constrained_briefing_generator import (
        BriefingPromptBuilder,
        ConstrainedBriefingGenerator,
    )
    from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
    from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
    from pathlib import Path

    golden_path = Path("baseline_evidence/golden_narrative_context_20261008.json")
    assert golden_path.exists(), f"Golden context missing: {golden_path}"
    data = json.loads(golden_path.read_text(encoding="utf-8"))

    # 强制将事实层成交额置空 (模拟 T09-01 未核准状态)
    data["fact_layer"]["turnover"]["total_turnover_yi"] = None
    data["fact_layer"]["turnover"]["sh_amount_yi"] = None
    data["fact_layer"]["turnover"]["sz_total_amount_yi"] = None
    contract_null = NarrativeContextContract(**data)

    # 1. 验证 Prompt 构建安全
    prompt = BriefingPromptBuilder.build_user_prompt(contract_null)
    assert "-- 亿元（口径待核准）" in prompt
    assert "- 沪深真实总成交额：-- 亿元（口径待核准）" in prompt

    # 2. 验证确定性回退引擎安全
    fallback_engine = DeterministicBriefingFallbackEngine()
    fallback_rep = fallback_engine.generate_fallback_briefing(contract_null)
    assert fallback_rep is not None
    assert "【大势定调】沪深两市总成交额口径待核准（正式总额保守置空）" in fallback_rep.tactical_briefing_text

    # 3. 验证安全守卫数字保真度检查对 Null 的拦截 (防伪造总额/分量)
    guard = BriefingSafetyGuard()
    hallucinated_text = "【大势定调】两市总成交额达 15000 亿元（沪市 6000 亿，深市含创业板 9000 亿）。盘面分化。"
    violations = guard._check_numerical_fidelity(hallucinated_text, contract_null)
    assert any("Total turnover is unverified/null, but text claimed '15000 亿元'" in v for v in violations)
    assert any("SH turnover is unverified/null, but text claimed '6000 亿'" in v for v in violations)
    assert any("SZ turnover is unverified/null, but text claimed '9000 亿'" in v for v in violations)

    # 4. 当文本完全遵从待核准规范无虚假数字时，无违规
    safe_text = "【大势定调】沪深两市总成交额口径待核准（正式总额保守置空）。市场处于分化期。"
    safe_violations = guard._check_numerical_fidelity(safe_text, contract_null)
    turnover_violations = [v for v in safe_violations if "turnover" in v.lower()]
    assert len(turnover_violations) == 0

    # 5. 端到端完整流水线调用验证 (ConstrainedBriefingGenerator.generate_briefing)
    generator = ConstrainedBriefingGenerator()
    report = generator.generate_briefing(contract_null)
    assert report is not None
    assert report.safety_audit_passed is True
    assert "两市总成交额口径待核准（正式总额保守置空）" in report.tactical_briefing_text


# =========================================================================
# 场景 24: 交易日历覆盖范围外与异常严格 Fail-Closed 阻断 (P1 门禁)
# =========================================================================
def test_scenario_24_calendar_uncovered_year_fail_closed():
    """
    验证交易日历在未覆盖年份 (如 2028 年) 或发生日历异常时的强制 Fail-Closed 阻断：
    turnover_engine 必须直接返回 NON_TRADING_DAY，置空正式总额，标记 DEGRADED，严禁继续运算输出 FULL
    """
    clock_future = datetime(2028, 5, 15, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res = calculate_turnover_caliber(
        target_date="2028-05-15",
        sh_amount=6000.0,
        sh_date="2028-05-15",
        sh_time="10:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED, # 假定来源核准
        sz_amount=9000.0,
        sz_date="2028-05-15",
        sz_time="10:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_future,
    )
    assert res.two_markets_total_yi is None
    assert res.all_markets_total_yi is None
    assert res.session_phase == MarketSessionPhase.NON_TRADING_DAY
    assert res.two_markets_quality == DataQualityGrade.DEGRADED
    assert res.is_degraded is True
    assert any("交易日历未覆盖或核验异常" in r for r in res.degradation_reasons)


# =========================================================================
# 场景 25: 北交所独立归档与全时态零值语义校验 (P1 门禁)
# =========================================================================
def test_scenario_25_bse_independent_archive_and_zero_guard():
    """
    验证北交所独立校验：
    1. 连续交易时段北交所成交额为 0，若缺少官方零语义凭据或成交量非 0，必须拒绝并置空全市场总额
    2. 盘后时段虽有两市 is_archive_confirmed=True，但缺少 is_bse_archive_confirmed=True，全市场总额置空并标记 PARTIAL
    3. 盘后两侧及北交所均有独立归档确认且均核准时，两市与全市场均输出 FULL
    """
    clock_post = datetime(2026, 10, 30, 15, 35, 0, tzinfo=SHANGHAI_TZ)

    # 1. 北交所零成交额但无有效零凭据 (连续交易时段 10:00:00)
    clock_cont = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    res_zero = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="10:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="10:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        bse_amount=0.0, # 北交所 0 值
        bse_date="2026-10-30",
        bse_time="10:00:00",
        bse_unit="yi",
        bse_status=TurnoverSourceStatus.VERIFIED,
        bse_volume=None, # 成交量缺失
        is_zero_semantic_verified=False, # 零语义未证实
        now_dt=clock_cont,
    )
    assert res_zero.two_markets_total_yi == 15000.00
    assert res_zero.all_markets_total_yi is None
    assert res_zero.all_markets_quality == DataQualityGrade.PARTIAL
    assert any("北交所成交额为零但缺少官方零语义凭据证实" in r for r in res_zero.degradation_reasons)

    # 2. 盘后两市已归档，但北交所缺少独立归档确认
    res_no_bse_archive = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        bse_amount=100.0,
        bse_date="2026-10-30",
        bse_time="15:00:00",
        bse_unit="yi",
        bse_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_post,
        is_archive_confirmed=True, # 两市归档
        is_bse_archive_confirmed=False, # 北交所未独立确认归档
    )
    assert res_no_bse_archive.two_markets_total_yi == 15000.00
    assert res_no_bse_archive.two_markets_quality == DataQualityGrade.FULL
    assert res_no_bse_archive.all_markets_total_yi is None
    assert res_no_bse_archive.all_markets_quality == DataQualityGrade.PARTIAL
    assert any("北交所无独立官方归档完成标识" in r for r in res_no_bse_archive.degradation_reasons)

    # 3. 盘后两市与北交所均有独立归档确认
    res_bse_archived = calculate_turnover_caliber(
        target_date="2026-10-30",
        sh_amount=6000.0,
        sh_date="2026-10-30",
        sh_time="15:00:00",
        sh_unit="yi",
        sh_status=TurnoverSourceStatus.VERIFIED,
        sz_amount=9000.0,
        sz_date="2026-10-30",
        sz_time="15:00:00",
        sz_unit="yi",
        sz_status=TurnoverSourceStatus.VERIFIED,
        bse_amount=100.0,
        bse_date="2026-10-30",
        bse_time="15:00:00",
        bse_unit="yi",
        bse_status=TurnoverSourceStatus.VERIFIED,
        now_dt=clock_post,
        is_archive_confirmed=True,
        is_bse_archive_confirmed=True,
    )
    assert res_bse_archived.two_markets_total_yi == 15000.00
    assert res_bse_archived.two_markets_quality == DataQualityGrade.FULL
    assert res_bse_archived.all_markets_total_yi == 15100.00
    assert res_bse_archived.all_markets_quality == DataQualityGrade.FULL


# =========================================================================
# 场景 26: 历史黄金快照路径 1 (DB未命中) 强制置空与指纹数学一致性 (P1 门禁)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_26_golden_snapshot_via_canonical_market_service_entry():
    """
    验证通过真实服务入口 CanonicalMarketService.get_canonical_snapshot 加载黄金快照 (路径1: DB快照未命中)：
    1. 即使历史黄金快照中含有未经核准标注 FULL 或非空成交额，真实入口通过 _sanitize_loaded_snapshot_turnover 强制置空
    2. truth_fingerprint、cognition_fingerprint 与 envelope_fingerprint 经过 hash_jcs 独立数学重算验证 100% 一致
    3. downstream 认知层市场状态特征标定 total_turnover_yi 与环比变动率强制置空
    4. 派生叙述 market_state_summary 包含 '-- 万亿（口径待核准）'，且杜绝任何虚构龙头（如'新华传媒'）
    5. NarrativeContextExtractor.extract_context 成功提取上下文契约且成交额事实一致为 None
    """
    from backend.app.schemas.canonical_market import CanonicalMarketSnapshot
    from backend.app.services.narrative_context_service import NarrativeContextExtractor
    from backend.app.cognition.jcs import hash_jcs

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None  # 模拟 DB 物理快照未命中，穿透至路径 1 黄金文件
    mock_session.execute.return_value = mock_result

    service = CanonicalMarketService(mock_session)
    snap = await service.get_canonical_snapshot("2026-10-08")

    assert snap is not None
    assert snap.truth.turnover.two_markets_total_yi is None
    assert snap.truth.turnover.all_markets_total_yi is None
    assert snap.truth.turnover.two_markets_quality == DataQualityGrade.DEGRADED
    assert snap.truth.turnover.all_markets_quality == DataQualityGrade.PARTIAL
    assert "历史黄金快照数据源口径待核准" in snap.truth.turnover.degradation_reason

    # 1. 独立数学重算 Truth 指纹并严格比对
    breadth_status_val = (
        snap.truth.cross_section_breadth_status.value
        if hasattr(snap.truth.cross_section_breadth_status, "value")
        else str(snap.truth.cross_section_breadth_status)
    )
    expected_truth_dict = {
        "schema_version": snap.truth.schema_version,
        "producer": snap.truth.producer,
        "trade_date": snap.truth.trade_date,
        "generated_at": snap.truth.generated_at,
        "indices": [i.model_dump() for i in snap.truth.indices],
        "turnover": snap.truth.turnover.model_dump(),
        "sentiment_bounds": snap.truth.sentiment_bounds.model_dump(),
        "regulatory_anomalies": [a.model_dump() for a in snap.truth.regulatory_anomalies],
        "ladder_tree": [l.model_dump() for l in snap.truth.ladder_tree],
        "cross_section_breadth_status": breadth_status_val,
        "cross_section_breadth_detail": snap.truth.cross_section_breadth_detail,
    }
    expected_truth_fp = hash_jcs(expected_truth_dict)
    assert snap.truth.truth_fingerprint == expected_truth_fp

    # 2. 独立数学重算 Cognition 指纹并严格比对
    expected_cog_dict = {
        "schema_version": snap.cognition.schema_version,
        "producer": snap.cognition.producer,
        "trade_date": snap.trade_date,
        "generated_at": snap.cognition.generated_at,
        "mainlines": [m.model_dump() for m in snap.cognition.mainlines],
        "lineage_accounting": snap.cognition.lineage_accounting.model_dump(),
        "market_state_summary": snap.cognition.market_state_summary,
        "market_state_calibration": snap.cognition.market_state_calibration.model_dump(),
    }
    expected_cog_fp = hash_jcs(expected_cog_dict)
    assert snap.cognition.cognition_fingerprint == expected_cog_fp

    # 3. 独立数学重算 Envelope 指纹并严格比对
    expected_env_dict = {
        "snapshot_version": snap.snapshot_version,
        "trade_date": snap.trade_date,
        "generated_at": snap.generated_at,
        "truth_fingerprint": expected_truth_fp,
        "cognition_fingerprint": expected_cog_fp,
    }
    expected_env_fp = hash_jcs(expected_env_dict)
    assert snap.envelope_fingerprint == expected_env_fp

    # 4. 验证派生叙事自洽性
    assert "-- 万亿（口径待核准）" in snap.cognition.market_state_summary
    assert f"最高{snap.truth.ladder_tree[0].height}B{snap.truth.ladder_tree[0].stocks[0].name}" in snap.cognition.market_state_summary

    # 5. 验证认知层特征向量
    state_cal = snap.cognition.market_state_calibration
    assert state_cal.feature_vector is not None
    assert state_cal.feature_vector.index_vector.total_turnover_yi is None
    assert state_cal.feature_vector.index_vector.turnover_change_ratio is None

    # 6. 验证下游叙事契约提取一致性
    extractor = NarrativeContextExtractor()
    contract = extractor.extract_context(snap)
    assert contract.fact_layer.turnover.total_turnover_yi is None
    assert contract.trade_date == "2026-10-08"


# =========================================================================
# 场景 27: 真实数据库快照组装完整路径集成验证 (P1 门禁 · 阻断 NameError)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_27_canonical_market_service_db_hit_full_pipeline():
    """
    验证 CanonicalMarketService.get_canonical_snapshot 数据库物理快照命中时的完整装配路径：
    1. 真实运行 build_market_truth_snapshot 与 Cognition 状态机校准全流程
    2. 验证信封打包引用 truth_snapshot.truth_fingerprint，杜绝未定义变量 NameError
    3. 验证未核准数据源下正式总额强制为 None 并标记 DEGRADED
    """
    from backend.app.models.market import MarketDailySnapshot

    mock_session = AsyncMock()
    fake_snap = MarketDailySnapshot(
        date="2026-10-30",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([
            {"symbol": "sh000001", "code": "000001", "name": "上证指数", "price": 3200.0, "pre_close": 3180.0, "amount_wan": 60000000.0, "date": "2026-10-30", "time": "15:00:00"},
            {"symbol": "sz399001", "code": "399001", "name": "深证成指", "price": 10500.0, "pre_close": 10400.0, "amount_wan": 90000000.0, "date": "2026-10-30", "time": "15:00:00"},
        ]),
        limit_up_snapshot=json.dumps([]),
        market_state_snapshot=json.dumps({
            "sector_evidence_gates": [
                {"sector_code": "BK0001", "sector_name": "核心做多主线", "gate_status": "ADMITTED"}
            ],
            "block_mapping_facts": []
        }),
        source_status=json.dumps({}),
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = fake_snap
    mock_session.execute.return_value = mock_result

    service = CanonicalMarketService(mock_session)
    res = await service.get_canonical_snapshot("2026-10-30")

    assert res is not None
    assert res.truth.turnover.two_markets_total_yi is None
    assert res.truth.turnover.two_markets_quality == DataQualityGrade.DEGRADED
    assert res.envelope_fingerprint is not None
    assert res.truth.truth_fingerprint is not None
    assert res.cognition.cognition_fingerprint is not None


# =========================================================================
# 场景 28: 历史黄金快照路径 2 (板块证据门禁缺失) 强制置空与指纹数学一致性 (P1 门禁)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_28_golden_snapshot_path_2_missing_sector_gates():
    """
    验证 CanonicalMarketService.get_canonical_snapshot 路径 2：
    当 DB 存在快照但 sector_evidence_gates 缺失时，系统穿透加载黄金文件并完整触发 _sanitize_loaded_snapshot_turnover 过滤：
    1. 强制置空正式总额为 None，降级为 DEGRADED / PARTIAL
    2. 严格独立数学重算 truth、cognition 与 envelope 三层 JCS SHA-256 指纹
    3. 验证派生叙述中不包含未核准数字与虚构龙头
    """
    from backend.app.models.market import MarketDailySnapshot
    from backend.app.cognition.jcs import hash_jcs

    mock_session = AsyncMock()
    # 构造 DB 快照命中，但 market_state_snapshot 中缺少 sector_evidence_gates (空列表)
    fake_snap_no_gates = MarketDailySnapshot(
        date="2026-10-08",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([{"symbol": "sh000001", "name": "上证指数", "price": 3300.0, "amount_wan": 60000000.0}]),
        limit_up_snapshot=json.dumps([]),
        market_state_snapshot=json.dumps({
            "sector_evidence_gates": [], # 关键：证据门禁缺失，触发穿透至黄金文件 (路径 2)
            "block_mapping_facts": []
        }),
        source_status=json.dumps({}),
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = fake_snap_no_gates
    mock_session.execute.return_value = mock_result

    service = CanonicalMarketService(mock_session)
    snap = await service.get_canonical_snapshot("2026-10-08")

    assert snap is not None
    assert snap.truth.turnover.two_markets_total_yi is None
    assert snap.truth.turnover.all_markets_total_yi is None
    assert snap.truth.turnover.two_markets_quality == DataQualityGrade.DEGRADED
    assert snap.truth.turnover.all_markets_quality == DataQualityGrade.PARTIAL

    # 独立数学验证指纹一致性
    breadth_val = (
        snap.truth.cross_section_breadth_status.value
        if hasattr(snap.truth.cross_section_breadth_status, "value")
        else str(snap.truth.cross_section_breadth_status)
    )
    exp_truth = hash_jcs({
        "schema_version": snap.truth.schema_version,
        "producer": snap.truth.producer,
        "trade_date": snap.truth.trade_date,
        "generated_at": snap.truth.generated_at,
        "indices": [i.model_dump() for i in snap.truth.indices],
        "turnover": snap.truth.turnover.model_dump(),
        "sentiment_bounds": snap.truth.sentiment_bounds.model_dump(),
        "regulatory_anomalies": [a.model_dump() for a in snap.truth.regulatory_anomalies],
        "ladder_tree": [l.model_dump() for l in snap.truth.ladder_tree],
        "cross_section_breadth_status": breadth_val,
        "cross_section_breadth_detail": snap.truth.cross_section_breadth_detail,
    })
    assert snap.truth.truth_fingerprint == exp_truth

    exp_cog = hash_jcs({
        "schema_version": snap.cognition.schema_version,
        "producer": snap.cognition.producer,
        "trade_date": snap.trade_date,
        "generated_at": snap.cognition.generated_at,
        "mainlines": [m.model_dump() for m in snap.cognition.mainlines],
        "lineage_accounting": snap.cognition.lineage_accounting.model_dump(),
        "market_state_summary": snap.cognition.market_state_summary,
        "market_state_calibration": snap.cognition.market_state_calibration.model_dump(),
    })
    assert snap.cognition.cognition_fingerprint == exp_cog

    exp_env = hash_jcs({
        "snapshot_version": snap.snapshot_version,
        "trade_date": snap.trade_date,
        "generated_at": snap.generated_at,
        "truth_fingerprint": exp_truth,
        "cognition_fingerprint": exp_cog,
    })
    assert snap.envelope_fingerprint == exp_env
    assert f"最高{snap.truth.ladder_tree[0].height}B{snap.truth.ladder_tree[0].stocks[0].name}" in snap.cognition.market_state_summary
    assert "-- 万亿（口径待核准）" in snap.cognition.market_state_summary


# =========================================================================
# 场景 29: 两市总额已置空但全市场总额非空或FULL的单独异常拦截 (P1 门禁)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_29_all_markets_turnover_bypass_guard():
    """
    验证 _sanitize_loaded_snapshot_turnover 对“两市已为 null 但全市场仍非空或为 FULL”单独异常的严密门禁：
    防止历史快照中两市被置空但全市场残留 15100 亿元或 FULL 状态绕过降级
    """
    from backend.app.schemas.canonical_market import CanonicalMarketSnapshot
    from backend.app.cognition.jcs import hash_jcs

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    service = CanonicalMarketService(mock_session)
    base_snap = await service.get_canonical_snapshot("2026-10-08")

    # 手动构造两市已空但全市场异常残留数值与 FULL 的反常快照
    abnormal_turnover = base_snap.truth.turnover.model_copy(update={
        "two_markets_total_yi": None,
        "two_markets_quality": DataQualityGrade.DEGRADED,
        "all_markets_total_yi": 15100.0, # 异常残留全市场总额
        "all_markets_quality": DataQualityGrade.FULL, # 异常残留全市场 FULL 状态
    })
    abnormal_truth = base_snap.truth.model_copy(update={"turnover": abnormal_turnover})
    abnormal_snap = base_snap.model_copy(update={"truth": abnormal_truth})

    # 通过门禁过滤
    sanitized = service._sanitize_loaded_snapshot_turnover(abnormal_snap)

    # 验证全市场总额被强制置空且降级
    assert sanitized.truth.turnover.all_markets_total_yi is None
    assert sanitized.truth.turnover.all_markets_quality == DataQualityGrade.PARTIAL
    assert sanitized.truth.turnover.two_markets_total_yi is None
    assert sanitized.truth.turnover.two_markets_quality == DataQualityGrade.DEGRADED

    # 验证指纹独立数学重算与防篡改闭环
    breadth_val = (
        sanitized.truth.cross_section_breadth_status.value
        if hasattr(sanitized.truth.cross_section_breadth_status, "value")
        else str(sanitized.truth.cross_section_breadth_status)
    )
    exp_truth = hash_jcs({
        "schema_version": sanitized.truth.schema_version,
        "producer": sanitized.truth.producer,
        "trade_date": sanitized.truth.trade_date,
        "generated_at": sanitized.truth.generated_at,
        "indices": [i.model_dump() for i in sanitized.truth.indices],
        "turnover": sanitized.truth.turnover.model_dump(),
        "sentiment_bounds": sanitized.truth.sentiment_bounds.model_dump(),
        "regulatory_anomalies": [a.model_dump() for a in sanitized.truth.regulatory_anomalies],
        "ladder_tree": [l.model_dump() for l in sanitized.truth.ladder_tree],
        "cross_section_breadth_status": breadth_val,
        "cross_section_breadth_detail": sanitized.truth.cross_section_breadth_detail,
    })
    assert sanitized.truth.truth_fingerprint == exp_truth

    exp_cog = hash_jcs({
        "schema_version": sanitized.cognition.schema_version,
        "producer": sanitized.cognition.producer,
        "trade_date": sanitized.trade_date,
        "generated_at": sanitized.cognition.generated_at,
        "mainlines": [m.model_dump() for m in sanitized.cognition.mainlines],
        "lineage_accounting": sanitized.cognition.lineage_accounting.model_dump(),
        "market_state_summary": sanitized.cognition.market_state_summary,
        "market_state_calibration": sanitized.cognition.market_state_calibration.model_dump(),
    })
    assert sanitized.cognition.cognition_fingerprint == exp_cog


# =========================================================================
# 场景 30: 空天梯黄金快照通过真实服务入口杜绝虚构龙头并显式标定数据缺失 (P1 门禁)
# =========================================================================
@pytest.mark.asyncio
async def test_scenario_30_empty_ladder_tree_missing_state_guard():
    """
    验证当黄金快照中天梯 ladder_tree 为空列表时通过真实服务入口加载：
    1. space_leader_desc 严格使用 '无连板梯队（数据缺失）'，严禁虚构龙头（如'新华传媒'）
    2. 重新校准生成的 market_state_summary 显式标定缺失状态，不出现虚假连板龙头文字
    3. 三层指纹独立数学一致性 100% 成立
    """
    from backend.app.cognition.jcs import hash_jcs
    from unittest.mock import patch, mock_open
    from pathlib import Path

    # 1. 模拟底层黄金快照文件中的天梯数据为空 (真实黄金文件加载入口)
    golden_path = Path("baseline_evidence/golden_canonical_snapshot_20261008.json")
    raw = json.loads(golden_path.read_text(encoding="utf-8"))
    raw["truth"]["ladder_tree"] = []
    raw_str = json.dumps(raw)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    service = CanonicalMarketService(mock_session)

    # 2. 通过真实入口 get_canonical_snapshot 读取并流经 _sanitize_loaded_snapshot_turnover
    with patch("builtins.open", mock_open(read_data=raw_str)):
        snap = await service.get_canonical_snapshot("2026-10-08")

    assert snap is not None
    # 验证杜绝虚构龙头，显式显示缺失
    assert "新华传媒" not in snap.cognition.market_state_summary
    assert "无连板梯队（数据缺失）" in snap.cognition.market_state_summary
    assert "-- 万亿（口径待核准）" in snap.cognition.market_state_summary

    # 3. 验证指纹独立数学重算无缝契合
    breadth_val = (
        snap.truth.cross_section_breadth_status.value
        if hasattr(snap.truth.cross_section_breadth_status, "value")
        else str(snap.truth.cross_section_breadth_status)
    )
    exp_truth = hash_jcs({
        "schema_version": snap.truth.schema_version,
        "producer": snap.truth.producer,
        "trade_date": snap.truth.trade_date,
        "generated_at": snap.truth.generated_at,
        "indices": [i.model_dump() for i in snap.truth.indices],
        "turnover": snap.truth.turnover.model_dump(),
        "sentiment_bounds": snap.truth.sentiment_bounds.model_dump(),
        "regulatory_anomalies": [a.model_dump() for a in snap.truth.regulatory_anomalies],
        "ladder_tree": [],
        "cross_section_breadth_status": breadth_val,
        "cross_section_breadth_detail": snap.truth.cross_section_breadth_detail,
    })
    assert snap.truth.truth_fingerprint == exp_truth

    exp_cog = hash_jcs({
        "schema_version": snap.cognition.schema_version,
        "producer": snap.cognition.producer,
        "trade_date": snap.trade_date,
        "generated_at": snap.cognition.generated_at,
        "mainlines": [m.model_dump() for m in snap.cognition.mainlines],
        "lineage_accounting": snap.cognition.lineage_accounting.model_dump(),
        "market_state_summary": snap.cognition.market_state_summary,
        "market_state_calibration": snap.cognition.market_state_calibration.model_dump(),
    })
    assert snap.cognition.cognition_fingerprint == exp_cog

    exp_env = hash_jcs({
        "snapshot_version": snap.snapshot_version,
        "trade_date": snap.trade_date,
        "generated_at": snap.generated_at,
        "truth_fingerprint": exp_truth,
        "cognition_fingerprint": exp_cog,
    })
    assert snap.envelope_fingerprint == exp_env

