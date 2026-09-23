import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cognition.interfaces import CognitionInput
from app.cognition.config import get_default_market_state_v1_config
from app.cognition.market_state import MarketStateComputer
from app.data.capabilities import DataQuality

def build_full_mock_market_data():
    return {
        "indices": [
            {"code": "sh000001", "name": "上证指数", "price": 3050.0, "pct_change": 0.85, "amount_wan": 45000000.0},
            {"code": "sz399001", "name": "深证成指", "price": 9800.0, "pct_change": 1.10, "amount_wan": 55000000.0},
            {"code": "sz399006", "name": "创业板指", "price": 1920.0, "pct_change": 1.45, "amount_wan": 15000000.0},
            {"code": "sh000688", "name": "科创50", "price": 850.0, "pct_change": 2.10, "amount_wan": 8000000.0},
        ],
        "limit_up": {
            "total_count": 55,
            "max_height": 5,
            "continued_count": 18,
            "limit_down_count": 2,
            "broken_limit_ratio": 0.18
        },
        "breadth": {
            "up_count": 3400,
            "down_count": 1500,
            "flat_count": 200
        },
        "micro_cap": {
            "pct_change": 1.30
        },
        "external_risk": {
            "a50_pct_change": 0.45,
            "a50_long_short_indicator": None # 允许为 None
        },
        "prev_total_amount": 11500.0,
        "prev_limit_up_count": 48
    }

async def run_m14_unit_tests():
    print("=== 开始 M1.4 V1 分层市场状态算法单元测试 ===")
    config = get_default_market_state_v1_config()
    computer = MarketStateComputer(config)

    # -------------------------------------------------------------
    # 测试用例 1: 正常完整输入 -> 质量应当为 FULL 或 PARTIAL (因为 a50多空为None)
    # -------------------------------------------------------------
    data_full = build_full_mock_market_data()
    res1 = await computer.compute_market_state(CognitionInput(market_data=data_full))
    print(f"[用例 1] 完整输入 - 全局质量: {res1.data_quality}, 综合得分: {res1.composite_score}, 标签: {res1.state_label}")
    assert res1.composite_score is not None
    assert 0.0 <= res1.composite_score <= 100.0
    assert "D1" in res1.dimensions
    assert "D2" in res1.dimensions
    assert "D3" in res1.dimensions
    # 验证 1A.2 架构铁律：D3 杜绝标量塌缩（score为None），且具备独立双子域
    assert res1.dimensions["D3"].score is None, "铁律：D3不得进行标量塌缩，score必须为None"
    assert "speculative_structure" in res1.dimensions["D3"].sub_domains
    assert "tail_extremes" in res1.dimensions["D3"].sub_domains
    assert res1.dimensions["D3"].sub_domains["tail_extremes"]["metrics"]["broken_limit_ratio"]["raw"] == 0.18
    assert res1.dimensions["D3"].metrics.get("broken_limit_ratio") == 0.18
    print("  [OK] 用例 1 通过：各子维度正常打分与双子域结构符合预期")

    # -------------------------------------------------------------
    # 测试用例 2: 关键维度缺失 (例如 D1 市场整体全部指数缺失) -> INVALID 铁律测试
    # -------------------------------------------------------------
    data_missing_d1 = build_full_mock_market_data()
    data_missing_d1["indices"] = [] # 抽空核心指数行情
    res2 = await computer.compute_market_state(CognitionInput(market_data=data_missing_d1))
    print(f"[用例 2] 核心指数缺失 - 全局质量: {res2.data_quality}, 综合得分: {res2.composite_score}, 标签: {res2.state_label}")
    assert res2.data_quality == DataQuality.INVALID
    assert res2.composite_score is None, "铁律：INVALID 状态下 composite_score 必须强制为 None，绝不用默认值伪造！"
    assert res2.state_label == "UNAVAILABLE_DUE_TO_DATA_QUALITY"
    print("  [OK] 用例 2 通过：关键维度缺失时严格输出 INVALID 且 composite_score=null，零填充防伪有效！")

    # -------------------------------------------------------------
    # 测试用例 3: 非关键维度缺失 (D4 微盘股缺失) -> PARTIAL 动态重归一化测试
    # -------------------------------------------------------------
    data_missing_d4 = build_full_mock_market_data()
    data_missing_d4["micro_cap"] = {} # 缺失微盘数据
    res3 = await computer.compute_market_state(CognitionInput(market_data=data_missing_d4))
    print(f"[用例 3] 微盘股缺失 - 全局质量: {res3.data_quality}, 综合得分: {res3.composite_score}, 缺失项: {res3.missing_metrics}")
    assert res3.data_quality == DataQuality.PARTIAL
    assert res3.composite_score is not None
    assert "micro_cap_pct_change" in res3.missing_metrics
    print("  [OK] 用例 3 通过：非关键维度缺失时正确降级为 PARTIAL 并重归一化计算")

    # -------------------------------------------------------------
    # 测试用例 4: 动态将 D5(外部风险) 配置为关键维度 -> 若 A50 缺失立即判定 INVALID
    # 验证用户的核心原则：“关键维度/关键指标由配置和业务场景定义，而不是永久硬编码”
    # -------------------------------------------------------------
    custom_config = get_default_market_state_v1_config()
    for d in custom_config.dimensions:
        if d.dimension_id == "D5":
            d.is_critical_dimension = True # 动态提升为关键维度
            for m in d.metrics:
                if m.name == "a50_pct_change":
                    m.quality_rule = "critical" # 设为关键指标

    strict_computer = MarketStateComputer(custom_config)
    data_missing_a50 = build_full_mock_market_data()
    data_missing_a50["external_risk"] = {} # 缺失 A50
    res4 = await strict_computer.compute_market_state(CognitionInput(market_data=data_missing_a50))
    print(f"[用例 4] 动态将D5提升为关键维度后A50缺失 - 全局质量: {res4.data_quality}, 得分: {res4.composite_score}")
    assert res4.data_quality == DataQuality.INVALID
    assert res4.composite_score is None
    print("  [OK] 用例 4 通过：关键维度与指标完全支持配置化动态定义，未永久硬编码！")

    print("\n>>> M1.4 V1 全部 4 项核心测试全绿通过！ <<<")

if __name__ == "__main__":
    asyncio.run(run_m14_unit_tests())
