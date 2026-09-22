from datetime import date, datetime, timedelta

class TradingCalendar:
    """
    A股交易日历基础实现
    - 基础判断：排除周六、周日
    - 预留法定节假日配置扩展
    """

    def __init__(self, custom_holidays: set[str] | None = None):
        # 预留自定义节假日列表 (YYYY-MM-DD)
        self.holidays = custom_holidays or set()

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
