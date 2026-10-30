from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def get_shanghai_now() -> datetime:
    """获取 Asia/Shanghai 时区的当前服务端时间"""
    return datetime.now(SHANGHAI_TZ)


def has_second_precision(time_val: str) -> bool:
    """
    检查时间字符串是否真实具备秒级精度 (HH:MM:SS 或 YYYYMMDDHHMMSS)。
    坚决拒绝仅有时分 (HH:MM) 或缺少秒数的粗粒度时间。

    安全防范重点：
    1. 紧凑纯数字格式 (如 14 位 YYYYMMDDHHMMSS 或 6 位 HHMMSS) 判定为具备秒级；4/8/12 位等判定为缺失秒级。
    2. 带时区偏移 (如 +08:00, -05:30, Z) 时，必须在时区剥离前保留连字符与符号语义，绝不能提前全局 replace("-", "") 将负时区数字误计为时间精度。
    3. 钟表时间必须具备完整的 HH:MM:SS 结构 (精确包含 2 个冒号分隔出时、分、秒)。
    """
    s = str(time_val or "").strip()
    if not s:
        return False

    # 若不含冒号 ':'，只可能是紧凑纯数字格式或纯日期
    if ":" not in s:
        main_digits = s.split(".")[0]
        if main_digits.isdigit():
            if len(main_digits) == 6:
                return True
            if len(main_digits) >= 14:
                return True
            return False
        return False

    # 包含冒号 ':'，说明为带冒号分隔的时间或日期时间字符串
    # 1. 提取时间部分 (剥离前置日期部分，以空格或 'T' / 't' 分隔)
    if " " in s:
        t_part = s.split(" ", 1)[-1].strip()
    elif "T" in s:
        t_part = s.split("T", 1)[-1].strip()
    elif "t" in s:
        t_part = s.split("t", 1)[-1].strip()
    else:
        t_part = s

    # 2. 剥离时间部分末尾的时区偏移 (+HH:MM, -HH:MM, +HHMM, -HHMM, Z, z)
    if "Z" in t_part:
        t_part = t_part.split("Z")[0]
    if "z" in t_part:
        t_part = t_part.split("z")[0]
    if "+" in t_part:
        t_part = t_part.split("+")[0]
    if "-" in t_part:
        t_part = t_part.split("-")[0]

    clock_str = t_part.strip()
    if not clock_str:
        return False

    # 3. 校验时钟时间段：必须具备 HH:MM:SS 结构 (恰好包含 2 个冒号)
    parts = clock_str.split(":")
    if len(parts) != 3:
        return False

    hh, mm, ss_raw = parts[0], parts[1], parts[2]
    ss = ss_raw.split(".")[0]
    if hh.isdigit() and mm.isdigit() and ss.isdigit():
        return len(ss) == 2
    return False


