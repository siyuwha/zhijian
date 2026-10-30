from datetime import date, datetime, timedelta

class CalendarCoverageError(RuntimeError):
    """交易日历覆盖范围不足或未配置法定休市安排异常"""
    pass

# 2023 - 2026 年法定节假日休市日历
DEFAULT_HOLIDAYS = {
    # 2023 年法定休市
    "2023-01-02",
    "2023-01-23", "2023-01-24", "2023-01-25", "2023-01-26", "2023-01-27",
    "2023-04-05",
    "2023-05-01", "2023-05-02", "2023-05-03",
    "2023-06-22", "2023-06-23",
    "2023-09-29", "2023-10-02", "2023-10-03", "2023-10-04", "2023-10-05", "2023-10-06",

    # 2024 年法定休市
    "2024-01-01",
    "2024-02-09", "2024-02-12", "2024-02-13", "2024-02-14", "2024-02-15", "2024-02-16",
    "2024-04-04", "2024-04-05",
    "2024-05-01", "2024-05-02", "2024-05-03",
    "2024-06-10",
    "2024-09-16", "2024-09-17",
    "2024-10-01", "2024-10-02", "2024-10-03", "2024-10-04", "2024-10-07",

    # 2025 年法定休市
    "2025-01-01",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04",
    "2025-04-04",
    "2025-05-01", "2025-05-02", "2025-05-05",
    "2025-05-31", "2025-06-02",
    "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",

    # 2026 年法定休市
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
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07",
}

DEFAULT_HOLIDAY_LABELS = {
    # 2023 年休市标签
    "2023-01-02": "元旦休市",
    "2023-01-23": "春节休市", "2023-01-24": "春节休市", "2023-01-25": "春节休市", "2023-01-26": "春节休市", "2023-01-27": "春节休市",
    "2023-04-05": "清明休市",
    "2023-05-01": "劳动节休市", "2023-05-02": "劳动节休市", "2023-05-03": "劳动节休市",
    "2023-06-22": "端午休市", "2023-06-23": "端午休市",
    "2023-09-29": "中秋休市", "2023-10-02": "国庆休市", "2023-10-03": "国庆休市", "2023-10-04": "国庆休市", "2023-10-05": "国庆休市", "2023-10-06": "国庆休市",

    # 2026 年主要休市标签
    "2026-01-01": "元旦休市",
    "2026-01-02": "元旦休市",
    "2026-02-16": "春节休市",
    "2026-02-17": "春节休市",
    "2026-02-18": "春节休市",
    "2026-02-19": "春节休市",
    "2026-02-20": "春节休市",
    "2026-04-03": "清明休市",
    "2026-04-06": "清明休市",
    "2026-05-01": "劳动节休市",
    "2026-05-04": "劳动节休市",
    "2026-05-05": "劳动节休市",
    "2026-06-19": "端午休市",
    "2026-09-25": "中秋休市",
    "2026-10-01": "国庆休市",
    "2026-10-02": "国庆休市",
    "2026-10-03": "国庆休市",
    "2026-10-04": "国庆休市",
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
    - 严格覆盖范围校验：未覆盖年份主动抛出 CalendarCoverageError 阻止非预期成交
    """

    SUPPORTED_YEARS = {2023, 2024, 2025, 2026}

    def __init__(
        self,
        custom_holidays: set[str] | None = None,
        custom_holiday_labels: dict[str, str] | None = None,
        supported_years: set[int] | None = None
    ):
        self.holidays = set(DEFAULT_HOLIDAYS)
        self.holiday_labels = dict(DEFAULT_HOLIDAY_LABELS)
        self.supported_years = set(supported_years or self.SUPPORTED_YEARS)
        if custom_holidays:
            self.holidays.update(custom_holidays)
        if custom_holiday_labels:
            self.holiday_labels.update(custom_holiday_labels)

    def check_coverage(self, target_date: date | str) -> date:
        """检查目标日期是否在日历有效覆盖年份内，未覆盖则明确抛出异常"""
        if isinstance(target_date, str):
            d = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        else:
            d = target_date
        if d.year not in self.supported_years:
            raise CalendarCoverageError(
                f"交易日历未覆盖年份 {d.year} 的法定休市安排（当前仅支持 {sorted(self.supported_years)}），日历不可用"
            )
        return d

    def get_weekday_name(self, target_date: date | str | None = None) -> str:
        """获取中文星期名称，如 '周一'、'周三'、'周日'"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        return WEEKDAYS_ZH[target_date.weekday()]

    def get_holiday_name(self, target_date: date | str | None = None) -> str | None:
        """获取法定节假日休市名称（如 '国庆休市'），若非节假日则返回 None"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        date_str = target_date.strftime("%Y-%m-%d")
        return self.holiday_labels.get(date_str)

    def format_date_with_weekday(self, target_date: date | str | None = None) -> str:
        """格式化为带星期几及休市状态的日期字符串，如 '2026-09-30 (周三)'、'2026-10-01 (周四·国庆休市)'"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        date_str = target_date.strftime("%Y-%m-%d")
        wd = WEEKDAYS_ZH[target_date.weekday()]
        h_name = self.holiday_labels.get(date_str)
        if h_name:
            return f"{date_str} ({wd}·{h_name})"
        elif target_date.weekday() in (5, 6):
            return f"{date_str} ({wd}·周末休市)"
        return f"{date_str} ({wd})"

    def is_trading_day(self, target_date: date | str | None = None, enforce_coverage: bool = False) -> bool:
        """判断是否为交易日（默认当前日期，严格校验覆盖范围）"""
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.strptime(target_date[:10], "%Y-%m-%d").date()

        if enforce_coverage:
            self.check_coverage(target_date)

        # 0 = Monday, ..., 6 = Sunday
        if target_date.weekday() in (5, 6):
            return False

        date_str = target_date.strftime("%Y-%m-%d")
        if date_str in self.holidays:
            return False

        return True

    def next_trading_day(self, target_date: date | str, enforce_coverage: bool = True) -> date:
        """获取下一个交易日（跨越未覆盖年份时主动抛出异常）"""
        if isinstance(target_date, str):
            curr = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        else:
            curr = target_date

        if enforce_coverage:
            self.check_coverage(curr)

        while True:
            curr += timedelta(days=1)
            if enforce_coverage and curr.year not in self.supported_years:
                raise CalendarCoverageError(
                    f"推算下一交易日跨越至未覆盖年份 {curr.year}，日历不可用"
                )
            if self.is_trading_day(curr, enforce_coverage=enforce_coverage):
                return curr

    def prev_trading_day(self, target_date: date | str, enforce_coverage: bool = True) -> date:
        """获取上一个交易日"""
        if isinstance(target_date, str):
            curr = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        else:
            curr = target_date

        if enforce_coverage:
            self.check_coverage(curr)

        while True:
            curr -= timedelta(days=1)
            if enforce_coverage and curr.year not in self.supported_years:
                raise CalendarCoverageError(
                    f"推算上一交易日跨越至未覆盖年份 {curr.year}，日历不可用"
                )
            if self.is_trading_day(curr, enforce_coverage=enforce_coverage):
                return curr

calendar = TradingCalendar()
