import asyncio
import json
import logging
import os
import sys
from datetime import datetime

# 设置工作目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session, init_db
from app.data.service import DataService
from app.data.capabilities import DataQuality
from app.data.providers import init_providers
from app.cognition.market_state import MarketStateComputer
from app.cognition.config import get_default_market_state_v1_config
from app.cognition.interfaces import CognitionInput
from app.models.cognition import CognitionMarketState
from app.models.report import DailyReview
from sqlalchemy import select

# 关闭冗余的 SQLAlchemy 引擎日志，保证验收报告整洁
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("m14_real_verify")

async def run_verification():
    init_providers()
    today = datetime.now().strftime("%Y-%m-%d")
    today_compact = today.replace("-", "")
    print(f"\n{'='*70}")
    print(f"   M1.4 V1 真实市场数据接入与状态引擎深度验收 (G5-Phase 1A)")
    print(f"   交易日: {today} | 验收时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    await init_db()

    async with async_session() as session:
        data_service = DataService(session)
        config = get_default_market_state_v1_config()
        computer = MarketStateComputer(config)

        # ----------------------------------------------------------------------
        # 1. 真实数据抓取 (Provider -> Capability)
        # ----------------------------------------------------------------------
        print("[1/5] 发起真实网络数据请求，抓取各 Provider 行情...")
        
        # 1.1 指数行情 (Sina)
        indices_codes = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        res_indices = await data_service.get_index_quotes(indices_codes)
        print(f"  * [Sina] 核心指数行情: Provider={res_indices.provider}, 质量={res_indices.quality.value}, 笔数={len(res_indices.data or [])}")

        # 1.2 全市场广度 (Eastmoney)
        res_breadth = await data_service.get_market_breadth()
        print(f"  * [Eastmoney] 市场广度: Provider={res_breadth.provider}, 质量={res_breadth.quality.value}, 数据={res_breadth.data}")

        # 1.3 涨跌停、连板及炸板池 (Eastmoney/TongHuaShun)
        res_limit_up = await data_service.get_limit_up_pool(today)
        lu_summary = res_limit_up.data or {}
        print(f"  * [Eastmoney] 涨跌停池: Provider={res_limit_up.provider}, 质量={res_limit_up.quality.value}")
        print(f"      - 涨停家数: {lu_summary.get('total_count')}")
        print(f"      - 跌停家数: {lu_summary.get('limit_down_count')}")
        print(f"      - 炸板家数: {lu_summary.get('broken_limit_count')}")
        print(f"      - 真实炸板率: {lu_summary.get('broken_limit_ratio')}")
        print(f"      - 最高连板高度: {lu_summary.get('max_height')} 板")

        # 1.4 微盘股风格代理 (Eastmoney)
        res_micro = await data_service.get_micro_cap_quote()
        print(f"  * [Eastmoney] 微盘风格: Provider={res_micro.provider}, 质量={res_micro.quality.value}, 标的={res_micro.data.get('name') if res_micro.data else None}, 涨跌幅={res_micro.data.get('pct_change') if res_micro.data else None}%")

        # 1.5 外部风险与A50 (Sina)
        res_ext = await data_service.get_external_risk()
        print(f"  * [Sina] 外部风险A50: Provider={res_ext.provider}, 质量={res_ext.quality.value}, A50变动={res_ext.data.get('a50_pct_change') if res_ext.data else None}%, 多空指标={res_ext.data.get('a50_long_short_indicator') if res_ext.data else None}")

        # 1.6 高位股连板承接表现 (Eastmoney)
        res_high_tier = await data_service.get_high_tier_performance()
        print(f"  * [Eastmoney] 高标承接表现: Provider={res_high_tier.provider}, 质量={res_high_tier.quality.value}, 昨日连板涨幅={res_high_tier.data.get('pct_change') if res_high_tier.data else None}%")

        # ----------------------------------------------------------------------
        # 2. 组装原始快照并送入 M1.4 V1 状态引擎计算
        # ----------------------------------------------------------------------
        print(f"\n[2/5] 组装原始快照，送入 MarketStateComputer 计算...")
        raw_snapshot = {
            "indices": res_indices.data or [],
            "limit_up": res_limit_up.data or {},
            "breadth": res_breadth.data or {},
            "micro_cap": res_micro.data or {},
            "external_risk": res_ext.data or {},
            "high_tier": res_high_tier.data or {},
            "prev_total_amount": None, # 首日测试无昨日成交额
            "prev_limit_up_count": None
        }

        market_state = await computer.compute_market_state(CognitionInput(market_data=raw_snapshot))

        print(f"\n{'='*70}")
        print(f"   M1.4 V1 计算结果综述")
        print(f"{'='*70}")
        print(f"  > 全局数据质量 (data_quality) : {market_state.data_quality.value}")
        print(f"  > 综合得分 (composite_score)   : {market_state.composite_score}")
        print(f"  > 状态标签 (state_label)       : {market_state.state_label}")
        print(f"  > 缺失指标项 (missing_metrics) : {market_state.missing_metrics}")

        # ----------------------------------------------------------------------
        # 3. 逐维度（D1~D6）详细审计
        # ----------------------------------------------------------------------
        print(f"\n[3/5] D1~D6 分层子维度详细审计:")
        print(f"{'-'*70}")
        for dim_id, dim_state in market_state.dimensions.items():
            print(f"  【{dim_id} - {dim_state.name}】")
            print(f"    - 得分: {dim_state.score} | 质量: {dim_state.quality.value} | 状态: {dim_state.state_label}")
            print(f"    - 原生采集指标值:")
            for k, v in dim_state.metrics.items():
                print(f"        {k}: {v}")
            print(f"    - 单指标打分及权重贡献:")
            for ind in dim_state.indicators_detail:
                disp = ind.raw_data.get("display_name", ind.name)
                print(f"        * {disp} ({ind.name}): 原值={ind.value}, 归一化得分={ind.score}, 权重={ind.weight}, 贡献分={ind.contribution:.2f}")
            print(f"{'-'*70}")

        # ----------------------------------------------------------------------
        # 4. 关键规则专门复核 (G5-Phase 1A.2 终审铁律与断言)
        # ----------------------------------------------------------------------
        print(f"\n[4/5] 关键设计与铁律核查 (G5-Phase 1A.2):")
        
        # 4.1 D2 纯广度解耦断言
        d2_metrics = market_state.dimensions.get("D2", {}).metrics
        print(f"  * D2 纯广度指标池: {list(d2_metrics.keys())}")
        assert "limit_up_count" not in d2_metrics, "严重违背铁律：D2 仍残留 limit_up_count！"
        assert "limit_down_count" not in d2_metrics, "严重违背铁律：D2 仍残留 limit_down_count！"
        assert "broken_limit_ratio" not in d2_metrics, "严重违背铁律：D2 仍残留 broken_limit_ratio！"
        assert market_state.dimensions["D2"].metric_polarity == "BREADTH_EXPANSION", "D2 语义极性错误"
        print("    --> [通过] D2 彻底与涨跌停、炸板率解耦，纯度 100%。")

        # 4.2 D3 双子域正交断言
        d3_state = market_state.dimensions.get("D3", {})
        assert d3_state.sub_domains is not None, "严重错误：D3 缺失 sub_domains 双子域结构！"
        sub_a = d3_state.sub_domains.get("speculative_structure")
        sub_b = d3_state.sub_domains.get("tail_extremes")
        assert sub_a is not None and sub_b is not None, "严重错误：D3 双子域不完整！"
        print(f"  * D3 双子域独立输出: Sub-A(投机高标)={sub_a.get('score')}, Sub-B(尾部极端)={sub_b.get('score')}")
        assert d3_state.score is None, f"严重违背铁律：D3 核心 score 必须为 None 以杜绝标量塌缩，实测={d3_state.score}"
        assert d3_state.reference_score is not None, "D3 必须提供 reference_score 仅供参考诊断"
        assert d3_state.metric_polarity == "HEAT_EXTREMITY", "D3 语义极性错误"
        print("    --> [通过] D3 成功实现双子域独立正交输出，核心 score 严格为 None，彻底封堵标量塌缩。")

        # 4.3 D5 与 D6 语义极性断言
        assert market_state.dimensions["D5"].name == "外部环境", "D5 名称未更正为外部环境"
        assert market_state.dimensions["D5"].metric_polarity == "EXTERNAL_BENIGNITY", "D5 极性元数据不匹配"
        assert market_state.dimensions["D6"].metric_polarity == "LIQUIDITY_ACTIVITY", "D6 极性元数据不匹配"
        print("    --> [通过] D5(外部环境)与 D6(流动性活跃度)语义极性规范落地。")

        # 4.4 零伪造与缺失降级核查
        a50_ls = market_state.dimensions.get("D5", {}).metrics.get("a50_long_short_indicator")
        print(f"  * A50 多空指标实测值: {a50_ls}")
        assert a50_ls is None, "严重错误：A50 多空在不可得时被伪造了数值！"
        print("    --> [通过] A50 多空指标严格为 None，未伪造默认值。")

        # ----------------------------------------------------------------------
        # 5. 数据库持久化及回读验证
        # ----------------------------------------------------------------------
        print(f"\n[5/5] 测试写入 SQLite 数据库并回读校验...")
        dim_dump = {d_id: s.model_dump() for d_id, s in market_state.dimensions.items()}
        cog_record = CognitionMarketState(
            date=today,
            timestamp=datetime.now().isoformat(),
            indicators=json.dumps(dim_dump, ensure_ascii=False),
            composite_score=market_state.composite_score,
            state_label=market_state.state_label,
            config_snapshot=json.dumps(config.model_dump(), ensure_ascii=False),
            data_quality=market_state.data_quality.value
        )
        session.add(cog_record)
        await session.flush()

        # 回读验证
        stmt = select(CognitionMarketState).where(CognitionMarketState.id == cog_record.id)
        saved_cog = (await session.execute(stmt)).scalars().first()
        assert saved_cog is not None
        assert saved_cog.composite_score == market_state.composite_score
        assert saved_cog.data_quality == market_state.data_quality.value
        saved_dims = json.loads(saved_cog.indicators)
        assert len(saved_dims) == len(market_state.dimensions)
        print(f"  * CognitionMarketState 快照写入成功 (ID={saved_cog.id})，回读字段完全匹配！")

        print(f"\n{'='*70}")
        print(f"   G5-Phase 1A 验收运行完成！")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(run_verification())
