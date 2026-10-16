"""
短线核心认知指标研究契约与计算引擎测试套件
文件路径：backend/tests/test_research_divergence_contracts_and_calculator.py
上位依据：
1. DOSSIER-COGNITION-RESEARCH-20261016-V1.0 (9 大交付物标准)
2. 验收标准：指标无歧义可复算、分母安全、前视隔离、微观结构约束硬性核验
"""

import pytest
from pydantic import ValidationError
from backend.app.schemas.research_divergence_contract import (
    RearDivergenceMetrics,
    NextDayPenaltyLabel,
    SectorBreadthMetrics,
    LeaderRoleItem,
    LeaderRoleEnum,
    ConfidenceGrade,
    StockRoleTaxonomySnapshot,
    CognitiveResearchPacket,
)
from backend.app.cognition.research.divergence_calculator import DivergenceMetricsCalculator


class TestResearchDivergenceContracts:
    """契约模型安全性与防伪测试"""

    def test_contract_immutability_and_forbid_extra(self):
        """测试契约的不可变性 (frozen=True) 与额外字段禁止 (extra='forbid')"""
        metrics = RearDivergenceMetrics(
            sector_code="BK0968",
            trade_date="2026-10-16",
            evaluation_time="2026-10-16T15:05:00+08:00",
            rear_stock_count=10,
            rear_negative_ratio=0.70,
            avg_spread_fade=4.25,
            avg_peak_pullback=0.038,
            sector_broken_ratio=0.3333,
            core_rear_relative_strength=7.50,
            is_sample_sufficient=True,
            confidence=ConfidenceGrade.L2_DERIVED,
        )

        # 验证只读不可变
        with pytest.raises(ValidationError):
            metrics.rear_stock_count = 12  # type: ignore

        # 验证禁止额外注入字段
        with pytest.raises(ValidationError):
            RearDivergenceMetrics(
                sector_code="BK0968",
                trade_date="2026-10-16",
                evaluation_time="2026-10-16T15:05:00+08:00",
                rear_stock_count=10,
                rear_negative_ratio=0.70,
                avg_spread_fade=4.25,
                avg_peak_pullback=0.038,
                sector_broken_ratio=0.3333,
                core_rear_relative_strength=7.50,
                is_sample_sufficient=True,
                confidence=ConfidenceGrade.L2_DERIVED,
                malicious_field="hack",  # type: ignore
            )

    def test_broken_ratio_zero_denominator_safety(self):
        """测试无人触板时炸板率必须为 None，严禁伪造为 0.0"""
        metrics = RearDivergenceMetrics(
            sector_code="BK0001",
            trade_date="2026-10-16",
            evaluation_time="2026-10-16T15:05:00+08:00",
            rear_stock_count=8,
            rear_negative_ratio=0.50,
            avg_spread_fade=1.2,
            avg_peak_pullback=0.015,
            sector_broken_ratio=None,  # 显式为 None
            core_rear_relative_strength=2.0,
            is_sample_sufficient=True,
            confidence=ConfidenceGrade.L2_DERIVED,
        )
        assert metrics.sector_broken_ratio is None


