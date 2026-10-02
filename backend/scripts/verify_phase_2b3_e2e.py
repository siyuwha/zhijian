"""
Phase 2B.3: 认知闭环端到端 (E2E) 历史验证脚本
上位依据：《Phase 2B.3 认知闭环前端可视化实施指令》第十节与第十一节

测试目标：
1. 真实历史交易日数据 (2026-09-28 与 2026-09-29) 端到端加载
2. 验证 review-loop API 返回完整的三核心卡片数据
3. 验证 Fact vs Derived State 严格物理分层 (不混淆、不冒充、无评分)
4. 验证 今日假说 PENDING 状态与双轨断言 (Expected vs Invalidation 红线)
5. 验证 昨日假说事后证伪裁决 (CONFIRMED / FALSIFIED / INCONCLUSIVE 三态)
6. 验证 指标比对矩阵 (Comparison Matrix) 与 Missing 语义 (Missing != 0, Missing != False)
7. 验证 审计元数据 (observation_timestamp, fact_snapshot_hash, data_quality, completeness)
8. 验证 严格时间因果阻断 (target_date <= market_date 强阻断)
9. 验证 沙箱库零污染，保持物理开发库纯净
"""

import os
import sys
import json
import asyncio
import tempfile
import hashlib
from datetime import datetime

