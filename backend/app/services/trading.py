import hashlib
import time
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, time as dt_time
from fastapi import HTTPException
from sqlalchemy import select, func, and_, or_, not_
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.trading import TradeRecord, Position, TradeNote
from ..schemas.trading import (
    TradeRecordCreate,
    ReversalTradeCreate,
    CorrectTradeRecordRequest,
    TradeNoteCreate,
    TradeRecordResponse,
    PositionResponse,
    TradeStatsResponse,
    TradeNoteResponse,
)
from ..core.calendar import calendar
from ..data.service import DataService

class TradingService:
    """G1-M3 交易记录与持仓管理服务 (v1.2)"""

    def __init__(self, session: AsyncSession, data_service: Optional[DataService] = None):
        self.session = session
        self.data_service = data_service or DataService()

    def _generate_fingerprint(self, code: str, direction: str, price: float, quantity: int, trade_time: str) -> str:
        raw = f"{code}_{direction}_{price:.3f}_{quantity}_{trade_time}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _is_market_trading_time(self) -> bool:
        """判断当前是否处于A股连续交易时间段"""
        now = datetime.now()
        if not calendar.is_trading_day(now.date()):
            return False
        t = now.time()
        morning = (t >= dt_time(9, 30, 0) and t <= dt_time(11, 30, 0))
        afternoon = (t >= dt_time(13, 0, 0) and t <= dt_time(15, 0, 0))
        return morning or afternoon

    async def add_trade_record(self, payload: TradeRecordCreate) -> TradeRecord:
        """
        录入真实买卖事实流水并驱动派生持仓更新
        - 幂等性校验与 60s 指纹防重
        - 服务端强制派生计算 amount
        - 卖出超卖强校验拦截（400 阻断）
        """
        # 0. 严格拦截策略模拟数据误入真实交易事实账本 (物理隔离保护)
        if payload.source in ("STRATEGY_WORKBENCH", "SIMULATION") or (payload.trade_reason and ("模拟" in payload.trade_reason or "虚拟跟单" in payload.trade_reason)):
            raise HTTPException(status_code=400, detail="真实交易账本严禁录入策略模拟交易数据，模拟交易请使用 /api/v1/simulation 接口。")

        # 1. 幂等性防重检查
        if payload.idempotency_key:
            stmt = select(TradeRecord).where(TradeRecord.idempotency_key == payload.idempotency_key)
            existing = (await self.session.execute(stmt)).scalars().first()
            if existing:
                return existing

        # 2. 60秒指纹去重（防止网络卡顿连击）
        # 查找相同代码、方向、价格、数量、交易时间的记录
        stmt_dup = select(TradeRecord).where(
            TradeRecord.code == payload.code,
            TradeRecord.direction == payload.direction.lower(),
            TradeRecord.price == payload.price,
            TradeRecord.quantity == payload.quantity,
            TradeRecord.trade_time == payload.trade_time,
            TradeRecord.record_type == "TRADE",
        )
        duplicate = (await self.session.execute(stmt_dup)).scalars().first()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": 409,
                    "message": "检测到重复提交的交易流水，请勿重复操作",
                    "error_type": "DUPLICATE_TRADE_RECORD",
                    "existing_id": duplicate.id,
                },
            )

        # 3. 强制服务端计算派生金额
        amount = round(payload.price * payload.quantity, 2)

        # 4. 卖出超卖强校验
        stmt_pos = select(Position).where(Position.code == payload.code)
        pos = (await self.session.execute(stmt_pos)).scalars().first()
        current_holding_qty = pos.quantity if pos else 0

        if payload.direction.lower() == "sell":
            if current_holding_qty < payload.quantity:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": 400,
                        "message": f"当前持仓数量不足以卖出：持仓 {current_holding_qty} 股，申请卖出 {payload.quantity} 股",
                        "error_type": "INSUFFICIENT_POSITION_ERROR",
                        "code_str": payload.code,
                        "current_qty": current_holding_qty,
                        "requested_sell_qty": payload.quantity,
                    },
                )

        # 0. 规范清洗股票名称，确保 UTF-8，彻底清除乱码与 ????
        cleaned_name = payload.name
        if cleaned_name:
            cleaned_name = cleaned_name.replace("?", "").replace("？", "").strip()
            if not cleaned_name:
                cleaned_name = None
        if not cleaned_name or cleaned_name == payload.code:
            try:
                sec_list = await self.search_securities(payload.code, limit=1)
                if sec_list and sec_list[0].get("name"):
                    cleaned_name = sec_list[0]["name"].strip()
            except Exception:
                pass
        if not cleaned_name:
            cleaned_name = pos.name if (pos and pos.name and "?" not in pos.name) else payload.code

        # 5. 写入 Truth Ledger
        record = TradeRecord(
            code=payload.code,
            name=cleaned_name,
            direction=payload.direction.lower(),
            price=payload.price,
            quantity=payload.quantity,
            amount=amount,
            trade_time=payload.trade_time,
            trade_reason=payload.trade_reason,
            source=payload.source,
            record_type="TRADE",
            reversed_record_id=None,
            idempotency_key=payload.idempotency_key,
        )
        self.session.add(record)

        # 6. 单向驱动派生持仓更新
        if payload.direction.lower() == "buy":
            if pos:
                new_qty = pos.quantity + payload.quantity
                new_total_cost = round(pos.total_cost + amount, 2)
                pos.quantity = new_qty
                pos.total_cost = new_total_cost
                pos.avg_cost = round(new_total_cost / new_qty, 3) if new_qty > 0 else payload.price
                if cleaned_name and cleaned_name != pos.code:
                    pos.name = cleaned_name
            else:
                pos = Position(
                    code=payload.code,
                    name=cleaned_name,
                    quantity=payload.quantity,
                    avg_cost=payload.price,
                    total_cost=amount,
                    current_price=None,
                    price_type="UNAVAILABLE",
                    floating_pnl=None,
                )
                self.session.add(pos)
        elif payload.direction.lower() == "sell":
            pos.quantity -= payload.quantity
            if pos.quantity == 0:
                pos.total_cost = 0.0
                pos.avg_cost = 0.0
                pos.current_price = None
                pos.floating_pnl = 0.0
            else:
                pos.total_cost = round(pos.quantity * pos.avg_cost, 2)

        # 确保交易事实优先落盘 (硬约束 3: 交易账本永远优先于 AI 服务)
        await self.session.commit()
        await self.session.refresh(record)

        # 7. 派生单笔认知对撞诊断 (严格与交易事务解耦，故障绝不影响交易事实)
        try:
            from .cognition_review import CognitionReviewService
            cog_service = CognitionReviewService(self.session)
            await cog_service.diagnose_trade(record.id)
        except Exception as diag_err:
            import logging
            logging.getLogger(__name__).warning(
                f"交易 #{record.id} 自动认知诊断触发异常 (已安全解耦降级，交易事实百分之百落盘): {diag_err}"
            )

        return record

    async def create_reversal_record(self, payload: ReversalTradeCreate) -> TradeRecord:
        """
        创建会计红字冲正记录（Reversal Record）
        - 绝对禁止就地修改或删除历史流水
        - 生成反向对冲流水记录，成对抵消
        - 触发代码级持仓重算对账，使持仓与均价彻底复原
        """
        if payload.idempotency_key:
            stmt = select(TradeRecord).where(TradeRecord.idempotency_key == payload.idempotency_key)
            existing = (await self.session.execute(stmt)).scalars().first()
            if existing:
                return existing

        stmt_target = select(TradeRecord).where(TradeRecord.id == payload.target_record_id)
        target = (await self.session.execute(stmt_target)).scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="未找到待冲正的交易记录")

        if target.record_type == "REVERSAL":
            raise HTTPException(status_code=400, detail="不能对冲正记录再次发起冲正")

        stmt_rev_check = select(TradeRecord).where(TradeRecord.reversed_record_id == target.id)
        already_reversed = (await self.session.execute(stmt_rev_check)).scalars().first()
        if already_reversed:
            raise HTTPException(status_code=400, detail="该记录已被冲正，不可重复冲正")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rev_direction = "sell" if target.direction == "buy" else "buy"
        rev_amount = round(target.price * target.quantity, 2)

        rev_record = TradeRecord(
            code=target.code,
            name=target.name,
            direction=rev_direction,
            price=target.price,
            quantity=target.quantity,
            amount=rev_amount,
            trade_time=now_str,
            trade_reason=f"[系统冲正: 抵消流水#{target.id}] {payload.reason}",
            source=target.source,
            record_type="REVERSAL",
            reversed_record_id=target.id,
            idempotency_key=payload.idempotency_key,
        )
        self.session.add(rev_record)
        await self.session.flush()

        # 触发该标的的持仓全量顺序重放，从根本上复原持仓状态与均价，杜绝虚假已实现盈亏
        await self._reconcile_single_code(target.code)

        await self.session.commit()
        await self.session.refresh(rev_record)
        return rev_record

    async def correct_trade_record(self, payload: CorrectTradeRecordRequest) -> Dict[str, Any]:
        """
        对既有交易执行审计链不可篡改纠错 (P1-C)
        流程：
        1. 验证目标交易 target_record 存在且为有效 TRADE (未被冲正)
        2. 生成系统冲正流水 REVERSAL，消除原交易对账本与持仓的影响
        3. 生成修正后的新交易流水 TRADE，记录溯源信息
        4. 顺序重放持仓 (若代码发生变更，同时重算原标的与新标的持仓)
        5. 提交事务，触发新交易的解耦认知诊断
        """
        stmt = select(TradeRecord).where(TradeRecord.id == payload.target_record_id)
        target = (await self.session.execute(stmt)).scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="待纠错的交易记录不存在")
        if target.record_type != "TRADE":
            raise HTTPException(status_code=400, detail="只能对正常交易流水 (TRADE) 进行纠错")

        stmt_rev_check = select(TradeRecord).where(TradeRecord.reversed_record_id == target.id)
        already_reversed = (await self.session.execute(stmt_rev_check)).scalars().first()
        if already_reversed:
            raise HTTPException(status_code=400, detail="该记录已被冲正或纠错，不可重复操作")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rev_direction = "sell" if target.direction == "buy" else "buy"
        rev_amount = round(target.price * target.quantity, 2)

        # 1. 创建红字冲正流水
        rev_record = TradeRecord(
            code=target.code,
            name=target.name,
            direction=rev_direction,
            price=target.price,
            quantity=target.quantity,
            amount=rev_amount,
            trade_time=now_str,
            trade_reason=f"[纠错冲正: 抵消流水#{target.id}] {payload.reason}",
            source=target.source,
            record_type="REVERSAL",
            reversed_record_id=target.id,
            idempotency_key=f"correct_rev_{target.id}_{int(time.time()*1000)}"
        )
        self.session.add(rev_record)
        await self.session.flush()

        # 2. 准备修正后的新交易数据
        corr = payload.corrected_data
        corr_amount = round(corr.price * corr.quantity, 2)
        corr_name = corr.name
        if corr_name:
            corr_name = corr_name.replace("?", "").replace("？", "").strip()
            if not corr_name:
                corr_name = None
        if not corr_name or corr_name == corr.code:
            try:
                sec_list = await self.search_securities(corr.code, limit=1)
                if sec_list and sec_list[0].get("name"):
                    corr_name = sec_list[0]["name"].strip()
            except Exception:
                pass
        if not corr_name:
            corr_name = corr.code

        new_record = TradeRecord(
            code=corr.code,
            name=corr_name,
            direction=corr.direction.lower(),
            price=corr.price,
            quantity=corr.quantity,
            amount=corr_amount,
            trade_time=corr.trade_time,
            trade_reason=f"[纠错修正自流水#{target.id}] {corr.trade_reason or payload.reason}",
            source=corr.source,
            record_type="TRADE",
            reversed_record_id=None,
            idempotency_key=corr.idempotency_key or f"corr_new_{target.id}_{int(time.time()*1000)}"
        )
        self.session.add(new_record)
        await self.session.flush()

        # 3. 继承或迁移复盘笔记 (若原交易有笔记)
        stmt_note = select(TradeNote).where(TradeNote.trade_id == target.id)
        target_note = (await self.session.execute(stmt_note)).scalars().first()
        if target_note:
            new_note = TradeNote(
                trade_id=new_record.id,
                date=target_note.date,
                mental_state=target_note.mental_state,
                decision_logic=target_note.decision_logic,
                reflection=target_note.reflection,
                lessons=f"[从流水#{target.id}纠错继承] {target_note.lessons or ''}"
            )
            self.session.add(new_note)

        # 4. 全量重放受影响标的的持仓
        await self._reconcile_single_code(target.code)
        if corr.code != target.code:
            await self._reconcile_single_code(corr.code)

        await self.session.commit()
        await self.session.refresh(rev_record)
        await self.session.refresh(new_record)

        # 5. 解耦触发新交易的认知诊断
        try:
            from .cognition_review import CognitionReviewService
            cog_service = CognitionReviewService(self.session)
            await cog_service.diagnose_trade(new_record.id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"纠错新交易 #{new_record.id} 自动认知诊断触发降级: {e}")

        return {
            "reversal_record": rev_record,
            "corrected_record": new_record,
            "reversal": rev_record,
            "corrected": new_record
        }


    async def _reconcile_single_code(self, code: str) -> Position:
        """针对单只标的顺序回放流水，成对排除冲正对，重算派生持仓"""
        stmt = select(TradeRecord).where(
            TradeRecord.code == code,
            TradeRecord.source.notin_(["STRATEGY_WORKBENCH", "SIMULATION"]),
            not_(TradeRecord.trade_reason.like("%模拟%")),
            not_(TradeRecord.trade_reason.like("%虚拟跟单%"))
        ).order_by(TradeRecord.trade_time.asc(), TradeRecord.id.asc())
        all_records = list((await self.session.execute(stmt)).scalars().all())

        # 提取冲正对集合
        reversal_ids = set()
        for r in all_records:
            if r.record_type == "REVERSAL" and r.reversed_record_id:
                reversal_ids.add(r.reversed_record_id)
                reversal_ids.add(r.id)

        # 状态机回放
        effective_records = [r for r in all_records if r.id not in reversal_ids]
        qty = 0
        total_cost = 0.0
        avg_cost = 0.0
        stock_name = code

        for r in effective_records:
            if r.name:
                stock_name = r.name
            if r.direction == "buy":
                qty += r.quantity
                total_cost += r.amount
                avg_cost = round(total_cost / qty, 3) if qty > 0 else 0.0
            elif r.direction == "sell":
                qty = max(0, qty - r.quantity)
                if qty == 0:
                    total_cost = 0.0
                    avg_cost = 0.0
                else:
                    total_cost = round(qty * avg_cost, 2)

        # 更新物化视图 Position
        stmt_pos = select(Position).where(Position.code == code)
        pos = (await self.session.execute(stmt_pos)).scalars().first()
        if not pos:
            pos = Position(code=code, name=stock_name, quantity=qty, avg_cost=avg_cost, total_cost=total_cost)
            self.session.add(pos)
        else:
            pos.name = stock_name
            pos.quantity = qty
            pos.avg_cost = avg_cost
            pos.total_cost = total_cost
            if qty == 0:
                pos.current_price = None
                pos.floating_pnl = 0.0
                pos.price_type = "UNAVAILABLE"

        return pos

    async def reconcile_positions(self, code: Optional[str] = None) -> Dict[str, Any]:
        """全量对账与派生持仓重建服务"""
        if code:
            pos = await self._reconcile_single_code(code)
            await self.session.commit()
            return {"status": "SUCCESS", "reconciled_codes": [code], "positions": [{"code": pos.code, "quantity": pos.quantity, "avg_cost": pos.avg_cost}]}
        
        # 获取所有出现过的股票代码
        stmt = select(TradeRecord.code).distinct()
        codes = list((await self.session.execute(stmt)).scalars().all())
        results = []
        for c in codes:
            pos = await self._reconcile_single_code(c)
            results.append({"code": pos.code, "quantity": pos.quantity, "avg_cost": pos.avg_cost})
        
        await self.session.commit()
        return {"status": "SUCCESS", "reconciled_codes": codes, "positions": results}

    async def purge_simulation_records_from_truth_ledger(self) -> Dict[str, Any]:
        """清除误写入真实交易账本的历史策略模拟流水，恢复真实账户纯净"""
        from sqlalchemy import delete
        stmt_sim_ids = select(TradeRecord.id, TradeRecord.code).where(
            or_(
                TradeRecord.source.in_(["STRATEGY_WORKBENCH", "SIMULATION"]),
                TradeRecord.trade_reason.like("%模拟%"),
                TradeRecord.trade_reason.like("%虚拟跟单%"),
                TradeRecord.idempotency_key.like("sim_%")
            )
        )
        sim_rows = (await self.session.execute(stmt_sim_ids)).all()
        sim_ids = [r[0] for r in sim_rows]
        sim_codes = list(set(r[1] for r in sim_rows))

        if sim_ids:
            await self.session.execute(delete(TradeNote).where(TradeNote.trade_id.in_(sim_ids)))
            await self.session.execute(delete(TradeRecord).where(TradeRecord.id.in_(sim_ids)))
            await self.session.commit()

            for c in sim_codes:
                await self._reconcile_single_code(c)
            await self.session.commit()

        return {"purged_records_count": len(sim_ids), "affected_codes": sim_codes}

    async def search_securities(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """A股标的代码/名称/拼音双向搜索 (支持本地持仓库优先聚合与外部主数据模糊搜索)"""
        if not query or not str(query).strip():
            return []
        q = str(query).strip().lower()

        results = []
        seen_codes = set()

        # 1. 优先从本地 Position 与 TradeRecord 匹配已交易的标的 (毫秒级响应)
        try:
            stmt_pos = select(Position).where(
                or_(Position.code.like(f"%{q}%"), Position.name.like(f"%{q}%"))
            ).limit(limit)
            local_pos = (await self.session.execute(stmt_pos)).scalars().all()
            for p in local_pos:
                if p.code and p.code not in seen_codes:
                    seen_codes.add(p.code)
                    results.append({
                        "code": p.code,
                        "name": p.name or p.code,
                        "pinyin": "",
                        "market": "持仓标的"
                    })
        except Exception:
            pass

        # 2. 从外部标准证券主数据搜索补全
        try:
            ext_res = await self.data_service.search_securities(q, limit=limit)
            if ext_res and ext_res.data:
                for item in ext_res.data:
                    c = item.get("code")
                    if c and c not in seen_codes:
                        seen_codes.add(c)
                        results.append(item)
                        if len(results) >= limit:
                            break
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"外部证券搜索异常: {e}")

        return results[:limit]

    async def get_positions(self, refresh_quote: bool = True) -> List[Dict[str, Any]]:
        """
        获取当前有效持仓列表
        - 联动 Data Layer 抽象 StockQuoteCapability 获取最新行情
        - 明确区分 REALTIME 与 PREV_CLOSE（铁律 9）
        - 行情断流显式标记 UNAVAILABLE，绝不填假数据
        """
        stmt = select(Position).where(Position.quantity > 0)
        positions = list((await self.session.execute(stmt)).scalars().all())

        if refresh_quote and positions:
            codes = [p.code for p in positions]
            try:
                data_result = await self.data_service.get_stock_quotes(codes)
                quote_map = {}
                if data_result and data_result.data:
                    for item in data_result.data:
                        if isinstance(item, dict):
                            if "code" in item:
                                quote_map[item["code"]] = item
                                # 剥离市场前缀作为 key (例如 sh600519 -> 600519)
                                clean_code = str(item["code"]).replace("sh", "").replace("sz", "").replace("bj", "")
                                quote_map[clean_code] = item
                            if "symbol" in item:
                                quote_map[item["symbol"]] = item

                is_live = self._is_market_trading_time()
                for pos in positions:
                    q = quote_map.get(pos.code)
                    if q and q.get("price") and float(q["price"]) > 0:
                        cur_p = round(float(q["price"]), 3)
                        pos.current_price = cur_p
                        # 落实硬约束 4: 严格区分盘中实时与收盘补偿语义
                        pos.price_type = "REALTIME" if is_live else "EOD_COMPENSATED"
                        pos.quote_time = q.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        pos.floating_pnl = round((cur_p - pos.avg_cost) * pos.quantity, 2)
                    else:
                        if pos.current_price is not None:
                            pos.price_type = "EXPIRED"
                        else:
                            pos.price_type = "UNAVAILABLE"
                            pos.floating_pnl = None

                await self.session.commit()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"更新持仓行情异常: {e}")

        results = []
        for p in positions:
            p_dict = {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "quantity": p.quantity,
                "avg_cost": p.avg_cost,
                "total_cost": p.total_cost,
                "current_price": p.current_price,
                "price_type": p.price_type or "UNAVAILABLE",
                "quote_time": p.quote_time,
                "floating_pnl": p.floating_pnl,
                "floating_pnl_pct": round((p.current_price - p.avg_cost) / p.avg_cost * 100, 2) if (p.current_price and p.avg_cost > 0) else None,
                "market_value": round(p.current_price * p.quantity, 2) if p.current_price else None,
                "updated_at": p.updated_at,
            }
            results.append(p_dict)

        return results

    async def get_records(
        self,
        code: Optional[str] = None,
        direction: Optional[str] = None,
        record_type: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """多维查询交易事实流水"""
        stmt = select(TradeRecord)
        filters = []
        if code:
            filters.append(TradeRecord.code == code)
        if direction:
            filters.append(TradeRecord.direction == direction.lower())
        if record_type:
            filters.append(TradeRecord.record_type == record_type.upper())

        # 严格物理隔离：排除所有策略模拟交易流水
        filters.append(TradeRecord.source.notin_(["STRATEGY_WORKBENCH", "SIMULATION"]))
        filters.append(not_(TradeRecord.trade_reason.like("%模拟%")))
        filters.append(not_(TradeRecord.trade_reason.like("%虚拟跟单%")))

        if filters:
            stmt = stmt.where(and_(*filters))

        # 统计总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # 分页
        stmt = stmt.order_by(TradeRecord.trade_time.desc(), TradeRecord.id.desc()).offset((page - 1) * limit).limit(limit)
        records = list((await self.session.execute(stmt)).scalars().all())

        # 关联查询笔记
        rec_ids = [r.id for r in records]
        notes_map = {}
        if rec_ids:
            stmt_notes = select(TradeNote).where(TradeNote.trade_id.in_(rec_ids))
            notes = list((await self.session.execute(stmt_notes)).scalars().all())
            for n in notes:
                notes_map[n.trade_id] = n

        items = []
        for r in records:
            n = notes_map.get(r.id)
            items.append({
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "direction": r.direction,
                "price": r.price,
                "quantity": r.quantity,
                "amount": r.amount,
                "trade_time": r.trade_time,
                "trade_reason": r.trade_reason,
                "source": r.source,
                "record_type": r.record_type,
                "reversed_record_id": r.reversed_record_id,
                "idempotency_key": r.idempotency_key,
                "created_at": r.created_at,
                "note": {
                    "id": n.id,
                    "trade_id": n.trade_id,
                    "date": n.date,
                    "mental_state": n.mental_state,
                    "decision_logic": n.decision_logic,
                    "reflection": n.reflection,
                    "lessons": n.lessons,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at,
                } if n else None,
            })

        return {"items": items, "total": total, "page": page, "limit": limit}

    async def get_record_detail(self, record_id: int) -> Dict[str, Any]:
        """获取单笔交易详情与附带反思笔记"""
        stmt = select(TradeRecord).where(TradeRecord.id == record_id)
        record = (await self.session.execute(stmt)).scalars().first()
        if not record:
            raise HTTPException(status_code=404, detail="交易记录不存在")

        stmt_note = select(TradeNote).where(TradeNote.trade_id == record_id)
        note = (await self.session.execute(stmt_note)).scalars().first()

        return {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "direction": record.direction,
            "price": record.price,
            "quantity": record.quantity,
            "amount": record.amount,
            "trade_time": record.trade_time,
            "trade_reason": record.trade_reason,
            "source": record.source,
            "record_type": record.record_type,
            "reversed_record_id": record.reversed_record_id,
            "created_at": record.created_at,
            "note": {
                "id": note.id,
                "trade_id": note.trade_id,
                "date": note.date,
                "mental_state": note.mental_state,
                "decision_logic": note.decision_logic,
                "reflection": note.reflection,
                "lessons": note.lessons,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
            } if note else None,
        }

    async def add_or_update_note(self, payload: TradeNoteCreate) -> TradeNote:
        """
        提交或增量追加交易复盘反思笔记（1:1强绑定）
        - append_mode=True 自动添加时间戳前缀增量合并
        """
        # 校验 trade_id 是否存在
        stmt_rec = select(TradeRecord).where(TradeRecord.id == payload.trade_id)
        rec = (await self.session.execute(stmt_rec)).scalars().first()
        if not rec:
            raise HTTPException(status_code=404, detail=f"关联的交易记录ID #{payload.trade_id} 不存在")

        stmt = select(TradeNote).where(TradeNote.trade_id == payload.trade_id)
        note = (await self.session.execute(stmt)).scalars().first()

        now_hhmm = datetime.now().strftime("%H:%M")

        if note:
            if payload.append_mode and payload.reflection:
                existing = note.reflection or ""
                note.reflection = f"{existing}\n[{now_hhmm} 追加]: {payload.reflection}".strip()
            elif payload.reflection:
                note.reflection = payload.reflection

            if payload.mental_state:
                note.mental_state = payload.mental_state
            if payload.decision_logic:
                note.decision_logic = payload.decision_logic
            if payload.lessons:
                note.lessons = payload.lessons
            note.date = payload.date
            note.updated_at = func.now()
        else:
            ref_content = f"[{now_hhmm} 初次反思]: {payload.reflection}" if (payload.append_mode and payload.reflection) else payload.reflection
            note = TradeNote(
                trade_id=payload.trade_id,
                date=payload.date,
                mental_state=payload.mental_state,
                decision_logic=payload.decision_logic,
                reflection=ref_content,
                lessons=payload.lessons,
            )
            self.session.add(note)

        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def get_note_by_trade_id(self, trade_id: int) -> Optional[TradeNote]:
        stmt = select(TradeNote).where(TradeNote.trade_id == trade_id)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_stats(self) -> Dict[str, Any]:
        """
        计算严密量化统计指标（落实补丁 1、3）
        - 冲正对 100% 物理隔离，不污染胜率与盈亏
        - 单笔卖出胜率（Closed Leg Win Rate）
        - 未平仓浮动持仓绝不计入胜率样本集
        """
        # 1. 查询全量流水按时间正序回放计算真实平仓盈亏
        stmt = select(TradeRecord).order_by(TradeRecord.trade_time.asc(), TradeRecord.id.asc())
        all_records = list((await self.session.execute(stmt)).scalars().all())

        # 剔除冲正对
        reversal_ids = set()
        for r in all_records:
            if r.record_type == "REVERSAL" and r.reversed_record_id:
                reversal_ids.add(r.reversed_record_id)
                reversal_ids.add(r.id)

        effective_records = [r for r in all_records if r.id not in reversal_ids]

        # 跟踪每个股票在卖出时的成本均价以计算单笔卖出已实现盈亏
        stock_positions: Dict[str, Dict[str, float]] = {}
        closed_sells = []

        for r in effective_records:
            code = r.code
            if code not in stock_positions:
                stock_positions[code] = {"qty": 0, "total_cost": 0.0, "avg_cost": 0.0}
            sp = stock_positions[code]

            if r.direction == "buy":
                sp["qty"] += r.quantity
                sp["total_cost"] += r.amount
                sp["avg_cost"] = round(sp["total_cost"] / sp["qty"], 3) if sp["qty"] > 0 else 0.0
            elif r.direction == "sell":
                sell_qty = r.quantity
                cost_basis = sp["avg_cost"]
                realized_pnl = round((r.price - cost_basis) * sell_qty, 2)
                closed_sells.append({
                    "record_id": r.id,
                    "code": r.code,
                    "sell_price": r.price,
                    "avg_cost": cost_basis,
                    "quantity": sell_qty,
                    "realized_pnl": realized_pnl,
                })
                sp["qty"] = max(0, sp["qty"] - sell_qty)
                if sp["qty"] == 0:
                    sp["total_cost"] = 0.0
                    sp["avg_cost"] = 0.0
                else:
                    sp["total_cost"] = round(sp["qty"] * sp["avg_cost"], 2)

        # 2. 统计指标计算
        closed_count = len(closed_sells)
        win_sells = [s for s in closed_sells if s["realized_pnl"] > 0]
        loss_sells = [s for s in closed_sells if s["realized_pnl"] < 0]

        win_count = len(win_sells)
        loss_count = len(loss_sells)
        total_realized_pnl = round(sum(s["realized_pnl"] for s in closed_sells), 2)

        closed_leg_win_rate = round(win_count / closed_count * 100, 2) if closed_count > 0 else None

        avg_win = (sum(s["realized_pnl"] for s in win_sells) / win_count) if win_count > 0 else 0.0
        avg_loss = (abs(sum(s["realized_pnl"] for s in loss_sells)) / loss_count) if loss_count > 0 else 0.0
        payoff_ratio = round(avg_win / avg_loss, 2) if (avg_win > 0 and avg_loss > 0) else None

        # 3. 统计当前有效持仓市值与浮盈
        positions = await self.get_positions(refresh_quote=False)
        total_market_value = 0.0
        total_floating_pnl = 0.0
        has_unavailable = False

        for p in positions:
            if p.get("market_value") is not None:
                total_market_value += p["market_value"]
            if p.get("floating_pnl") is not None:
                total_floating_pnl += p["floating_pnl"]
            if p.get("price_type") == "UNAVAILABLE":
                has_unavailable = True

        quote_status = "PARTIAL" if has_unavailable and positions else ("UNAVAILABLE" if not positions else "FULL")
        total_pnl = round(total_realized_pnl + (total_floating_pnl if quote_status != "UNAVAILABLE" else 0.0), 2)

        return {
            "total_trades": len(effective_records),
            "closed_trades": closed_count,
            "win_trades": win_count,
            "loss_trades": loss_count,
            "closed_leg_win_rate": closed_leg_win_rate,
            "payoff_ratio": payoff_ratio,
            "total_realized_pnl": total_realized_pnl,
            "total_floating_pnl": round(total_floating_pnl, 2) if positions else 0.0,
            "total_market_value": round(total_market_value, 2) if positions else 0.0,
            "total_pnl": total_pnl,
            "quote_status": quote_status,
        }
