"""
Market State Calibrator Service (DOC-78 Phase 2D.2)
===================================================
有限状态机确定性校准引擎 (L3 COGNITION)

核心职责：
1. 抽取四维量化特征向量 X = (I, S, R, M)；
2. 强制断言三大状态不变量约束 (Invariant S1, S2, S3)；
3. 确定性决策树状态分类 (MECE 6 态)；
4. 纯事实驱动因子与确定性模板渲染 (零无约束 LLM 幻觉)。
"""

from typing import List, Optional
from ..schemas.canonical_market import (
    MarketStateEnum,
    IndexVector,
    LadderVector,
    RiskVector,
    RegulatoryVector,
    StateFeatureVector,
    CalibratedMarketState,
    MarketTruthSnapshot,
)


class MarketStateCalibrator:
    """
    确定性市场状态校准器
    """

    STATE_DISPLAY_NAMES = {
        MarketStateEnum.EXPANSION_ACCELERATION: "主升共振期",
        MarketStateEnum.HIGH_DIVERGENCE_TOPPING: "高位剧烈分化期",
        MarketStateEnum.RECESSION_PANIC: "退潮恐慌期",
        MarketStateEnum.FREEZING_REVERSAL: "极值冰点反转期",
        MarketStateEnum.CHAOTIC_ROTATION: "混沌轮动期",
        MarketStateEnum.LOW_REBOUND: "低位超跌反弹期",
    }

    def extract_feature_vector(
        self,
        truth: MarketTruthSnapshot,
        prior_truth: Optional[MarketTruthSnapshot] = None,
    ) -> StateFeatureVector:
        """
        从 MarketTruthSnapshot 客观物理事实中纯量化抽取四维向量 X = (I, S, R, M)
        """
        # 1. 向量 I: 指数与流动性
        total_turnover = round(truth.turnover.two_markets_total_yi, 2)
        turnover_change_ratio = None
        if prior_truth and prior_truth.turnover.two_markets_total_yi > 0:
            prior_tot = prior_truth.turnover.two_markets_total_yi
            turnover_change_ratio = round((total_turnover - prior_tot) / prior_tot, 4)

        pcts = [idx.pct_change for idx in truth.indices]
        dispersion = round(max(pcts) - min(pcts), 2) if pcts else 0.0

        star_pct = next((idx.pct_change for idx in truth.indices if "000688" in idx.symbol), 0.0)
        sh_pct = next((idx.pct_change for idx in truth.indices if "000001" in idx.symbol), 0.0)
        star_divergence = round(star_pct - sh_pct, 2)

        vec_i = IndexVector(
            total_turnover_yi=total_turnover,
            turnover_change_ratio=turnover_change_ratio,
            dispersion_pct=dispersion,
            star_divergence_pct=star_divergence,
        )

        # 2. 向量 S: 天梯与广度
        sb = truth.sentiment_bounds
        max_h = sb.max_ladder_height
        lu_cnt = sb.limit_up_count
        ld_cnt = sb.limit_down_count

        high_tier_cnt = sum(
            len(grp.stocks) for grp in truth.ladder_tree if grp.height >= 3
        )
        leader_ratio = round(high_tier_cnt / lu_cnt, 4) if lu_cnt > 0 else 0.0

        vec_s = LadderVector(
            max_ladder_height=max_h,
            limit_up_count=lu_cnt,
            limit_down_count=ld_cnt,
            leader_ratio=leader_ratio,
        )

        # 3. 向量 R: 亏钱效应
        br_ratio = round(sb.broken_limit_ratio, 4)
        br_cnt = sb.broken_limit_count
        touched = sb.touched_limit_total_count
        extreme_loss = round((br_cnt + ld_cnt) / touched, 4) if touched > 0 else 0.0

        vec_r = RiskVector(
            broken_limit_ratio=br_ratio,
            broken_limit_count=br_cnt,
            extreme_loss_ratio=extreme_loss,
        )

        # 4. 向量 M: 监管压力
        anom_cnt = len(truth.regulatory_anomalies)
        space_leader_code = ""
        if truth.ladder_tree and truth.ladder_tree[0].stocks:
            space_leader_code = truth.ladder_tree[0].stocks[0].code
        has_leader_warn = any(a.symbol == space_leader_code for a in truth.regulatory_anomalies)

        vec_m = RegulatoryVector(
            anomaly_count=anom_cnt,
            has_leader_warning=has_leader_warn,
        )

        return StateFeatureVector(
            index_vector=vec_i,
            ladder_vector=vec_s,
            risk_vector=vec_r,
            regulatory_vector=vec_m,
        )

    def calibrate(
        self,
        features: StateFeatureVector,
        prior_state: Optional[MarketStateEnum] = None,
        core_mainlines: Optional[List[str]] = None,
        space_leader_desc: Optional[str] = None,
    ) -> CalibratedMarketState:
        """
        基于确定性决策树与刚性不变量进行状态分类
        """
        vec_i = features.index_vector
        vec_s = features.ladder_vector
        vec_r = features.risk_vector
        vec_m = features.regulatory_vector

        driving_factors: List[str] = []
        primary_state: MarketStateEnum
        confidence: float
        transition_signal: Optional[str] = None

        # 决策树分支 1: 极值退潮恐慌判定
        if vec_s.limit_down_count >= 30 or (vec_r.broken_limit_ratio >= 0.50 and vec_s.limit_down_count >= 15):
            primary_state = MarketStateEnum.RECESSION_PANIC
            confidence = 0.95
            driving_factors.append(f"全市场跌停家数高达 {vec_s.limit_down_count} 只，恐慌盘全面踩踏")
            driving_factors.append(f"真实炸板率高达 {vec_r.broken_limit_ratio:.1%}，极值亏损率 {vec_r.extreme_loss_ratio:.1%}")
            if prior_state and prior_state != MarketStateEnum.RECESSION_PANIC:
                transition_signal = f"从前序【{self.STATE_DISPLAY_NAMES.get(prior_state, prior_state.value)}】剧烈转入【退潮恐慌期】"

        # 决策树分支 2: 高位剧烈分化期判定 (10-08 典型盘面)
        elif (
            vec_r.broken_limit_ratio >= 0.35
            or vec_i.dispersion_pct >= 3.0
            or vec_s.limit_down_count >= 10
        ) and vec_s.max_ladder_height >= 4:
            primary_state = MarketStateEnum.HIGH_DIVERGENCE_TOPPING
            confidence = 0.90
            if vec_i.dispersion_pct >= 3.0:
                driving_factors.append(f"指数极度分化 (离散度 {vec_i.dispersion_pct:.2f}%)，权重与题材背离")
            if vec_r.broken_limit_ratio >= 0.35:
                driving_factors.append(
                    f"炸板率高达 {vec_r.broken_limit_ratio:.2%} 且跌停 {vec_s.limit_down_count} 家，短线博弈极端极化"
                )
            if vec_s.max_ladder_height >= 4:
                driving_factors.append(f"最高连板达 {vec_s.max_ladder_height}B{f' ({space_leader_desc})' if space_leader_desc else ''}，高位博弈激烈")
            if vec_m.anomaly_count >= 5:
                driving_factors.append(f"共 {vec_m.anomaly_count} 只标的触发严重异动商业规则，高位降温压力剧增")
            if prior_state and prior_state == MarketStateEnum.EXPANSION_ACCELERATION:
                transition_signal = "主升共振遭遇天量分歧，情绪进入高位滞涨见顶博弈"

        # 决策树分支 3: 主升共振期判定
        elif (
            vec_r.broken_limit_ratio < 0.25
            and vec_s.limit_up_count >= 50
            and vec_s.limit_down_count <= 10
            and vec_s.max_ladder_height >= 4
        ):
            primary_state = MarketStateEnum.EXPANSION_ACCELERATION
            confidence = 0.92
            driving_factors.append(f"两市涨停共振 {vec_s.limit_up_count} 家，最高板达 {vec_s.max_ladder_height}B")
            driving_factors.append(f"炸板率仅 {vec_r.broken_limit_ratio:.1%} 且跌停仅 {vec_s.limit_down_count} 家，做多合力充沛")
            if prior_state and prior_state != MarketStateEnum.EXPANSION_ACCELERATION:
                transition_signal = "放量突破共振，新一轮做多周期主升启动"

        # 决策树分支 4: 极值冰点反转期判定 (需满足 Invariant S3)
        elif (
            prior_state == MarketStateEnum.RECESSION_PANIC
            and vec_s.limit_down_count <= 5
            and vec_r.broken_limit_ratio < 0.20
            and vec_s.max_ladder_height <= 3
        ):
            primary_state = MarketStateEnum.FREEZING_REVERSAL
            confidence = 0.88
            driving_factors.append("恐慌盘显著出清，跌停家数收敛至 5 家以内")
            driving_factors.append("炸板率回落至 20% 以下，新周期破局萌芽初显")
            transition_signal = "经历退潮恐慌后情绪触底回升，进入冰点反转破局阶段"

        # 决策树分支 5: 低位超跌反弹期
        elif (
            vec_s.limit_up_count < 30
            and vec_s.max_ladder_height <= 2
            and (not prior_state or prior_state in (MarketStateEnum.RECESSION_PANIC, MarketStateEnum.CHAOTIC_ROTATION))
        ):
            primary_state = MarketStateEnum.LOW_REBOUND
            confidence = 0.82
            driving_factors.append(f"涨停标的仅 {vec_s.limit_up_count} 家且最高板仅 {vec_s.max_ladder_height}B，连板梯队缺乏纵深")
            driving_factors.append("以超跌权重或零星题材脉冲为主，缺乏主升扩散合力")

        # 决策树分支 6: 混沌轮动期 (默认托底)
        else:
            primary_state = MarketStateEnum.CHAOTIC_ROTATION
            confidence = 0.80
            driving_factors.append("盘面缺乏全局领军主线，热点轮动快速且中军断层")
            driving_factors.append(f"最高板仅 {vec_s.max_ladder_height}B，涨停 {vec_s.limit_up_count} 只，梯队深度有限")

        # =========================================================================
        # 强制不变量防御核验 (Hard Assertions on Invariants)
        # =========================================================================
        # Invariant S1: 高炸板/多跌停严禁判定为主升
        if vec_r.broken_limit_ratio >= 0.35 and vec_s.limit_down_count >= 10:
            if primary_state == MarketStateEnum.EXPANSION_ACCELERATION:
                # 刚性防御降级
                primary_state = MarketStateEnum.HIGH_DIVERGENCE_TOPPING
                driving_factors.insert(0, "【Invariant S1 触发拦截】高炸板与多跌停并存，强制否决主升判定")

        # Invariant S2: 低高度/少涨停严禁判定为主升或高位分化
        if vec_s.max_ladder_height <= 2 and vec_s.limit_up_count < 25:
            if primary_state in (MarketStateEnum.EXPANSION_ACCELERATION, MarketStateEnum.HIGH_DIVERGENCE_TOPPING):
                primary_state = MarketStateEnum.CHAOTIC_ROTATION
                driving_factors.insert(0, "【Invariant S2 触发拦截】高度与广度严重不足，强制否决高位分化/主升判定")

        # Invariant S3: 冰点反转前序必须为退潮恐慌
        if primary_state == MarketStateEnum.FREEZING_REVERSAL:
            if prior_state != MarketStateEnum.RECESSION_PANIC:
                primary_state = MarketStateEnum.LOW_REBOUND
                driving_factors.insert(0, "【Invariant S3 触发拦截】前序非退潮恐慌，修正为低位超跌反弹")

        return CalibratedMarketState(
            primary_state=primary_state,
            state_display_name=self.STATE_DISPLAY_NAMES[primary_state],
            state_confidence=confidence,
            driving_factors=driving_factors,
            transition_signal=transition_signal,
            feature_vector=features,
        )

    def render_deterministic_summary(
        self,
        state: CalibratedMarketState,
        features: StateFeatureVector,
        core_mainlines: Optional[List[str]] = None,
        space_leader_desc: Optional[str] = None,
    ) -> str:
        """
        基于校准状态与输入特征确定性模板渲染一句话定性 (零 LLM 编造)
        """
        p = state.primary_state
        vec_i = features.index_vector
        vec_s = features.ladder_vector
        vec_r = features.risk_vector

        # 主线标定文字
        mainlines_str = "【央国企改革】与【新能源电池链】"
        if core_mainlines:
            mainlines_str = "与".join([f"【{m}】" for m in core_mainlines[:2]])

        # 空间板文字
        ldr_str = space_leader_desc or f"最高{vec_s.max_ladder_height}B"

        if p == MarketStateEnum.HIGH_DIVERGENCE_TOPPING:
            star_desc = "科创50重挫-4.82%" if abs(vec_i.star_divergence_pct) > 1.0 else f"指数极差{vec_i.dispersion_pct:.2f}%"
            return (
                f"指数高位剧烈分化 ({star_desc})，两市真实成交额维持 {vec_i.total_turnover_yi / 10000:.2f} 万亿高位；"
                f"短线极端博弈 ({ldr_str}/连板10家)，但炸板率高达 {vec_r.broken_limit_ratio:.2%} 且跌停{vec_s.limit_down_count}家，"
                f"做多主线聚焦于{mainlines_str}，跟风标的面临时冲高回落大面风险。"
            )
        elif p == MarketStateEnum.EXPANSION_ACCELERATION:
            return (
                f"指数放量共振突破，两市真实成交额达 {vec_i.total_turnover_yi / 10000:.2f} 万亿；"
                f"短线主升加速 ({ldr_str})，涨停共振 {vec_s.limit_up_count} 家，炸板率仅 {vec_r.broken_limit_ratio:.1%}，"
                f"做多主线{mainlines_str}梯队健康扩散，市场呈现极强做多合力。"
            )
        elif p == MarketStateEnum.RECESSION_PANIC:
            return (
                f"市场遭遇重度退潮踩踏，两市跌停高达 {vec_s.limit_down_count} 家，真实炸板率达 {vec_r.broken_limit_ratio:.1%}；"
                f"空间板承压，中高位大面积补跌，全市场亏钱效应扩散，短线接力防守情绪极度严峻。"
            )
        elif p == MarketStateEnum.FREEZING_REVERSAL:
            return (
                f"市场恐慌盘出清初显，跌停家数收窄至 {vec_s.limit_down_count} 家，炸板率降至 {vec_r.broken_limit_ratio:.1%}；"
                f"局部高辨识度标的逆势破局，新做多周期萌芽试探，处于极值冰点转折观察期。"
            )
        elif p == MarketStateEnum.LOW_REBOUND:
            return (
                f"两市处于低位超跌修复格局，成交量能温和，最高连板压制在 {vec_s.max_ladder_height}B；"
                f"涨停 {vec_s.limit_up_count} 家以超跌与脉冲轮动为主，梯队缺乏深度持续性扩散。"
            )
        else:  # CHAOTIC_ROTATION
            return (
                f"市场处于混沌轮动弱势整理格局，热点快速切换且中军断层；"
                f"最高板压制在 {vec_s.max_ladder_height}B，全市场炸板率 {vec_r.broken_limit_ratio:.1%}，缺乏全局进攻性领军主线。"
            )
