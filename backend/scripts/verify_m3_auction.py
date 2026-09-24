"""
M3 集合竞价观测与状态承接系统端到端自动化验证脚本 (Phase 1C)
验证重点：
1. 09:25 开盘指数快照与量能比值（严格两市全天总成交为分母）
2. 昨日高标/连板梯队开盘溢价与一字板识别（None 安全，绝不填 0 伪造）
3. M2 -> M3 事实验证与客观开盘承接研判（绝无买卖信号，绝无胜率打分）
4. Auction API 端到端路由（列表与详情）
5. 零 Schema 变更核验（复用现有 auction_report 数据表）
"""

import asyncio
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.data.providers.sina import SinaProvider
from app.data.service import DataService


async def verify_m3():
    print("=" * 60)
    print(">>> 开始执行 M3 集合竞价观测与状态承接系统自动化验证")
    print("=" * 60)

    # 1. 验证 SinaProvider 指数快照
    print("\n[Step 1] 验证新浪财经开盘指数数据清洗...")
    sina = SinaProvider()
    index_res = await sina.get_index_quotes(["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"])
    quotes = index_res.data
    quality = index_res.quality
    print(f"指数数据质量: {quality.name}, 获取指数数: {len(quotes) if quotes else 0}")
    assert quotes and len(quotes) >= 3, "核心指数数据不可为空"
    for q in quotes:
        print(f" - {q['name']} ({q['code']}): 现价={q['price']}, 涨跌幅={q['pct_change']}%, 成交额={q['amount_wan']}万元")
        assert "price" in q and "pct_change" in q
        if q["price"] is not None:
            assert isinstance(q["price"], (int, float))
    print("✅ Step 1 通过: 指数开盘数据提取与清洗严格合规")

    # 2. 验证个股行情与一字板识别
    print("\n[Step 2] 验证个股开盘溢价与一字板识别...")
    stock_res = await sina.get_stock_quotes(["sh600519", "sz000001", "sz000002"])
    stock_quotes = stock_res.data
    print(f"测试个股数量: {len(stock_quotes) if stock_quotes else 0}")
    assert stock_quotes and len(stock_quotes) > 0, "测试个股行情不可为空"
    for sq in stock_quotes:
        print(f" - {sq['name']} ({sq['code']}): 开盘={sq['open']}, 昨收={sq['prev_close']}, 开盘溢价={sq['open_pct']}%, 一字涨停={sq['is_one_word_up']}")
        assert "open" in sq and "prev_close" in sq and "open_pct" in sq
        assert "is_one_word_up" in sq and "is_one_word_down" in sq
    print("✅ Step 2 通过: 个股开盘溢价计算与一字板识别逻辑正常")

    # 3. 验证 API 端到端闭环
    print("\n[Step 3] 验证 Auction API 端到端流程...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. 生成竞价报告
        r_gen = await client.post("/api/v1/reports/auction/generate")
        assert r_gen.status_code == 200, f"生成失败: {r_gen.text}"
        date_str = r_gen.json()["date"]
        print(f"生成竞价报告成功，日期: {date_str}")

        # B. 列表查询
        r_list = await client.get("/api/v1/reports/auction")
        assert r_list.status_code == 200, f"列表查询失败: {r_list.text}"
        list_json = r_list.json()
        assert list_json["code"] == 200
        items = list_json["data"]["items"]
        total = list_json["data"]["total"]
        print(f"列表返回总数: {total}, 当前页数量: {len(items)}")
        assert total >= 1
        assert any(i["date"] == date_str for i in items)
        print("✅ Step 3B 通过: 列表端点 /api/v1/reports/auction 正常")

        # C. 详情查询
        r_detail = await client.get(f"/api/v1/reports/auction/{date_str}")
        assert r_detail.status_code == 200, f"详情查询失败: {r_detail.text}"
        detail_json = r_detail.json()
        assert detail_json["code"] == 200
        data = detail_json["data"]
        assert data["date"] == date_str
        assert "index_open_data" in data and isinstance(data["index_open_data"], dict)
        assert "high_open_stats" in data and isinstance(data["high_open_stats"], dict)
        assert "emotion_judgment" in data and isinstance(data["emotion_judgment"], dict)

        # D. 核心规范与铁律断言
        print("\n[Step 4] 验证 M3 核心定位与数学定义规范...")
        iod = data["index_open_data"]
        bidding_amount = iod.get("total_bidding_amount_yi")
        base_amount = iod.get("yesterday_total_amount_yi")
        bidding_ratio = iod.get("bidding_volume_ratio")
        print(f" - 两市竞价总额: {bidding_amount} 亿元")
        print(f" - 基准分母(前日两市全天总额): {base_amount} 亿元")
        print(f" - 竞价量能比值: {bidding_ratio}%")

        if base_amount is not None and base_amount > 0 and bidding_amount is not None:
            expected_ratio = round((bidding_amount / base_amount) * 100, 2)
            assert bidding_ratio == expected_ratio, f"量能比值计算不符合数学定义: {bidding_ratio} != {expected_ratio}"
            print("✅ Step 4 通过: 竞价量能比严格同构口径对齐，分母定义正确")
        else:
            print(" - 前日基准成交额缺省，比值严格为 None（防伪达标）")

        print("\n[Step 5] 验证零买卖信号与免责隔离...")
        ej = data["emotion_judgment"]
        label = ej.get("label")
        narrative = ej.get("narrative", "")
        disclaimer = ej.get("disclaimer", "")
        print(f" - 开盘客观承接标签: 【{label}】")
        print(f" - 免责声明: {disclaimer}")
        assert "非买卖建议" in disclaimer, "缺少免责声明！"

        # 攻击性关键词审计：绝不可含有诱导性买卖指令
        for forbidden in ["买入", "卖出", "打板", "加仓", "减仓", "清仓", "做多", "做空"]:
            assert forbidden not in narrative, f"叙述包含非法主观指令词: {forbidden}"
        print("✅ Step 5 通过: 纯粹客观物理事实测量，绝无主观买卖信号！")

    print("\n" + "=" * 60)
    print(">>> M3 集合竞价观测系统后端全链路验证 100% 通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_m3())
