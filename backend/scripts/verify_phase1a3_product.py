import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app

async def verify_phase1a3_product():
    print("=" * 70)
    print("   G5-Phase 1A.3 收盘复盘全链路产品化端到端自动化验收")
    print("=" * 70)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 触发生成复盘报告
        print("\n[1/4] 触发生成每日复盘 (POST /api/v1/reports/daily-review/generate)...")
        r_gen = await client.post("/api/v1/reports/daily-review/generate")
        assert r_gen.status_code == 200, f"生成失败: {r_gen.text}"
        gen_json = r_gen.json()
        assert gen_json["code"] == 200
        rev_date = gen_json["date"]
        print(f"  --> [PASS] 生成成功，复盘日期: {rev_date}")

        # 2. 验证复盘列表接口 (GET /api/v1/reports/daily-review)
        print("\n[2/4] 获取复盘列表 (GET /api/v1/reports/daily-review)...")
        r_list = await client.get("/api/v1/reports/daily-review?limit=10&offset=0")
        assert r_list.status_code == 200, f"列表请求失败: {r_list.text}"
        list_json = r_list.json()
        assert list_json["code"] == 200
        items = list_json["data"]["items"]
        total = list_json["data"]["total"]
        print(f"  --> [PASS] 列表返回正常，记录总数: {total}, 当前返回: {len(items)} 条")
        assert total >= 1, "记录总数应至少为 1"
        first_item = items[0]
        assert "date" in first_item
        assert "state_label" in first_item
        assert "data_quality" in first_item
        print(f"  --> 首条复盘: 日期={first_item['date']}, 物理状态={first_item['state_label']}, 质量={first_item['data_quality']}")

        # 3. 验证复盘详情接口 (GET /api/v1/reports/daily-review/{date})
        print(f"\n[3/4] 获取复盘详情 (GET /api/v1/reports/daily-review/{rev_date})...")
        r_detail = await client.get(f"/api/v1/reports/daily-review/{rev_date}")
        assert r_detail.status_code == 200, f"详情请求失败: {r_detail.text}"
        detail_json = r_detail.json()
        assert detail_json["code"] == 200
        data = detail_json["data"]

        assert data["date"] == rev_date
        assert "market_overview" in data and isinstance(data["market_overview"], list)
        assert "market_state" in data and data["market_state"] is not None

        ms = data["market_state"]
        dims = ms.get("dimensions", {})
        print(f"  --> 全局物理标签: {ms.get('state_label')}, 数据质量: {ms.get('data_quality')}")
        print(f"  --> 包含维度: {list(dims.keys())}")

        # 4. 深度断言 1A.2 / 1A.3 核心军规与契约
        print("\n[4/4] 深度断言六维状态向量与抗塌缩契约...")
        # 4.1 D2 纯粹广度断言
        assert "D2" in dims, "缺失 D2"
        d2 = dims["D2"]
        d2_metrics = d2.get("metrics", {})
        assert "limit_up_count" not in d2_metrics, "铁律违背：D2中严禁出现涨停家数！"
        assert "limit_down_count" not in d2_metrics, "铁律违背：D2中严禁出现跌停家数！"
        assert "broken_limit_ratio" not in d2_metrics, "铁律违背：D2中严禁出现炸板率！"
        print("  --> [PASS] D2 纯粹广度检验通过 (不含涨跌停与炸板)")

        # 4.2 D3 双子域正交断言
        assert "D3" in dims, "缺失 D3"
        d3 = dims["D3"]
        assert d3.get("score") is None, "铁律违背：D3 核心得分必须为 None，严禁标量塌缩！"
        assert "sub_domains" in d3 and d3["sub_domains"] is not None, "D3 必须具备 sub_domains"
        sub_domains = d3["sub_domains"]
        assert "speculative_structure" in sub_domains, "缺失投机高标结构子域 (Sub-A)"
        assert "tail_extremes" in sub_domains, "缺失尾部极端博弈子域 (Sub-B)"
        sub_a = sub_domains["speculative_structure"]
        sub_b = sub_domains["tail_extremes"]
        print(f"  --> [PASS] D3 双子域检验通过: Sub-A 得分={sub_a.get('score')}, Sub-B 得分={sub_b.get('score')}")

        # 4.3 D5 / D6 物理语义与极性断言
        assert "D5" in dims and dims["D5"]["name"] == "外部环境", "D5 名称应为外部环境"
        assert "D6" in dims and dims["D6"]["name"] == "流动性", "D6 名称应为流动性"
        valid_labels = [
            "极弱收缩", "偏弱整理", "平稳中性", "偏强扩散", "极度亢奋", "数据缺失", "INVALID",
            "部分缺失 (双子域独立)", "正交双子域 (无标量塌缩)"
        ]
        for dim_id, dim_obj in dims.items():
            assert "metric_polarity" in dim_obj, f"{dim_id} 缺失极性元数据"
            assert "semantics_desc" in dim_obj, f"{dim_id} 缺失语义描述"
            assert dim_obj["state_label"] in valid_labels, f"非法物理状态标签: {dim_obj['state_label']}"
        print("  --> [PASS] D1~D6 物理极性元数据与客观标签全量合规！")

    print("\n" + "=" * 70)
    print("   G5-Phase 1A.3 端到端产品化验收全部 100% 通过！")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(verify_phase1a3_product())
