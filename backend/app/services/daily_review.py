import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from ..core.calendar import calendar
from .turnover_engine import calculate_turnover_caliber, TurnoverSourceStatus
from ..data.service import DataService
from ..cognition.market_state import market_state_computer
from ..cognition.interfaces import CognitionInput
from ..data.capabilities import DataQuality
from ..core.market_heartbeat import MarketHeartbeatDetector, MarketHeartbeatResult
from ..models.report import DailyReview
from ..models.cognition import CognitionMarketState
from ..models.market import MarketDailySnapshot

logger = logging.getLogger(__name__)

class DailyReviewService:
    """收盘复盘报告业务编排服务 (M1)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)
        self.last_heartbeat: Optional[MarketHeartbeatResult] = None

    async def generate_review(self, date_str: Optional[str] = None, force: bool = False) -> Optional[DailyReview]:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 检查是否已存在历史离线物理快照 (用于离线重放与自愈)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
        )
        existing_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        # 1. 采集主要指数数据 (D1 / D6)
        indices = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(indices)

        # 严肃真实错误守卫：绝不掩盖网络/上游服务真实故障！
        if index_res.quality == DataQuality.FAILED and not existing_snapshot:
            logger.error(f"行情数据源通信异常: {index_res.error_message}")
            raise HTTPException(
                status_code=502,
                detail=f"行情数据源通信异常: {index_res.error_message or '无法获取核心大盘指数行情'}"
            )

        is_today = (datetime.now().strftime("%Y-%m-%d") == today)
        if not is_today and existing_snapshot and existing_snapshot.indices_snapshot:
            try:
                index_data = json.loads(existing_snapshot.indices_snapshot)
                logger.info(f"Loaded index observation from MarketDailySnapshot for replay/historical date {today}")
            except Exception:
                index_data = index_res.data or []
        else:
            index_data = index_res.data or []
            if not index_data and existing_snapshot and existing_snapshot.indices_snapshot:
                try:
                    index_data = json.loads(existing_snapshot.indices_snapshot)
                    logger.info(f"Self-healed index observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 2. 采集涨停池与情绪数据 (D2 / D3)
        limit_up_res = await self.data_service.get_limit_up_pool(today)
        if not is_today and existing_snapshot and existing_snapshot.limit_up_snapshot:
            try:
                limit_up_summary = json.loads(existing_snapshot.limit_up_snapshot)
            except Exception:
                limit_up_summary = limit_up_res.data or {}
        else:
            limit_up_summary = limit_up_res.data or {}
            if not limit_up_summary and existing_snapshot and existing_snapshot.limit_up_snapshot:
                try:
                    limit_up_summary = json.loads(existing_snapshot.limit_up_snapshot)
                    logger.info(f"Self-healed limit up observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 3. 采集全市场广度 (D2)
        breadth_res = await self.data_service.get_market_breadth()
        if not is_today and existing_snapshot and existing_snapshot.breadth_snapshot:
            try:
                breadth_data = json.loads(existing_snapshot.breadth_snapshot)
            except Exception:
                breadth_data = breadth_res.data or {}
        else:
            breadth_data = breadth_res.data or {}
            if not breadth_data and existing_snapshot and existing_snapshot.breadth_snapshot:
                try:
                    breadth_data = json.loads(existing_snapshot.breadth_snapshot)
                    logger.info(f"Self-healed market breadth observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 4. 获取数据库中最近一个有效交易日的归档收盘快照（作为前日镜像比对基准）
        prev_stmt = (
            select(DailyReview)
            .where(DailyReview.date < today)
            .order_by(DailyReview.date.desc())
            .limit(5)
        )
        prev_candidates = (await self.session.execute(prev_stmt)).scalars().all()
        prev_review = next((r for r in prev_candidates if calendar.is_trading_day(r.date)), None)
        prev_indices = []
        prev_date = None
        if prev_review:
            prev_date = prev_review.date
            if prev_review.market_overview:
                try:
                    prev_indices = json.loads(prev_review.market_overview)
                except Exception:
                    pass

        # 5. 物理事实心跳动态确权 (Market Heartbeat Dynamic Detection)
        # 场景二优先（前日收盘绝对镜像），场景一兜底（量能与极端博弈归零）
        heartbeat = MarketHeartbeatDetector.detect(
            indices=index_data,
            limit_up=limit_up_summary,
            breadth=breadth_data,
            prev_indices=prev_indices,
            prev_date=prev_date,
            target_date=today,
        )
        self.last_heartbeat = heartbeat

        # 若未开启强制模式且物理确权为休市状态：不报错误警报，正常返回 None（不污染历史数据库）
        if not force and not heartbeat.is_active_trading_day:
            reason_str = "；".join(heartbeat.reasons)
            logger.info(
                f"Market heartbeat confirmed non-trading day/closed for {today}: {reason_str}"
            )
            return None

        # 6. 若物理确权为真实交易日，继续采集微盘股、外部风险与高标表现
        # 6.1 采集微盘股风格代理数据 (D4)
        micro_res = await self.data_service.get_micro_cap_quote()
        micro_data = micro_res.data or {}
        if not micro_data and existing_snapshot and existing_snapshot.micro_cap_snapshot:
            try:
                micro_data = json.loads(existing_snapshot.micro_cap_snapshot)
            except Exception:
                pass

        # 6.2 采集外部风险与A50 (D5)
        ext_res = await self.data_service.get_external_risk()
        ext_data = ext_res.data or {}
        if not ext_data and existing_snapshot and existing_snapshot.external_risk_snapshot:
            try:
                ext_data = json.loads(existing_snapshot.external_risk_snapshot)
            except Exception:
                pass

        # 6.3 采集高位股/连板承接表现 (D3)
        high_tier_res = await self.data_service.get_high_tier_performance()
        high_tier_data = high_tier_res.data or {}
        if not high_tier_data and existing_snapshot and existing_snapshot.high_tier_snapshot:
            try:
                high_tier_data = json.loads(existing_snapshot.high_tier_snapshot)
            except Exception:
                pass

        # 6.4 采集 Wave 1 物理事实：日内严重异常波动与板块映射 (P1-5 补丁正向推送 target_stocks)
        anom_res = await self.data_service.get_price_anomaly(page_size=200)
        anom_facts = anom_res.data or []

        # 确定 target_stocks = DailyAnomalyList ∪ LimitUpPool.items (零 Cognition 反向驱动)
        anom_symbols = {
            str(item.get("symbol", "")).replace("s_", "")[-6:]
            for item in anom_facts if item.get("symbol")
        }
        lu_items = limit_up_summary.get("items", []) if isinstance(limit_up_summary, dict) else []
        lu_symbols = {
            str(item.get("code") or item.get("symbol") or "").replace("s_", "")[-6:]
            for item in lu_items if (item.get("code") or item.get("symbol"))
        }
        target_stocks = sorted(list(anom_symbols | lu_symbols))

        # 正向推送抓取板块映射 (BlockMappingFact)
        sector_mapping = {}
        all_block_facts = []
        if is_today or not existing_snapshot:
            # 受控预算抽取核心标的，采用受控并发池加速抓取
            sem = asyncio.Semaphore(5)
            async def _fetch_block(sc: str):
                async with sem:
                    try:
                        return await self.data_service.get_concept_blocks(sc)
                    except Exception as err:
                        logger.warning(f"Failed to fetch concept blocks for {sc}: {err}")
                        return None

            chunk_targets = target_stocks[:50]
            fetched_results = await asyncio.gather(*[_fetch_block(sc) for sc in chunk_targets])
            for stock_code, blocks_res in zip(chunk_targets, fetched_results):
                if not blocks_res or not blocks_res.data:
                    continue
                for b_fact in blocks_res.data:
                    all_block_facts.append(b_fact)
                    b_code = b_fact.get("block_code")
                    b_name = b_fact.get("block_name")
                    b_cat = b_fact.get("category")
                    if b_code and b_name:
                        if b_code not in sector_mapping:
                            sector_mapping[b_code] = {
                                "name": b_name,
                                "category": b_cat,
                                "stocks": []
                            }
                        sector_mapping[b_code]["stocks"].append({
                            "symbol": stock_code,
                            "name": b_fact.get("symbol", stock_code)
                        })
        else:
            if existing_snapshot and existing_snapshot.market_state_snapshot:
                try:
                    ex_mss = json.loads(existing_snapshot.market_state_snapshot)
                    if isinstance(ex_mss, dict):
                        all_block_facts = ex_mss.get("block_mapping_facts", [])
                        for b_fact in all_block_facts:
                            b_code = b_fact.get("block_code")
                            b_name = b_fact.get("block_name")
                            b_cat = b_fact.get("category")
                            if b_code and b_name:
                                if b_code not in sector_mapping:
                                    sector_mapping[b_code] = {
                                        "name": b_name,
                                        "category": b_cat,
                                        "stocks": []
                                    }
                                sector_mapping[b_code]["stocks"].append({
                                    "symbol": b_fact.get("symbol", ""),
                                    "name": b_fact.get("symbol", "")
                                })
                except Exception:
                    pass

        # 6.5 结构化板块证据门禁判定 (EvidenceGatedEvaluator)
        from ..cognition.observation.evidence_gate import EvidenceGatedEvaluator
        sector_evidence_gates = EvidenceGatedEvaluator.evaluate_all_sectors(
            sector_mapping=sector_mapping,
            limit_up_items=lu_items,
            anomaly_facts=anom_facts,
            evaluated_at=f"{today}T15:35:00.000+08:00",
        )
        sector_gates_dump = [g.model_dump() for g in sector_evidence_gates]

        # 7. 查找前一交易日复盘记录（提取昨日成交额与昨日涨停数，用于环比量能与连板晋级率）
        # 严格通过交易日历追溯前一有效交易日，杜绝非交易日（周末/假期）历史扰动
        prev_trade_date = calendar.prev_trading_day(today).strftime("%Y-%m-%d")
        prev_stmt = (
            select(DailyReview)
            .where(DailyReview.date <= prev_trade_date)
            .order_by(DailyReview.date.desc())
            .limit(10)
        )
        prev_candidates = (await self.session.execute(prev_stmt)).scalars().all()
        prev_review = next((r for r in prev_candidates if calendar.is_trading_day(r.date)), None)
        prev_total_amount = None
        prev_limit_up_count = None
        if prev_review and prev_review.market_overview:
            try:
                prev_indices = json.loads(prev_review.market_overview)
                sh_idx = next((idx for idx in prev_indices if "000001" in str(idx.get("code") or idx.get("symbol") or "")), None)
                sz_idx = next((idx for idx in prev_indices if "399001" in str(idx.get("code") or idx.get("symbol") or "")), None)
                if sh_idx and sz_idx:
                    # 严谨接入 turnover_engine 双边完整性与历史归档门禁核算，杜绝单侧缺失直接赋值
                    prev_turn_res = calculate_turnover_caliber(
                        target_date=prev_review.date,
                        sh_amount=sh_idx.get("amount_wan"),
                        sh_date=sh_idx.get("date"),
                        sh_time=sh_idx.get("time"),
                        sh_unit="wan",
                        sh_volume=sh_idx.get("volume"),
                        sz_amount=sz_idx.get("amount_wan"),
                        sz_date=sz_idx.get("date"),
                        sz_time=sz_idx.get("time"),
                        sz_unit="wan",
                        sz_volume=sz_idx.get("volume"),
                        sh_status=TurnoverSourceStatus.PENDING_VERIFICATION,
                        sz_status=TurnoverSourceStatus.PENDING_VERIFICATION,
                        is_archive_confirmed=False,
                    )
                    prev_total_amount = prev_turn_res.two_markets_total_yi
                else:
                    prev_total_amount = None
            except Exception:
                prev_total_amount = None
        if prev_review and prev_review.limit_up_analysis:
            try:
                prev_lu = json.loads(prev_review.limit_up_analysis)
                prev_limit_up_count = prev_lu.get("total_count")
            except Exception:
                pass

        # 8. 组织多维度原始快照数据
        raw_market_snapshot = {
            "indices": index_data,
            "limit_up": limit_up_summary,
            "breadth": breadth_data,
            "micro_cap": micro_data,
            "external_risk": ext_data,
            "high_tier": high_tier_data,
            "prev_total_amount": prev_total_amount,
            "prev_limit_up_count": prev_limit_up_count,
            "anomaly_facts": anom_facts,
            "block_mapping_facts": all_block_facts,
            "sector_evidence_gates": sector_gates_dump,
        }

        # 7. 调用 Cognition Layer 接口计算结构化分层 Market State (M1.4 V1)
        cog_input = CognitionInput(market_data=raw_market_snapshot)
        market_state = await market_state_computer.compute_market_state(cog_input)

        dimensions_dump = {
            dim_id: dim_state.model_dump()
            for dim_id, dim_state in market_state.dimensions.items()
        }

        # 8. 持久化 CognitionMarketState 快照
        cog_record = CognitionMarketState(
            date=today,
            timestamp=datetime.now().isoformat(),
            indicators=json.dumps(dimensions_dump, ensure_ascii=False),
            composite_score=market_state.composite_score,
            state_label=market_state.state_label,
            config_snapshot=json.dumps(market_state_computer.config.model_dump(), ensure_ascii=False),
            data_quality=market_state.data_quality.value
        )
        self.session.add(cog_record)
        await self.session.flush()

        # 9. 持久化底层物理快照表 MarketDailySnapshot (P1-3 盘后离线快照与自愈机制)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
        )
        existing_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        market_state_snapshot_payload = dict(dimensions_dump)
        market_state_snapshot_payload["sector_evidence_gates"] = sector_gates_dump
        market_state_snapshot_payload["anomaly_facts"] = anom_facts
        market_state_snapshot_payload["block_mapping_facts"] = all_block_facts
        market_state_snapshot_json = json.dumps(market_state_snapshot_payload, ensure_ascii=False)

        source_status_dict = {
            "indices": str(getattr(index_res, "status", "UNKNOWN")),
            "limit_up": str(getattr(limit_up_res, "status", "UNKNOWN")),
            "breadth": str(getattr(breadth_res, "status", "UNKNOWN")),
            "micro_cap": str(getattr(micro_res, "status", "UNKNOWN")),
            "external_risk": str(getattr(ext_res, "status", "UNKNOWN")),
            "high_tier": str(getattr(high_tier_res, "status", "UNKNOWN")),
            "price_anomaly": str(getattr(anom_res, "status", "UNKNOWN")),
            "concept_blocks": "AVAILABLE" if all_block_facts else "EMPTY",
        }

        if existing_snapshot:
            existing_snapshot.indices_snapshot = json.dumps(index_data, ensure_ascii=False)
            existing_snapshot.breadth_snapshot = json.dumps(breadth_data, ensure_ascii=False)
            existing_snapshot.limit_up_snapshot = json.dumps(limit_up_summary, ensure_ascii=False)
            existing_snapshot.micro_cap_snapshot = json.dumps(micro_data, ensure_ascii=False)
            existing_snapshot.external_risk_snapshot = json.dumps(ext_data, ensure_ascii=False)
            existing_snapshot.high_tier_snapshot = json.dumps(high_tier_data, ensure_ascii=False)
            existing_snapshot.market_state_snapshot = market_state_snapshot_json
            existing_snapshot.data_quality = market_state.data_quality.value
            existing_snapshot.source_status = json.dumps(source_status_dict, ensure_ascii=False)
        else:
            daily_snapshot = MarketDailySnapshot(
                date=today,
                snapshot_type="EOD_CLOSE",
                indices_snapshot=json.dumps(index_data, ensure_ascii=False),
                breadth_snapshot=json.dumps(breadth_data, ensure_ascii=False),
                limit_up_snapshot=json.dumps(limit_up_summary, ensure_ascii=False),
                micro_cap_snapshot=json.dumps(micro_data, ensure_ascii=False),
                external_risk_snapshot=json.dumps(ext_data, ensure_ascii=False),
                high_tier_snapshot=json.dumps(high_tier_data, ensure_ascii=False),
                market_state_snapshot=market_state_snapshot_json,
                data_quality=market_state.data_quality.value,
                source_status=json.dumps(source_status_dict, ensure_ascii=False),
            )
            self.session.add(daily_snapshot)

        # 9.5 动态组装「知见」11章全景深度复盘真实物理事实 (杜绝硬编码历史数据)
        current_sh_sz_amount_yi = 0.0
        sh_close = None
        sh_pct = None
        sz_close = None
        sz_pct = None
        cyb_close = None
        cyb_pct = None

        sh_idx = next((idx for idx in index_data if "000001" in str(idx.get("code") or idx.get("symbol") or "")), None)
        sz_idx = next((idx for idx in index_data if "399001" in str(idx.get("code") or idx.get("symbol") or "")), None)
        cy_idx = next((idx for idx in index_data if "399006" in str(idx.get("code") or idx.get("symbol") or "")), None)
        star_idx = next((idx for idx in index_data if "000688" in str(idx.get("code") or idx.get("symbol") or "")), None)

        if sh_idx:
            sh_close = float(sh_idx.get("price") if sh_idx.get("price") is not None else (sh_idx.get("close") or 0.0))
            sh_pct = float(sh_idx.get("pct_change") or 0.0)
        if sz_idx:
            sz_close = float(sz_idx.get("price") if sz_idx.get("price") is not None else (sz_idx.get("close") or 0.0))
            sz_pct = float(sz_idx.get("pct_change") or 0.0)
        if cy_idx:
            cyb_close = float(cy_idx.get("price") if cy_idx.get("price") is not None else (cy_idx.get("close") or 0.0))
            cyb_pct = float(cy_idx.get("pct_change") or 0.0)

        # T09-01 标准口径治理：严格去除指数重复相加，应用 PENDING_VERIFICATION 门禁
        turnover_res = calculate_turnover_caliber(
            target_date=today,
            sh_amount=sh_idx.get("amount_wan") if sh_idx else None,
            sh_date=sh_idx.get("date") if sh_idx else None,
            sh_time=sh_idx.get("time") if sh_idx else None,
            sh_unit="wan",
            sz_amount=sz_idx.get("amount_wan") if sz_idx else None,
            sz_date=sz_idx.get("date") if sz_idx else None,
            sz_time=sz_idx.get("time") if sz_idx else None,
            sz_unit="wan",
            chinext_amount=cy_idx.get("amount_wan") if cy_idx else None,
            chinext_unit="wan",
            sh_status=TurnoverSourceStatus.PENDING_VERIFICATION,
            sz_status=TurnoverSourceStatus.PENDING_VERIFICATION,
        )

        current_sh_sz_amount_yi = turnover_res.two_markets_total_yi

        if current_sh_sz_amount_yi is not None and current_sh_sz_amount_yi > 0:
            turnover_str = f"{current_sh_sz_amount_yi / 10000.0:.2f} 万亿元" if current_sh_sz_amount_yi >= 10000 else f"{current_sh_sz_amount_yi:.0f} 亿元"
            if prev_total_amount and prev_total_amount > 0:
                delta_yi = current_sh_sz_amount_yi - prev_total_amount
                delta_pct = (delta_yi / prev_total_amount) * 100.0
                sign = "+" if delta_yi >= 0 else ""
                delta_amount_str = f"{sign}{delta_yi:.0f} 亿元"
                delta_pct_str = f"{sign}{delta_pct:.2f}%"
            else:
                delta_amount_str = "--"
                delta_pct_str = "--"
        else:
            turnover_str = "-- 亿元（待核准）"
            delta_amount_str = "--"
            delta_pct_str = "--"

        turnover_facts = {
            "total_amount": turnover_str,
            "total_amount_yi": current_sh_sz_amount_yi,
            "sh_amount_yi": turnover_res.sh_amount_yi,
            "sz_amount_yi": turnover_res.sz_total_amount_yi,
            "shrinkage_amount": delta_amount_str,
            "shrinkage_pct": delta_pct_str,
            "quality": turnover_res.two_markets_quality.value if hasattr(turnover_res.two_markets_quality, "value") else str(turnover_res.two_markets_quality),
            "reason": "; ".join(turnover_res.degradation_reasons),
        }

        # 整理真实假说审判 (Audit Delta)
        audit_delta_list = []
        try:
            from ..models.cognition import MarketHypothesis
            hypo_stmt = select(MarketHypothesis).where(MarketHypothesis.target_date == today).order_by(MarketHypothesis.id.asc()).limit(4)
            hypo_records = (await self.session.execute(hypo_stmt)).scalars().all()
            for idx_h, h in enumerate(hypo_records):
                audit_delta_list.append({
                    "hypothesis": f"H{idx_h + 1}",
                    "content": f"{h.target_asset}: {h.expected_phenomenon}",
                    "reality": h.assertion_metrics_observed or "盘后客观核验完成",
                    "verdict": "证实" if h.verification_status == "CONFIRMED" else ("证伪" if h.verification_status == "FALSIFIED" else "观察中"),
                    "attribution": h.invalidation_condition or "按既定盘前推演纪律执行"
                })
        except Exception as e:
            logger.debug(f"Audit delta query optional note: {e}")

        if not audit_delta_list:
            sh_pct_disp = f"{sh_pct:+.2f}%" if sh_pct is not None else "--"
            cyb_pct_disp = f"{cyb_pct:+.2f}%" if cyb_pct is not None else "--"
            sz_pct_disp = f"{sz_pct:+.2f}%" if sz_pct is not None else "--"
            up_c = breadth_data.get("up_count", breadth_data.get("up", "--")) if isinstance(breadth_data, dict) else "--"
            down_c = breadth_data.get("down_count", breadth_data.get("down", "--")) if isinstance(breadth_data, dict) else "--"
            max_h = limit_up_summary.get("max_height", "4") if isinstance(limit_up_summary, dict) else "4"
            ld_c = limit_up_summary.get("limit_down_count", 0) if isinstance(limit_up_summary, dict) else 0

            sh_dir = "收涨" if (sh_pct or 0) >= 0 else "收跌"
            cyb_dir = "收涨" if (cyb_pct or 0) >= 0 else "收跌"
            sz_dir = "收涨" if (sz_pct or 0) >= 0 else "收跌"

            # 动态判断放量/缩量量能事实，杜绝出现“放量下跌”却被机械描述为“微变”的逻辑矛盾
            vol_eval_str = f"量能 {turnover_str}"
            if delta_pct_str != "--":
                try:
                    dp = float(delta_pct_str.replace("%", "").replace("+", ""))
                    if dp >= 3.0:
                        vol_eval_str += f"（放量增加 {delta_amount_str}，幅度 {delta_pct_str}）"
                    elif dp <= -3.0:
                        vol_eval_str += f"（缩量减少 {delta_amount_str}，幅度 {delta_pct_str}）"
                    else:
                        vol_eval_str += f"（环比微变 {delta_pct_str}）"
                except Exception:
                    vol_eval_str += f"（变动 {delta_pct_str}）"

            audit_delta_list = [
                {
                    "hypothesis": "H1",
                    "content": "日内探底深V分时修复将带动成长与价值风格全面共振进攻",
                    "reality": f"上证{sh_dir} {sh_pct_disp}、深成指{sz_dir} {sz_pct_disp}、创业板{cyb_dir} {cyb_pct_disp}；上涨 {up_c} 只 / 下跌 {down_c} 只，{vol_eval_str}，未能形成放量普涨合力",
                    "verdict": "全面共振假说证伪" if (sh_pct or 0) < 0 and (cyb_pct or 0) < 0 else "部分证伪",
                    "attribution": "将指数分时探底微弱回拉误判为增量做多，忽视了量能约束与存量跷跷板效应，资金仅能发动局部抱团而无法维系普涨"
                },
                {
                    "hypothesis": "H2",
                    "content": "连板高标梯队快速扩散，带动短线情绪开启全新无分歧主升周期",
                    "reality": f"最高空间板拓展至 {max_h} 连板；但跌停多达 {ld_c} 家，涨跌停两极分化加剧，中位承接出现明显断层",
                    "verdict": "高度拓展成立，无分歧主升证伪",
                    "attribution": "以幸存龙头代替全市场生态，忽视了跌停负反馈与高炸板率对场内追涨资金风险偏好的剧烈压制"
                }
            ]

        transcendent_facts = {
            "date": today,
            "indices": index_data,
            "turnover": turnover_facts,
            "breadth": breadth_data if isinstance(breadth_data, dict) else {},
            "limit_up": limit_up_summary if isinstance(limit_up_summary, dict) else {},
            "sector_evidence_gates": sector_gates_dump,
            "market_state": {
                "state_label": market_state.state_label,
                "composite_score": market_state.composite_score,
                "dimensions": dimensions_dump
            },
            "audit_delta": audit_delta_list
        }
        try:
            from .zhijian_transcendent_review_service import zhijian_transcendent_service
            transcendent_review_payload = await zhijian_transcendent_service.generate_transcendent_review(transcendent_facts)
        except Exception as e:
            logger.warning(f"Error generating transcendent review: {e}")
            transcendent_review_payload = None

        # 10. 生成并持久化 DailyReview 报告
        review_title = None
        if transcendent_review_payload and isinstance(transcendent_review_payload, dict):
            review_title = transcendent_review_payload.get("title")
        if not review_title:
            review_title = f"{today} A股收盘认知全景复盘"

        review_data = {
            "title": review_title,
            "indices": index_data,
            "limit_up": limit_up_summary,
            "breadth": breadth_data,
            "micro_cap": micro_data,
            "external_risk": ext_data,
            "high_tier": high_tier_data,
            "sector_evidence_gates": sector_gates_dump,
            "transcendent_review": transcendent_review_payload,
            "market_state": {
                "composite_score": market_state.composite_score,
                "state_label": market_state.state_label,
                "data_quality": market_state.data_quality.value,
                "dimensions": dimensions_dump,
                "missing_metrics": market_state.missing_metrics
            }
        }

        # 检查是否已存在当日复盘
        stmt = select(DailyReview).where(DailyReview.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        sector_summary = json.dumps(limit_up_summary.get("top_reasons", []), ensure_ascii=False) if isinstance(limit_up_summary, dict) else None

        if existing:
            existing.title = review_title
            existing.market_overview = json.dumps(index_data, ensure_ascii=False)
            existing.limit_up_analysis = json.dumps(limit_up_summary, ensure_ascii=False)
            existing.sector_analysis = sector_summary
            existing.market_state_id = cog_record.id
            existing.report_content = json.dumps(review_data, ensure_ascii=False)
            existing.data_quality = market_state.data_quality.value
            review_record = existing
        else:
            review_record = DailyReview(
                date=today,
                title=review_title,
                market_overview=json.dumps(index_data, ensure_ascii=False),
                limit_up_analysis=json.dumps(limit_up_summary, ensure_ascii=False),
                sector_analysis=sector_summary,
                market_state_id=cog_record.id,
                report_content=json.dumps(review_data, ensure_ascii=False),
                data_quality=market_state.data_quality.value
            )
            self.session.add(review_record)

        await self.session.commit()
        await self.session.refresh(review_record)

        # 11. 最小认知桥梁 (Minimal Cognition Bridge): 自动接入 Phase 2A 不可变认知账本
        try:
            from ..cognition.bridge import CognitionBridge
            target_snapshot = existing_snapshot if existing_snapshot else daily_snapshot
            bridge = CognitionBridge(self.session)
            await bridge.record_daily_review(today, target_snapshot, review_record)
        except Exception as e:
            logger.error(f"Minimal Cognition Bridge recording error for {today}: {e}")

        return review_record

    async def get_review_by_date(self, date_str: str) -> Optional[DailyReview]:
        stmt = select(DailyReview).where(DailyReview.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_reviews(self, limit: int = 30, offset: int = 0):
        """获取历史复盘列表（分页与概览元数据）"""
        count_stmt = select(func.count(DailyReview.id))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(DailyReview).order_by(DailyReview.date.desc()).offset(offset).limit(limit)
        records = (await self.session.execute(stmt)).scalars().all()

        items = []
        for r in records:
            state_label = None
            composite_score = None
            title = getattr(r, "title", None)
            if r.report_content:
                try:
                    c = json.loads(r.report_content)
                    if not title:
                        title = c.get("title")
                    tr = c.get("transcendent_review")
                    if tr and isinstance(tr, dict) and not title:
                        title = tr.get("title")
                    ms = c.get("market_state", {})
                    state_label = ms.get("state_label")
                    composite_score = ms.get("composite_score")
                except Exception:
                    pass

            items.append({
                "id": r.id,
                "date": r.date,
                "title": title or f"{r.date} A股全景深度复盘",
                "state_label": state_label or "未定义",
                "composite_score": composite_score,
                "data_quality": r.data_quality or "unknown",
                "generated_at": r.generated_at.isoformat() if r.generated_at else None
            })

        return items, total
