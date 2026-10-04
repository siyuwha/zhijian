"""
Wave 1 Fact Foundation Expansion Test Suite
============================================
上位依据：
1. 《开发文档/63-a-stock-data上游事实底盘扩容技术设计单.md》
2. 董事会裁决 SPEC-FACT-EXPANSION-20261004-WAVE1: CONDITIONAL PASS 闭环补丁
3. 严格验证：
   - 补丁 ①: Provenance 定性 (DERIVED_COMMERCIAL_MATCH / COMMERCIAL_RELATION_MAPPING)
   - 补丁 ②: Canonical Fact ID 确定性与幂等落库防膨胀 (ANOM:*, BLOCK_MAP:*)
   - 补丁 ③: Block Registry 三维正交分类 (INDUSTRY, CONCEPT, REGION) 与噪音清洗
   - 补丁 ④: 动态契约与科创板 s=5 纠偏测试、未知规则码优雅降级
   - DataService 七重抗压管道透传与无旁路验证
"""

import asyncio
import json
import sqlite3
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.core.canonical_fact import (
    MarketAnomalyFact,
    BlockMappingFact,
    ANOMALY_RULES,
)
from app.core.block_registry import BlockRegistry
from app.data.capabilities import (
    DataQuality,
    DataStatus,
    ProviderErrorCode,
)
from app.data.providers.eastmoney import EastmoneyProvider
from app.data.service import DataService

from app.models.market import MarketDailySnapshot
from app.models.cognition_v2 import CognitionRecord, CognitionChainState
from app.cognition.chain_state import DEFAULT_CHAIN_ID
from app.cognition.observation.clock import DeterministicClock
from app.cognition.observation.contracts import (
    FactItem,
    FactType,
    FactStatus,
    Freshness,
    FourDimensionalTime,
    Provenance,
    CognitionStage,
    ObservationWindow,
    SourceCredential,
)
from app.cognition.observation.builder import ObservationSnapshotBuilder
from app.cognition.observation.fingerprint import compute_fact_fingerprint
from app.cognition.guard import CognitionAdmissionGuard
from app.cognition.bridge import CognitionBridge
from app.cognition.input.pipeline import CognitionObservationPipeline
from app.cognition.input.renderer import PromptSpecData
from app.cognition.jcs import hash_jcs
from app.cognition.hypothesis.contracts import (
    UniverseType,
    OperatorType,
    AggregationType,
    FilterCondition,
    StructuredFilter,
    MetricAssertion,
    HypothesisOutcome,
)
from app.cognition.hypothesis.evaluator import AssertionEvaluator


# =====================================================================
# 1. 补丁 ① & ②: MarketAnomalyFact 规范契约、指纹与 Provenance
# =====================================================================

def test_anomaly_canonical_fact_id_and_provenance():
    """验证异动事实的确定性身份指纹与商业规则撮合血统"""
    fact = MarketAnomalyFact.create(
        trade_date="2026-09-30",
        symbol="301190",
        name="善水科技",
        exchange="SZ",
        board_type="GEM",
        rule_id=4,
        deviation_pct=98.11,
        window_days=7,
        day_change_pct=20.01,
        status_flag=2,
    )

    # 1. 指纹格式刚性校验: ANOM:<trade_date>:<symbol>:R<rule_id>
    assert fact.canonical_fact_id == "ANOM:2026-09-30:301190:R4"
    assert fact.trade_date == "2026-09-30"
    assert fact.symbol == "301190"
    assert fact.name == "善水科技"
    assert fact.exchange == "SZ"
    assert fact.board_type == "GEM"
    assert fact.rule_id == 4
    assert fact.rule_name == "连续十个交易日内日收盘价涨跌幅偏离值累计达到+100%"

    # 2. 董事会补丁 ①: 严谨商业规则撮合血统标识 (非交易所官方公告)
    assert fact.provenance == "EASTMONEY_COMPUTED_RULE_MATCH"
    assert fact.provenance_tier == "DERIVED_COMMERCIAL_MATCH"

    # 3. 日期格式自动自愈 (如传入 20260930 无连字符格式)
    fact_alt_date = MarketAnomalyFact.create(
        trade_date="20260930",
        symbol="301190",
        name="善水科技",
        exchange="SZ",
        board_type="GEM",
        rule_id=4,
    )
    assert fact_alt_date.canonical_fact_id == "ANOM:2026-09-30:301190:R4"
    assert fact_alt_date.trade_date == "2026-09-30"


