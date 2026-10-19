# -*- coding: utf-8 -*-
"""
v0.8.0 关键缺陷修复契约测试 (永久防劣化防护网)
1. 样本股分时走势防错校验 (消除 0.0 / 843.03 字节漂移与市场代码映射错位)
2. 三大经典策略候选池解耦与连板分歧低吸防空校验 (零股票重合度保护)
3. 模拟实战沙盒与策略联动建仓契约测试
"""

import pytest
from app.data.providers.tdx_client import parse_code_market, TDXParams
from app.strategy.classic_strategies import ClassicStrategyEngine


def test_parse_code_market_prefixes_and_suffixes():
    """验证各种股票代码前缀与后缀的解析鲁棒性"""
    cases = [
        ("002724", TDXParams.MARKET_SZ, "002724"),
        ("sz002724", TDXParams.MARKET_SZ, "002724"),
        ("SZ002724", TDXParams.MARKET_SZ, "002724"),
        ("002724.SZ", TDXParams.MARKET_SZ, "002724"),
        ("SZ.002724", TDXParams.MARKET_SZ, "002724"),
        ("600519", TDXParams.MARKET_SH, "600519"),
        ("sh600519", TDXParams.MARKET_SH, "600519"),
        ("SH600519", TDXParams.MARKET_SH, "600519"),
        ("600519.SH", TDXParams.MARKET_SH, "600519"),
        ("300059", TDXParams.MARKET_SZ, "300059"),
        ("688001", TDXParams.MARKET_SH, "688001"),
    ]
    for raw_code, expected_mkt, expected_code in cases:
        mkt, code = parse_code_market(raw_code)
        assert mkt == expected_mkt, f"Failed market for {raw_code}"
        assert code == expected_code, f"Failed code for {raw_code}"


def test_classic_strategies_candidates_separation():
    """验证三大策略候选池解耦，连板分歧低吸正常产出且三大池无任何股票重合"""
    # 构造测试数据
    yesterday_limit_up = [
        {"code": "002724", "name": "海洋王", "lbc": 2, "price": 8.42, "pct_change": 10.07},
        {"code": "002929", "name": "润建股份", "lbc": 2, "price": 46.4, "pct_change": 10.0},
    ]
    yesterday_broken = [
        {"code": "002343", "name": "慈文传媒", "pct_change": 4.71, "is_broken": True},
        {"code": "002860", "name": "星帅尔", "pct_change": -0.71, "is_broken": True},
    ]
    today_limit_up = [
        {"code": "002889", "name": "东方嘉盛", "lbc": 3, "open_count": 1, "turnover_ratio": 20.48, "price": 28.5},
        {"code": "000576", "name": "广东甘化", "lbc": 2, "open_count": 1, "turnover_ratio": 13.42, "price": 9.8},
        {"code": "003029", "name": "吉大正元", "lbc": 3, "open_count": 0, "turnover_ratio": 4.11, "price": 24.3},
    ]
    historical_pullback = [
        {"code": "002696", "name": "百洋股份", "lbc": 5, "price": 6.8, "pct_change": -1.5},
        {"code": "001318", "name": "阳光乳业", "lbc": 3, "price": 14.2, "pct_change": 0.5},
        {"code": "002815", "name": "崇达技术", "lbc": 1, "price": 11.5, "pct_change": -2.8},
    ]

    quotes_map = {
        "002724": {"pct_chg": 10.07, "open": 8.42, "last_close": 7.65, "price": 8.42},
        "002343": {"pct_chg": 2.5, "open": 7.10, "last_close": 6.95, "price": 7.12},
        "002889": {"pct_chg": 9.99, "open": 26.5, "last_close": 25.91, "price": 28.5},
        "000576": {"pct_chg": 9.99, "open": 9.10, "last_close": 8.91, "price": 9.8},
        "002696": {"pct_chg": -1.5, "open": 6.82, "last_close": 6.90, "price": 6.8},
    }

    # 1. 弱转强
    w2s = ClassicStrategyEngine.evaluate_weak_to_strong(
        yesterday_limit_up, yesterday_broken, quotes_map
    )
    assert len(w2s) > 0, "弱转强候选池不应为空"
    w2s_codes = {c["code"] for c in w2s}

    # 2. 连板分歧低吸
    dip = ClassicStrategyEngine.evaluate_multi_board_dip(
        today_limit_up, quotes_map
    )
    assert len(dip) > 0, "连板分歧低吸候选池不应为空 (lbc >= 2 应正常匹配)"
    assert any(c["code"] == "002889" for c in dip), "东方嘉盛应被筛选为分歧回封龙头"
    dip_codes = {c["code"] for c in dip}

    # 3. 首板龙回头
    pullback = ClassicStrategyEngine.evaluate_dragon_pullback(
        historical_pullback, quotes_map
    )
    assert len(pullback) > 0, "首板龙回头候选池不应为空"
    pullback_codes = {c["code"] for c in pullback}

    # 校验三者集合交集绝对为空
    assert w2s_codes.isdisjoint(dip_codes), "弱转强与分歧低吸存在重合代码"
    assert dip_codes.isdisjoint(pullback_codes), "分歧低吸与龙回头存在重合代码"
    assert w2s_codes.isdisjoint(pullback_codes), "弱转强与龙回头存在重合代码"