class TestDivergenceCalculator:
    """计算引擎数学复算与边界测试"""

    def test_rear_divergence_calculation(self):
        """测试后排负反馈五项指标精确数学复算"""
        constituents = [
            # 核心标的 1 (高度 3B, 涨停)
            {
                "code": "000001",
                "name": "平安龙头",
                "close": 13.31,
                "prev_close": 12.10,
                "high": 13.31,
                "amount": 200000.0,
                "is_limit_up": True,
                "touched_limit_up": True,
                "height": 3,
            },
            # 核心标的 2 (容量中军，占板块成交 50%)
            {
                "code": "000002",
                "name": "中军容量",
                "close": 21.00,
                "prev_close": 20.00,
                "high": 21.20,
                "amount": 500000.0,
                "is_limit_up": False,
                "touched_limit_up": False,
                "height": 1,
            },
            # 后排标的 1: 冲高大幅回落 (Prev 10, High 10.8, Close 9.5) -> 负收益, High-Close=1.3
            {
                "code": "000003",
                "name": "后排大面",
                "close": 9.50,
                "prev_close": 10.00,
                "high": 10.80,
                "amount": 50000.0,
                "is_limit_up": False,
                "touched_limit_up": False,
                "height": 1,
            },
            # 后排标的 2: 炸板回落 (Prev 10, High 11.0, Close 10.2) -> 正收益, 曾触板
            {
                "code": "000004",
                "name": "后排炸板",
                "close": 10.20,
                "prev_close": 10.00,
                "high": 11.00,
                "amount": 50000.0,
                "is_limit_up": False,
                "touched_limit_up": True,
                "height": 1,
            },
            # 后排标的 3: 阴跌 (Prev 10, High 10.0, Close 9.6) -> 负收益
            {
                "code": "000005",
                "name": "后排阴跌1",
                "close": 9.60,
                "prev_close": 10.00,
                "high": 10.00,
                "amount": 40000.0,
                "is_limit_up": False,
                "touched_limit_up": False,
                "height": 1,
            },
            # 后排标的 4: 阴跌 (Prev 10, High 10.1, Close 9.4) -> 负收益
            {
                "code": "000006",
                "name": "后排阴跌2",
                "close": 9.40,
                "prev_close": 10.00,
                "high": 10.10,
                "amount": 40000.0,
                "is_limit_up": False,
                "touched_limit_up": False,
                "height": 1,
            },
            # 后排标的 5: 微涨 (Prev 10, High 10.3, Close 10.1) -> 正收益
            {
                "code": "000007",
                "name": "后排微红",
                "close": 10.10,
                "prev_close": 10.00,
                "high": 10.30,
                "amount": 40000.0,
                "is_limit_up": False,
                "touched_limit_up": False,
                "height": 1,
            },
        ]

        metrics = DivergenceMetricsCalculator.calculate_rear_divergence_metrics(
            sector_code="BK0968",
            trade_date="2026-10-16",
            evaluation_time="2026-10-16T15:05:00+08:00",
            constituents=constituents,
        )

        # 核心股票应为 000001 (3B最高) 和 000002 (成交额 500000/920000 = 54.3% >= 15%)
        # 后排股票为 000003, 000004, 000005, 000006, 000007 (共 5 只)
        assert metrics.rear_stock_count == 5
        assert metrics.is_sample_sufficient is True

        # 后排负收益标的: 000003 (9.5<10), 000005 (9.6<10), 000006 (9.4<10) -> 3/5 = 0.60
        assert metrics.rear_negative_ratio == 0.60

        # 板块触板标的: 000001(封板), 000004(炸板) -> 共2只触板，1只炸板 -> 炸板率 = 1/2 = 0.50
        assert metrics.sector_broken_ratio == 0.50

        # 后排冲高回落价差 ΔGain = (High - Close)/PrevClose * 100
        # 000003: (10.8 - 9.5)/10 = 13%
        # 000004: (11.0 - 10.2)/10 = 8%
        # 000005: (10.0 - 9.6)/10 = 4%
        # 000006: (10.1 - 9.4)/10 = 7%
        # 000007: (10.3 - 10.1)/10 = 2%
        # 均值 = (13 + 8 + 4 + 7 + 2) / 5 = 6.8%
        assert metrics.avg_spread_fade == 6.80

        # 核心涨幅均值: 000001 (+10%), 000002 (+5%) -> 7.5%
        # 后排涨幅均值: -5%, +2%, -4%, -6%, +1% -> (-12)/5 = -2.4%
        # 剪刀差 CRRS = 7.5 - (-2.4) = 9.9%
        assert metrics.core_rear_relative_strength == 9.90

    def test_solitary_monopoly_state(self):
        """测试涨停独苗状态判定逻辑"""
        # 场景 1: 唯1只涨停且高度为 3B，但板块涨幅中位数只有 0.2%，且无 1B 助攻 -> 判定为独苗
        constituents_monopoly = [
            {"code": "000001", "name": "独苗龙头", "close": 13.31, "prev_close": 12.10, "is_limit_up": True, "height": 3, "amount": 50000.0},
            {"code": "000002", "name": "跟风1", "close": 9.90, "prev_close": 10.00, "is_limit_up": False, "height": 1, "amount": 10000.0},
            {"code": "000003", "name": "跟风2", "close": 9.80, "prev_close": 10.00, "is_limit_up": False, "height": 1, "amount": 10000.0},
            {"code": "000004", "name": "跟风3", "close": 10.05, "prev_close": 10.00, "is_limit_up": False, "height": 1, "amount": 10000.0},
        ]

        breadth_res = DivergenceMetricsCalculator.calculate_sector_breadth_metrics(
            sector_code="BK0002",
            sector_name="独苗题材",
            trade_date="2026-10-16",
            total_market_turnover_yi=10000.0,
            constituents=constituents_monopoly,
        )
        assert breadth_res.limit_up_count == 1
        assert breadth_res.is_solitary_monopoly is True
        assert breadth_res.monopoly_leader_code == "000001"
        assert breadth_res.monopoly_turnover_ratio == round(50000.0 / 80000.0, 4)

        # 场景 2: 有 1 只 3B 涨停，但同时有 1 只首板（1B）助攻 -> 存在梯队，不属于独苗
        constituents_with_ladder = [
            {"code": "000001", "name": "主线龙头", "close": 13.31, "prev_close": 12.10, "is_limit_up": True, "height": 3, "amount": 50000.0},
            {"code": "000002", "name": "首板助攻", "close": 11.00, "prev_close": 10.00, "is_limit_up": True, "height": 1, "amount": 20000.0},
            {"code": "000003", "name": "跟风2", "close": 9.80, "prev_close": 10.00, "is_limit_up": False, "height": 1, "amount": 10000.0},
        ]
        breadth_ladder = DivergenceMetricsCalculator.calculate_sector_breadth_metrics(
            sector_code="BK0003",
            sector_name="梯队健全题材",
            trade_date="2026-10-16",
            total_market_turnover_yi=10000.0,
            constituents=constituents_with_ladder,
        )
        assert breadth_ladder.limit_up_count == 2
        assert breadth_ladder.is_solitary_monopoly is False
        assert breadth_ladder.monopoly_leader_code is None

    def test_leader_multi_label_coexistence(self):
        """测试核心股多标签可并存模型 (如 趋势核心 与 容量核心 同时并存)"""
        profile = {
            # 满足趋势核心
            "ma20_slope": 22.0,
            "above_ma20_ma60": True,
            "max_drawdown_20d": 0.08,
            "turnover_market_percentile": 0.96,
            "continuous_board_count": 1,
            # 满足容量核心
            "stock_turnover_yi": 38.5,
            "sector_turnover_yi": 100.0,
            "market_cap_rank_in_sector": 1,
            "day_pct_change": 5.8,
            # 其它
            "is_space_leader": False,
            "is_catchup_runner": False,
            "is_independent_event": False,
        }

        snapshot = DivergenceMetricsCalculator.classify_stock_roles(
            security_id="002460.SZ",
            stock_code="002460",
            canonical_name="赣锋锂业",
            trade_date="2026-10-16",
            effective_time="2026-10-16T15:05:00+08:00",
            profile=profile,
        )

        role_types = [r.role for r in snapshot.active_roles]
        assert LeaderRoleEnum.TREND_CORE in role_types
        assert LeaderRoleEnum.SECTOR_CAPACITY_CORE in role_types
        assert len(snapshot.active_roles) == 2

    def test_next_day_penalty_label_isolation(self):
        """测试次日负反馈 Y 标签评估与隔离"""
        next_day_constituents = [
            {"code": "000001", "open_pct": -2.5, "low_pct": -5.0, "is_limit_up": False},
            {"code": "000002", "open_pct": -1.8, "low_pct": -3.0, "is_limit_up": False},
            {"code": "000003", "open_pct": 0.5, "low_pct": -1.0, "is_limit_up": False},
            {"code": "000004", "open_pct": -3.5, "low_pct": -6.0, "is_limit_up": False},
        ]
        yesterday_broken = ["000004"]

        label = DivergenceMetricsCalculator.evaluate_next_day_penalty_label(
            sector_code="BK0968",
            next_trade_date="2026-10-19",
            labeled_at="2026-10-19T09:25:00+08:00",
            next_day_constituents=next_day_constituents,
            yesterday_broken_codes=yesterday_broken,
            leader_code="000001",
        )

        # 4 只中有 3 只满足 open < -1.5 或 low < -4.0 (000001, 000002, 000004) -> 3/4 = 0.75
        assert label.next_day_penalty_ratio == 0.75
        # 昨日炸板股 000004 次日低开 -3.5% < -3.0% -> 1/1 = 1.0
        assert label.broken_stocks_next_open_loss_ratio == 1.0
        assert label.leader_next_open_pct == -2.5
        assert label.leader_next_success is False