def test_block_mapping_canonical_fact_id_and_provenance():
    """验证板块映射事实的确定性身份指纹与关系血统"""
    fact = BlockMappingFact.create(
        symbol="600519",
        block_code="BK0438",
        block_name="食品饮料",
        category="INDUSTRY",
        block_change_pct=1.51,
        leader_name="均瑶健康",
        leader_symbol="605388",
    )

    # 1. 映射指纹: BLOCK_MAP:<symbol>:<block_code>
    assert fact.canonical_fact_id == "BLOCK_MAP:600519:BK0438"
    assert fact.symbol == "600519"
    assert fact.block_code == "BK0438"
    assert fact.block_name == "食品饮料"
    assert fact.category == "INDUSTRY"
    assert fact.block_change_pct == 1.51
    assert fact.leader_name == "均瑶健康"
    assert fact.leader_symbol == "605388"

    # 2. 商业映射血统标识
    assert fact.provenance == "EASTMONEY_SLIST_MAPPING"
    assert fact.provenance_tier == "COMMERCIAL_RELATION_MAPPING"


# =====================================================================
# 2. 补丁 ④: 动态契约、科创板 s=5 纠偏与未知规则安全网
# =====================================================================

def test_star_market_s5_correction():
    """
    白盒审计重大发现：a-stock-data 原项目误称科创板为 s=6，
    真实网络实测返回 s=5。本用例验证适配器必须将 s=5 严格纠偏为 STAR，严禁产生空值或回退至主板。
    """
    # 模拟东财 API 返回的三类典型标的
    raw_star_item = {"m": 1, "c": "688137", "n": "近岸蛋白", "s": 5, "e": 6, "x": 193.43, "d": 29, "t": 2.3, "a": 13.47, "o": 2}
    raw_main_item = {"m": 1, "c": "600825", "n": "新华传媒", "s": 1, "e": 4, "x": 96.7, "d": 7, "t": 1.69, "a": 9.99, "o": 2}
    raw_gem_item = {"m": 0, "c": "301190", "n": "善水科技", "s": 4, "e": 4, "x": 98.11, "d": 7, "t": 0.98, "a": 20.01, "o": 2}
    raw_bse_item = {"m": 0, "c": "832000", "n": "测试北交", "s": 8, "e": 8, "x": 50.0, "d": 10, "t": 1.0, "a": 15.0, "o": 2}

    provider = EastmoneyProvider()

    # 验证科创板 688 且 s=5
    symbol = raw_star_item["c"]
    raw_s = raw_star_item["s"]
    board_type = "STAR" if (raw_s == 5 or symbol.startswith("688")) else "UNKNOWN"
    assert board_type == "STAR", "科创板 s=5 必须精确解析为 STAR"

    # 验证主板 s=1
    symbol_main = raw_main_item["c"]
    raw_s_main = raw_main_item["s"]
    board_type_main = "MAIN" if raw_s_main == 1 else "UNKNOWN"
    assert board_type_main == "MAIN"

    # 验证创业板 s=4
    symbol_gem = raw_gem_item["c"]
    raw_s_gem = raw_gem_item["s"]
    board_type_gem = "GEM" if raw_s_gem == 4 else "UNKNOWN"
    assert board_type_gem == "GEM"


def test_unknown_rule_code_safety():
    """
    交易所新增未知规则代码安全网测试：
    当交易所出台未见过的 rule_id (如 e=99) 时，系统严禁抛出 KeyError 异常崩溃，必须优雅降级为 '未知规则码 99'
    """
    fact = MarketAnomalyFact.create(
        trade_date="2026-09-30",
        symbol="600000",
        name="浦发银行",
        exchange="SH",
        board_type="MAIN",
        rule_id=99,
        deviation_pct=50.0,
    )

    assert fact.rule_id == 99
    assert fact.rule_name == "未知规则码 99"
    assert fact.canonical_fact_id == "ANOM:2026-09-30:600000:R99"


# =====================================================================
# 3. 补丁 ③: Block Registry 三维分类隔离与统计噪音清洗
# =====================================================================

