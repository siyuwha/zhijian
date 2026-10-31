"""
市场成交额标准口径与质量降级引擎 (Turnover Engine)
T09-01 成交额口径治理标准实现 (GATE-2D0-02 核心防线)

规则依据：
1. 沪深不重叠：深交所总额已含主板与创业板，上交所总额已含主板与科创板；两市合计 = SH + SZ (绝不重复叠加创业板 sz399006 或科创50 sh000688)。
2. 保守降级门禁：候选来源未取得交易所/供应商权威核准前，保持 PENDING_VERIFICATION (待核准)；
   任一必要分量待核准、缺失或过期时，正式总额为 None (null)，严禁以 0.0 假冒完整合计，质量不得标 FULL。
3. 时态与新鲜度：严格防御未来时间；交易时段多维判定 (盘前/竞价/连续/盘后/历史)；
   连续交易年龄 <= 300s；两侧时差 <= 60s 为同步，60s ~ 300s 为异步降级，> 300s 拒绝；
   盘后与历史无显式归档完成凭据不得标 FULL。
4. 全精度计算：各分量保持高精度无损转换为亿元，先求和、展示层最终四舍五入。
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, time as dtime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional, List, Dict, Any, Union

from ..schemas.canonical_market import DataQualityGrade
from ..core.calendar import calendar

SHANGHAI_TZ = timezone(timedelta(hours=8))


class TurnoverSourceStatus(str, Enum):
    """数据源口径核准状态"""
    VERIFIED = "VERIFIED"                  # 已核准 (官方凭据闭环，可计入正式全市场总额)
    PENDING_VERIFICATION = "PENDING_VERIFICATION"  # 待核准 (候选来源，按门禁保守置空正式总额)
    INVALID_FOR_TOTAL = "INVALID_FOR_TOTAL"        # 不可用于两市合计 (如创业板指、科创50等成份切片)


class MarketSessionPhase(str, Enum):
    """交易生命周期阶段"""
    PRE_MARKET = "PRE_MARKET"                  # 盘前 00:00 - 09:15
    CALL_AUCTION = "CALL_AUCTION"              # 集合竞价 09:15 - 09:30
    CONTINUOUS_TRADING = "CONTINUOUS_TRADING"  # 连续交易 09:30 - 15:00
    MIDDAY_INTERMISSION = "MIDDAY_INTERMISSION"# 午间休市 11:30 - 13:00
    POST_MARKET = "POST_MARKET"                # 盘后 15:00 - 24:00
    HISTORICAL = "HISTORICAL"                  # 历史交易日
    NON_TRADING_DAY = "NON_TRADING_DAY"        # 非交易日/休市


def to_shanghai_dt(dt: Optional[datetime]) -> Optional[datetime]:
    """标准化时间为 Asia/Shanghai 时区"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def parse_quote_time(date_str: Optional[str], time_str: Optional[str]) -> Optional[datetime]:
    """严格解析 YYYY-MM-DD 和 HH:MM:SS 为 Asia/Shanghai datetime"""
    if not date_str or not time_str:
        return None
    date_clean = date_str.strip()
    time_clean = time_str.strip()
    # 支持带微秒或只有时分秒
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(f"{date_clean} {time_clean}", fmt)
            return dt.replace(tzinfo=SHANGHAI_TZ)
        except ValueError:
            continue
    # 支持 ISO 格式
    try:
        dt = datetime.fromisoformat(time_clean)
        return to_shanghai_dt(dt)
    except Exception:
        pass
    return None


def is_valid_numeric(v: Any) -> bool:
    """检验数值有效性：非空、有限、非负"""
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v) and v >= 0
    if isinstance(v, Decimal):
        return not v.is_nan() and not v.is_infinite() and v >= 0
    return False


def normalize_to_yi_decimal(
    amount: Any,
    unit: str = "wan"
) -> Optional[Decimal]:
    """
    无损将任意单位转换为亿元 Decimal
    unit 可选: 'yuan' (元), 'wan' (万元), 'yi' (亿元)
    """
    if not is_valid_numeric(amount):
        return None
    try:
        dec = Decimal(str(amount))
        u = unit.lower().strip()
        if u in ("yuan", "元"):
            return dec / Decimal("100000000")
        elif u in ("wan", "万元"):
            return dec / Decimal("10000")
        elif u in ("yi", "亿元"):
            return dec
        else:
            return None
    except Exception:
        return None


