import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_factory
from app.services.daily_review import DailyReviewService
from app.models.report import DailyReview
from app.models.cognition import CognitionMarketState
from sqlalchemy import select

async def run_red_team_attacks():
    print("=" * 80)
    print("      [RED TEAM ATTACK ENGINE] 启动 G5-Phase 1A.3 破坏性攻击与压力测试")
    print("=" * 80)

    transport = ASGITransport(app=app)
    results = {}

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # =====================================================================
        # 攻击 1：分页与非法查询参数攻击 (GET /api/v1/reports/daily-review)
        # =====================================================================
        print("\n>>> [ATTACK 1] 分页边界与异常参数渗透...")
        r_neg = await client.get("/api/v1/reports/daily-review?limit=-10&offset=-5")
        print(f"  [-] limit=-10, offset=-5 响应状态码: {r_neg.status_code}")
        # 检查是否崩溃
        assert r_neg.status_code in [200, 422], f"异常参数导致未捕获错误: {r_neg.status_code}"

        r_overflow = await client.get("/api/v1/reports/daily-review?limit=999999&offset=999999")
        print(f"  [-] 超大 offset 响应: status={r_overflow.status_code}")
        data_of = r_overflow.json()
        assert data_of["code"] == 200
        assert data_of["data"]["items"] == []
        print("  [+] 分页超限安全防护通过 (返回空列表)")

        # =====================================================================
        # 攻击 2：不存在的日期与注入攻击 (GET /api/v1/reports/daily-review/{date})
        # =====================================================================
        print("\n>>> [ATTACK 2] 路径参数恶意注入与越界日期攻击...")
        r_404 = await client.get("/api/v1/reports/daily-review/1970-01-01")
        assert r_404.status_code == 404, f"期望404，实际: {r_404.status_code}"
        print("  [+] 不存在日期正确返回 404 Not Found")

        r_inject = await client.get("/api/v1/reports/daily-review/test'OR'1'='1")
        assert r_inject.status_code in [404, 400], f"SQL注入测试状态码异常: {r_inject.status_code}"
        print("  [+] SQL注入试探安全拦截 (404/400)")

        # =====================================================================
        # 攻击 3：历史老数据缺失 market_state 场景 (兼容性与空字段韧性攻击)
        # =====================================================================
        print("\n>>> [ATTACK 3] 历史遗留脏数据注入攻击（模拟 report_content 无 market_state、market_state_id 为空）...")
        async with async_session_factory() as session:
            dirty_date = "2020-01-01"
            # 检查是否已存在
            stmt = select(DailyReview).where(DailyReview.date == dirty_date)
            dirty_rec = (await session.execute(stmt)).scalars().first()
            if not dirty_rec:
                dirty_rec = DailyReview(
                    date=dirty_date,
                    market_overview=None,
                    limit_up_analysis=None,
                    market_state_id=None,
                    report_content=json.dumps({"title": "老数据测试"}, ensure_ascii=False),
                    data_quality=None
                )
                session.add(dirty_rec)
                await session.commit()

        # 请求这个脏数据详情
        r_dirty = await client.get(f"/api/v1/reports/daily-review/{dirty_date}")
        assert r_dirty.status_code == 200, f"脏数据导致接口崩溃: {r_dirty.status_code}"
        dirty_resp = r_dirty.json()
        assert dirty_resp["code"] == 200
        dirty_data = dirty_resp["data"]
        print(f"  [-] 脏数据响应: market_state={dirty_data.get('market_state')}, overview={dirty_data.get('market_overview')}, quality={dirty_data.get('data_quality')}")
        # 验证零填充防伪：market_state 缺失时绝不能伪造出假的分数！
        assert dirty_data.get("market_state") is None, "铁律违背：脏数据不应无中生有产生 market_state！"
        print("  [+] 脏数据下 market_state 保持为 None，无假数据伪造！")

        # 检查列表接口在面对 data_quality=None 时的表现
        r_list_dirty = await client.get("/api/v1/reports/daily-review?limit=50")
        list_json = r_list_dirty.json()
        dirty_item = next((it for it in list_json["data"]["items"] if it["date"] == dirty_date), None)
        assert dirty_item is not None
        print(f"  [-] 脏数据列表项: state_label='{dirty_item['state_label']}', quality='{dirty_item['data_quality']}', score={dirty_item['composite_score']}")
        assert dirty_item["composite_score"] is None, "铁律违背：老旧脏数据 composite_score 绝不能填 0！"

        # =====================================================================
        # 攻击 4：极端市场场景白盒攻击（涨跌停潮、全市场停牌、分母为0压力测试）
        # =====================================================================
        print("\n>>> [ATTACK 4] 认知状态机极端边界数学与逻辑攻击...")
        from app.cognition.market_state import market_state_computer
        from app.cognition.interfaces import CognitionInput

        # 场景 4.1：全市场跌停极端踩踏（上涨家数=0，下跌家数=5000，涨停=0，跌停=3000，空间板=0）
        print("  [-] 场景 4.1：全市场跌停极端踩踏...")
        stampede_input = CognitionInput(
            market_data={
                "indices": [
                    {"code": "sh000001", "name": "上证指数", "price": "2800", "pct_change": "-9.99", "amount_wan": "10000000"},
                    {"code": "sz399001", "name": "深证成指", "price": "8500", "pct_change": "-10.00", "amount_wan": "15000000"},
                    {"code": "sz399006", "name": "创业板指", "price": "1600", "pct_change": "-19.99", "amount_wan": "5000000"},
                    {"code": "sh000688", "name": "科创50", "price": "700", "pct_change": "-19.99", "amount_wan": "3000000"}
                ],
                "limit_up": {
                    "total_count": 0,
                    "limit_down_count": 3000,
                    "max_height": 0,
                    "broken_limit_ratio": 0.0,
                    "continued_count": 0
                },
                "breadth": {
                    "up_count": 0,
                    "down_count": 5000,
                    "flat_count": 0
                },
                "micro_cap": {"pct_change": -10.0},
                "external_risk": {"a50_pct_change": -3.5},
                "high_tier": {"pct_change": -10.0},
                "prev_total_amount": 33000.0,
                "prev_limit_up_count": 50
            }
        )
        res_stampede = await market_state_computer.compute_market_state(stampede_input)
        print(f"  [+] 踩踏场景输出: 综合分={res_stampede.composite_score}, 物理标签='{res_stampede.state_label}', 质量={res_stampede.data_quality}")
        assert res_stampede.composite_score is not None
        assert res_stampede.composite_score < 30, f"极端跌停踩踏下综合分应极低，实际={res_stampede.composite_score}"
        d3_stampede = res_stampede.dimensions["D3"]
        assert d3_stampede.score is None, "铁律违背：踩踏行情下 D3 必须防塌缩 (score is None)"
        assert d3_stampede.sub_domains["speculative_structure"]["score"] is not None
        assert d3_stampede.sub_domains["tail_extremes"]["score"] is not None
        print(f"  [+] D3 独立双子域得分: Sub-A={d3_stampede.sub_domains['speculative_structure']['score']}, Sub-B={d3_stampede.sub_domains['tail_extremes']['score']}")

        # 场景 4.2：全市场断流/全空无数据极端场景
        print("\n  [-] 场景 4.2：数据源全断流（空字典输入）...")
        empty_input = CognitionInput(market_data={})
        res_empty = await market_state_computer.compute_market_state(empty_input)
        print(f"  [+] 空输入输出: 综合分={res_empty.composite_score}, 标签='{res_empty.state_label}', 质量={res_empty.data_quality}")
        assert res_empty.composite_score is None, "铁律违背：空数据下综合分必须为 None！绝不可填 0！"
        assert res_empty.data_quality.value in ["partial", "invalid"], f"空数据下质量应降级: {res_empty.data_quality}"
        print("  [+] 零填充防伪抗击穿测试通过 (综合分依法置空)")

        # 场景 4.3：昨日成交额为0的边界测试 (D6 环比量能除以0防护)
        print("\n  [-] 场景 4.3：昨日成交额为 0 / 负数边界...")
        zero_prev_input = CognitionInput(
            market_data={
                "indices": [
                    {"code": "sh000001", "name": "上证指数", "price": "3000", "pct_change": "0.5", "amount_wan": "1000000"}
                ],
                "prev_total_amount": 0.0
            }
        )
        res_zero_prev = await market_state_computer.compute_market_state(zero_prev_input)
        d6_metrics = res_zero_prev.dimensions["D6"].metrics
        print(f"  [+] D6 metrics: {d6_metrics}")
        assert "amount_change_ratio" not in d6_metrics or d6_metrics.get("amount_change_ratio") is None, "当昨日成交额为0时，不得强行除以0计算变化率"
        print("  [+] 除以 0 防御测试通过")

        print("\n" + "=" * 80)
        print("      [RED TEAM ATTACK ENGINE] 所有后端攻击场景执行完毕！")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(run_red_team_attacks())
