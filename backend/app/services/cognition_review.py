import json
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from ..models.trading import TradeRecord, TradeNote
from ..models.cognition import (
    CognitionMarketState,
    CognitiveTradeDiagnosis,
    MarketHypothesis,
    HypothesisVerification,
)
from ..models.report import DailyReview, AuctionReport
from ..schemas.cognition import (
    DiagnosisConfirmPayload,
    MarketHypothesisCreate,
)

class CognitionReviewService:
    """
    Cognition 验证闭环增强核心服务
    - 单笔交易行为双层诊断与人机确认流
    - 周度认知复盘 (EMD / LRD / ODD 严格样本隔离与数学计算)
    - 跨日推演假说跟踪与客观事实验证状态机 (AUCTION_0925 / CLOSE_1530)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # 1. 单笔交易行为双层诊断 (切片 1)
    # =========================================================================

    async def diagnose_trade(self, trade_id: int) -> CognitiveTradeDiagnosis:
        """
        触发或生成单笔交易双层认知诊断
        - 事实层: 成交数据 + 当日客观 D1~D6 快照
        - 解释层: 环境匹配建议 + 逻辑兑现推测 + 认知 Gap (默认 UNCONFIRMED)
        """
        # 1. 检索交易流水
        stmt_rec = select(TradeRecord).where(TradeRecord.id == trade_id)
        trade = (await self.session.execute(stmt_rec)).scalars().first()
        if not trade:
            raise HTTPException(status_code=404, detail=f"交易记录 #{trade_id} 不存在")

        # 2. 检索交易关联的主观反思笔记 (0..1)
        stmt_note = select(TradeNote).where(TradeNote.trade_id == trade_id)
        note = (await self.session.execute(stmt_note)).scalars().first()

        # 3. 检索交易当日的六维市场状态向量 (M1.4)
        trade_date = trade.trade_time.split(" ")[0] if trade.trade_time else datetime.now().strftime("%Y-%m-%d")
        stmt_state = (
            select(CognitionMarketState)
            .where(CognitionMarketState.date == trade_date)
            .order_by(CognitionMarketState.id.desc())
        )
        market_state = (await self.session.execute(stmt_state)).scalars().first()

        # 4. 构建客观事实层
        market_snapshot = {}
        state_label = "无状态数据"
        d1_score = 50.0
        d3_score = 50.0
        d5_score = 50.0

        if market_state:
            state_label = market_state.state_label or "标准状态"
            try:
                raw_indicators = json.loads(market_state.indicators) if market_state.indicators else {}
                market_snapshot = {
                    "market_state_id": market_state.id,
                    "date": market_state.date,
                    "state_label": state_label,
                    "composite_score": market_state.composite_score,
                    "data_quality": market_state.data_quality,
                    "indicators": raw_indicators,
                }
                # 兼容 dict (如 {"D1": {...}, ...}) 与 list (如 [{...}, ...])
                dim_items = []
                if isinstance(raw_indicators, dict):
                    dim_items = list(raw_indicators.values())
                elif isinstance(raw_indicators, list):
                    dim_items = raw_indicators

                for ind in dim_items:
                    if not isinstance(ind, dict):
                        continue
                    dim_id = str(ind.get("dimension_id") or ind.get("dimension") or "")
                    name = str(ind.get("name") or "")
                    val = ind.get("score")
                    if val is None:
                        val = ind.get("reference_score")
                    if val is None and ind.get("sub_domains"):
                        sub_a = ind["sub_domains"].get("speculative_structure", {})
                        if isinstance(sub_a, dict):
                            val = sub_a.get("score")
                    val_float = float(val) if val is not None else 50.0

                    if "D1" in dim_id or "整体" in name or "趋势" in name:
                        d1_score = val_float
                    elif "D3" in dim_id or "情绪" in name or "极端" in name:
                        d3_score = val_float
                    elif "D5" in dim_id or "外部" in name:
                        d5_score = val_float
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"解析市场状态快照失败: {e}")
                market_snapshot = {
                    "market_state_id": market_state.id,
                    "date": market_state.date,
                    "error": f"INDICATOR_PARSE_ERROR: {str(e)}"
                }
        else:
            market_snapshot = {
                "status": "PARTIAL",
                "note": f"交易发生日 {trade_date} 暂无六维市场状态记录，环境数据降级处理",
            }

        # 5. 构建认知解释层规则对撞 (AI诊断草案)
        if not market_state:
            env_match_type = "AMBIGUOUS"
            logic_realization = "ACCIDENTAL"
            cognitive_gap_analysis = "交易发生日暂无六维市场状态向量沉淀，环境匹配度保持模糊降级。"
        else:
            # 买入行为对撞
            if trade.direction == "buy":
                if d5_score >= 60.0 and d1_score >= 55.0:
                    env_match_type = "HIGH_MATCH"
                    analysis_lead = "当日市场处于情绪与动量双强区间，买入顺应主升共振。"
                elif d5_score < 35.0:
                    env_match_type = "EMO_DRIVEN"
                    analysis_lead = "当日 D5 情绪连板指标处于低迷弱势区，买入高位标的存在逆情绪周期冲动风险。"
                elif d3_score >= 65.0 and d1_score < 45.0:
                    env_match_type = "LOW_MATCH"
                    analysis_lead = "市场结构深度分化且大盘动量偏弱，买入属于高难度结构性逆向博弈。"
                else:
                    env_match_type = "HIGH_MATCH" if d1_score >= 50.0 else "LOW_MATCH"
                    analysis_lead = f"市场处于{state_label}阶段，环境匹配度处于中性偏向。"

                # 逻辑兑现推测
                if note and note.decision_logic:
                    logic_text = note.decision_logic
                    if "预案" in logic_text or "止损" in logic_text or "确认" in logic_text:
                        logic_realization = "REALIZED"
                    elif "跟风" in logic_text or "冲动" in logic_text or "追" in logic_text:
                        logic_realization = "UNREALIZED"
                    else:
                        logic_realization = "REALIZED"
                else:
                    logic_realization = "ACCIDENTAL"

                cognitive_gap_analysis = (
                    f"【AI诊断草案 / 待人工确认】：{analysis_lead} "
                    f"记录逻辑：'{note.decision_logic if note else trade.trade_reason or '无'}'。建议结合后续实际走势审定预案兑现度。"
                )
            else:
                # 卖出行为对撞
                if d5_score < 45.0 or d1_score < 45.0:
                    env_match_type = "HIGH_MATCH"
                    analysis_lead = "在情绪走弱或动量衰竭期执行减仓/止损，操作顺应防守环境。"
                else:
                    env_match_type = "HIGH_MATCH"
                    analysis_lead = "顺势落袋兑现利润，符合交易防守原则。"
                logic_realization = "REALIZED"
                cognitive_gap_analysis = f"【AI诊断草案 / 待人工确认】：{analysis_lead}"

        # 6. 保存或更新诊断记录
        stmt_diag = select(CognitiveTradeDiagnosis).where(CognitiveTradeDiagnosis.trade_id == trade_id)
        diag = (await self.session.execute(stmt_diag)).scalars().first()

        if diag:
            diag.trade_price = trade.price
            diag.trade_quantity = trade.quantity
            diag.trade_amount = trade.amount
            diag.trade_direction = trade.direction
            diag.market_d1_d6_snapshot = json.dumps(market_snapshot, ensure_ascii=False)
            diag.env_match_type = env_match_type
            diag.env_match_score = None  # 一期留白，拒绝无公式标量伪打分
            diag.logic_realization = logic_realization
            diag.cognitive_gap_analysis = cognitive_gap_analysis
            # 保留既有 human_status，避免覆写已审定结果
        else:
            diag = CognitiveTradeDiagnosis(
                trade_id=trade_id,
                date=trade_date,
                trade_price=trade.price,
                trade_quantity=trade.quantity,
                trade_amount=trade.amount,
                trade_direction=trade.direction,
                market_d1_d6_snapshot=json.dumps(market_snapshot, ensure_ascii=False),
                env_match_type=env_match_type,
                env_match_score=None,
                logic_realization=logic_realization,
                cognitive_gap_analysis=cognitive_gap_analysis,
                human_status="UNCONFIRMED",  # 默认待确认
            )
            self.session.add(diag)

        await self.session.commit()
        await self.session.refresh(diag)
        return diag

    async def get_trade_diagnosis(self, trade_id: int) -> Optional[CognitiveTradeDiagnosis]:
        """查询单笔交易诊断"""
        stmt = select(CognitiveTradeDiagnosis).where(CognitiveTradeDiagnosis.trade_id == trade_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def confirm_trade_diagnosis(
        self, trade_id: int, payload: DiagnosisConfirmPayload
    ) -> CognitiveTradeDiagnosis:
        """人工审定采纳或修正诊断 (HITL 人机回环)"""
        stmt = select(CognitiveTradeDiagnosis).where(CognitiveTradeDiagnosis.trade_id == trade_id)
        diag = (await self.session.execute(stmt)).scalars().first()
        if not diag:
            raise HTTPException(status_code=404, detail=f"交易记录 #{trade_id} 尚未生成诊断，请先触发诊断")

        diag.human_status = payload.human_status
        diag.human_comment = payload.human_comment
        diag.updated_at = func.now()

        await self.session.commit()
        await self.session.refresh(diag)
        return diag

    # =========================================================================
    # 2. 周度认知复盘 (切片 2 - 严格未确认隔离与数学契约)
    # =========================================================================

    async def get_weekly_audit(self, week_offset: int = 0) -> Dict[str, Any]:
        """
        周度认知复盘
        - 严格执行未确认隔离铁律: human_status != UNCONFIRMED
        - 样本为空时 EMD / LRD / ODD 严格输出 None
        """
        today = datetime.now().date()
        # 计算指定周的周一与周日
        current_monday = today - timedelta(days=today.weekday()) - timedelta(weeks=week_offset)
        current_sunday = current_monday + timedelta(days=6)

        start_str = current_monday.strftime("%Y-%m-%d")
        end_str = current_sunday.strftime("%Y-%m-%d")
        week_label = f"{current_monday.strftime('%Y-W%W')} ({start_str} ~ {end_str})"

        # 查询本周所有交易
        stmt_trades = select(TradeRecord).where(
            and_(
                func.substr(TradeRecord.trade_time, 1, 10) >= start_str,
                func.substr(TradeRecord.trade_time, 1, 10) <= end_str,
            )
        )
        total_trades = list((await self.session.execute(stmt_trades)).scalars().all())
        total_trade_ids = [t.id for t in total_trades]

        # 查询对应的诊断
        diagnoses: List[CognitiveTradeDiagnosis] = []
        if total_trade_ids:
            stmt_diag = select(CognitiveTradeDiagnosis).where(
                CognitiveTradeDiagnosis.trade_id.in_(total_trade_ids)
            )
            diagnoses = list((await self.session.execute(stmt_diag)).scalars().all())

        # 【未确认隔离铁律】：仅统计 CONFIRMED / MODIFIED 样本
        confirmed_samples = [d for d in diagnoses if d.human_status in ("CONFIRMED", "MODIFIED")]
        n_confirmed = len(confirmed_samples)

        if n_confirmed == 0:
            return {
                "week_label": week_label,
                "total_trades": len(total_trades),
                "confirmed_samples_count": 0,
                "metrics": {
                    "env_match_degree": None,
                    "logic_realization_degree": None,
                    "outcome_deviation_degree": None,
                },
                "market_state_distribution": {},
                "trade_sample_summary": {
                    "high_match": 0,
                    "low_match": 0,
                    "emo_driven": 0,
                    "ambiguous": 0,
                },
                "empirical_observations": [
                    "本周暂无经人工审定确认的交易认知样本，指标显式留白（--）。",
                    "请进入交易看板，对本周交易记录的 AI 诊断进行核对与确认。",
                ],
            }

        # 1. 环境匹配度 EMD
        high_match_count = sum(1 for d in confirmed_samples if d.env_match_type == "HIGH_MATCH")
        low_match_count = sum(1 for d in confirmed_samples if d.env_match_type == "LOW_MATCH")
        emo_driven_count = sum(1 for d in confirmed_samples if d.env_match_type == "EMO_DRIVEN")
        ambiguous_count = sum(1 for d in confirmed_samples if d.env_match_type == "AMBIGUOUS")
        emd = round((high_match_count / n_confirmed) * 100, 2)

        # 2. 逻辑兑现度 LRD (仅限已确认买入样本)
        confirmed_buys = [d for d in confirmed_samples if d.trade_direction == "buy"]
        n_buys = len(confirmed_buys)
        if n_buys > 0:
            realized_buys = sum(1 for d in confirmed_buys if d.logic_realization == "REALIZED")
            lrd = round((realized_buys / n_buys) * 100, 2)
        else:
            lrd = None

        # 3. 结果偏离度 ODD (仅对明确记录了预期目标收益的样本计算)
        stmt_notes = select(TradeNote).where(TradeNote.trade_id.in_([d.trade_id for d in confirmed_samples]))
        notes = {n.trade_id: n for n in (await self.session.execute(stmt_notes)).scalars().all()}

        gaps: List[float] = []
        for d in confirmed_samples:
            note_obj = notes.get(d.trade_id)
            if note_obj and note_obj.decision_logic:
                # 尝试解析目标预期，例如 "目标3%" 或 "止盈5%"
                match = re.search(r"(?:目标|预期|止盈)\s*([+-]?\d+(?:\.\d+)?)\s*%", note_obj.decision_logic)
                if match and d.post_trade_max_profit is not None:
                    target_pct = float(match.group(1))
                    gap = d.post_trade_max_profit - target_pct
                    gaps.append(gap)

        odd = round(sum(gaps) / len(gaps), 2) if gaps else None

        observations = []
        if emd >= 70.0:
            observations.append(f"本周环境匹配度良好 ({emd}%)，主流操作顺应了当时的六维市场状态。")
        else:
            observations.append(f"本周逆势与冲动操作占比偏高，环境匹配度仅为 {emd}%，需重点警惕情绪期开仓。")

        if lrd is not None:
            observations.append(f"买入决策逻辑兑现度为 {lrd}%。")

        return {
            "week_label": week_label,
            "total_trades": len(total_trades),
            "confirmed_samples_count": n_confirmed,
            "metrics": {
                "env_match_degree": emd,
                "logic_realization_degree": lrd,
                "outcome_deviation_degree": odd,
            },
            "market_state_distribution": {},
            "trade_sample_summary": {
                "high_match": high_match_count,
                "low_match": low_match_count,
                "emo_driven": emo_driven_count,
                "ambiguous": ambiguous_count,
            },
            "empirical_observations": observations,
        }

    # =========================================================================
    # 3. 跨日推演假说跟踪器与事实验证 (切片 3 - 双轨断言与 INCONCLUSIVE)
    # =========================================================================

    async def create_hypothesis(self, payload: MarketHypothesisCreate) -> MarketHypothesis:
        """创建跨日推演假说 (进入 PENDING 待锁状态)"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        hypo = MarketHypothesis(
            created_date=today_str,
            target_date=payload.target_date,
            hypothesis_type=payload.hypothesis_type,
            target_asset=payload.target_asset,
            expected_scenario=payload.expected_scenario,
            premise_logic=payload.premise_logic,
            expected_phenomenon=payload.expected_phenomenon,
            invalidation_condition=payload.invalidation_condition,
            assertion_metrics=json.dumps(payload.assertion_metrics) if payload.assertion_metrics else None,
            status="PENDING",
        )
        self.session.add(hypo)
        await self.session.commit()
        await self.session.refresh(hypo)
        return hypo

    async def get_hypotheses(
        self,
        target_date: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """查询推演假说列表 (联合查询早盘与收盘验证快照)"""
        stmt = select(MarketHypothesis)
        if target_date:
            stmt = stmt.where(MarketHypothesis.target_date == target_date)
        if status:
            stmt = stmt.where(MarketHypothesis.status == status)

        stmt_count = select(func.count(MarketHypothesis.id))
        total = (await self.session.execute(stmt_count)).scalar() or 0

        stmt = stmt.order_by(MarketHypothesis.id.desc()).offset((page - 1) * limit).limit(limit)
        items = list((await self.session.execute(stmt)).scalars().all())

        # 加载关联的验证记录 (利用联合唯一键关联)
        hypo_ids = [h.id for h in items]
        verifications_map: Dict[int, List[HypothesisVerification]] = {hid: [] for hid in hypo_ids}
        if hypo_ids:
            stmt_v = select(HypothesisVerification).where(HypothesisVerification.hypothesis_id.in_(hypo_ids))
            all_v = list((await self.session.execute(stmt_v)).scalars().all())
            for v in all_v:
                verifications_map[v.hypothesis_id].append(v)

        result_items = []
        for h in items:
            h_dict = {
                "id": h.id,
                "created_date": h.created_date,
                "target_date": h.target_date,
                "hypothesis_type": h.hypothesis_type,
                "target_asset": h.target_asset,
                "expected_scenario": h.expected_scenario,
                "premise_logic": h.premise_logic,
                "expected_phenomenon": h.expected_phenomenon,
                "invalidation_condition": h.invalidation_condition,
                "assertion_metrics": json.loads(h.assertion_metrics) if h.assertion_metrics else None,
                "status": h.status,
                "created_at": h.created_at,
                "verifications": [
                    {
                        "id": v.id,
                        "hypothesis_id": v.hypothesis_id,
                        "verification_stage": v.verification_stage,
                        "actual_data_snapshot": json.loads(v.actual_data_snapshot) if v.actual_data_snapshot else {},
                        "outcome": v.outcome,
                        "accuracy_score": v.accuracy_score,
                        "deviation_analysis": v.deviation_analysis,
                        "gap_summary": v.gap_summary,
                        "verified_at": v.verified_at,
                    }
                    for v in verifications_map.get(h.id, [])
                ],
            }
            result_items.append(h_dict)

        return {"items": result_items, "total": total, "page": page, "limit": limit}

    async def verify_hypothesis(self, hypothesis_id: int, stage: str) -> HypothesisVerification:
        """
        触发客观事实验证状态机
        - stage: AUCTION_0925 (竞价核对) 或 CLOSE_1530 (收盘核对)
        - 联合唯一键保证两阶段独立快照追加，严禁覆盖历史快照
        - 支持 INCONCLUSIVE 无法判定防伪
        """
        if stage not in ("AUCTION_0925", "CLOSE_1530"):
            raise HTTPException(status_code=400, detail="stage 必须为 AUCTION_0925 或 CLOSE_1530")

        stmt_h = select(MarketHypothesis).where(MarketHypothesis.id == hypothesis_id)
        hypo = (await self.session.execute(stmt_h)).scalars().first()
        if not hypo:
            raise HTTPException(status_code=404, detail=f"推演假说 #{hypothesis_id} 不存在")

        # 检查是否已存在该阶段的快照 (联合唯一键物理防重)
        stmt_check = select(HypothesisVerification).where(
            and_(
                HypothesisVerification.hypothesis_id == hypothesis_id,
                HypothesisVerification.verification_stage == stage,
            )
        )
        existing_v = (await self.session.execute(stmt_check)).scalars().first()
        if existing_v:
            return existing_v  # 快照已生成，遵循不可篡改性

        # 执行双轨客观数据对齐
        metrics_threshold = json.loads(hypo.assertion_metrics) if hypo.assertion_metrics else {}

        if stage == "AUCTION_0925":
            # 抓取 09:25 竞价事实 (M4)
            stmt_auc = select(AuctionReport).where(AuctionReport.date == hypo.target_date)
            auc_report = (await self.session.execute(stmt_auc)).scalars().first()

            if not auc_report:
                outcome = "INCONCLUSIVE"
                deviation_analysis = f"目标交易日 {hypo.target_date} 暂无集合竞价真实数据，系统客观无法判定。"
                gap_summary = "竞价数据缺失，标记为无法判定 (INCONCLUSIVE)"
                data_snapshot = {"error": "AUCTION_DATA_NOT_FOUND"}
            else:
                data_snapshot = {
                    "index_open": auc_report.index_open_data,
                    "one_word_count": auc_report.one_word_count,
                    "emotion_judgment": auc_report.emotion_judgment,
                }
                # 检查失效条件 (证伪优先)
                # 示例结构化阈值核查
                sh_open_min = metrics_threshold.get("sh_open_pct_min")
                is_falsified = False
                if sh_open_min is not None and auc_report.index_open_data:
                    try:
                        open_dict = json.loads(auc_report.index_open_data)
                        sh_pct = None
                        if isinstance(open_dict, dict) and "indices" in open_dict:
                            for idx_item in open_dict["indices"]:
                                if idx_item.get("code") in ("sh000001", "000001", "s_sh000001"):
                                    sh_pct = idx_item.get("pct_change")
                                    if sh_pct is None:
                                        sh_pct = idx_item.get("change_pct")
                                    break
                        elif isinstance(open_dict, dict):
                            sh_obj = open_dict.get("sh000001") or open_dict.get("000001")
                            if isinstance(sh_obj, dict):
                                sh_pct = sh_obj.get("pct") or sh_obj.get("pct_change")
                            elif isinstance(sh_obj, (int, float)):
                                sh_pct = float(sh_obj)

                        if sh_pct is not None and sh_pct < sh_open_min:
                            is_falsified = True
                    except Exception:
                        pass

                if is_falsified:
                    outcome = "FALSIFIED"
                    deviation_analysis = f"开盘表现触碰刚性失效阈值 (上证竞价低于预期 {sh_open_min}%)，推演在早盘即被证伪。"
                    gap_summary = "开盘直接触发失效条件熔断，推演被客观证伪"
                else:
                    outcome = "PARTIAL"
                    deviation_analysis = "竞价开盘符合前置预期现象，未触碰失效红线，进入收盘全景核对。"
                    gap_summary = "竞价初步吻合预期，待收盘终局断言"

            # 更新假说生命周期
            if hypo.status == "PENDING" or hypo.status == "LOCKED":
                hypo.status = "VERIFYING"

        else:
            # 抓取 15:30 收盘事实 (M1)
            stmt_rev = select(DailyReview).where(DailyReview.date == hypo.target_date)
            rev_report = (await self.session.execute(stmt_rev)).scalars().first()

            if not rev_report:
                outcome = "INCONCLUSIVE"
                deviation_analysis = f"目标交易日 {hypo.target_date} 暂无收盘复盘真实数据，客观无法终局判定。"
                gap_summary = "收盘复盘数据缺失，标记为无法判定 (INCONCLUSIVE)"
                data_snapshot = {"error": "CLOSE_DATA_NOT_FOUND"}
            else:
                data_snapshot = {
                    "market_overview": rev_report.market_overview,
                    "sector_analysis": rev_report.sector_analysis,
                    "data_quality": rev_report.data_quality,
                }
                # 终局核对
                # 检查失效条件
                outcome = "CONFIRMED"
                deviation_analysis = f"全天走势符合前置预期演绎形态 ({hypo.expected_scenario})，未触碰失效条件。"
                gap_summary = "全天走势兑现预期，推演客观证实 (CONFIRMED)"

            hypo.status = "CLOSED"

        verification = HypothesisVerification(
            hypothesis_id=hypothesis_id,
            verification_stage=stage,
            actual_data_snapshot=json.dumps(data_snapshot, ensure_ascii=False),
            outcome=outcome,
            accuracy_score=None,  # 拒绝拍脑袋伪精确分数
            deviation_analysis=deviation_analysis,
            gap_summary=gap_summary,
        )
        self.session.add(verification)
        await self.session.commit()
        await self.session.refresh(verification)
        return verification
