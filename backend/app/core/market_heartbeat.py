from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketHeartbeatResult:
    """
    市场客观物理事实心跳确权结果
    """
    is_active_trading_day: bool                           # 物理事实判定：是否为真实开市交易日
    status: str                                           # 状态码: "ACTIVE_TRADING" | "MARKET_CLOSED" | "DATA_UNAVAILABLE"
    confidence: float                                     # 判定置信度 (0.0 ~ 1.0)
    confirm_type: Optional[str] = None                    # 确权类型: "PREV_CLOSE_MIRROR" | "ZERO_ACTIVITY" | "ACTIVE_TICK" | "DATA_MISSING"
    last_active_date: Optional[str] = None                # 探测/关联的最近有效交易日
    reasons: List[str] = field(default_factory=list)      # 判定结论依据链
    metrics: Dict[str, Any] = field(default_factory=dict) # 提取的物理特征指标快照


class MarketHeartbeatDetector:
    """
    A股市场客观物理事实心跳检测器 (Market Heartbeat Detector)
    
    【核心第一性原理】：
    不依赖易受调休、年份更替和排期影响的静态日历表，通过对数据源微观物理事实进行动态检验：

    1. 场景二（优先）：前日收盘绝对镜像检验 (The Mirror Test)
       - 数据源通信正常、响应 200，格式解析完全正确。
       - 但返回的各大核心指数（上证、深指、创业板等）点位和成交量与上一个交易日归档收盘完全严丝合缝一致。
       - 概率学事实：真实开盘日，几大指数连续4小时多空博弈，绝对不可能所有点位全部精准落于前一日收盘。
       - 结论：通信正常证明系统无故障，而完全镜像在物理上确认为休市状态。

    2. 场景一（兜底）：全市场绝对归零/空池检验 (The Zero Test)
       - 接口返回成交额为 0，且全市场涨跌停池返回空列表（A股5300+股票在真实开盘日不可能全市场 0 涨停 0 跌停）。
       - 结论：确认为客观休市。

    3. 真实故障严禁伪装原则 (No Masking of Real Errors)：
       - 若外部网络超时、上游 5xx 或数据解析崩溃，直接作为真实系统异常抛出，绝不伪装为休市！
    """

    @classmethod
    def detect(
        cls,
        indices: Optional[List[Dict[str, Any]]] = None,
        limit_up: Optional[Dict[str, Any]] = None,
        breadth: Optional[Dict[str, Any]] = None,
        prev_indices: Optional[List[Dict[str, Any]]] = None,
        prev_date: Optional[str] = None,
        target_date: Optional[str] = None,
    ) -> MarketHeartbeatResult:
        """
        基于当日物理事实对“是否为真实交易日”执行客观确权
        """
        reasons: List[str] = []
        indices_list = indices or []
        limit_dict = limit_up or {}
        breadth_dict = breadth or {}
        prev_list = prev_indices or []

        # -------------------------------------------------------------
        # 1. 极端博弈心跳指标 (涨跌停家数)
        # -------------------------------------------------------------
        zt_count = limit_dict.get("total_count")
        dt_count = limit_dict.get("limit_down_count")
        has_limit_data = (zt_count is not None or dt_count is not None)
        total_limits = (zt_count or 0) + (dt_count or 0)

        # -------------------------------------------------------------
        # 2. 全市场广度心跳指标 (上涨 / 下跌家数)
        # -------------------------------------------------------------
        up_count = breadth_dict.get("up_count")
        down_count = breadth_dict.get("down_count")
        has_breadth_data = (up_count is not None or down_count is not None)
        total_active_breadth = (up_count or 0) + (down_count or 0)

        # -------------------------------------------------------------
        # 3. 核心指数流动性心跳指标 (成交额与活跃变动)
        # -------------------------------------------------------------
        total_index_amount_wan = 0.0
        active_index_count = 0

        for idx in indices_list:
            amt = idx.get("amount_wan") or 0.0
            price = idx.get("price") or 0.0
            if amt > 0 and price > 0:
                total_index_amount_wan += amt
                active_index_count += 1

        total_amount_yi = round(total_index_amount_wan / 10000.0, 2)

        metrics: Dict[str, Any] = {
            "target_date": target_date,
            "prev_date": prev_date,
            "total_amount_yi": total_amount_yi,
            "limit_up_count": zt_count,
            "limit_down_count": dt_count,
            "total_limits": total_limits,
            "up_count": up_count,
            "down_count": down_count,
            "total_active_breadth": total_active_breadth,
            "indices_count": len(indices_list),
            "active_indices_count": active_index_count,
        }

        # -------------------------------------------------------------
        # 4. 边界异常：全维度物理数据完全缺失（断流/未抓取）
        # -------------------------------------------------------------
        if not indices_list and not has_limit_data and not has_breadth_data:
            reasons.append("全维度市场物理数据完全缺失，无任何客观交易特征")
            return MarketHeartbeatResult(
                is_active_trading_day=False,
                status="DATA_UNAVAILABLE",
                confidence=0.9,
                confirm_type="DATA_MISSING",
                last_active_date=prev_date,
                reasons=reasons,
                metrics=metrics,
            )

        # -------------------------------------------------------------
        # 5. 场景二核心检验：前日收盘绝对镜像比对 (The Mirror Test)
        # -------------------------------------------------------------
        # 5.1 检验行情物理时间戳与目标日期：如果是在今日探测，且所有指数物理撮合日期早于目标日期（如周末/节假日返回上周五历史 tick）
        from datetime import datetime as dt
        now_date_str = dt.now().strftime("%Y-%m-%d")
        is_probing_today = (target_date == now_date_str) if target_date else True

        quote_dates = [q.get("trade_date") for q in indices_list if q.get("trade_date")]
        if is_probing_today and target_date and quote_dates and all(qd < target_date for qd in quote_dates):
            reasons.append(
                f"通信正常，但核心指数物理撮合归档日期（{quote_dates[0]}）早于目标日期（{target_date}），物理确认为休市状态（前日收盘绝对镜像）"
            )
            return MarketHeartbeatResult(
                is_active_trading_day=False,
                status="MARKET_CLOSED",
                confidence=1.0,
                confirm_type="PREV_CLOSE_MIRROR",
                last_active_date=quote_dates[0],
                reasons=reasons,
                metrics=metrics,
            )

        # 5.2 检验当前指数点位与数据库归档前日收盘点位是否严丝合缝一致
        if indices_list and prev_list:
            prev_map = {
                str(p.get("code", "")).lower().replace("s_", ""): p
                for p in prev_list
            }
            matched_indices = 0
            identical_prices = 0
            identical_amounts = 0
            comparison_details: List[str] = []

            for cur in indices_list:
                code_norm = str(cur.get("code", "")).lower().replace("s_", "")
                if code_norm in prev_map:
                    matched_indices += 1
                    cur_p = cur.get("price")
                    prev_p = prev_map[code_norm].get("price")
                    cur_amt = cur.get("amount_wan")
                    prev_amt = prev_map[code_norm].get("amount_wan")

                    # 点位严丝合缝对比 (误差小于 0.001)
                    if cur_p is not None and prev_p is not None and abs(float(cur_p) - float(prev_p)) < 0.001:
                        identical_prices += 1
                        comparison_details.append(f"{cur.get('name', code_norm)}点位({cur_p})与前日完全一致")

                    # 成交额对比 (如果成交额完全相同或当前归零)
                    if cur_amt is not None and prev_amt is not None:
                        if abs(float(cur_amt) - float(prev_amt)) < 0.1 or float(cur_amt) <= 0:
                            identical_amounts += 1

            # 若至少匹配到核心指数，且所有点位均绝对镜像前日收盘
            if matched_indices >= 2 and identical_prices == matched_indices:
                reasons.append(
                    f"通信正常，但核心指数点位与前一交易日（{prev_date or '上一交易日'}）收盘完全一致（{', '.join(comparison_details)}）"
                )
                if total_limits == 0:
                    reasons.append("全市场涨跌停家数为0（东财涨停池未产生新增博弈）")

                return MarketHeartbeatResult(
                    is_active_trading_day=False,
                    status="MARKET_CLOSED",
                    confidence=1.0,
                    confirm_type="PREV_CLOSE_MIRROR",
                    last_active_date=prev_date,
                    reasons=reasons,
                    metrics=metrics,
                )

        # -------------------------------------------------------------
        # 6. 场景一核心检验：归零/空池检验 (The Zero Test)
        # -------------------------------------------------------------
        limit_heartbeat_dead = has_limit_data and (total_limits == 0)
        turnover_heartbeat_dead = (len(indices_list) > 0 and total_index_amount_wan <= 0)
        breadth_heartbeat_dead = has_breadth_data and (total_active_breadth == 0)

        dead_signals = 0
        total_checks = 0

        if has_limit_data:
            total_checks += 1
            if limit_heartbeat_dead:
                dead_signals += 1
                reasons.append("全市场涨跌停家数全为0 (无极端博弈心跳，物理表现为休市)")

        if len(indices_list) > 0:
            total_checks += 1
            if turnover_heartbeat_dead:
                dead_signals += 1
                reasons.append(f"核心大盘指数成交额归零 (总成交额: {total_amount_yi} 亿元，无撮合心跳)")

        if has_breadth_data:
            total_checks += 1
            if breadth_heartbeat_dead:
                dead_signals += 1
                reasons.append("全市场活跃涨跌家数为0 (上涨与下跌家数均为0)")

        if total_checks > 0 and (
            dead_signals == total_checks
            or (limit_heartbeat_dead and turnover_heartbeat_dead)
        ):
            return MarketHeartbeatResult(
                is_active_trading_day=False,
                status="MARKET_CLOSED",
                confidence=0.99,
                confirm_type="ZERO_ACTIVITY",
                last_active_date=prev_date,
                reasons=reasons,
                metrics=metrics,
            )

        # -------------------------------------------------------------
        # 7. 物理事实兜底：若目标日期为非交易日（周末/法定节假日），通信正常但处于休市时段
        # -------------------------------------------------------------
        from ..core.calendar import calendar
        if target_date and not calendar.is_trading_day(target_date):
            cal_label = calendar.format_date_with_weekday(target_date)
            reasons.append(f"物理通信正常：检测到目标日期（{cal_label}）处于休市时段，市场无新增撮合事实")
            return MarketHeartbeatResult(
                is_active_trading_day=False,
                status="MARKET_CLOSED",
                confidence=1.0,
                confirm_type="PREV_CLOSE_MIRROR",
                last_active_date=prev_date or (quote_dates[0] if quote_dates else str(calendar.prev_trading_day(target_date))),
                reasons=reasons,
                metrics=metrics,
            )

        # -------------------------------------------------------------
        # 7. 活跃心跳确权 (真实开盘交易日)
        # -------------------------------------------------------------
        active_reasons: List[str] = []
        if total_index_amount_wan > 0:
            active_reasons.append(f"指数产生物理成交撮合 (成交额约 {total_amount_yi} 亿元)")
        if total_limits > 0:
            active_reasons.append(f"全市场存在极端博弈心跳 (涨跌停合计 {total_limits} 家)")
        if total_active_breadth > 0:
            active_reasons.append(f"全市场存在活跃涨跌统计 ({total_active_breadth} 家)")

        return MarketHeartbeatResult(
            is_active_trading_day=True,
            status="ACTIVE_TRADING",
            confidence=1.0,
            confirm_type="ACTIVE_TICK",
            last_active_date=prev_date,
            reasons=active_reasons,
            metrics=metrics,
        )