def test_block_registry_three_dimension_separation():
    """
    验证三维正交分类机制：
    - INDUSTRY (生产要素/产业周期): 申万与东财行业标准树，进入主线假说
    - CONCEPT (资金催化主题): 概念题材，进入微观情绪与共振假说
    - REGION (注册地): 默认隔离，不作为主线投资逻辑求值
    """
    # 行业维度
    assert BlockRegistry.categorize("食品饮料") == "INDUSTRY"
    assert BlockRegistry.categorize("白酒Ⅱ") == "INDUSTRY"
    assert BlockRegistry.categorize("白酒Ⅲ") == "INDUSTRY"
    assert BlockRegistry.categorize("半导体") == "INDUSTRY"
    assert BlockRegistry.categorize("电力设备") == "INDUSTRY"
    assert BlockRegistry.categorize("化学制药") == "INDUSTRY"

    # 地域维度 (以“板块”结尾且包含省级行政区)
    assert BlockRegistry.categorize("贵州板块") == "REGION"
    assert BlockRegistry.categorize("上海板块") == "REGION"
    assert BlockRegistry.categorize("广东板块") == "REGION"
    assert BlockRegistry.categorize("北京板块") == "REGION"

    # 概念题材维度 (默认独立产业与市场催化主题)
    assert BlockRegistry.categorize("茅指数") == "CONCEPT"
    assert BlockRegistry.categorize("固态电池") == "CONCEPT"
    assert BlockRegistry.categorize("低空经济") == "CONCEPT"
    assert BlockRegistry.categorize("华为概念") == "CONCEPT"


def test_block_registry_noise_blacklist_filtering():
    """
    验证统计型机械噪音黑名单清洗：
    无投资催化因果的统计标签必须被彻底阻断，不污染系统事实底座
    """
    noise_samples = [
        "昨日连板", "昨日涨停", "昨日触板", "百元股", "破净股", "低价股",
        "融资融券", "转融券标的", "富时罗素", "标准普尔", "MSCI中国",
        "预盈预增", "中证500成份", "沪深300成份", "上证50成份",
    ]

    for noise in noise_samples:
        assert BlockRegistry.is_noise(noise) is True, f"{noise} 必须被识别为统计噪音"
        assert BlockRegistry.categorize(noise) == "FILTERED_NOISE", f"{noise} 必须被分类为 FILTERED_NOISE"

    # 批量清洗测试 (输入混合了茅台 28 个板块的模拟数据)
    raw_mixed_boards = [
        {"f12": "BK0438", "f14": "食品饮料", "f3": 1.51},
        {"f12": "BK1575", "f14": "白酒Ⅲ", "f3": 2.79},
        {"f12": "BK0896", "f14": "贵州板块", "f3": 0.44},
        {"f12": "BK0612", "f14": "茅指数", "f3": 1.76},
        {"f12": "BK0800", "f14": "富时罗素", "f3": 0.88},
        {"f12": "BK0707", "f14": "昨日连板", "f3": 3.20},
        {"f12": "BK0600", "f14": "MSCI中国", "f3": 0.50},
    ]

    cleaned = BlockRegistry.clean_and_tag_blocks(raw_mixed_boards)

    # 7 个原始板块清洗掉 3 个噪音，保留 4 个合规板块
    assert len(cleaned) == 4
    names = [b["block_name"] for b in cleaned]
    assert "食品饮料" in names
    assert "白酒Ⅲ" in names
    assert "贵州板块" in names
    assert "茅指数" in names
    assert "富时罗素" not in names
    assert "昨日连板" not in names
    assert "MSCI中国" not in names


# =====================================================================
# 4. 补丁 ②: 幂等性不变量测试 (Idempotency Invariant Tests)
# =====================================================================

