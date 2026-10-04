"""
Canonical Fact Data Models and Identifiers
==========================================
Wave 1 事实底盘扩容：规范化事实契约与幂等身份指纹
严格执行：
1. 确定性无碰撞 canonical_fact_id (幂等落库防账本膨胀)
2. 显式 provenance 标记 (DERIVED_COMMERCIAL_MATCH)
3. 严格纠偏科创板 s=5 (STAR)
4. 12 规则代码严肃映射
"""

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


# 交易所严重异常波动 12 规则代码字典（沪深北交易所交易规则标准）
ANOMALY_RULES: Dict[int, str] = {
    1: "主板连续10个交易日内4次出现同向异常波动",
    2: "创业板连续10个交易日内3次出现同向异常波动",
    3: "科创板连续10个交易日内3次出现同向异常波动",
    4: "连续十个交易日内日收盘价涨跌幅偏离值累计达到+100%",
    5: "连续十个交易日内日收盘价涨跌幅偏离值累计达到-50%",
    6: "连续三十个交易日内日收盘价涨跌幅偏离值累计达到+200%",
    7: "连续三十个交易日内日收盘价涨跌幅偏离值累计达到-70%",
    8: "北交所连续10个交易日内3次出现同向异常波动",
    40: "连续十个交易日内日收盘价涨跌幅偏离值累计达到+150%",
    50: "连续十个交易日内日收盘价涨跌幅偏离值累计达到-60%",
    60: "连续30个交易日内日收盘价涨跌幅偏离值累计达到+300%",
    70: "连续30个交易日内日收盘价涨跌幅偏离值累计达到-75%",
}


@dataclass(frozen=True)
class MarketAnomalyFact:
    """
    交易所规则异动事实 (规范化 Canonical Fact)
    """
    canonical_fact_id: str
    trade_date: str
    symbol: str
    name: str
    exchange: str            # "SH", "SZ", "BJ"
    board_type: str          # "MAIN", "GEM", "STAR", "BSE"
    rule_id: int
    rule_name: str
    deviation_pct: Optional[float] = None
    window_days: Optional[int] = None
    day_change_pct: Optional[float] = None
    status_flag: int = 0     # 0=已发生, 1=已公告, 2=监控中
    provenance: str = "EASTMONEY_COMPUTED_RULE_MATCH"
    provenance_tier: str = "DERIVED_COMMERCIAL_MATCH"

    @classmethod
    def create(
        cls,
        trade_date: str,
        symbol: str,
        name: str,
        exchange: str,
        board_type: str,
        rule_id: int,
        deviation_pct: Optional[float] = None,
        window_days: Optional[int] = None,
        day_change_pct: Optional[float] = None,
        status_flag: int = 0,
    ) -> "MarketAnomalyFact":
        # 严格生成幂等唯一身份指纹
        clean_date = trade_date.replace("-", "")
        # 格式化日期确保 YYYY-MM-DD
        if len(clean_date) == 8:
            formatted_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}"
        else:
            formatted_date = trade_date

        fact_id = f"ANOM:{formatted_date}:{symbol}:R{rule_id}"
        rule_name = ANOMALY_RULES.get(rule_id, f"未知规则码 {rule_id}")

        return cls(
            canonical_fact_id=fact_id,
            trade_date=formatted_date,
            symbol=symbol,
            name=name,
            exchange=exchange,
            board_type=board_type,
            rule_id=rule_id,
            rule_name=rule_name,
            deviation_pct=deviation_pct,
            window_days=window_days,
            day_change_pct=day_change_pct,
            status_flag=status_flag,
            provenance="EASTMONEY_COMPUTED_RULE_MATCH",
            provenance_tier="DERIVED_COMMERCIAL_MATCH",
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlockMappingFact:
    """
    个股板块关系映射事实 (规范化 Canonical Fact)
    """
    canonical_fact_id: str
    symbol: str
    block_code: str
    block_name: str
    category: str            # "INDUSTRY", "CONCEPT", "REGION"
    block_change_pct: Optional[float] = None
    leader_name: Optional[str] = None
    leader_symbol: Optional[str] = None
    provenance: str = "EASTMONEY_SLIST_MAPPING"
    provenance_tier: str = "COMMERCIAL_RELATION_MAPPING"

    @classmethod
    def create(
        cls,
        symbol: str,
        block_code: str,
        block_name: str,
        category: str,
        block_change_pct: Optional[float] = None,
        leader_name: Optional[str] = None,
        leader_symbol: Optional[str] = None,
    ) -> "BlockMappingFact":
        fact_id = f"BLOCK_MAP:{symbol}:{block_code}"
        return cls(
            canonical_fact_id=fact_id,
            symbol=symbol,
            block_code=block_code,
            block_name=block_name,
            category=category,
            block_change_pct=block_change_pct,
            leader_name=leader_name,
            leader_symbol=leader_symbol,
            provenance="EASTMONEY_SLIST_MAPPING",
            provenance_tier="COMMERCIAL_RELATION_MAPPING",
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