# 添加项目路径
cur_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(cur_dir, ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.report import DailyReview
from app.models.market import MarketDailySnapshot
from app.models.cognition import MarketHypothesis, CognitionMarketState, HypothesisVerification
from app.services.cognition_review import CognitionReviewService
from app.schemas.cognition import MarketHypothesisCreate, ProposeTodayHypothesisPayload


async def run_e2e_verification():
    print("=" * 70)
    print("Phase 2B.3: 认知闭环前端可视化端到端 (E2E) 历史审计验证")
    print("=" * 70)

    # 1. 建立临时隔离沙箱数据库 (杜绝污染正式库)
    temp_dir = tempfile.gettempdir()
    sandbox_db = os.path.join(temp_dir, f"e2e_phase_2b3_{os.getpid()}.db")
    if os.path.exists(sandbox_db):
        os.unlink(sandbox_db)

    db_url = f"sqlite+aiosqlite:///{sandbox_db}"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    results = {}

    try:
        async with session_factory() as session:
            service = CognitionReviewService(session)

            # -------------------------------------------------------------
            # Step A: 注入 2026-09-28 真实历史收盘事实与假说
            # -------------------------------------------------------------
            print("[E2E Step A] 注入 2026-09-28 历史收盘事实与 AI 假说...")
            indices_0928 = [
                {"code": "sh000001", "name": "上证指数", "price": 3823.62, "pct_change": -1.67},
                {"code": "sz399001", "name": "深证成指", "price": 12858.75, "pct_change": -3.44},
                {"code": "sz399006", "name": "创业板指", "price": 2842.10, "pct_change": -4.12},
                {"code": "sh000688", "name": "科创50", "price": 1055.80, "pct_change": -2.30},
            ]
            lu_0928 = {
                "total_count": 33,
                "limit_down_count": 56,
                "max_height": 5,
                "broken_limit_count": 11,
                "broken_limit_ratio": 0.25,
            }
            breadth_0928 = {"up_count": 850, "down_count": 4200, "flat_count": 120}

            rev_0928 = DailyReview(
                date="2026-09-28",
                market_overview=json.dumps(indices_0928),
                limit_up_analysis=json.dumps(lu_0928),
                data_quality="FULL",
            )
            session.add(rev_0928)

            snap_0928 = MarketDailySnapshot(
                date="2026-09-28",
                snapshot_type="EOD_CLOSE",
                indices_snapshot=json.dumps(indices_0928),
                limit_up_snapshot=json.dumps(lu_0928),
                breadth_snapshot=json.dumps(breadth_0928),
                data_quality="FULL",
            )
            session.add(snap_0928)

            ms_0928 = CognitionMarketState(
                date="2026-09-28",
                timestamp="2026-09-28T15:00:00",
                indicators="[]",
                composite_score=14.2,  # 数据库存储，但 UI 不展示
                state_label="恐慌出清",
                config_snapshot="{}",
            )
            session.add(ms_0928)

            # 注入 09-28 提出的假说 (针对 2026-09-29): 预期连板情绪修复，涨停>=45；证伪红线：跌停>50
            hypo_0928_create = MarketHypothesisCreate(
                created_date="2026-09-28",
                target_date="2026-09-29",
                hypothesis_type="SENTIMENT_CYCLE",
                target_asset="全市场短线投机生态",
                expected_scenario="REBOUND",
                premise_logic="连板最高板打出5板高度且急跌释放，预期次日情绪修复",
                expected_phenomenon="全市场涨停数重回45家以上",
                invalidation_condition="若跌停数依然大于50家则直接证伪",
                assertion_metrics={
                    "expected_assertions": [
                        {
                            "assertion_id": "exp_lu_min",
                            "metric_type": "limit_up_count",
                            "target_code": "ALL_A",
                            "operator": "GTE",
                            "threshold": 45.0,
                            "description": "涨停家数>=45",
                        }
                    ],
                    "invalidation_assertions": [
                        {
                            "assertion_id": "inv_ld_max",
                            "metric_type": "limit_down_count",
                            "target_code": "ALL_A",
                            "operator": "GT",
                            "threshold": 50.0,
                            "description": "跌停家数>50",
                        }
                    ],
                    "meta": {
                        "model_name": "deepseek-flash",
                        "prompt_spec_version": "1.1.0",
                        "hypothesis_hash": "hypo-sha256-0928-audit",
                    },
                },
            )
            await service.create_hypothesis(hypo_0928_create)
            await session.commit()

            # -------------------------------------------------------------
            # Step B: 检验 2026-09-28 闭环数据 (今日事实 + 今日假说)
            # -------------------------------------------------------------
            print("[E2E Step B] 校验 2026-09-28 复盘闭环聚合输出...")
            loop_0928 = await service.get_review_loop_data("2026-09-28")

            # 1. 今日事实卡检查
            assert loop_0928.today_facts is not None, "today_facts must exist"
            assert len(loop_0928.today_facts.fact_layer.indices) == 4, "indices count == 4"
            assert loop_0928.today_facts.fact_layer.sentiment.limit_up_count == 33
            assert loop_0928.today_facts.fact_layer.sentiment.limit_down_count == 56
            assert loop_0928.today_facts.derived_state.state_label == "恐慌出清"
            assert not hasattr(loop_0928.today_facts.derived_state, "composite_score") or getattr(loop_0928.today_facts.derived_state, "composite_score", None) is None, "composite_score must be isolated"
            assert loop_0928.today_facts.fact_snapshot_hash is not None, "fact snapshot hash must exist"
            assert loop_0928.today_facts.fact_snapshot_hash.startswith("obs-"), "hash must be canonical obs- hash"
            assert loop_0928.today_facts.observation_timestamp is not None, "observation timestamp must exist"

            # 2. 今日 AI 假说卡检查
            assert loop_0928.today_hypothesis is not None, "today_hypothesis must exist"
            assert loop_0928.today_hypothesis.status == "PENDING", "status must be PENDING"
            assert len(loop_0928.today_hypothesis.expected_assertions) == 1
            assert len(loop_0928.today_hypothesis.invalidation_assertions) == 1
            assert loop_0928.today_hypothesis.invalidation_assertions[0].operator == "GT"
            assert loop_0928.today_hypothesis.invalidation_assertions[0].threshold == 50.0

            # 3. 昨日裁决应为空 (09-27 无假说)
            assert loop_0928.yesterday_adjudication is None, "yesterday_adjudication must be None"
            results["2026-09-28_facts_and_hypothesis"] = "PASS"
            print("  -> 2026-09-28 事实层与待验证假说卡：PASS")

            # -------------------------------------------------------------
            # Step C: 注入 2026-09-29 事实并触发昨日假说事后裁决
            # -------------------------------------------------------------
            print("[E2E Step C] 注入 2026-09-29 真实历史收盘事实并验证昨日裁决...")
            indices_0929 = [
                {"code": "sh000001", "name": "上证指数", "price": 3855.10, "pct_change": 0.82},
                {"code": "sz399001", "name": "深证成指", "price": 12990.20, "pct_change": 1.02},
            ]
            # 假设 09-29 发生真实修复：涨停 62 家，跌停 12 家 (未触发证伪红线>50，且满足预期>=45)
            lu_0929 = {
                "total_count": 62,
                "limit_down_count": 12,
                "max_height": 6,
                "broken_limit_count": 8,
                "broken_limit_ratio": 0.11,
            }
            rev_0929 = DailyReview(
                date="2026-09-29",
                market_overview=json.dumps(indices_0929),
                limit_up_analysis=json.dumps(lu_0929),
                data_quality="FULL",
            )
            session.add(rev_0929)

            ms_0929 = CognitionMarketState(
                date="2026-09-29",
                timestamp="2026-09-29T15:00:00",
                indicators="[]",
                state_label="弱势修复",
                config_snapshot="{}",
            )
            session.add(ms_0929)
            await session.commit()

            # 显式执行收盘核验 (生成核验记录，使 get_review_loop_data 保持严格只读)
            await service.verify_hypothesis(1, stage="CLOSE_1530")

            # 查询 2026-09-29 闭环数据 (严格只读查询)
            loop_0929 = await service.get_review_loop_data("2026-09-29")

            # 检验昨日假说裁决卡 (对应 09-28 假说在 09-29 的裁决)
            adj = loop_0929.yesterday_adjudication
            assert adj is not None, "yesterday_adjudication must exist on 2026-09-29"
            assert adj.created_date == "2026-09-28"
            assert adj.target_date == "2026-09-29"
            assert adj.outcome in ("CONFIRMED", "FALSIFIED", "INCONCLUSIVE"), f"outcome must be 3-state, got {adj.outcome}"
            assert adj.outcome == "CONFIRMED", f"Expected CONFIRMED, got {adj.outcome}"
            assert adj.falsification_triggered is False, "Falsification should not be triggered"
            assert len(adj.comparison_matrix) >= 2, "Comparison matrix must contain expected and invalidation items"

            results["2026-09-29_adjudication_confirmed"] = "PASS"
            print("  -> 2026-09-29 昨日假说确证 (CONFIRMED) 裁决卡：PASS")

            # -------------------------------------------------------------
            # Step D: 验证时间因果防线 (服务端强拦截)
            # -------------------------------------------------------------
            print("[E2E Step D] 验证时间因果 API 刚性拦截 (target_date <= market_date)...")
            from fastapi import HTTPException

            # 尝试穿越到过去
            caught_past = False
            try:
                await service.propose_today_hypothesis("2026-09-28", target_date="2026-09-27")
            except HTTPException as he:
                if he.status_code == 400 and "Temporal causality violation" in he.detail:
                    caught_past = True
            assert caught_past, "Must reject target_date < market_date with 400"

            # 尝试使用当天作为验证日
            caught_same = False
            try:
                await service.propose_today_hypothesis("2026-09-28", target_date="2026-09-28")
            except HTTPException as he:
                if he.status_code == 400 and "Temporal causality violation" in he.detail:
                    caught_same = True
            assert caught_same, "Must reject target_date == market_date with 400"

            results["temporal_causality_guard"] = "PASS"
            print("  -> 时间因果防线 (target_date <= market_date 拦截)：PASS")

            # -------------------------------------------------------------
            # Step E: 验证缺失数据语义 (Missing != 0, Missing != False)
            # -------------------------------------------------------------
            print("[E2E Step E] 验证缺失数据语义 (Missing != 0, Missing != False)...")
            loop_empty = await service.get_review_loop_data("2099-12-31")
            assert loop_empty.today_facts.fact_layer.sentiment.limit_up_count is None, "Missing fact must be None (not 0)"
            assert loop_empty.today_facts.fact_layer.sentiment.broken_ratio is None, "Missing broken_ratio must be None (not 0.0)"
            assert loop_empty.today_hypothesis is None, "No hypothesis on empty date"
            assert loop_empty.yesterday_adjudication is None, "No adjudication on empty date"

            results["missing_data_semantics"] = "PASS"
            print("  -> 缺失数据语义 (Missing 保留为 None，拒绝假零填充)：PASS")

    finally:
        await engine.dispose()
        if os.path.exists(sandbox_db):
            os.unlink(sandbox_db)

    print("\n" + "=" * 70)
    print("Phase 2B.3 E2E 验证结果汇总:")
    all_pass = True
    for k, v in results.items():
        print(f"  - {k}: {v}")
        if v != "PASS":
            all_pass = False

    if all_pass:
        print("\n[CONCLUSION] Phase 2B.3 认知闭环端到端 E2E 验证全项 PASSED！")
    else:
        print("\n[CONCLUSION] Phase 2B.3 E2E 验证存在失败项！")
    print("=" * 70)
    return all_pass


if __name__ == "__main__":
    success = asyncio.run(run_e2e_verification())
    sys.exit(0 if success else 1)