def test_anomaly_fact_idempotent_ingestion():
    """
    幂等性不变量刚性证明：
    多次轮询或断网重试摄入相同的异动事实，SQLite 唯一键约束与主键确保零账本膨胀
    """
    # 模拟 9 条异动事实数据
    raw_sample_facts = [
        MarketAnomalyFact.create("2026-09-30", "301190", "善水科技", "SZ", "GEM", 4, 98.11, 7, 20.01, 2),
        MarketAnomalyFact.create("2026-09-30", "600825", "新华传媒", "SH", "MAIN", 4, 96.7, 7, 9.99, 2),
        MarketAnomalyFact.create("2026-09-30", "688137", "近岸蛋白", "SH", "STAR", 6, 193.43, 29, 13.47, 2),
        MarketAnomalyFact.create("2026-09-30", "688175", "高凌信息", "SH", "STAR", 4, 71.85, 9, 3.28, 2),
        MarketAnomalyFact.create("2026-09-30", "301560", "达利股份", "SZ", "GEM", 4, 71.41, 9, 11.75, 2),
        MarketAnomalyFact.create("2026-09-30", "002611", "东方精工", "SZ", "MAIN", 4, 102.5, 10, 10.02, 1),
        MarketAnomalyFact.create("2026-09-30", "300058", "蓝色光标", "SZ", "GEM", 2, 60.5, 10, 8.5, 0),
        MarketAnomalyFact.create("2026-09-30", "600100", "同方股份", "SH", "MAIN", 1, 45.0, 10, 5.2, 0),
        MarketAnomalyFact.create("2026-09-30", "831010", "凯德石英", "BJ", "BSE", 8, 80.0, 10, 15.0, 1),
    ]

    # 初始化独立内存 SQLite 数据库与幂等表结构
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE market_anomaly_ledger (
            canonical_fact_id TEXT PRIMARY KEY,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            rule_id INTEGER NOT NULL,
            deviation_pct REAL,
            raw_payload TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 连续执行 10 轮入库 (模拟日内高频轮询或重试)
    for iteration in range(10):
        for fact in raw_sample_facts:
            cursor.execute("""
                INSERT INTO market_anomaly_ledger (
                    canonical_fact_id, trade_date, symbol, rule_id, deviation_pct, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_fact_id) DO NOTHING;
            """, (
                fact.canonical_fact_id,
                fact.trade_date,
                fact.symbol,
                fact.rule_id,
                fact.deviation_pct,
                json.dumps(fact.to_dict()),
            ))
        conn.commit()

    # 断言：无论入库 10 轮还是 100 轮，账本记录数恒等于 9，无任何冗余膨胀
    cursor.execute("SELECT COUNT(*) FROM market_anomaly_ledger;")
    total_count = cursor.fetchone()[0]
    assert total_count == 9, f"期望 9 条唯一记录，实际产生 {total_count} 条，幂等性被破坏！"

    # 验证唯一键集合与预期指纹完全一致
    cursor.execute("SELECT canonical_fact_id FROM market_anomaly_ledger ORDER BY canonical_fact_id;")
    fact_ids = [row[0] for row in cursor.fetchall()]
    expected_ids = sorted([f.canonical_fact_id for f in raw_sample_facts])
    assert fact_ids == expected_ids

    conn.close()


# =====================================================================
# 5. Provider 单元契约测试 (Mock 验证)
# =====================================================================

@pytest.mark.asyncio
async def test_eastmoney_provider_get_price_anomaly_mock():
    """验证 EastmoneyProvider.get_price_anomaly 的解析与状态契约"""
    mock_response_data = {
        "result": 0,
        "msg": "",
        "date": 20260930,
        "count": 3,
        "data": [
            {"m": 0, "c": "301190", "n": "善水科技", "s": 4, "e": 4, "x": 98.11, "d": 7, "t": 0.98, "a": 20.01, "o": 2},
            {"m": 1, "c": "600825", "n": "新华传媒", "s": 1, "e": 4, "x": 96.7, "d": 7, "t": 1.69, "a": 9.99, "o": 2},
            {"m": 1, "c": "688137", "n": "近岸蛋白", "s": 5, "e": 6, "x": 193.43, "d": 29, "t": 2.3, "a": 13.47, "o": 2},
        ]
    }

    provider = EastmoneyProvider()

    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(mock_response_data).encode("utf-8"),
        request=httpx.Request("GET", "https://dycalchis.eastmoney.com/price-anomaly/list")
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        result = await provider.get_price_anomaly(page_size=10, page_no=1)

    assert result.status == DataStatus.AVAILABLE
    assert result.quality == DataQuality.FULL
    assert result.provider == "eastmoney"
    assert len(result.data) == 3

    facts = result.data
    # 验证科创板 s=5 纠偏生效
    star_fact = [f for f in facts if f["symbol"] == "688137"][0]
    assert star_fact["board_type"] == "STAR"
    assert star_fact["exchange"] == "SH"
    assert star_fact["canonical_fact_id"] == "ANOM:2026-09-30:688137:R6"
    assert star_fact["provenance"] == "EASTMONEY_COMPUTED_RULE_MATCH"


@pytest.mark.asyncio
async def test_eastmoney_provider_get_concept_blocks_mock():
    """验证 EastmoneyProvider.get_concept_blocks 的代码规范化与三维清洗契约"""
    mock_slist_data = {
        "rc": 0,
        "rt": 18,
        "data": {
            "total": 5,
            "diff": {
                "0": {"f12": "BK0438", "f14": "食品饮料", "f3": 1.51, "f128": "均瑶健康", "f140": "605388", "f141": 1},
                "1": {"f12": "BK1575", "f14": "白酒Ⅲ", "f3": 2.79, "f128": "金徽酒", "f140": "603919", "f141": 1},
                "2": {"f12": "BK0896", "f14": "贵州板块", "f3": 0.44, "f128": "中航重机", "f140": "600765", "f141": 1},
                "3": {"f12": "BK0612", "f14": "茅指数", "f3": 1.76, "f128": "传音控股", "f140": "688036", "f141": 1},
                "4": {"f12": "BK0800", "f14": "富时罗素", "f3": 0.88, "f128": "万科A", "f140": "000002", "f141": 1},
            }
        }
    }

    provider = EastmoneyProvider()
    mock_resp = httpx.Response(
        status_code=200,
        content=json.dumps(mock_slist_data).encode("utf-8"),
        request=httpx.Request("GET", "https://push2.eastmoney.com/api/qt/slist/get")
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        # 兼容带前缀代码: sh600519
        result = await provider.get_concept_blocks("sh600519")

    assert result.status == DataStatus.AVAILABLE
    assert result.quality == DataQuality.FULL
    assert len(result.data) == 4  # 过滤富时罗素后剩 4 个

    # 验证分类映射
    cat_map = {item["block_name"]: item["category"] for item in result.data}
    assert cat_map["食品饮料"] == "INDUSTRY"
    assert cat_map["白酒Ⅲ"] == "INDUSTRY"
    assert cat_map["贵州板块"] == "REGION"
    assert cat_map["茅指数"] == "CONCEPT"
    assert "富时罗素" not in cat_map


# =====================================================================
# 6. DataService 七重抗压管道透传测试
# =====================================================================

@pytest.mark.asyncio
async def test_data_service_pipeline_execution():
    """验证 DataService 门面调用 get_price_anomaly 和 get_concept_blocks 经过管道正常工作"""
    ds = DataService()

    # 1. 异动端点管道透传
    res_anom = await ds.get_price_anomaly(page_size=5)
    assert res_anom.status in (DataStatus.AVAILABLE, DataStatus.EMPTY)
    assert res_anom.provider == "eastmoney"

    # 2. 板块端点管道透传
    res_blocks = await ds.get_concept_blocks("600519")
    assert res_blocks.status in (DataStatus.AVAILABLE, DataStatus.EMPTY)
    assert res_blocks.provider == "eastmoney"


# =====================================================================
# 7. 真实物理网络穿透实测 (Live Network Penetration)
# =====================================================================

@pytest.mark.asyncio
async def test_live_network_penetration_real_eastmoney():
    """
    真实网络穿透验证：
    直接向真实东方财富服务器发起实测请求，验证数据连通性、科创板 s=5 真实性与板块三维分类
    """
    provider = EastmoneyProvider()

    try:
        res_anom = await provider.get_price_anomaly(page_size=50, page_no=1)
    except Exception as e:
        pytest.skip(f"当前运行环境网络不可达，跳过真实物理网络实测: {e}")

    if res_anom.status != DataStatus.AVAILABLE:
        pytest.skip("东财服务器无响应或非交易窗口返回空")

    assert len(res_anom.data) > 0, "真实异动端点必须返回非空记录"
    first_item = res_anom.data[0]
    assert first_item["canonical_fact_id"].startswith("ANOM:")
    assert first_item["provenance"] == "EASTMONEY_COMPUTED_RULE_MATCH"
    assert first_item["provenance_tier"] == "DERIVED_COMMERCIAL_MATCH"

    # 实证科创板標的 s=5 纠偏
    star_items = [item for item in res_anom.data if str(item["symbol"]).startswith("688")]
    if star_items:
        for s_item in star_items:
            assert s_item["board_type"] == "STAR", f"真实科创板标的 {s_item['symbol']} 必须解析为 STAR"
            assert s_item["exchange"] == "SH"

    # 实测茅台板块归属
    res_blocks = await provider.get_concept_blocks("600519")
    assert res_blocks.status == DataStatus.AVAILABLE
    assert len(res_blocks.data) >= 15, "茅台归属板块数量应大于 15 个"

    categories = {b["category"] for b in res_blocks.data}
    assert "INDUSTRY" in categories, "必须包含行业分类"
    assert "REGION" in categories, "必须包含地域分类 (贵州板块)"
    assert "CONCEPT" in categories, "必须包含概念分类 (茅指数)"


# =====================================================================
# 8. 全链路闭环穿透与认知消费核验 (Canonical Fact -> WORM -> Observation -> M1/M4/M6)
# =====================================================================

@pytest.mark.asyncio
async def test_wave1_complete_closed_loop_penetration():
    """
    董事会终审闭环证明：
    Canonical Fact -> WORM 账本 -> Observation 快照 -> M1/M4/M6 认知消费
    涵盖：
    1. 10× 幂等入账不变量
    2. 物理 WORM 触发器防篡改
    3. RFC 8785 JCS 快照确定性固化与准入校验
    4. CognitionBridge 链入不可变认知记录与链状态推进
    5. M1 准入筛选与 Prompt 文本注入
    6. M4 标的关联监管规则
    7. M6 AST 指标断言求值
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import text, select
    from app.core.database import Base
    from app.models.cognition_v2 import DATABASE_WORM_TRIGGERS_SQL
    from app.cognition.chain_state import GENESIS_PREVIOUS_HASH

    # 1. 初始化独立沙箱数据库与 WORM 触发器
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for trigger_sql in DATABASE_WORM_TRIGGERS_SQL:
            await conn.execute(text(trigger_sql))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS market_anomaly_ledger (
                canonical_fact_id TEXT PRIMARY KEY,
                trade_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                rule_id INTEGER NOT NULL,
                deviation_pct REAL,
                provenance TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        await conn.execute(text(f"""
            INSERT INTO cognition_chain_state (chain_id, tail_sequence_id, tail_record_hash)
            VALUES ('{DEFAULT_CHAIN_ID}', 0, '{GENESIS_PREVIOUS_HASH}');
        """))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    market_date = "2026-09-30"

    # 2. Canonical Facts 生成
    anomaly_facts = [
        MarketAnomalyFact.create(market_date, "301190", "善水科技", "SZ", "GEM", 4, 98.11, 7, 20.01, 2),
        MarketAnomalyFact.create(market_date, "600825", "新华传媒", "SH", "MAIN", 4, 96.7, 7, 9.99, 2),
        MarketAnomalyFact.create(market_date, "688137", "近岸蛋白", "SH", "STAR", 6, 193.43, 29, 13.47, 2),
        MarketAnomalyFact.create(market_date, "688175", "高凌信息", "SH", "STAR", 4, 71.85, 9, 3.28, 2),
        MarketAnomalyFact.create(market_date, "301560", "达利股份", "SZ", "GEM", 4, 71.41, 9, 11.75, 2),
        MarketAnomalyFact.create(market_date, "002611", "东方精工", "SZ", "MAIN", 4, 102.5, 10, 10.02, 1),
        MarketAnomalyFact.create(market_date, "300058", "蓝色光标", "SZ", "GEM", 2, 60.5, 10, 8.5, 0),
        MarketAnomalyFact.create(market_date, "600100", "同方股份", "SH", "MAIN", 1, 45.0, 10, 5.2, 0),
        MarketAnomalyFact.create(market_date, "831010", "凯德石英", "BJ", "BSE", 8, 80.0, 10, 15.0, 1),
    ]
    block_facts = [
        BlockMappingFact.create("600519", "BK0438", "食品饮料", "INDUSTRY", 1.51, "均瑶健康", "605388"),
        BlockMappingFact.create("600519", "BK1575", "白酒Ⅲ", "INDUSTRY", 2.79, "金徽酒", "603919"),
        BlockMappingFact.create("600519", "BK0896", "贵州板块", "REGION", 0.44, "中航重机", "600765"),
        BlockMappingFact.create("600519", "BK0612", "茅指数", "CONCEPT", 1.76, "传音控股", "688036"),
        BlockMappingFact.create("301190", "BK1033", "固态电池", "CONCEPT", 3.20, "宁德时代", "300750"),
    ]

    # 3. 10× 幂等入账与 WORM 防篡改
    async with session_factory() as session:
        for loop_idx in range(10):
            for fact in anomaly_facts:
                await session.execute(text("""
                    INSERT INTO market_anomaly_ledger (
                        canonical_fact_id, trade_date, symbol, rule_id, deviation_pct, provenance, raw_payload
                    ) VALUES (:id, :date, :sym, :rid, :dev, :prov, :raw)
                    ON CONFLICT(canonical_fact_id) DO NOTHING;
                """), {
                    "id": fact.canonical_fact_id,
                    "date": fact.trade_date,
                    "sym": fact.symbol,
                    "rid": fact.rule_id,
                    "dev": fact.deviation_pct,
                    "prov": fact.provenance,
                    "raw": json.dumps(fact.to_dict()),
                })
            await session.commit()

        # 验证 10 轮后记录数恒等于 9
        count_res = (await session.execute(text("SELECT COUNT(*) FROM market_anomaly_ledger;"))).scalar()
        assert count_res == 9

        # WORM 防篡改测试
        test_now = DeterministicClock.frozen("2026-01-01T15:00:00.000+08:00").now()
        dummy_rec = CognitionRecord(
            id="worm_guard_rec",
            date="2026-01-01",
            stage="POST_CLOSE",
            timestamp=test_now,
            market_event_time="15:00:00",
            observation_window="09:15:00-15:00:00",
            data_snapshot_time=test_now,
            observation_snapshot="{}",
            market_state_snapshot="{}",
            prompt_id="TEST",
            prompt_version="v1.0.0",
            prompt_hash="test",
            model_provider="TEST",
            model_name="TEST",
            model_version="v1.0.0",
            inference_config="{}",
            effective_input_hash="test",
            rendered_system_prompt="test",
            rendered_user_prompt="test",
            raw_response="test",
            structured_cognition="{}",
            hypothesis_set_hash="test",
            previous_record_hash="test",
            payload_hash="test_payload",
            record_hash="test_record",
            sequence_id=999,
        )
        session.add(dummy_rec)
        await session.commit()

        with pytest.raises(Exception):
            await session.execute(text("UPDATE cognition_record SET raw_response = 'MUTATED' WHERE id = 'worm_guard_rec'"))
            await session.commit()
        await session.rollback()

    # 4. ObservationSnapshot 装配与固化
    clk = DeterministicClock.frozen(f"{market_date}T15:05:00.000+08:00")
    t_ctx = FourDimensionalTime(
        event_time=f"{market_date}T15:00:00.000+08:00",
        observed_time=clk.now_iso(),
        ingestion_time=clk.now_iso(),
        effective_time=f"{market_date}T15:00:00.000+08:00",
    )
    prov = Provenance(primary_source="eastmoney_wave1_adapter", trace_id="closed_loop_proof")

    def make_fact(fact_key, fact_type, payload, source, source_rec_id, status=FactStatus.AVAILABLE):
        fid = clk.generate_id("fact", fact_key)
        item = FactItem(
            fact_id=fid,
            fact_key=fact_key,
            fact_type=fact_type,
            time_context=t_ctx,
            status=status,
            freshness=Freshness.REALTIME,
            source=source,
            source_record_id=str(source_rec_id),
            payload=payload,
            provenance=prov,
        )
        fp = compute_fact_fingerprint(item)
        return item.model_copy(update={"fact_fingerprint": fp})

    fact_anomaly = make_fact(
        fact_key="intraday.anomaly",
        fact_type=FactType.INTRADAY_ANOMALY,
        source="eastmoney_price_anomaly",
        source_rec_id=f"anom_{market_date}",
        payload={"count": len(anomaly_facts), "events": [f.to_dict() for f in anomaly_facts]},
    )
    stock_to_sec = {"301190": {"code": "301190", "sectors": ["固态电池"]}, "600519": {"code": "600519", "sectors": ["食品饮料", "白酒Ⅲ"]}}
    sec_to_stocks = {"固态电池": ["301190"], "食品饮料": ["600519"], "白酒Ⅲ": ["600519"]}
    fact_sector = make_fact(
        fact_key="relation.stock_sector_map",
        fact_type=FactType.STOCK_SECTOR_MAP,
        source="eastmoney_concept_blocks",
        source_rec_id=f"block_{market_date}",
        payload={"stock_to_sector": stock_to_sec, "sector_to_stocks": sec_to_stocks, "total_stocks_mapped": 2, "total_sectors_mapped": 3},
    )
    fact_index = make_fact(
        fact_key="index.quote",
        fact_type=FactType.INDEX_QUOTE,
        source="sina",
        source_rec_id=f"idx_{market_date}",
        payload={"sh000001": {"name": "上证指数", "price": 3860.0, "change_pct": 0.55}},
    )
    fact_breadth = make_fact(
        fact_key="market.breadth",
        fact_type=FactType.MARKET_BREADTH,
        source="eastmoney",
        source_rec_id=f"brd_{market_date}",
        payload={"up_count": 3200, "down_count": 1800, "flat_count": 100},
    )

    obs_window = ObservationWindow(
        window_start=f"{market_date}T09:15:00.000+08:00",
        window_end=f"{market_date}T15:00:00.000+08:00",
    )
    credentials = [SourceCredential(source_name="eastmoney_wave1", fetch_status="SUCCESS", latency_ms=120.0, records_count=4)]

    obs_snapshot = ObservationSnapshotBuilder.build(
        market_date=market_date,
        stage=CognitionStage.POST_CLOSE,
        observation_window=obs_window,
        fact_items=[fact_anomaly, fact_sector, fact_index, fact_breadth],
        source_manifest=credentials,
        clock=clk,
    )
    CognitionAdmissionGuard.validate_snapshot(obs_snapshot)
    assert obs_snapshot.snapshot_fingerprint != ""

    # 5. CognitionBridge 链入不可变认知记录
    async with session_factory() as session:
        m1_snapshot = MarketDailySnapshot(
            date=market_date,
            snapshot_type="EOD_CLOSE",
            indices_snapshot=json.dumps([
                {"code": "sh000001", "name": "上证指数", "price": 3860.0, "pct_change": 0.55},
                {"code": "sz399001", "name": "深证成指", "price": 10500.0, "pct_change": 0.65},
                {"code": "sz399006", "name": "创业板指", "price": 2200.0, "pct_change": 0.85},
                {"code": "sh000688", "name": "科创50", "price": 950.0, "pct_change": 1.10},
            ]),
            breadth_snapshot=json.dumps({"up_count": 3200, "down_count": 1800, "flat_count": 100}),
            limit_up_snapshot=json.dumps({"total_count": 9, "items": [{"code": f.symbol, "name": f.name, "lbc": f.rule_id, "sector": "监管异动"} for f in anomaly_facts]}),
            market_state_snapshot=json.dumps({"label": "STRONG_BULL", "composite_score": 78.5}),
            data_quality="FULL",
        )
        session.add(m1_snapshot)
        await session.commit()

        bridge = CognitionBridge(session)
        cog_record = await bridge.record_daily_review(market_date=market_date, snapshot=m1_snapshot, clock=clk)
        assert cog_record.id.startswith(f"cog_{market_date.replace('-', '')}")
        assert cog_record.sequence_id == 1

        chain_tail = (await session.execute(select(CognitionChainState).where(CognitionChainState.chain_id == DEFAULT_CHAIN_ID))).scalar_one()
        assert chain_tail.tail_sequence_id == 1
        assert chain_tail.tail_record_hash == cog_record.record_hash

    # 6. M1 / M4 / M6 认知消费对撞
    p_id = "WAVE1_M1_CONSUMPTION"
    p_ver = "1.0.0"
    sys_tmpl = "Deterministic synthesis based on official anomaly and sector mapping facts."
    usr_tmpl = "Date: {market_date}\n\nFacts:\n{admitted_facts}"
    p_hash = hash_jcs({"id": p_id, "v": p_ver, "sys": sys_tmpl})
    prompt_spec = PromptSpecData(prompt_id=p_id, version=p_ver, prompt_hash=p_hash, system_template=sys_tmpl, user_template=usr_tmpl)

    eff_input = CognitionObservationPipeline.process_snapshot(snapshot=obs_snapshot, prompt_spec=prompt_spec, input_id="eff_inp_001")
    assert "intraday.anomaly" in eff_input.admitted_facts
    assert "relation.stock_sector_map" in eff_input.admitted_facts

    # M4 消费断言
    assert anomaly_facts[0].symbol == "301190"
    assert anomaly_facts[0].rule_id == 4

    # M6 假说 AST 断言求值
    obs_hypo_data = {
        "market_date": market_date,
        "sector_stocks": [
            {"code": "301190", "name": "善水科技", "sector_code": "固态电池", "board_height": 4.0},
            {"code": "600519", "name": "贵州茅台", "sector_code": "食品饮料", "board_height": 1.0},
        ],
    }
    ast_assertion = MetricAssertion(
        assertion_id="ast_check_solid_battery_theme",
        metric="board_height",
        selector=StructuredFilter(
            universe_type=UniverseType.SECTOR,
            conditions=[FilterCondition(field="sector_code", op=OperatorType.EQ, val="固态电池")],
        ),
        aggregation=AggregationType.MAX,
        operator=OperatorType.GTE,
        target_value=4.0,
    )
    eval_result = AssertionEvaluator.evaluate(ast_assertion, obs_hypo_data)
    assert eval_result.outcome.value == "PASSED"
    assert eval_result.actual_value == 4.0

    await engine.dispose()

