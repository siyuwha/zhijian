"""
Phase 2D.3-C: Constrained Briefing Generator Service
===================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-C 授权与受约束 LLM 战报规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 严格基于 NarrativeContextContract 构建具有发言边界刚性约束的系统与用户 Prompt；
- 贯彻【大势定调】、【主线与梯队】、【风险与负反馈】、【明日推演与防守红线】四段式操盘内参范式；
- 全流程受 BriefingSafetyGuard 审查；审查不通过或生成异常无感触发 DeterministicBriefingFallbackEngine；
- 支持自适应处理不同微观市场周期 (如 10-08 高位剧烈分化期 vs 10-01 主升共振期)。
"""

from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import TacticalBriefingReport, SafetyAuditResult
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
from backend.app.services.tactical_briefing_service import TacticalBriefingService
from backend.app.schemas.canonical_market import MarketStateEnum


class BriefingPromptBuilder:
    """
    受约束 Prompt 构建器 (Prompt Speech Boundary Builder)
    """

    @staticmethod
    def build_system_prompt(contract: NarrativeContextContract) -> str:
        """
        构建包含显式发言边界与红线约束的 System Prompt
        """
        allowed = "\n  - ".join(contract.speech_boundary.allowed_claim_types)
        forbidden = "\n  - ".join(contract.speech_boundary.forbidden_claim_types)
        anchors = "\n  - ".join(contract.speech_boundary.required_evidence_anchors)

        return f"""你是一位拥有20年实战经验的顶级游资操盘手与头部券商特邀宏观策略内参首席顾问。
你的任务是根据系统提供的只读量化事实与认知假说，撰写一份冷峻、精炼、穿透力强、直击资金本质的【操盘内参实战战报】。

【刚性红线与发言边界】：
1. 允许声明类型：
  - {allowed}
2. 绝对禁止声明类型 (违者立即触发物理拦截并追责)：
  - {forbidden}
3. 严格 L5 隔离：严禁出现任何“买入”、“卖出”、“建仓”、“加仓”、“满仓”、“抄底”、“割肉”、“目标价”等交易指令或操作劝诱！
4. 严格实体单射：所有股票名称必须与提供的规范名称绝对一致（002242 必须为九阳股份，绝对严禁出现毅昌科技）！
5. 严格数字保真：严禁篡改或捏造成交额、炸板率、天梯高度或跌停家数！两市成交额已含创业板，严禁重复累加！
6. 必须体现的证据锚点：
  - {anchors}

【结构与字数规范】：
- 严格分为四大模块：
  1. 【大势定调】：量能真实口径与微观状态标定；
  2. 【主线与梯队】：核心做多战场代表标杆与空间最高板；
  3. 【风险与负反馈】：真实炸板率、跌停大面与交易所异动监控压力；
  4. 【明日推演与防守红线】：次日竞价核心观察哨与证伪触发条件。
- 总字数必须严格控制在 250 至 350 字之间，杜绝废话与泛泛而谈的宏观空话。"""

    @staticmethod
    def build_user_prompt(contract: NarrativeContextContract) -> str:
        """
        构建结构化用户提示词 (结构化注入 FACT, DERIVED, COGNITION)
        """
        fact = contract.fact_layer
        derived = contract.derived_layer
        cog = contract.cognition_layer

        ml_lines = []
        for ml in cog.candidate_mainlines[:3]:
            falsify_str = ml.falsification_condition.invalidation_rules[0] if ml.falsification_condition.invalidation_rules else "核心龙头竞价承接不足"
            ml_lines.append(
                f"- 第{ml.rank}主线【{ml.sector_name}】：龙头【{ml.leader_identity.canonical_name}】{ml.leader_height}B，"
                f"涨停 {ml.limit_up_count} 家。核心证伪条件：{falsify_str}"
            )
        mainline_summary = "\n".join(ml_lines)

        return f"""【业务日期】：{contract.trade_date}

【L0/L1 事实层 (FACT)】：
- 沪深真实总成交额：{fact.turnover.total_turnover_yi:.2f} 亿元（沪市 {fact.turnover.sh_amount_yi:.2f} 亿，深市含创业板 {fact.turnover.sz_total_amount_yi:.2f} 亿）
- 空间最高连板高度：{fact.ladder.max_height}B（空间标杆：【{fact.ladder.space_leader.canonical_name}】）
- 涨跌停微观统计：真实有效涨停 {fact.sentiment_counts.limit_up_count} 家，收盘跌停 {fact.sentiment_counts.limit_down_count} 家
- 交易所严重异常波动重点监控标的：{fact.regulatory.total_anomaly_count} 家

【L2 衍生结构层 (DERIVED)】：
- 真实炸板率：{derived.broken_limit_ratio * 100:.2f}%
- 极值亏损率：{derived.extreme_loss_ratio * 100:.2f}%

【L3 顶层认知假说层 (COGNITION)】：
- 市场微观状态标定：【{cog.market_state.state_display_name}】（置信度 {int(cog.market_state.state_confidence * 100)}%）
- 状态驱动事实：{'; '.join(cog.market_state.driving_factors)}
- 主线候选与梯队纵深：
{mainline_summary}

请严格遵守发言边界，输出操盘内参战报正文。"""


