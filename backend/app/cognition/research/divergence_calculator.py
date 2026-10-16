"""
短线核心认知指标量化计算引擎 (Divergence & Breadth & Role Calculator)
文件路径：backend/app/cognition/research/divergence_calculator.py
上位依据：
1. DOSSIER-COGNITION-RESEARCH-20261016-V1.0 (9 大交付物标准)
2. SPEC-DESIGN-PHASE2D-20261008-V1.0
3. 严格遵循纯数学无歧义、分母为零安全防护、PIT 时点因果隔离
"""

import statistics
from typing import List, Dict, Any, Optional, Tuple
from ...schemas.research_divergence_contract import (
    RearDivergenceMetrics,
    NextDayPenaltyLabel,
    SectorBreadthMetrics,
    LeaderRoleItem,
    LeaderRoleEnum,
    ConfidenceGrade,
    StockRoleTaxonomySnapshot,
)


class DivergenceMetricsCalculator:
    """后排负反馈与板块宽度认知计算器 (只读、幂等、无副作用)"""

    @staticmethod
    def calculate_rear_divergence_metrics(
        sector_code: str,
        trade_date: str,
        evaluation_time: str,
        constituents: List[Dict[str, Any]],
    ) -> RearDivergenceMetrics:
        """
        计算板块后排负反馈指标
        :param sector_code: 板块代码
        :param trade_date: 交易日 YYYY-MM-DD
        :param evaluation_time: 计算时间戳
        :param constituents: 板块成分股列表，每个元素包含:
            {
                "code": str,
                "name": str,
                "close": float,
                "prev_close": float,
                "high": float,
                "amount": float,
                "is_limit_up": bool,
                "touched_limit_up": bool,
                "height": int,
            }
        """
        if not constituents:
            return RearDivergenceMetrics(
                sector_code=sector_code,
                trade_date=trade_date,
                evaluation_time=evaluation_time,
                rear_stock_count=0,
                rear_negative_ratio=None,
                avg_spread_fade=0.0,
                avg_peak_pullback=0.0,
                sector_broken_ratio=None,
                core_rear_relative_strength=0.0,
                is_sample_sufficient=False,
                confidence=ConfidenceGrade.L2_DERIVED,
            )

        # 1. 计算板块核心股票集合 C_s,t
        total_sector_amount = sum(float(c.get("amount", 0.0) or 0.0) for c in constituents)
        max_height = max([int(c.get("height", 1) or 1) for c in constituents], default=1)

        core_codes = set()
        # 规则 1: 连板高度等于板块最高且高度 >= 2
        for c in constituents:
            h = int(c.get("height", 1) or 1)
            if h >= 2 and h == max_height:
                core_codes.add(c["code"])

        # 规则 2: 成交额前 2 且单票成交占板块总成交比重 >= 15%
        sorted_by_amount = sorted(
            constituents,
            key=lambda x: float(x.get("amount", 0.0) or 0.0),
            reverse=True,
        )
        if total_sector_amount > 0:
            for c in sorted_by_amount[:2]:
                amt = float(c.get("amount", 0.0) or 0.0)
                if (amt / total_sector_amount) >= 0.15:
                    core_codes.add(c["code"])

        # 若无任何个股满足上述条件，以最高板或成交最高者作为核心保底 (确保核心非空)
        if not core_codes and constituents:
            core_codes.add(sorted_by_amount[0]["code"])

        # 2. 划分后排集合 R_s,t = constituents \ core
        core_stocks = [c for c in constituents if c["code"] in core_codes]
        rear_stocks = [c for c in constituents if c["code"] not in core_codes]
        rear_count = len(rear_stocks)

        # 3. 计算后排各项指标
        if rear_count == 0:
            rear_negative_ratio = None
            avg_spread_fade = 0.0
            avg_peak_pullback = 0.0
            core_rear_diff = 0.0
        else:
            neg_count = 0
            spread_fades = []
            pullbacks = []
            rear_pct_changes = []

            for s in rear_stocks:
                close = float(s.get("close", 0.0))
                prev = float(s.get("prev_close", 0.0))
                high = float(s.get("high", close))

                # 涨跌幅
                pct = ((close - prev) / prev * 100.0) if prev > 0 else 0.0
                rear_pct_changes.append(pct)

                if close < prev:
                    neg_count += 1

                # 冲高回落价差 ΔGain = (High - Close) / PrevClose * 100%
                delta_gain = ((high - close) / prev * 100.0) if prev > 0 else 0.0
                spread_fades.append(delta_gain)

                # 最高价回撤比 Pullback = (High - Close) / High
                pullback = ((high - close) / high) if high > 0 else 0.0
                pullbacks.append(pullback)

            rear_negative_ratio = round(neg_count / rear_count, 4)
            avg_spread_fade = round(statistics.mean(spread_fades), 2)
            avg_peak_pullback = round(statistics.mean(pullbacks), 4)

            # 核心相对后排剪刀差 CRRS = CoreMeanPct - RearMeanPct
            core_pct_changes = [
                ((float(c.get("close", 0.0)) - float(c.get("prev_close", 0.0))) / float(c.get("prev_close", 1.0)) * 100.0)
                for c in core_stocks
                if float(c.get("prev_close", 0.0)) > 0
            ]
            core_mean_pct = statistics.mean(core_pct_changes) if core_pct_changes else 0.0
            rear_mean_pct = statistics.mean(rear_pct_changes) if rear_pct_changes else 0.0
            core_rear_diff = round(core_mean_pct - rear_mean_pct, 2)

        # 4. 板块炸板率 BLR_s
        touched_stocks = [c for c in constituents if c.get("touched_limit_up")]
        locked_stocks = [c for c in constituents if c.get("is_limit_up")]
        if not touched_stocks:
            sector_broken_ratio = None
        else:
            broken_count = len([c for c in touched_stocks if not c.get("is_limit_up")])
            sector_broken_ratio = round(broken_count / len(touched_stocks), 4)

        return RearDivergenceMetrics(
            sector_code=sector_code,
            trade_date=trade_date,
            evaluation_time=evaluation_time,
            rear_stock_count=rear_count,
            rear_negative_ratio=rear_negative_ratio,
            avg_spread_fade=avg_spread_fade,
            avg_peak_pullback=avg_peak_pullback,
            sector_broken_ratio=sector_broken_ratio,
            core_rear_relative_strength=core_rear_diff,
            is_sample_sufficient=(rear_count >= 5),
            confidence=ConfidenceGrade.L2_DERIVED,
        )

    @staticmethod
    def calculate_sector_breadth_metrics(
        sector_code: str,
        sector_name: str,
        trade_date: str,
        total_market_turnover_yi: float,
        constituents: List[Dict[str, Any]],
        amount_unit: str = "WAN",
    ) -> SectorBreadthMetrics:
        """
        计算板块宽度与独苗状态指标
        :param sector_code: 板块代码
        :param sector_name: 板块名称
        :param trade_date: 交易日期
        :param total_market_turnover_yi: 沪深全市场真实总成交额 (亿元，已去重)
        :param constituents: 板块成分股列表
        :param amount_unit: 成分股成交额单位 ("YUAN" 元, "WAN" 万元, "YI" 亿元，默认 "WAN")
        """
        n = len(constituents)
        if n == 0:
            raise ValueError(f"Constituents list cannot be empty for sector {sector_code}")

        up_count = 0
        limit_up_count = 0
        limit_down_count = 0
        pct_changes = []
        ladder_counts: Dict[str, int] = {}
        sector_amount_sum = 0.0

        limit_up_stocks = []

        for c in constituents:
            close = float(c.get("close", 0.0))
            prev = float(c.get("prev_close", 0.0))
            amt = float(c.get("amount", 0.0) or 0.0)
            sector_amount_sum += amt

            pct = ((close - prev) / prev * 100.0) if prev > 0 else 0.0
            pct_changes.append(pct)

            if close > prev:
                up_count += 1

            if c.get("is_limit_up"):
                limit_up_count += 1
                limit_up_stocks.append(c)
                h = int(c.get("height", 1) or 1)
                h_key = f"{h}B"
                ladder_counts[h_key] = ladder_counts.get(h_key, 0) + 1

            if c.get("is_limit_down"):
                limit_down_count += 1

        breadth_ratio = round(up_count / n, 4)
        median_pct = round(statistics.median(pct_changes), 2) if pct_changes else 0.0

        # 成交额换算为亿元
        unit_upper = amount_unit.upper()
        if unit_upper == "YUAN":
            sector_turnover_yi = round(sector_amount_sum / 100000000.0, 2)
        elif unit_upper == "WAN":
            sector_turnover_yi = round(sector_amount_sum / 10000.0, 2)
        elif unit_upper == "YI":
            sector_turnover_yi = round(sector_amount_sum, 2)
        else:
            sector_turnover_yi = round(sector_amount_sum / 10000.0, 2)

        raw_share = (sector_turnover_yi / total_market_turnover_yi) if total_market_turnover_yi > 0 else 0.0
        mkt_share = min(1.0, max(0.0, round(raw_share, 4)))

        # 判定独苗状态 MonopolyState:
        # 1. limit_up_count == 1
        # 2. 独苗高度 >= 2
        # 3. breadth_ratio < 0.40 或 median_pct < 1.0
        # 4. 板块内首板数量为 0 (ladder_counts.get("1B", 0) == 0)
        is_solitary = False
        monopoly_code = None
        monopoly_ratio = None

        if limit_up_count == 1:
            only_stock = limit_up_stocks[0]
            only_height = int(only_stock.get("height", 1) or 1)
            one_board_count = ladder_counts.get("1B", 0)

            if only_height >= 2 and (breadth_ratio < 0.40 or median_pct < 1.0) and one_board_count == 0:
                is_solitary = True
                monopoly_code = only_stock["code"]
                only_amount = float(only_stock.get("amount", 0.0) or 0.0)
                if sector_amount_sum > 0:
                    monopoly_ratio = round(only_amount / sector_amount_sum, 4)

        return SectorBreadthMetrics(
            sector_code=sector_code,
            sector_name=sector_name,
            trade_date=trade_date,
            pit_constituents_count=n,
            breadth_ratio=breadth_ratio,
            median_pct_change=median_pct,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            ladder_distribution=ladder_counts,
            is_solitary_monopoly=is_solitary,
            monopoly_leader_code=monopoly_code,
            monopoly_turnover_ratio=monopoly_ratio,
            sector_turnover_yi=sector_turnover_yi,
            market_turnover_share=mkt_share,
        )

    @staticmethod
    def classify_stock_roles(
        security_id: str,
        stock_code: str,
        canonical_name: str,
        trade_date: str,
        effective_time: str,
        profile: Dict[str, Any],
    ) -> StockRoleTaxonomySnapshot:
        """
        标的多标签角色拓扑判定 (支持标签并存)
        :param profile: 标的特征指标包:
            - ma20_slope: float
            - above_ma20_ma60: bool
            - max_drawdown_20d: float (如 0.08)
            - turnover_market_percentile: float (如 0.95)
            - continuous_board_count: int
            - is_space_leader: bool
            - lock_time: Optional[str] (如 "09:35:12")
            - lock_bid_ratio: Optional[float] (如 0.035)
            - stock_turnover_yi: float
            - sector_turnover_yi: float
            - market_cap_rank_in_sector: int
            - day_pct_change: float
            - is_catchup_runner: bool
            - is_independent_event: bool
        """
        active_roles: List[LeaderRoleItem] = []

        # 1. 趋势型核心 (TREND_CORE)
        ma20_slope = float(profile.get("ma20_slope", 0.0))
        above_mas = bool(profile.get("above_ma20_ma60", False))
        mdd20 = float(profile.get("max_drawdown_20d", 1.0))
        mkt_pctile = float(profile.get("turnover_market_percentile", 0.0))
        lbc = int(profile.get("continuous_board_count", 0))

        if (
            ma20_slope >= 15.0
            and above_mas
            and mdd20 <= 0.12
            and mkt_pctile >= 0.90
            and lbc <= 2
        ):
            active_roles.append(
                LeaderRoleItem(
                    role=LeaderRoleEnum.TREND_CORE,
                    confidence=ConfidenceGrade.L1_DETERMINISTIC,
                    effective_time=effective_time,
                    mathematical_evidence={
                        "ma20_slope": round(ma20_slope, 2),
                        "max_drawdown_20d": round(mdd20, 4),
                        "turnover_percentile": round(mkt_pctile, 2),
                    },
                    invalidation_condition="收盘价连续2日跌破20日均线，或单日长阴跌幅超过-7%且创10日新低",
                )
            )

        # 2. 连板情绪核心 (LADDER_EMOTION_CORE)
        is_space_leader = bool(profile.get("is_space_leader", False))
        lock_bid_ratio = float(profile.get("lock_bid_ratio", 0.0) or 0.0)
        lock_time = profile.get("lock_time", "")

        is_early_lock = False
        if lock_time and lock_time < "09:40:00":
            is_early_lock = True

        if lbc >= 3 and is_space_leader and (lock_bid_ratio >= 0.02 or is_early_lock):
            active_roles.append(
                LeaderRoleItem(
                    role=LeaderRoleEnum.LADDER_EMOTION_CORE,
                    confidence=ConfidenceGrade.L1_DETERMINISTIC,
                    effective_time=effective_time,
                    mathematical_evidence={
                        "continuous_board_count": float(lbc),
                        "lock_bid_ratio": round(lock_bid_ratio, 4),
                    },
                    invalidation_condition="日内炸板未回封；次日竞价低开超过-4%且5分钟内无法翻红；连板中断",
                )
            )

        # 3. 板块容量核心 (SECTOR_CAPACITY_CORE)
        stock_turnover_yi = float(profile.get("stock_turnover_yi", 0.0))
        sector_turnover_yi = float(profile.get("sector_turnover_yi", 0.0))
        mcap_rank = int(profile.get("market_cap_rank_in_sector", 999))
        day_pct = float(profile.get("day_pct_change", 0.0))

        sector_share = (stock_turnover_yi / sector_turnover_yi) if sector_turnover_yi > 0 else 0.0
        if (stock_turnover_yi >= 25.0 or sector_share >= 0.20) and mcap_rank <= 3 and day_pct >= 4.0:
            active_roles.append(
                LeaderRoleItem(
                    role=LeaderRoleEnum.SECTOR_CAPACITY_CORE,
                    confidence=ConfidenceGrade.L2_DERIVED,
                    effective_time=effective_time,
                    mathematical_evidence={
                        "stock_turnover_yi": round(stock_turnover_yi, 2),
                        "turnover_share_in_sector": round(sector_share, 4),
                        "market_cap_rank": float(mcap_rank),
                        "day_pct_change": round(day_pct, 2),
                    },
                    invalidation_condition="成交额占板块比重跌破5%；连续3日走势跑输板块指数超过1.5倍标准差",
                )
            )

        # 4. 补涨型核心 (CATCHUP_RUNNER_CORE)
        if bool(profile.get("is_catchup_runner", False)):
            active_roles.append(
                LeaderRoleItem(
                    role=LeaderRoleEnum.CATCHUP_RUNNER_CORE,
                    confidence=ConfidenceGrade.L2_DERIVED,
                    effective_time=effective_time,
                    mathematical_evidence={
                        "continuous_board_count": float(lbc),
                        "first_limit_time_minute": float(profile.get("first_limit_minute", 10)),
                    },
                    invalidation_condition="空间龙头发生跌停引发板块全面退潮；自身次日未能高开连板",
                )
            )

        # 5. 独立事件型 (INDEPENDENT_EVENT_CORE)
        if bool(profile.get("is_independent_event", False)):
            active_roles.append(
                LeaderRoleItem(
                    role=LeaderRoleEnum.INDEPENDENT_EVENT_CORE,
                    confidence=ConfidenceGrade.L3_COGNITIVE,
                    effective_time=effective_time,
                    mathematical_evidence={
                        "sector_limit_up_count": 1.0,
                        "market_beta": float(profile.get("market_beta", 0.05)),
                    },
                    invalidation_condition="重组或利好事件被监管问询/终止；板块出现大面积群体连板扩散 (转化为板块龙头)",
                )
            )

        return StockRoleTaxonomySnapshot(
            security_id=security_id,
            stock_code=stock_code,
            canonical_name=canonical_name,
            trade_date=trade_date,
            active_roles=active_roles,
        )

    @staticmethod
    def evaluate_next_day_penalty_label(
        sector_code: str,
        next_trade_date: str,
        labeled_at: str,
        next_day_constituents: List[Dict[str, Any]],
        yesterday_broken_codes: List[str],
        leader_code: Optional[str] = None,
    ) -> NextDayPenaltyLabel:
        """
        评估事后次日负反馈标签 (Y_t+1)
        警告：严禁将本函数的输出作为特征输入任何决策模型！
        """
        n = len(next_day_constituents)
        if n == 0:
            return NextDayPenaltyLabel(
                sector_code=sector_code,
                next_trade_date=next_trade_date,
                labeled_at=labeled_at,
                next_day_penalty_ratio=0.0,
                broken_stocks_next_open_loss_ratio=None,
                leader_next_open_pct=None,
                leader_next_success=None,
            )

        # 次日极端负反馈: 开盘 < -1.5% 或 日内最低 < -4.0%
        penalty_count = 0
        leader_open_pct = None
        leader_success = None

        code_to_stock = {s["code"]: s for s in next_day_constituents}

        for s in next_day_constituents:
            open_pct = float(s.get("open_pct", 0.0))
            low_pct = float(s.get("low_pct", 0.0))
            if open_pct < -1.5 or low_pct < -4.0:
                penalty_count += 1

            if leader_code and s["code"] == leader_code:
                leader_open_pct = round(open_pct, 2)
                leader_success = bool(s.get("is_limit_up", False))

        penalty_ratio = round(penalty_count / n, 4)

        # 昨天炸板个股的次日开盘极值亏损率 (低开 < -3.0%)
        broken_loss_ratio = None
        if yesterday_broken_codes:
            matched_broken = [code_to_stock[c] for c in yesterday_broken_codes if c in code_to_stock]
            if matched_broken:
                severe_loss_count = sum(1 for b in matched_broken if float(b.get("open_pct", 0.0)) < -3.0)
                broken_loss_ratio = round(severe_loss_count / len(matched_broken), 4)

        return NextDayPenaltyLabel(
            sector_code=sector_code,
            next_trade_date=next_trade_date,
            labeled_at=labeled_at,
            next_day_penalty_ratio=penalty_ratio,
            broken_stocks_next_open_loss_ratio=broken_loss_ratio,
            leader_next_open_pct=leader_open_pct,
            leader_next_success=leader_success,
        )