def parse_quote_datetime(item: Dict[str, Any], default_date: Optional[str] = None) -> Optional[datetime]:
    """
    从行情数据字典中解析出 Asia/Shanghai 时区的时间戳对象。
    支持字段: time, datetime, servertime, timestamp, 结合 date / trade_date。
    核心安全铁律：
    1. 强制要求包含时分秒时间精度；严禁对仅有日期的行情伪造零点 (防止开盘零点附近被误判为新鲜)。
    2. 严格正确转换时区偏移 (如 UTC+0 转换为 Asia/Shanghai，绝不可盲目截断时区导致未来时间漏检)。
    """
    if not isinstance(item, dict):
        return None

    # 1. 尝试直接解析 Unix 时间戳 (秒或毫秒)
    ts = item.get("timestamp")
    if ts is not None:
        try:
            val = float(ts)
            if val > 1e11:  # 毫秒时间戳
                val /= 1000.0
            return datetime.fromtimestamp(val, tz=SHANGHAI_TZ)
        except (ValueError, TypeError, OverflowError):
            pass

    # 2. 提取日期部分 (YYYY-MM-DD 或 YYYYMMDD)
    date_val = str(item.get("date") or item.get("trade_date") or default_date or "").strip()
    clean_date = ""
    if date_val:
        d_digits = date_val.replace("-", "").replace("/", "").strip()
        if len(d_digits) == 8 and d_digits.isdigit():
            clean_date = f"{d_digits[:4]}-{d_digits[4:6]}-{d_digits[6:8]}"

    # 3. 提取时间/日期时间字符串
    raw_time = item.get("time") or item.get("datetime") or item.get("servertime")
    time_val = str(raw_time or "").strip()
    if not time_val:
        # 仅有日期缺失时间：刚性拒绝伪造零点，必须具备时分秒方可作为盘中有效行情
        return None

    # 刚性校验秒级时间精度 (必须真实包含秒 HH:MM:SS 或 YYYYMMDDHHMMSS)
    # 坚决拒绝仅有时分 (HH:MM) 或缺少秒数的粗粒度报价 (防止 10:00 自动补为 10:00:00 绕过秒级校验)
    if not has_second_precision(time_val):
        return None

    # 4. 尝试 ISO 8601 解析 (支持带时区偏移如 +00:00, +08:00, Z)
    # 例如: "2026-10-30T10:00:00+00:00", "2026-10-30 10:00:00+00:00", "2026-10-30T10:00:00Z"
    iso_candidate = time_val.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_candidate)
        # 必须确认解析结果含有时间信息（防止纯日期 "2026-10-30" 被 fromisoformat 自动补 00:00:00）
        if len(time_val) <= 10 and (time_val.isdigit() or "-" in time_val or "/" in time_val):
            return None
        # 如果缺少时区，指定为 Asia/Shanghai；若带有时区偏移，正确转换到 Asia/Shanghai
        if dt.tzinfo is not None:
            return dt.astimezone(SHANGHAI_TZ)
        else:
            return dt.replace(tzinfo=SHANGHAI_TZ)
    except (ValueError, TypeError):
        pass

    # 5. 尝试紧凑格式 YYYYMMDDHHMMSS (如腾讯 20261030102950)
    compact_candidate = time_val.replace("-", "").replace(":", "").replace(" ", "").replace("/", "").strip()
    if len(compact_candidate) == 14 and compact_candidate.isdigit():
        try:
            dt = datetime.strptime(compact_candidate, "%Y%m%d%H%M%S")
            return dt.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            pass

    # 6. 尝试标准日期时间格式 (带/不带微秒，不含时区)
    normalized_val = time_val.replace("T", " ").strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M:%S.%f",
    ):
        try:
            dt = datetime.strptime(normalized_val, fmt)
            return dt.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue

    # 7. 若 time_val 仅为纯时间 (如 "10:29:50" 或 "10:29:50.123")，结合 clean_date
    if clean_date and ":" in time_val:
        full_time_str = f"{clean_date} {time_val}"
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
        ):
            try:
                dt = datetime.strptime(full_time_str, fmt)
                return dt.replace(tzinfo=SHANGHAI_TZ)
            except ValueError:
                continue

    return None


def validate_quote_item(item: Dict[str, Any], now: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    单条行情时态与新鲜度校验：
    1. 必须使用 Asia/Shanghai 服务端时间判断当日
    2. 新鲜度要求 0 ≤ 当前时间 − 报价时间 ≤ 300 秒；未来时间戳严格拒绝
    3. 严禁接受缺失时分秒（仅有日期）的未成熟报价
    """
    if not isinstance(item, dict):
        return False, "Quote item is not a dictionary"

    if now is None:
        now = get_shanghai_now()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=SHANGHAI_TZ)
    else:
        now = now.astimezone(SHANGHAI_TZ)

    today_str = now.strftime("%Y-%m-%d")

    q_dt = parse_quote_datetime(item)
    if q_dt is None:
        return False, "Missing or unparseable quote timestamp (dateless or invalid HH:MM:SS)"

    # 1. 服务端 Asia/Shanghai 交易日期校验
    q_date_str = q_dt.strftime("%Y-%m-%d")
    if q_date_str != today_str:
        return False, f"Date mismatch: quote date '{q_date_str}' != server today '{today_str}' (Asia/Shanghai)"

    # 2. 新鲜度数学区间校验: 0 ≤ 当前时间 − 报价时间 ≤ 300 秒
    diff_sec = (now - q_dt).total_seconds()
    if diff_sec < 0:
        return False, f"Future timestamp: quote time '{q_dt.strftime('%Y-%m-%d %H:%M:%S')}' is {-diff_sec:.1f}s in future of server time '{now.strftime('%Y-%m-%d %H:%M:%S')}'"
    if diff_sec > 300.0:
        return False, f"Stale quote: age {diff_sec:.1f}s exceeds 300s window (quote '{q_dt.strftime('%Y-%m-%d %H:%M:%S')}' vs now '{now.strftime('%Y-%m-%d %H:%M:%S')}')"

    return True, ""


def validate_quote_batch(items: Any, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    批量行情时态与新鲜度校验。整批中的每条数据均需满足当日与新鲜度要求。
    """
    if items is None:
        return False, "Quote payload is None"

    if isinstance(items, dict):
        items = [items]

    if not isinstance(items, (list, tuple)):
        return False, f"Invalid quote payload type: {type(items)}"

    if len(items) == 0:
        return False, "Empty quote payload list"

    for idx, it in enumerate(items):
        ok, reason = validate_quote_item(it, now=now)
        if not ok:
            code = it.get("code") or it.get("symbol") or f"index_{idx}" if isinstance(it, dict) else f"index_{idx}"
            return False, f"Quote for '{code}' failed validation: {reason}"

    return True, ""