def round_yi_float(dec: Optional[Decimal], decimals: int = 2) -> Optional[float]:
    """最终展示层标准四舍五入转 float"""
    if dec is None:
        return None
    q = Decimal("10") ** -decimals
    return float(dec.quantize(q, rounding=ROUND_HALF_UP))


@dataclass
class MarketTurnoverResult:
    """标准成交额核算与质量结果契约"""
    # 各分量保留展示 (亿元)
    sh_amount_yi: Optional[float] = None
    sz_total_amount_yi: Optional[float] = None
    chinext_slice_amount_yi: Optional[float] = None
    chinext_ratio_in_sz: Optional[float] = None
    bse_amount_yi: Optional[float] = None

    # 正式全市场总额：未核准或失效时严格为 None
    two_markets_total_yi: Optional[float] = None
    all_markets_total_yi: Optional[float] = None

    # 独立质量等级
    two_markets_quality: DataQualityGrade = DataQualityGrade.DEGRADED
    all_markets_quality: DataQualityGrade = DataQualityGrade.PARTIAL

    session_phase: MarketSessionPhase = MarketSessionPhase.CONTINUOUS_TRADING
    is_degraded: bool = True
    degradation_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sh_amount_yi": self.sh_amount_yi,
            "sz_total_amount_yi": self.sz_total_amount_yi,
            "chinext_slice_amount_yi": self.chinext_slice_amount_yi,
            "chinext_ratio_in_sz": self.chinext_ratio_in_sz,
            "bse_amount_yi": self.bse_amount_yi,
            "two_markets_total_yi": self.two_markets_total_yi,
            "all_markets_total_yi": self.all_markets_total_yi,
            "two_markets_quality": self.two_markets_quality.value if hasattr(self.two_markets_quality, "value") else str(self.two_markets_quality),
            "all_markets_quality": self.all_markets_quality.value if hasattr(self.all_markets_quality, "value") else str(self.all_markets_quality),
            "session_phase": self.session_phase.value,
            "is_degraded": self.is_degraded,
            "degradation_reasons": self.degradation_reasons,
        }


