from ..registry import registry
from .sina import SinaProvider
from .tonghuashun import TongHuaShunProvider
from .baostock_provider import BaostockProvider
from .cls import CLSProvider
from .eastmoney import EastmoneyProvider

def init_providers():
    """初始化并注册默认数据提供者"""
    sina = SinaProvider()
    ths = TongHuaShunProvider()
    baostock = BaostockProvider()
    cls = CLSProvider()
    east = EastmoneyProvider()

    # 指数与个股行情
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

    # 快讯新闻：财联社为主，新浪为备用降级
    registry.register("news", "cls", cls, is_primary=True)
    registry.register("news", "sina", sina, is_primary=False)

init_providers()
