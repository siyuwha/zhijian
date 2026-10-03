from datetime import date, datetime, timedelta

# 2026 年法定节假日休市日历扩展
DEFAULT_HOLIDAYS = {
    # 元旦
    "2026-01-01", "2026-01-02",
    # 春节
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    # 清明节
    "2026-04-03", "2026-04-06",
    # 劳动节
    "2026-05-01", "2026-05-04", "2026-05-05",
    # 端午节
    "2026-06-19",
    # 中秋节
    "2026-09-25",
    # 国庆节
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
}

DEFAULT_HOLIDAY_LABELS = {
    # 元旦
    "2026-01-01": "元旦休市",
    "2026-01-02": "元旦休市",
    # 春节
    "2026-02-16": "春节休市",
    "2026-02-17": "春节休市",
    "2026-02-18": "春节休市",
    "2026-02-19": "春节休市",
    "2026-02-20": "春节休市",
    # 清明节
    "2026-04-03": "清明休市",
    "2026-04-06": "清明休市",
    # 劳动节
    "2026-05-01": "劳动节休市",
    "2026-05-04": "劳动节休市",
    "2026-05-05": "劳动节休市",
    # 端午节
    "2026-06-19": "端午休市",
    # 中秋节
    "2026-09-25": "中秋休市",
    # 国庆节
    "2026-10-01": "国庆休市",
    "2026-10-02": "国庆休市",
    "2026-10-05": "国庆休市",
    "2026-10-06": "国庆休市",
    "2026-10-07": "国庆休市",
}

WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

class TradingCalendar:
    """
    A股交易日历基础实现
    - 基础判断：排除周六、周日
    - 扩展支持：法定节假日（中秋、国庆、春节等）自动休市判定
    - 星期几与法定休市标签格式化支持
    """

    def __init__(self, custom_holidays: set[str] | None = None, custom_holiday_labels: dict[str, str] | None = None):
        self.holidays = set(DEFAULT_HOLIDAYS)
        self.holiday_labels = dict(DEFAULT_HOLIDAY_LABELS)
        if custom_holidays:
            self.holidays.update(custom_holidays)
        if custom_holiday_labels:
            self.holiday_labels.update(custom_holiday_labels)

    def get_weekday_name(self, target_date: date | str | None = None) -> str:
        """获取中文星期名称，如 '周一'、'周三'、'周日'"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        return WEEKDAYS_ZH[target_date.weekday()]

    def get_holiday_name(self, target_date: date | str | None = None) -> str | None:
        """获取法定节假日休市名称（如 '国庆休市'），若非节假日则返回 None"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        date_str = target_date.strftime("%Y-%m-%d")
        return self.holiday_labels.get(date_str)

    def format_date_with_weekday(self, target_date: date | str | None = None) -> str:
        """格式化为带星期几及休市状态的日期字符串，如 '2026-09-30 (周三)'、'2026-10-01 (周四·国庆休市)'、'2026-09-26 (周六·周末休市)'"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        date_str = target_date.strftime("%Y-%m-%d")
        wd = WEEKDAYS_ZH[target_date.weekday()]
        h_name = self.holiday_labels.get(date_str)
        if h_name:
            return f"{date_str} ({wd}·{h_name})"
        elif target_date.weekday() in (5, 6):
            return f"{date_str} ({wd}·周末休市)"
        return f"{date_str} ({wd})"

    def is_trading_day(self, target_date: date | str | None = None) -> bool:
        """判断是否为交易日（默认当前日期）"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date, "%Y-%m-%d").date()

        # 0 = Monday, ..., 6 = Sunday
        if target_date.weekday() in (5, 6):
            return False

        date_str = target_date.strftime("%Y-%m-%d")
        if date_str in self.holidays:
            return False

        return True

    def next_trading_day(self, target_date: date | str) -> date:
        """获取下一个交易日"""
        if isinstance(target_date, str):
            curr = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            curr = target_date

        while True:
            curr += timedelta(days=1)
            if self.is_trading_day(curr):
                return curr

    def prev_trading_day(self, target_date: date | str) -> date:
        """获取上一个交易日"""
        if isinstance(target_date, str):
            curr = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            curr = target_date

        while True:
            curr -= timedelta(days=1)
            if self.is_trading_day(curr):
                return curr

calendar = TradingCalendar()
