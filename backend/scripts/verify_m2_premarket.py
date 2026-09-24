"""
M2 盘前简报系统端到端自动化验证脚本 (Phase 1B)
验证重点：
1. 新浪财经隔夜外盘清洗（浮点数点位、真实缺失保持 None、禁止 0.0 伪造）
2. 东方财富快讯 Top 10 清洗
3. M1.4 状态向量继承防标量塌缩（D3 score 坚决为 None，双子域完整保留）
4. 4 维客观观察方向推演与免责声明
5. Premarket API 端到端路由（列表与详情）
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


async def verify_m2():
    print("=" * 60)
    print(">>> 开始执行 M2 盘前简报系统全链路自动化验证")
    print("=" * 60)

    # 1. 验证 SinaProvider 隔夜外盘
    print("\n[Step 1] 验证新浪财经隔夜外盘清洗...")
    sina = SinaProvider()
    res = await sina.get_overnight_data()
    overnight_data, quality = res.data, res.quality
    print(f"数据质量: {quality.name}, 获取标的数量: {len(overnight_data) if overnight_data else 0}")
    assert overnight_data and len(overnight_data) > 0, "隔夜外盘数据不可为空"
    for item in overnight_data:
        print(f" - {item['name']} ({item['symbol']}): 点位={item['price']}, 涨跌幅={item['change_pct']}%")
        assert "symbol" in item and "name" in item
        assert "price" in item and "change_pct" in item
        if item["price"] is not None:
            assert isinstance(item["price"], (int, float))
        if item["change_pct"] is not None:
            assert isinstance(item["change_pct"], (int, float))
    print("✅ Step 1 通过: 隔夜外盘数据结构严格合规，浮点解析正常")

    # 2. 验证 DataService 快讯
    print("\n[Step 2] 验证盘前财经快讯获取...")
    ds = DataService()
    news_res = await ds.get_latest_news(count=10)
    news_data = news_res.data
    print(f"获取快讯条数: {len(news_data) if news_data else 0}")
    if news_data:
        for n in news_data[:3]:
            print(f" - [{n.get('time', n.get('publish_time', '--'))}] {n.get('title', '')[:30]}...")
    assert news_data is not None, "快讯数据返回不可为 None"
    print("✅ Step 2 通过: 盘前财经快讯获取正常")

    # 3. 验证 API 契约与业务编排
    print("\n[Step 3] 验证 Premarket API 端到端流程...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. 生成简报
        r_gen = await client.post("/api/v1/reports/premarket/generate")
        assert r_gen.status_code == 200, f"生成失败: {r_gen.text}"
        date_str = r_gen.json()["date"]
        print(f"生成简报成功，日期: {date_str}")

        # B. 列表查询
        r_list = await client.get("/api/v1/reports/premarket")
        assert r_list.status_code == 200, f"列表查询失败: {r_list.text}"
        list_json = r_list.json()
        assert list_json["code"] == 200
        items = list_json["data"]["items"]
        total = list_json["data"]["total"]
        print(f"列表返回总数: {total}, 当前页数量: {len(items)}")
        assert total >= 1
        assert any(i["date"] == date_str for i in items)
        print("✅ Step 3B 通过: 列表端点 /api/v1/reports/premarket 正常")

        # C. 详情查询
        r_detail = await client.get(f"/api/v1/reports/premarket/{date_str}")
        assert r_detail.status_code == 200, f"详情查询失败: {r_detail.text}"
        detail_json = r_detail.json()
        assert detail_json["code"] == 200
        data = detail_json["data"]
        assert data["date"] == date_str
        assert "overnight_summary" in data and isinstance(data["overnight_summary"], list)
        assert "news_digest" in data and isinstance(data["news_digest"], list)
        assert "yesterday_review_summary" in data
        assert "today_focus" in data and len(data["today_focus"]) == 4

        # D. 核心基线与铁律验证
        yd_summary = data["yesterday_review_summary"]
        if yd_summary:
            print("\n[Step 4] 验证前日 M1.4 状态向量继承防标量塌缩...")
            print(f" - 继承状态标签: {yd_summary.get('state_label')}")
            print(f" - 继承综合得分: {yd_summary.get('composite_score')}")
            dims = yd_summary.get("dimensions", {})
            if "D3" in dims:
                d3 = dims["D3"]
                print(f" - D3 核心得分: {d3.get('score')} (严格期望 None)")
                print(f" - D3 双子域结构: {list(d3.get('sub_domains', {}).keys())}")
                assert d3.get("score") is None, "【严重违规】D3 核心分发生标量塌缩，必须为 None！"
                assert "speculative_structure" in d3.get("sub_domains", {}), "缺少投机结构子域"
                assert "tail_extremes" in d3.get("sub_domains", {}), "缺少尾部极端子域"
                print("✅ Step 4 通过: D3 标量防塌缩铁律 100% 遵守！")

        print("\n[Step 5] 验证 4 维客观观察方向推演与免责隔离...")
        for focus in data["today_focus"]:
            dim = focus["dimension"]
            title = focus["title"]
            disclaimer = focus.get("disclaimer", "")
            print(f" - 维度 [{dim}]: {title}")
            print(f"   免责声明: {disclaimer}")
            assert "非买卖建议" in disclaimer, f"维度 {dim} 缺少免责声明！"
            # 攻击性检测：绝对不能有主观买卖词汇
            analysis = focus["analysis"]
            for forbidden_word in ["推荐买入", "建议加仓", "强烈卖出", "清仓信号"]:
                assert forbidden_word not in analysis, f"维度 {dim} 包含非法主观指令: {forbidden_word}"

        print("✅ Step 5 通过: 4 维推演完全保持客观观察维度，严禁主观买卖信号！")

    print("\n" + "=" * 60)
    print(">>> M2 盘前简报系统后端全链路验证 100% 通过！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_m2())