class ConstrainedBriefingGenerator:
    """
    受约束 LLM 操盘战报生成器 (Constrained Briefing Generator)
    """

    def __init__(
        self,
        safety_guard: Optional[BriefingSafetyGuard] = None,
        fallback_engine: Optional[DeterministicBriefingFallbackEngine] = None,
        llm_client: Optional[Callable[[str, str], str]] = None,
    ):
        self.safety_guard = safety_guard or BriefingSafetyGuard()
        self.fallback_engine = fallback_engine or DeterministicBriefingFallbackEngine(
            safety_guard=self.safety_guard
        )
        self.briefing_service = TacticalBriefingService(
            safety_guard=self.safety_guard,
            fallback_engine=self.fallback_engine,
        )
        self.llm_client = llm_client

    def generate_briefing(
        self,
        contract: NarrativeContextContract,
        generated_at: str = "2026-10-09T03:00:00Z",
    ) -> TacticalBriefingReport:
        """
        全流程生成战报：
        1. 构建受约束 Prompt；
        2. 调用 LLM 或自适应模拟推理；
        3. 经 BriefingSafetyGuard 拦截审查；
        4. 通过则发布正式战报，失败则无感降级。
        """
        sys_prompt = BriefingPromptBuilder.build_system_prompt(contract)
        usr_prompt = BriefingPromptBuilder.build_user_prompt(contract)

        candidate_text: Optional[str] = None
        if self.llm_client:
            try:
                candidate_text = self.llm_client(sys_prompt, usr_prompt)
            except Exception as e:
                # LLM 故障/异常，直接无感保底
                return self.fallback_engine.generate_fallback_briefing(
                    context=contract,
                    fallback_reason=f"LLM Client Exception ({type(e).__name__}): {str(e)}",
                    generated_at=generated_at,
                )
        else:
            # 默认高保真受约束自适应生成器 (根据 MarketState 自适应生成高质量操盘内参文本)
            candidate_text = self._adaptive_stylized_generation(contract)

        return self.briefing_service.produce_briefing(
            context=contract,
            candidate_text=candidate_text,
            generated_at=generated_at,
        )

    def _adaptive_stylized_generation(self, contract: NarrativeContextContract) -> str:
        """
        自适应操盘手文风生成器：针对不同市场状态呈现差异化战术文风，
        且严格遵守发言边界与数字事实。
        """
        fact = contract.fact_layer
        derived = contract.derived_layer
        cog = contract.cognition_layer

        total_to = fact.turnover.total_turnover_yi
        sh_to = fact.turnover.sh_amount_yi
        sz_to = fact.turnover.sz_total_amount_yi
        state_label = cog.market_state.state_display_name
        confidence_pct = int(cog.market_state.state_confidence * 100)
        max_h = fact.ladder.max_height
        space_leader = fact.ladder.space_leader.canonical_name
        broken_pct = derived.broken_limit_ratio * 100
        limit_down = fact.sentiment_counts.limit_down_count
        anomaly_count = fact.regulatory.total_anomaly_count

        top_ml = cog.candidate_mainlines[0] if cog.candidate_mainlines else None
        second_ml = cog.candidate_mainlines[1] if len(cog.candidate_mainlines) > 1 else None

        top_leader = top_ml.leader_identity.canonical_name if top_ml else space_leader
        top_h = top_ml.leader_height if top_ml else max_h
        falsification = (
            top_ml.falsification_condition.invalidation_rules[0]
            if top_ml and top_ml.falsification_condition.invalidation_rules
            else "核心龙头竞价承接力不足"
        )

        if cog.market_state.primary_state == MarketStateEnum.HIGH_DIVERGENCE_TOPPING:
            # 高位剧烈分化期文风：强调高位兑现、炸板与防守
            p1 = (
                f"【大势定调】两市总成交额达 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"盘面处于典型的【{state_label}】（置信度 {confidence_pct}%），资金高位兑现加剧。"
            )
            p2 = (
                f"【主线与梯队】核心战场由【{top_ml.sector_name if top_ml else '主线'}】（龙头【{top_leader}】{top_h}B）"
                f"与【{second_ml.sector_name if second_ml else '分支'}】勉力维系，市场最高板标杆为 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】微观亏钱效应急剧放大：日内真实炸板率高达 {broken_pct:.2f}%，收盘跌停 {limit_down} 家；"
                f"交易所严重异常波动重点监控达 {anomaly_count} 家，高位核按钮频发使得情绪大幅承压。"
            )
            p4 = (
                f"【明日推演与防守红线】明日竞价重点盯紧【{space_leader}】溢价表现与【{top_leader}】承接力度。"
                f"核心防守证伪红线：{falsification}。"
            )
        elif cog.market_state.primary_state == MarketStateEnum.EXPANSION_ACCELERATION:
            # 主升共振期文风：强调赚钱效应、梯队完整与流动性充足
            p1 = (
                f"【大势定调】两市总成交额达 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"盘面处于强劲的【{state_label}】（置信度 {confidence_pct}%），多头动能全面迸发。"
            )
            p2 = (
                f"【主线与梯队】核心主线【{top_ml.sector_name if top_ml else '主线'}】梯队纵深完整，"
                f"龙头【{top_leader}】强势挺进 {top_h}B，全市场空间高度打开至 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】盘面良性运行：真实炸板率仅为 {broken_pct:.2f}%，收盘跌停 {limit_down} 家；"
                f"监管异动标的仅 {anomaly_count} 家，做多情绪处于良性通道。"
            )
            p4 = (
                f"【明日推演与防守红线】明日竞价重点观察空间标杆【{space_leader}】的接力意愿与后排首板晋级率。"
                f"核心证伪红线：{falsification}。"
            )
        else:
            # 其他状态下的标准稳健文风
            p1 = (
                f"【大势定调】沪深两市真实总成交额为 {total_to:.2f} 亿元（沪市 {sh_to:.2f} 亿，深市含创业板 {sz_to:.2f} 亿）。"
                f"市场当前状态标定为【{state_label}】（判定置信度 {confidence_pct}%）。"
            )
            p2 = (
                f"【主线与梯队】核心做多战场为【{top_ml.sector_name if top_ml else '主线'}】（龙头【{top_leader}】{top_h}B），"
                f"最高空间板为 {max_h}B【{space_leader}】。"
            )
            p3 = (
                f"【风险与负反馈】真实炸板率达 {broken_pct:.2f}%，收盘跌停 {limit_down} 家，"
                f"交易所严重异常波动监控 {anomaly_count} 家。"
            )
            p4 = (
                f"【明日推演与防守红线】次日重点跟踪【{space_leader}】竞价承接。核心证伪红线：{falsification}。"
            )

        return f"{p1}{p2}{p3}{p4}"