def calculate_turnover_caliber(
    target_date: str,
    # 沪市分量
    sh_amount: Any,
    sh_date: Optional[str] = None,
    sh_time: Optional[str] = None,
    sh_unit: str = "wan",
    sh_volume: Optional[float] = None,
    sh_status: TurnoverSourceStatus = TurnoverSourceStatus.PENDING_VERIFICATION,
    # 深市分量
    sz_amount: Any = None,
    sz_date: Optional[str] = None,
    sz_time: Optional[str] = None,
    sz_unit: str = "wan",
    sz_volume: Optional[float] = None,
    sz_status: TurnoverSourceStatus = TurnoverSourceStatus.PENDING_VERIFICATION,
    # 创业板切片 (深市内部结构)
    chinext_amount: Any = None,
    chinext_unit: str = "wan",
    # 北交所分量
    bse_amount: Any = None,
    bse_date: Optional[str] = None,
    bse_time: Optional[str] = None,
    bse_unit: str = "wan",
    bse_volume: Optional[float] = None,
    bse_status: TurnoverSourceStatus = TurnoverSourceStatus.PENDING_VERIFICATION,
    # 评估与控制参数
    now_dt: Optional[datetime] = None,
    is_archive_confirmed: bool = False,
    is_bse_archive_confirmed: bool = False,
    is_zero_semantic_verified: bool = False,
    max_continuous_stale_sec: float = 300.0,
    max_inter_market_delta_sec: float = 60.0,
) -> MarketTurnoverResult:
    """
    全生命周期两市与全市场成交额计算与门禁裁决核心函数
    """
    now_sh = to_shanghai_dt(now_dt) or datetime.now(SHANGHAI_TZ)
    today_str = now_sh.strftime("%Y-%m-%d")
    is_today = (target_date == today_str)

    res = MarketTurnoverResult()

    # 0. 交易日历核验 (非交易日/周末/节假日强制置空正式总额并标 NON_TRADING_DAY)
    try:
        if not calendar.is_trading_day(target_date, enforce_coverage=True):
            res.session_phase = MarketSessionPhase.NON_TRADING_DAY
            res.two_markets_quality = DataQualityGrade.DEGRADED
            res.all_markets_quality = DataQualityGrade.DEGRADED
            res.two_markets_total_yi = None
            res.all_markets_total_yi = None
            res.is_degraded = True
            res.degradation_reasons.append(f"目标日期 {target_date} 为非开市交易日（周末/法定节假日），正式两市总额置空")
            # 仍可转换分量供展示
            sh_dec = normalize_to_yi_decimal(sh_amount, sh_unit)
            sz_dec = normalize_to_yi_decimal(sz_amount, sz_unit)
            res.sh_amount_yi = round_yi_float(sh_dec, 2)
            res.sz_total_amount_yi = round_yi_float(sz_dec, 2)
            return res
    except Exception as e:
        res.session_phase = MarketSessionPhase.NON_TRADING_DAY
        res.two_markets_quality = DataQualityGrade.DEGRADED
        res.all_markets_quality = DataQualityGrade.DEGRADED
        res.two_markets_total_yi = None
        res.all_markets_total_yi = None
        res.is_degraded = True
        res.degradation_reasons.append(f"交易日历未覆盖或核验异常 ({target_date}): {str(e)}，安全阻断并置空正式总额")
        sh_dec = normalize_to_yi_decimal(sh_amount, sh_unit)
        sz_dec = normalize_to_yi_decimal(sz_amount, sz_unit)
        res.sh_amount_yi = round_yi_float(sh_dec, 2)
        res.sz_total_amount_yi = round_yi_float(sz_dec, 2)
        return res

    # 1. 基准交易时段划分 (确保任何分支提前返回时均具有准确时段标识)
    if not is_today:
        res.session_phase = MarketSessionPhase.HISTORICAL
    else:
        cur_t = now_sh.time()
        if cur_t < dtime(9, 15):
            res.session_phase = MarketSessionPhase.PRE_MARKET
        elif cur_t < dtime(9, 30):
            res.session_phase = MarketSessionPhase.CALL_AUCTION
        elif cur_t <= dtime(15, 0):
            if dtime(11, 30) < cur_t < dtime(13, 0):
                res.session_phase = MarketSessionPhase.MIDDAY_INTERMISSION
            else:
                res.session_phase = MarketSessionPhase.CONTINUOUS_TRADING
        else:
            res.session_phase = MarketSessionPhase.POST_MARKET

    # 2. 单项全精度转 Decimal 亿元
    sh_dec = normalize_to_yi_decimal(sh_amount, sh_unit)
    sz_dec = normalize_to_yi_decimal(sz_amount, sz_unit)
    cy_dec = normalize_to_yi_decimal(chinext_amount, chinext_unit) if chinext_amount is not None else None
    bse_dec = normalize_to_yi_decimal(bse_amount, bse_unit) if bse_amount is not None else None

    # 保留分量用于诊断与展示
    res.sh_amount_yi = round_yi_float(sh_dec, 2)
    res.sz_total_amount_yi = round_yi_float(sz_dec, 2)
    res.chinext_slice_amount_yi = round_yi_float(cy_dec, 2)
    if sz_dec and sz_dec > 0 and cy_dec is not None and cy_dec >= 0:
        res.chinext_ratio_in_sz = round(float(cy_dec / sz_dec), 4)
    res.bse_amount_yi = round_yi_float(bse_dec, 2)

    # 2. 基础数值与单边缺失核查
    if sh_dec is None or sz_dec is None:
        res.two_markets_quality = DataQualityGrade.PARTIAL
        res.all_markets_quality = DataQualityGrade.PARTIAL
        res.is_degraded = True
        missing_side = "SH" if sh_dec is None else "SZ"
        res.degradation_reasons.append(f"单边市场成交额缺失或非法数值 ({missing_side})，正式总额置空")
        return res

    # 全生命周期零值语义防线：任一侧为 0 时，必须有官方零语义凭据证实且伴随显式 0 成交量，否则视为占位符/异常值
    phase_prefix = "盘前" if res.session_phase == MarketSessionPhase.PRE_MARKET else ""
    if sh_dec == Decimal(0):
        if not (is_zero_semantic_verified and (sh_volume is not None and sh_volume == 0)):
            res.two_markets_quality = DataQualityGrade.DEGRADED
            res.all_markets_quality = DataQualityGrade.DEGRADED
            res.two_markets_total_yi = None
            res.is_degraded = True
            res.degradation_reasons.append(f"{phase_prefix}零值语义未获来源证实（缺少官方零语义凭据证实或成交量缺失），正式总额置空")
            return res

    if sz_dec == Decimal(0):
        if not (is_zero_semantic_verified and (sz_volume is not None and sz_volume == 0)):
            res.two_markets_quality = DataQualityGrade.DEGRADED
            res.all_markets_quality = DataQualityGrade.DEGRADED
            res.two_markets_total_yi = None
            res.is_degraded = True
            res.degradation_reasons.append(f"{phase_prefix}零值语义未获来源证实（缺少官方零语义凭据证实或成交量缺失），正式总额置空")
            return res

    # 3. 日期核查
    if not sh_date or not sz_date:
        res.two_markets_quality = DataQualityGrade.PARTIAL
        res.all_markets_quality = DataQualityGrade.PARTIAL
        res.is_degraded = True
        res.degradation_reasons.append("市场报价缺少交易日期标识")
        return res

    if sh_date != target_date or sz_date != target_date:
        res.two_markets_quality = DataQualityGrade.UNAVAILABLE
        res.all_markets_quality = DataQualityGrade.UNAVAILABLE
        res.is_degraded = True
        res.degradation_reasons.append(f"交易日期不匹配: sh={sh_date}, sz={sz_date}, 目标={target_date}")
        return res

    # 4. 时间戳解析
    sh_dt = parse_quote_time(sh_date, sh_time)
    sz_dt = parse_quote_time(sz_date, sz_time)
    if sh_dt is None or sz_dt is None:
        res.two_markets_quality = DataQualityGrade.UNAVAILABLE
        res.all_markets_quality = DataQualityGrade.UNAVAILABLE
        res.is_degraded = True
        res.degradation_reasons.append("时间戳格式非法或缺失")
        return res

    # 5. 严格未来时间防御 (无论历史还是今天，报文绝对不能超前于当前评估时钟)
    if is_today:
        if (sh_dt - now_sh).total_seconds() > 0 or (sz_dt - now_sh).total_seconds() > 0:
            res.two_markets_quality = DataQualityGrade.UNAVAILABLE
            res.all_markets_quality = DataQualityGrade.UNAVAILABLE
            res.is_degraded = True
            res.degradation_reasons.append(
                f"拒绝未来时间报价: sh={sh_time}, sz={sz_time}, 当前时钟={now_sh.strftime('%H:%M:%S')}"
            )
            return res

    # 6. 生命周期时段划分与时效判定
    if not is_today:
        # 历史交易日模式
        if target_date > today_str:
            res.two_markets_quality = DataQualityGrade.UNAVAILABLE
            res.all_markets_quality = DataQualityGrade.UNAVAILABLE
            res.session_phase = MarketSessionPhase.HISTORICAL
            res.is_degraded = True
            res.degradation_reasons.append(f"拒绝未来目标交易日: {target_date}")
            return res

        res.session_phase = MarketSessionPhase.HISTORICAL
        # 历史数据必须满足收盘时点 (>= 15:00:00)
        if sh_dt.time() < dtime(15, 0, 0) or sz_dt.time() < dtime(15, 0, 0):
            res.two_markets_quality = DataQualityGrade.PARTIAL
            res.all_markets_quality = DataQualityGrade.PARTIAL
            res.is_degraded = True
            res.degradation_reasons.append(f"历史数据未达到收盘时点: sh={sh_time}, sz={sz_time}")
            return res

        # 历史归档确认检查：未取得官方归档完成标识时，正式总额必须严格为 None，标记 DEGRADED
        if is_archive_confirmed:
            is_two_fresh = True
            two_quality_candidate = DataQualityGrade.FULL
        else:
            is_two_fresh = False
            two_quality_candidate = DataQualityGrade.DEGRADED
            res.degradation_reasons.append("历史数据无官方归档完成标识，正式总额保守置空并标记 DEGRADED")

    else:
        # 当日实时模式
        cur_t = now_sh.time()
        if cur_t < dtime(9, 15):
            res.session_phase = MarketSessionPhase.PRE_MARKET
            # 盘前阶段零值严格判定
            if is_zero_semantic_verified and sh_dec == Decimal(0) and sz_dec == Decimal(0):
                is_two_fresh = True
                two_quality_candidate = DataQualityGrade.FULL
            else:
                is_two_fresh = False
                two_quality_candidate = DataQualityGrade.DEGRADED
                res.degradation_reasons.append("盘前零值语义未获来源证实或成交量缺失，正式总额置空")

        elif cur_t < dtime(9, 30):
            res.session_phase = MarketSessionPhase.CALL_AUCTION
            # 检查集合竞价报价时效
            if sh_dt.time() < dtime(9, 15) or sz_dt.time() < dtime(9, 15):
                is_two_fresh = False
                two_quality_candidate = DataQualityGrade.PARTIAL
                res.degradation_reasons.append(f"集合竞价阶段报价时间早于09:15开盘: sh={sh_time}, sz={sz_time}")
            else:
                sh_age = (now_sh - sh_dt).total_seconds()
                sz_age = (now_sh - sz_dt).total_seconds()
                if sh_age > max_continuous_stale_sec or sz_age > max_continuous_stale_sec:
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.PARTIAL
                    res.degradation_reasons.append(f"集合竞价行情超龄淘汰: sh_age={sh_age:.1f}s, sz_age={sz_age:.1f}s")
                else:
                    # 集合竞价阶段尚未产生连续全天总额，正式总额必须置空
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.DEGRADED
                    res.degradation_reasons.append("集合竞价阶段尚未产生连续全天总额，标记 DEGRADED")

        elif cur_t <= dtime(15, 0, 0):
            if dtime(11, 30) < cur_t < dtime(13, 0):
                res.session_phase = MarketSessionPhase.MIDDAY_INTERMISSION
                # 午间休市时段：报价时间应达到上午收盘时点 (>= 11:29:00)
                if sh_dt.time() < dtime(11, 29) or sz_dt.time() < dtime(11, 29):
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.PARTIAL
                    res.degradation_reasons.append(f"午间休市但早盘报价未达11:30收盘: sh={sh_time}, sz={sz_time}")
                else:
                    inter_delta = abs((sh_dt - sz_dt).total_seconds())
                    if inter_delta > max_inter_market_delta_sec:
                        is_two_fresh = True
                        two_quality_candidate = DataQualityGrade.DEGRADED
                        res.degradation_reasons.append(f"午间休盘沪深轻微异步 ({inter_delta:.1f}s > 60s)")
                    else:
                        is_two_fresh = True
                        two_quality_candidate = DataQualityGrade.DEGRADED
                        res.degradation_reasons.append("午间休市时段维持上午收盘额，标记 DEGRADED")
            else:
                res.session_phase = MarketSessionPhase.CONTINUOUS_TRADING
                # 连续交易时段：年龄与双侧时差检查
                sh_age = (now_sh - sh_dt).total_seconds()
                sz_age = (now_sh - sz_dt).total_seconds()
                inter_delta = abs((sh_dt - sz_dt).total_seconds())

                if sh_age > max_continuous_stale_sec or sz_age > max_continuous_stale_sec:
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.PARTIAL
                    res.degradation_reasons.append(
                        f"连续交易行情过期淘汰: sh_age={sh_age:.1f}s, sz_age={sz_age:.1f}s > {max_continuous_stale_sec}s"
                    )
                elif inter_delta > max_continuous_stale_sec:
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.PARTIAL
                    res.degradation_reasons.append(f"沪深时差超限淘汰: delta={inter_delta:.1f}s")
                elif inter_delta > max_inter_market_delta_sec:
                    # 60s ~ 300s: 异步降级
                    is_two_fresh = True
                    two_quality_candidate = DataQualityGrade.DEGRADED
                    res.degradation_reasons.append(f"沪深报价轻微异步 ({inter_delta:.1f}s > 60s)，降级为 DEGRADED")
                else:
                    # <= 60s 同步且新鲜
                    is_two_fresh = True
                    two_quality_candidate = DataQualityGrade.FULL

        else:
            res.session_phase = MarketSessionPhase.POST_MARKET
            # 盘后时段：报价时间必须达到收盘
            if sh_dt.time() < dtime(15, 0, 0) or sz_dt.time() < dtime(15, 0, 0):
                is_two_fresh = False
                two_quality_candidate = DataQualityGrade.PARTIAL
                res.degradation_reasons.append(f"盘后收盘报价未达15:00: sh={sh_time}, sz={sz_time}")
            else:
                # 15:35 壁钟并不能证明最终清算归档，必须有 explicit 归档凭据
                if is_archive_confirmed:
                    is_two_fresh = True
                    two_quality_candidate = DataQualityGrade.FULL
                else:
                    is_two_fresh = False
                    two_quality_candidate = DataQualityGrade.DEGRADED
                    res.degradation_reasons.append("盘后收盘尚未取得权威归档完成凭据，正式总额保守置空并标记 DEGRADED")

    # 7. 来源口径核准门禁 (核心防线)
    is_sh_verified = (sh_status == TurnoverSourceStatus.VERIFIED)
    is_sz_verified = (sz_status == TurnoverSourceStatus.VERIFIED)

    if not is_sh_verified or not is_sz_verified:
        # 只要任一市场分量待核准，正式总额强制置空，质量不得为 FULL
        res.two_markets_total_yi = None
        res.two_markets_quality = DataQualityGrade.DEGRADED if is_two_fresh else two_quality_candidate
        res.is_degraded = True
        unverified_list = []
        if not is_sh_verified:
            unverified_list.append("沪市候选指数")
        if not is_sz_verified:
            unverified_list.append("深市候选指数")
        res.degradation_reasons.append(
            f"口径待核准门禁生效：{'、'.join(unverified_list)}全市场覆盖范围尚未取得官方凭据，正式总额置空"
        )
    else:
        # 沪深来源均已核准且时效/数值有效
        if is_two_fresh:
            # 严格 sh + sz，严禁额外累加创业板切片！
            tot_dec = sh_dec + sz_dec
            res.two_markets_total_yi = round_yi_float(tot_dec, 2)
            res.two_markets_quality = two_quality_candidate
            res.is_degraded = (two_quality_candidate != DataQualityGrade.FULL)
        else:
            res.two_markets_total_yi = None
            res.two_markets_quality = two_quality_candidate
            res.is_degraded = True

    # 8. 北交所与全市场总额核查
    is_bse_verified = (bse_status == TurnoverSourceStatus.VERIFIED)
    bse_dt = parse_quote_time(bse_date, bse_time) if (bse_date and bse_time) else None

    # 北交所时态与零值语义独立校验
    bse_valid = False
    if bse_dec is not None and bse_date == target_date and bse_dt is not None:
        # 全周期独立零值语义校验：若北交所金额为 0，必须具备官方零语义凭据证实且成交量明确为 0
        if bse_dec == Decimal(0):
            if is_zero_semantic_verified and bse_volume is not None and bse_volume == 0:
                bse_zero_valid = True
            else:
                bse_zero_valid = False
                res.degradation_reasons.append("北交所成交额为零但缺少官方零语义凭据证实或成交量不为零，全市场总额置空")
        else:
            bse_zero_valid = True

        if bse_zero_valid:
            if is_today:
                # 检查北交所未来时间
                if (bse_dt - now_sh).total_seconds() <= 0:
                    if res.session_phase == MarketSessionPhase.CONTINUOUS_TRADING:
                        bse_age = (now_sh - bse_dt).total_seconds()
                        if bse_age <= max_continuous_stale_sec:
                            bse_valid = True
                    elif res.session_phase in (MarketSessionPhase.POST_MARKET, MarketSessionPhase.HISTORICAL):
                        if bse_dt.time() >= dtime(15, 0, 0) and is_bse_archive_confirmed:
                            bse_valid = True
                        elif not is_bse_archive_confirmed:
                            res.degradation_reasons.append("北交所无独立官方归档完成标识，全市场总额置空")
                    elif res.session_phase == MarketSessionPhase.PRE_MARKET:
                        if is_zero_semantic_verified and bse_dec == Decimal(0) and bse_volume == 0:
                            bse_valid = True
            else:
                if bse_dt.time() >= dtime(15, 0, 0) and is_bse_archive_confirmed:
                    bse_valid = True
                elif not is_bse_archive_confirmed:
                    res.degradation_reasons.append("北交所历史数据无独立官方归档完成标识，全市场总额置空")

    # 全市场总额：仅当两市总额已产生且北交所来源核准且有效时才合成，否则严格为 None，标记 PARTIAL
    if res.two_markets_total_yi is not None and is_bse_verified and bse_valid and bse_dec is not None:
        all_tot_dec = (sh_dec + sz_dec) + bse_dec
        res.all_markets_total_yi = round_yi_float(all_tot_dec, 2)
        res.all_markets_quality = res.two_markets_quality
    else:
        res.all_markets_total_yi = None
        if not is_bse_verified or not bse_valid:
            res.all_markets_quality = DataQualityGrade.PARTIAL
            if bse_dec is None:
                res.degradation_reasons.append("北交所数据缺失，全市场总额置空并标记 PARTIAL")
            elif not is_bse_verified:
                res.degradation_reasons.append("北证50/北交所口径待核准，不可合成全市场正式总额")
            else:
                res.degradation_reasons.append("北交所数据时效过期或时态不匹配，全市场正式总额置空")
        else:
            res.all_markets_quality = res.two_markets_quality

    return res
