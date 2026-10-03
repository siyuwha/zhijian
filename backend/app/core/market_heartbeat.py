from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class MarketHeartbeatResult:
    """
    市场物理事实心跳确权结果
    """
    is_active_trading_day: bool                           # 物理事实判定：是否为真实开市交易日
    confidence: float                                     # 判定置信度 (0.0 ~ 1.0)
    reasons: List[str] = field(default_factory=list)      # 判定结论依据链
    metrics: Dict[str, Any] = field(default_factory=dict) # 提取的物理特征指标快照


class MarketHeartbeatDetector:
    """
    A股市场客观物理事实心跳检测器 (Market Heartbeat Detector)
    
    【核心第一性原理】：
    1. 极端博弈心跳 (Limit Extremes Heartbeat)：
       - A股全市场 5300+ 只标的中，在真实开盘的交易日，极端博弈绝对存在。
       - 全市场「涨停家数 == 0 且 跌停家数 == 0」在实际交易日概率几乎为 0。
       - 若涨跌停双双归零，物理事实表征为休市。
    2. 指数撮合与流动性心跳 (Index Turnover & Movement Heartbeat)：
       - 核心大盘指数（上证、深证、创业板、科创50）在开市交易日必有微观撮合，成交额必大于 0。
       - 若各大指数成交额为 0，或价格点位无任何撮合变动，表征无物理开市。
    3. 全市场广度心跳 (Market Breadth Heartbeat)：
       - 真实交易日全市场上涨家数与下跌家数之和绝不会为 0。
    """

    @classmethod
    def detect(
        cls,
        indices: Optional[List[Dict[str, Any]]] = None,
        limit_up: Optional[Dict[str, Any]] = None,
        breadth: Optional[Dict[str, Any]] = None,
        target_date: Optional[str] = None,
    ) -> MarketHeartbeatResult:
        """
        基于当日收盘物理事实对“是否为真实交易日”执行双轨确权
        """
        reasons: List[str] = []
        indices_list = indices or []
        limit_dict = limit_up or {}
        breadth_dict = breadth or {}

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
                confidence=0.9,
                reasons=reasons,
                metrics=metrics,
            )

        # -------------------------------------------------------------
        # 5. 归零死亡信号统计
        # -------------------------------------------------------------
        # 规则 1：极端博弈归零（有涨跌停接口，但涨停=0且跌停=0）
        limit_heartbeat_dead = has_limit_data and (total_limits == 0)

        # 规则 2：大盘成交归零（有指数接口，但各大指数成交总额为 0）
        turnover_heartbeat_dead = (len(indices_list) > 0 and total_index_amount_wan <= 0)

        # 规则 3：全市场广度归零（有广度接口，但上涨数=0且下跌数=0）
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

        # -------------------------------------------------------------
        # 6. 终局裁决：若存在有效观测且死亡特征集中成立，判定为休市
        # -------------------------------------------------------------
        if total_checks > 0 and (
            dead_signals == total_checks
            or (limit_heartbeat_dead and turnover_heartbeat_dead)
        ):
            return MarketHeartbeatResult(
                is_active_trading_day=False,
                confidence=0.99,
                reasons=reasons,
                metrics=metrics,
            )

        # -------------------------------------------------------------
        # 7. 活跃心跳确权
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
            confidence=1.0,
            reasons=active_reasons,
            metrics=metrics,
        )
