from ..registry import registry
from .sina import SinaProvider
from .tonghuashun import TongHuaShunProvider
from .baostock_provider import BaostockProvider
from .cls import CLSProvider
from .eastmoney import EastmoneyProvider
from .tdx_provider import TdxProvider

def init_providers():
    """初始化并注册默认数据提供者"""
    sina = SinaProvider()
    ths = TongHuaShunProvider()
    baostock = BaostockProvider()
    cls = CLSProvider()
    east = EastmoneyProvider()
    tdx = TdxProvider()

    # 指数与个股行情 (Primary: Sina)
    registry.register("index_quote", "sina", sina, is_primary=True)
    registry.register("stock_quote", "sina", sina, is_primary=True)

    # 涨跌停与情绪
    registry.register("limit_up", "tonghuashun_eastmoney", ths, is_primary=True)

    # 全市场广度
    registry.register("market_breadth", "eastmoney", east, is_primary=True)

    # 微盘股与风格偏好 (抽象隔离)
    registry.register("micro_cap", "eastmoney", east, is_primary=True)

    # 高位股与连板生态承接表现
    registry.register("high_tier_performance", "eastmoney", east, is_primary=True)

    # 外部风险与A50
    registry.register("external_risk", "sina", sina, is_primary=True)

    # 隔夜外盘
    registry.register("overnight", "sina", sina, is_primary=True)

    # 日线结算
    registry.register("settlement", "baostock", baostock, is_primary=True)

    # 快讯新闻：CLS 财联社快讯为主源（已修复参数与签名，准入），Sina Feed 为双源容灾热备（Dual-Source Failover）
    registry.register("news", "cls", cls, is_primary=True)
    registry.register("news", "sina", sina, is_primary=False)

    # 证券主数据模糊搜索
    registry.register("security_search", "eastmoney", east, is_primary=True)

    # 交易所严重异常波动监管异动事实 (Wave 1: em_price_anomaly)
    registry.register("price_anomaly", "eastmoney", east, is_primary=True)

    # 个股概念与行业板块归属 (Wave 1: eastmoney_concept_blocks)
    registry.register("concept_blocks", "eastmoney", east, is_primary=True)
    registry.register("concept_blocks", "tdx_direct", tdx, is_primary=False)

    # 板块排行与主力资金流 (Sector & Money Flow)
    registry.register("sector", "eastmoney", east, is_primary=True)

    # 个股与板块分时分钟走势 (Intraday Minute Trends): Primary 为通达信直连物理真实点阵，Secondary 为东财容灾
    registry.register("stock_trends", "tdx_direct", tdx, is_primary=True)
    registry.register("stock_trends", "eastmoney", east, is_primary=False)

init_providers()

