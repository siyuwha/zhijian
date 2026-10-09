"""
Phase 2D.3-B: Briefing Safety Guard Service
===========================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-B 授权与安全防线规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 充当战报生成链路的“后置物理拦截审查器” (Post-Generation Hard Interceptor)；
- 100% 杜绝 LLM 幻觉数字漂移 (Numerical Fidelity Guard)；
- 100% 杜绝实体身份漂移，坚决防御 002242 -> 毅昌科技 (Entity Identity Guard)；
- 100% 拦截一切 L5 买卖/仓位交易指令与价格预测 (Illegal Directive Defense)；
- 100% 校验长度、排版与必备证据锚点 (Structure & Speech Boundary Guard)；
- 审查不通过则返回明确 violations，触发无感安全降级。
"""

import re
import math
import unicodedata
from datetime import datetime
from typing import List, Dict, Optional, Set, Any
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.schemas.canonical_market import CanonicalSecurityIdentity
from backend.app.services.canonical_market_service import CanonicalSecurityMasterRegistry


def canonical_round_decimal(val: float | int | str | Decimal, precision: int = 2) -> Decimal:
    """
    确定性规范四舍五入算法 (ROUND_HALF_UP, 严格规避 Python float banker's rounding ties-to-even 漂移)

    安全不变量：
    1. 拒绝空值 (None)、布尔值 (bool，由于 Python bool 是 int 子类需显式拦截) 与非法类型；
    2. 拒绝 NaN、+Infinity、-Infinity 极端无效值；
    3. 支持任意精度字符串与整型无损转换；
    4. 对浮点数采用原生最短往返无损表达 (Python 3.12 Grisu3 str(val))，废除硬编码 8 位截断；
    5. 严格遵循远离零舍入 (Round half away from zero，正负数绝对对称，消除负零 -0)；
    6. 支持任意合理整数 precision ([-50, 50]，支持正数或负数精度)。
    """
    if val is None:
        raise ValueError("Canonical rounding error: input value cannot be None")

    if isinstance(val, bool):
        raise ValueError(f"Canonical rounding error: boolean values are not supported, got bool '{val}'")

    if isinstance(val, (int, str)):
        try:
            val_cleaned = str(val).strip()
            if not val_cleaned:
                raise ValueError("Canonical rounding error: empty numeric string")
            d = Decimal(val_cleaned)
        except InvalidOperation as e:
            raise ValueError(f"Canonical rounding error: invalid numeric literal '{val}': {e}")
    elif isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Canonical rounding error: cannot round NaN or Infinite float value '{val}'")
        # Python 3.12 float str() uses Grisu3 algorithm, giving the exact shortest lossless decimal representation
        d = Decimal(str(val))
    elif isinstance(val, Decimal):
        d = val
    else:
        raise ValueError(f"Canonical rounding error: unsupported input type '{type(val).__name__}'")

    if d.is_nan() or d.is_infinite():
        raise ValueError(f"Canonical rounding error: Decimal value cannot be NaN or Infinite: '{d}'")

    if not isinstance(precision, int) or isinstance(precision, bool):
        raise ValueError(f"Canonical rounding error: precision must be an integer, got '{type(precision).__name__}'")

    if not (-50 <= precision <= 50):
        raise ValueError(f"Canonical rounding error: precision out of reasonable bounds [-50, 50], got {precision}")

    if precision < 0:
        target = Decimal(f"1e{-precision}")
        res = d.quantize(target, rounding=ROUND_HALF_UP).quantize(Decimal("1"))
    elif precision == 0:
        res = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        target = Decimal(f"1e{-precision}")
        res = d.quantize(target, rounding=ROUND_HALF_UP)

    # 规范化负零 (Normalize -0 / -0.0 to 0)
    if res == 0:
        res = Decimal("0").quantize(res)

    return res




# 绝对禁止出现的 L5 交易指令与主观操作引导词汇 (含显式指令、隐蔽式变相诱导与行为劝诫指令)
FORBIDDEN_DIRECTIVE_TERMS: List[str] = [
    # 显式交易动作 (L5 硬隔离)
    "买入", "卖出", "加仓", "减仓", "建仓", "满仓", "半仓", "清仓",
    "抄底", "割肉", "冲锋", "梭哈", "追高", "建议操作", "目标价",
    "止盈", "止损", "开仓", "平仓", "重仓", "轻仓", "打板买入",
    # 隐蔽式/变相交易诱导词 (P0-2 对抗测试防护)
    "低吸", "低吸机会", "关注低吸", "逢低布局", "逢低介入", "逢低吸纳",
    "逢阴低吸", "水下低吸", "轻仓试错", "试错机会", "建底仓", "分批建仓",
    "逢高减持", "逢高派发", "获利了结", "及时止盈", "做多机会", "积极做多",
    "上车", "上车机会", "立即上车", "下车", "及时下车", "提前潜伏", "博弈反弹",
    "买点", "卖点", "加仓点", "减仓点", "建仓点",
    # 隐蔽进出场及仓位诱导 (DOC-90 Item A 抗规避近义词扩充)
    "进场良机", "果断进场", "逢低进场", "分批进场", "择机进场", "随时进场", "择机介入",
    "落袋为安", "锁定利润", "断臂求生", "割肉离场",
    "打底仓", "首仓试错", "分批吸纳", "逢低加码", "积极加码", "择机加码",
    "建议配置", "重点配置", "纳入组合", "配置建议",
    # 操作劝诱与交易员行为劝诫词汇 (DOC-87 审计整改：杜绝任何第二人称或无主语行为指令)
    "杜绝逆势博弈", "严守核心龙头竞价承接红线", "严守竞价承接红线", "严守承接红线",
    "严守交易纪律", "严守操作纪律", "控制仓位", "持币观望", "空仓观望", "保持克制",
    "杜绝盲目出手", "切忌逆势接力", "切忌盲目追高"
]

# 拼音与音近变体 (Item A 规避防御)
PHONETIC_DIRECTIVE_TERMS: List[str] = [
    "mairu", "dixi", "shangche", "chaodi", "zuoduo",
    "mai_ru", "di_xi", "shang_che", "chao_di", "zuo_duo",
    "jiacang", "jiancang", "jia_cang", "jian_cang",
    "pingcang", "kaicang", "zhiying", "zhisun",
]

# 同形近形字混淆映射 (Homoglyphs: Cyrillic/Greek/Fullwidth -> Latin)
HOMOGLYPH_TRANSLATION_TABLE = str.maketrans({
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x',
    'і': 'i', 'ј': 'j', 'ѕ': 's', 'А': 'A', 'Е': 'E', 'О': 'O', 'Р': 'P',
    'С': 'C', 'У': 'Y', 'Х': 'X',
})

# 隔字插入标点与空白容差正则 (仅匹配非词标点与空白符号，绝不匹配中文字符 \w)
SEP_PATTERN = r'[\s\W_·\-\*\/\~`\!@#\$%\^&\*\(\)_\+=\[\]\{\}\|:;\"\'<>\,\.\?\/、]{0,6}?'

# 隐蔽式间接交易指令与行为操作劝诫正则拦截模式 (P0-2 & DOC-87 审计整改)
INDIRECT_DIRECTIVE_REGEX: List[str] = [
    # 1. 变相建仓/买入诱导 (必须携带诱导后缀：机会/标的/节奏/良机)
    r'(?:建议|提示|可|不妨|积极|重点)?[^，。；\n]{0,6}?(?:低吸|逢低|介入|布局|建仓|上车|试错|做多|进场|吸纳)(?:机会|标的|节奏|良机)',
    # 2. 抄底与左侧诱导
    r'逢[低阴弱][^，。；\n]{0,6}?(?:低吸|介入|布局|买入|建仓|进场|加码)',
    # 3. 卖出/兑现诱导
    r'逢[高阳强][^，。；\n]{0,6}?(?:派发|减持|减仓|兑现|出局|止盈|离场|了结)',
    # 4. 盘中激进指令
    r'(?:集合竞价|开盘|盘中)[^，。；\n]{0,8}?(?:上车|介入|买入|冲锋|进场)',
    # 5. 提前博弈指令
    r'提前(?:潜伏|埋伏)[^，。；\n]{0,6}?(?:博弈|等待)',
    # 6. 操作性劝诱与禁止性行为指令 (针对交易员发出的命令/劝告)
    r'(?:杜绝|严禁|切忌|切勿|切莫|务必|坚决|不可|万不可|千万不要)[^，。；\n]{0,10}?(?:逆势|博弈|操作|开仓|交易|接力|抄底|追高|做多|做空|试错|格局|出手|盲目)',
    # 7. 主观风控/承接红线指令 (向交易员命令“严守...红线/纪律”)
    r'严守[^，。；\n]{0,14}?(?:红线|底线|纪律|原则|承接)',
    # 8. 仓位控制指令 (向交易员命令“控制/压缩仓位”)
    r'(?:(?:建议|必须|应当|务必|切忌|严禁|不可|操作上|策略上|交易上)[^，。；\n]{0,6}?(?:控制|降低|压缩|减少|锁定|调整)[^，。；\n]{0,4}?(?:仓位|仓况|风险敞口))|(?:(?:降低|压缩|控制|减轻|清空|锁定)[^，。；\n]{0,4}?(?:仓位|仓况|头寸))|(?:(?:建议|必须|应当|务必|切忌|严禁|不可|操作上|策略上|交易上)[^，。；\n]{0,6}?(?:空仓|清仓|持币|满仓|半仓|重仓|轻仓|锁仓|观望))',
    # 9. 行为态度命令 (向交易员命令“保持观望/克制/谨慎/防御”)
    r'(?:建议|不妨|务必|切忌|请|操作上|策略上)[^，。；\n]{0,4}?(?:保持|采取)[^，。；\n]{0,4}?(?:观望|克制|谨慎|防御)',
    # 10. 警示性操作命令
    r'(?:严防|谨防|戒备)[^，。；\n]{0,8}?(?:追高|被套|回撤|踩雷)',
]


class BriefingSafetyGuard:
    """
    战报安全合规审查器 (BriefingSafetyGuard)
    双轨物理拦截，确保对外发布的每一份战报在数学、实体、法律和风控上绝对保真。
    """

    def __init__(self, registry: Optional[CanonicalSecurityMasterRegistry] = None):
        self.custom_registry = registry

    def audit(
        self,
        report_or_text: str | TacticalBriefingReport,
        context: NarrativeContextContract,
        key_battlegrounds: Optional[List[str]] = None,
        risk_warnings: Optional[List[str]] = None,
        next_day_observation_posts: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
    ) -> SafetyAuditResult:
        """
        全量执行四大安全合规审查项：
        1. 数字保真度审查 (Numerical Fidelity)
        2. 标的身份单射与 002242 防御审查 (Entity Master Binding)
        3. 交易指令与发言禁区拦截审查 (Illegal Directive Defense)
        4. 结构完整度与必备证据锚点审查 (Structure & Anchors)
        """
        if isinstance(report_or_text, TacticalBriefingReport):
            text = report_or_text.tactical_briefing_text
            battlegrounds = report_or_text.key_battlegrounds
            risks = report_or_text.risk_warnings
            observations = report_or_text.next_day_observation_posts
        else:
            text = str(report_or_text)
            battlegrounds = key_battlegrounds or []
            risks = risk_warnings or []
            observations = next_day_observation_posts or []

        violations: List[str] = []
        checks_run: List[str] = [
            "NumericalFidelityGuard",
            "EntityMasterIntegrityGuard",
            "IllegalDirectiveDefense",
            "StructureAndAnchorsGuard",
        ]

        # 1. 数字保真度审查
        violations.extend(self._check_numerical_fidelity(text, context))

        # 2. 实体身份单射与 002242 防御审查
        violations.extend(self._check_entity_master_binding(text, context))

        # 3. 交易指令与发言边界拦截审查
        violations.extend(
            self._check_illegal_directives(
                text=text,
                battlegrounds=battlegrounds,
                risks=risks,
                observations=observations,
                context=context,
            )
        )

        # 4. 结构完整度与必备证据锚点审查
        violations.extend(
            self._check_structure_and_anchors(
                report_or_text=report_or_text,
                text=text,
                battlegrounds=battlegrounds,
                risks=risks,
                observations=observations,
                context=context,
            )
        )

        passed = len(violations) == 0
        audited_at = datetime.now().isoformat()

        return SafetyAuditResult(
            passed=passed,
            trade_date=context.trade_date,
            trace_id=trace_id,
            audited_at=audited_at,
            checks_run=checks_run,
            violations=violations,
            sanitized_text=text if passed else None,
        )

    # -------------------------------------------------------------------------
    # 审查项 1: 数字保真度审查 (Numerical Fidelity - Decimal Canonical Matching)
    # -------------------------------------------------------------------------
    def _check_numerical_fidelity(
        self, text: str, context: NarrativeContextContract
    ) -> List[str]:
        violations: List[str] = []

        # 1.1 总成交额规范化解析与字段级精确匹配 (Decimal Canonical Matching)
        turnover_patterns = [
            r'(?:两市|沪深两市)?(?:真实)?(?:总成交额|总成交|成交额|成交金额)[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*(万亿元|万亿|亿元|亿)',
            r'([0-9]+(?:\.[0-9]+)?)\s*(万亿元|万亿|亿元|亿)[^，。；\n]{0,10}?(?:的总成交|成交额)',
        ]
        true_turnover = context.fact_layer.turnover.total_turnover_yi  # 16821.09
        for pat in turnover_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                # 排除沪市/深市前缀防止误匹配
                start_idx = max(0, m.start() - 6)
                prefix_context = text[start_idx:m.start()]
                if "沪市" in prefix_context or "深市" in prefix_context:
                    continue

                raw_num_str = m.group(1)
                unit = m.group(2)
                is_valid = False

                if "万亿" in unit:
                    norm_val = Decimal(raw_num_str) * Decimal('10000')
                    true_dec = canonical_round_decimal(true_turnover, 2)
                    abs_diff = abs(norm_val - true_dec)
                    # 对于万亿单位，必须具有足够精度 (有效误差 <= 0.5 亿元)
                    if abs_diff <= Decimal('0.5'):
                        is_valid = True
                    diff_report = f"{abs_diff}亿"
                else:
                    raw_dec = Decimal(raw_num_str)
                    dec_places = len(raw_num_str.split(".")[1]) if "." in raw_num_str else 0
                    expected_dec = canonical_round_decimal(true_turnover, dec_places)
                    abs_diff = abs(raw_dec - expected_dec)
                    if raw_dec == expected_dec:
                        is_valid = True
                    diff_report = f"{abs_diff}亿"

                if not is_valid:
                    violations.append(
                        f"NumericalFidelityViolation: Total turnover '{raw_num_str} {unit}' (normalized: {norm_val if '万亿' in unit else raw_dec:.2f}亿) "
                        f"diverges from true fact '{true_turnover:.2f}亿' "
                        f"(violates canonical value matching, divergence: {diff_report} beyond canonical rounding boundary)"
                    )

        # 1.2 沪深两市分市场成交额规范化解析 (Decimal Canonical Matching)
        sh_patterns = [
            r'沪市\s*(?:成交额|成交金额|成交|为|达)?\s*([0-9]+(?:\.[0-9]+)?)\s*(万亿元|万亿|亿元|亿)',
        ]
        true_sh = context.fact_layer.turnover.sh_amount_yi  # 8111.83
        for pat in sh_patterns:
            for m in re.finditer(pat, text):
                raw_num_str = m.group(1)
                unit = m.group(2)
                is_valid = False
                if "万亿" in unit:
                    norm_val = Decimal(raw_num_str) * Decimal('10000')
                    true_dec = canonical_round_decimal(true_sh, 2)
                    if abs(norm_val - true_dec) <= Decimal('0.5'):
                        is_valid = True
                else:
                    raw_dec = Decimal(raw_num_str)
                    dec_places = len(raw_num_str.split(".")[1]) if "." in raw_num_str else 0
                    expected_dec = canonical_round_decimal(true_sh, dec_places)
                    if raw_dec == expected_dec:
                        is_valid = True
                if not is_valid:
                    violations.append(
                        f"NumericalFidelityViolation: SH turnover '{raw_num_str} {unit}' "
                        f"diverges from true fact '{true_sh:.2f}亿'"
                    )

        sz_patterns = [
            r'深市(?:含创业板)?\s*(?:成交额|成交金额|成交|为|达)?\s*([0-9]+(?:\.[0-9]+)?)\s*(万亿元|万亿|亿元|亿)',
        ]
        true_sz = context.fact_layer.turnover.sz_total_amount_yi  # 8709.26
        for pat in sz_patterns:
            for m in re.finditer(pat, text):
                raw_num_str = m.group(1)
                unit = m.group(2)
                is_valid = False
                if "万亿" in unit:
                    norm_val = Decimal(raw_num_str) * Decimal('10000')
                    true_dec = canonical_round_decimal(true_sz, 2)
                    if abs(norm_val - true_dec) <= Decimal('0.5'):
                        is_valid = True
                else:
                    raw_dec = Decimal(raw_num_str)
                    dec_places = len(raw_num_str.split(".")[1]) if "." in raw_num_str else 0
                    expected_dec = canonical_round_decimal(true_sz, dec_places)
                    if raw_dec == expected_dec:
                        is_valid = True
                if not is_valid:
                    violations.append(
                        f"NumericalFidelityViolation: SZ turnover '{raw_num_str} {unit}' "
                        f"diverges from true fact '{true_sz:.2f}亿'"
                    )

        # 1.3 炸板率规范化解析与字段级精确匹配 (ROUND_HALF_UP Canonical Matching)
        broken_patterns = [
            r'(?:真实)?炸板率[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*%',
            r'([0-9]+(?:\.[0-9]+)?)\s*%[^，。；\n]{0,10}?(?:真实)?炸板率',
        ]
        true_broken_pct = context.derived_layer.broken_limit_ratio * 100  # 42.67
        for pat in broken_patterns:
            for m in re.finditer(pat, text):
                raw_pct_str = m.group(1)
                raw_dec = Decimal(raw_pct_str)
                dec_places = len(raw_pct_str.split(".")[1]) if "." in raw_pct_str else 0
                expected_dec = canonical_round_decimal(true_broken_pct, dec_places)
                if raw_dec != expected_dec:
                    violations.append(
                        f"NumericalFidelityViolation: Broken limit ratio '{raw_pct_str}%' diverges from derived fact "
                        f"'{true_broken_pct:.2f}%' (violates canonical value matching)"
                    )

        # 1.4 极值亏损率规范化解析 (ROUND_HALF_UP Canonical Matching)
        loss_patterns = [
            r'极值亏损率[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*%',
            r'([0-9]+(?:\.[0-9]+)?)\s*%[^，。；\n]{0,10}?极值亏损率',
        ]
        true_loss_pct = context.derived_layer.extreme_loss_ratio * 100  # 60.0
        for pat in loss_patterns:
            for m in re.finditer(pat, text):
                raw_pct_str = m.group(1)
                raw_dec = Decimal(raw_pct_str)
                dec_places = len(raw_pct_str.split(".")[1]) if "." in raw_pct_str else 0
                expected_dec = canonical_round_decimal(true_loss_pct, dec_places)
                if raw_dec != expected_dec:
                    violations.append(
                        f"NumericalFidelityViolation: Extreme loss ratio '{raw_pct_str}%' diverges from derived fact "
                        f"'{true_loss_pct:.2f}%'"
                    )

        # 1.5 指数极差离散度规范化解析 (ROUND_HALF_UP Canonical Matching)
        disp_patterns = [
            r'(?:指数)?(?:极差)?离散度[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*%',
            r'([0-9]+(?:\.[0-9]+)?)\s*%[^，。；\n]{0,10}?(?:指数)?(?:极差)?离散度',
        ]
        true_disp_pct = context.derived_layer.state_features.index_vector.dispersion_pct  # 4.03
        for pat in disp_patterns:
            for m in re.finditer(pat, text):
                raw_pct_str = m.group(1)
                raw_dec = Decimal(raw_pct_str)
                dec_places = len(raw_pct_str.split(".")[1]) if "." in raw_pct_str else 0
                expected_dec = canonical_round_decimal(true_disp_pct, dec_places)
                if raw_dec != expected_dec:
                    violations.append(
                        f"NumericalFidelityViolation: Index dispersion '{raw_pct_str}%' diverges from derived fact "
                        f"'{true_disp_pct:.2f}%'"
                    )

        # 1.6 空间最高板高度强离散校验 (精确等于整数)
        space_leader_patterns = [
            r'(?:最高空间标杆|空间标杆|高度标杆|全市场最高连板高度标杆为|全市场最高板|最高连板|最高板)[^，。；\n]{0,20}?([0-9]+)\s*(?:连板|板|B)',
            r'([0-9]+)\s*(?:连板|板|B)[^，。；\n]{0,15}?(?:最高空间标杆|空间标杆|高度标杆)',
        ]
        true_max_height = context.fact_layer.ladder.max_height
        for pat in space_leader_patterns:
            for m in re.finditer(pat, text):
                val = int(m.group(1))
                if val != true_max_height:
                    violations.append(
                        f"NumericalFidelityViolation: Space leader max height '{val}B' diverges from true fact "
                        f"'{true_max_height}B'"
                    )

        # 1.7 全市场涨停家数强离散校验 (全市场维度)
        full_limit_up_patterns = [
            r'(?:全市场|两市|共计|共有|共)(?:收盘|封死)?涨停[^，。；\n]{0,10}?([0-9]+)\s*(?:只|家)',
        ]
        true_limit_up = context.fact_layer.sentiment_counts.limit_up_count  # 43
        for pat in full_limit_up_patterns:
            for m in re.finditer(pat, text):
                val = int(m.group(1))
                if val != true_limit_up:
                    violations.append(
                        f"NumericalFidelityViolation: Full market limit up count '{val}' diverges from true fact '{true_limit_up}'"
                    )

        # 1.8 全市场收盘跌停家数强离散校验 (精确等于整数)
        down_patterns = [
            r'(?:收盘)?跌停[^，。；\n]{0,10}?([0-9]+)\s*(?:只|家)',
            r'([0-9]+)\s*(?:只|家)[^，。；\n]{0,10}?(?:收盘)?跌停',
        ]
        true_down = context.fact_layer.sentiment_counts.limit_down_count
        for pat in down_patterns:
            for m in re.finditer(pat, text):
                val = int(m.group(1))
                if val != true_down:
                    violations.append(
                        f"NumericalFidelityViolation: Limit down count '{val}' diverges from true fact "
                        f"'{true_down}'"
                    )

        # 1.9 商业数据商异动规则撮合标的数强离散校验 (P0-3 语义纠偏与整数匹配)
        reg_patterns = [
            r'(?:商业数据商异动规则撮合|异动规则撮合|严重异常波动|监管异动|商业规则监控)[^，。；\n]{0,20}?([0-9]+)\s*(?:只|家)',
            r'([0-9]+)\s*(?:只|家)[^，。；\n]{0,10}?(?:商业数据商异动规则撮合|异动规则撮合|严重异常波动|监管异动|商业规则监控)',
        ]
        true_anomaly = context.fact_layer.regulatory.total_anomaly_count
        for pat in reg_patterns:
            for m in re.finditer(pat, text):
                val = int(m.group(1))
                if val != true_anomaly:
                    violations.append(
                        f"NumericalFidelityViolation: Regulatory anomaly count '{val}' diverges from true fact "
                        f"'{true_anomaly}' (commercial anomaly rule match count)"
                    )

        # 1.10 核心主线龙头高度与成分涨停家数校验
        for ml in context.cognition_layer.candidate_mainlines:
            leader_name = ml.leader_identity.canonical_name
            # 龙头高度校验: 龙头【新华传媒】8B
            leader_h_patterns = [
                rf'【{leader_name}】[^。；\n]{{0,10}}?([0-9]+)\s*(?:连板|板|B)',
                rf'([0-9]+)\s*(?:连板|板|B)[^。；\n]{{0,10}}?【{leader_name}】',
            ]
            for l_pat in leader_h_patterns:
                for lm in re.finditer(l_pat, text):
                    val = int(lm.group(1))
                    if val != ml.leader_height:
                        violations.append(
                            f"NumericalFidelityViolation: Leader '{leader_name}' height '{val}B' diverges from true fact '{ml.leader_height}B'"
                        )
            # 主线涨停家数校验: 【央国企改革】...涨停 12 家
            sector_name = ml.sector_name
            sector_cnt_pat = rf'【{sector_name}】[^。；\n]{{0,50}}?涨停\s*([0-9]+)\s*(?:只|家)'
            for sm in re.finditer(sector_cnt_pat, text):
                val = int(sm.group(1))
                if val != ml.limit_up_count:
                    violations.append(
                        f"NumericalFidelityViolation: Sector '{sector_name}' limit up count '{val}' diverges from fact '{ml.limit_up_count}'"
                    )

        # 1.11 核心宽基指数涨跌幅规范化解析与字段级精确匹配 (负数/带符号 Decimal Canonical Matching)
        index_alias_map = {
            "sh000001": ["上证指数", "上证综指", "沪指", "上证"],
            "sz399001": ["深证成指", "深成指"],
            "sz399006": ["创业板指", "创指", "创业板"],
            "sh000688": ["科创50", "科创50指数"],
        }
        for idx in context.fact_layer.indices:
            aliases = index_alias_map.get(idx.symbol, [idx.name])
            aliases_pattern = "|".join([re.escape(a) for a in aliases])
            idx_pattern = rf'(?:{aliases_pattern})[^，。；\n]{{0,15}}?([+-]?[0-9]+(?:\.[0-9]+)?)\s*%'
            for m in re.finditer(idx_pattern, text):
                raw_pct_str = m.group(1)
                full_match_text = m.group(0)
                has_down_verb = any(w in full_match_text for w in ["跌", "挫", "回撤", "跳水", "绿盘"])
                has_up_verb = any(w in full_match_text for w in ["涨", "拉升", "红盘", "飙升"])
                raw_dec = Decimal(raw_pct_str)
                dec_places = len(raw_pct_str.split(".")[1]) if "." in raw_pct_str else 0
                true_pct = idx.pct_change
                expected_dec = canonical_round_decimal(true_pct, dec_places)
                expected_abs = canonical_round_decimal(abs(true_pct), dec_places)
                is_valid = False
                if raw_pct_str.startswith("-") or raw_pct_str.startswith("+"):
                    if raw_dec == expected_dec:
                        is_valid = True
                else:
                    if has_down_verb:
                        if true_pct <= 0 and raw_dec == expected_abs:
                            is_valid = True
                        elif true_pct > 0:
                            violations.append(
                                f"NumericalFidelityViolation: Index '{idx.name}' direction contradicts fact: "
                                f"text indicates decline ('{full_match_text}') but true pct_change is positive (+{true_pct:.2f}%)"
                            )
                            continue
                    elif has_up_verb:
                        if true_pct >= 0 and raw_dec == expected_abs:
                            is_valid = True
                        elif true_pct < 0:
                            violations.append(
                                f"NumericalFidelityViolation: Index '{idx.name}' direction contradicts fact: "
                                f"text indicates gain ('{full_match_text}') but true pct_change is negative ({true_pct:.2f}%)"
                            )
                            continue
                    else:
                        if raw_dec == expected_dec or raw_dec == expected_abs:
                            is_valid = True
                if not is_valid:
                    violations.append(
                        f"NumericalFidelityViolation: Index '{idx.name}' pct_change '{raw_pct_str}%' "
                        f"diverges from true fact '{true_pct:.2f}%' (expected '{expected_dec}%')"
                    )

        return violations

    # -------------------------------------------------------------------------
    # 审查项 2: 实体身份单射与 002242 防御审查
    # -------------------------------------------------------------------------
    def _check_entity_master_binding(
        self, text: str, context: NarrativeContextContract
    ) -> List[str]:
        violations: List[str] = []

        # 2.1 刚性红线: 毅昌科技绝对禁止出现 (002242 历史重大实体混淆防御)
        if "毅昌科技" in text:
            violations.append(
                "EntityIdentityViolation: '毅昌科技' is strictly forbidden in tactical briefing. "
                "Stock '002242' is authoritative '九阳股份', never '毅昌科技'!"
            )

        # 2.2 构建当前合法的个股主数据字典 (从 context 与 custom_registry)
        authorized_identities: Dict[str, str] = {}  # code -> name
        if self.custom_registry:
            for c, id_obj in self.custom_registry.get_dictionary().items():
                authorized_identities[c] = id_obj.canonical_name

        # 从 contract 注入所有已知个股身份
        for tier in context.fact_layer.ladder.tiers:
            for s in tier.stocks:
                authorized_identities[s.stock_code] = s.canonical_name
        authorized_identities[context.fact_layer.ladder.space_leader.stock_code] = (
            context.fact_layer.ladder.space_leader.canonical_name
        )
        for anom in context.fact_layer.regulatory.anomaly_stocks:
            authorized_identities[anom.stock_code] = anom.canonical_name
        for ml in context.cognition_layer.candidate_mainlines:
            authorized_identities[ml.leader_identity.stock_code] = ml.leader_identity.canonical_name

        # 2.3 检查 002242 的映射
        if "002242" in text:
            # 若包含 002242，附近必须不得出现除 九阳股份 之外的错误名称
            surrounding = text[max(0, text.find("002242") - 20) : min(len(text), text.find("002242") + 30)]
            if "毅昌科技" in surrounding:
                violations.append(
                    "EntityIdentityViolation: Code '002242' associated with '毅昌科技' detected in text."
                )

        # 2.4 扫描文本中出现的 6 位股票代码，必须属于 authorized_identities (排除浮点数小数部分)
        code_matches = re.findall(r'(?<![.\d])([0-368][0-9]{5})(?![.\d])', text)
        for code in code_matches:
            if code not in authorized_identities:
                violations.append(
                    f"EntityIdentityViolation: Unregistered security code referenced in briefing text: '{code}'"
                )

        return violations

    @staticmethod
    def _normalize_text_for_defense(text: str) -> str:
        """
        深度文本规范化 (DOC-90 Item A 抗规避防线):
        1. Unicode NFKC 兼容性等价分解与重组 (全角字母/数字/标点转半角);
        2. 剥离不可见字符、零宽连字/断字符、格式控制符 (如 \u200b-\u200f, \ufeff, \u00ad);
        3. 同形字符 (Homoglyphs Cyrillic -> Latin) 映射归一化;
        4. 保留原始中文字符与规范化标点供正则分析。
        """
        if not text:
            return ""
        # 1. NFKC 规范化 (全角转半角，复合字分解)
        norm = unicodedata.normalize('NFKC', text)
        # 2. 移除零宽字符、软连字符、不可见格式符
        norm = re.sub(r'[\u200b-\u200f\u2028-\u202f\ufeff\u00ad\u2060\u180e]', '', norm)
        # 3. 同形字替换
        norm = norm.translate(HOMOGLYPH_TRANSLATION_TABLE)
        return norm

    # -------------------------------------------------------------------------
    # 审查项 3: 交易指令与发言禁区拦截审查 (Illegal Directive Defense)
    # -------------------------------------------------------------------------
    def _check_illegal_directives(
        self,
        text: str,
        battlegrounds: List[str],
        risks: List[str],
        observations: List[str],
        context: NarrativeContextContract,
    ) -> List[str]:
        violations: List[str] = []

        all_content_blocks = [text] + battlegrounds + risks + observations
        combined_text = "\n".join(all_content_blocks)
        norm_combined_text = self._normalize_text_for_defense(combined_text)
        lower_norm = norm_combined_text.lower()

        # 3.1 拼音与音近变体指令扫描 (Pinyin / Phonetic Evasion Defense)
        for p_term in PHONETIC_DIRECTIVE_TERMS:
            # 采用字母断言边界，在中英文混排下精准捕获，且不误伤长英文单词
            if re.search(rf'(?<![a-zA-Z]){re.escape(p_term)}(?![a-zA-Z])', lower_norm):
                violations.append(
                    f"IllegalDirectiveViolation: Covert phonetic/pinyin trading directive detected: '{p_term}'"
                )

        # 3.2 违规 L5 交易指令词汇与隔字插入对抗扫描 (显式、隐蔽短语及标点/空白插入绕过)
        for term in FORBIDDEN_DIRECTIVE_TERMS:
            # 对于2字以上的中文违规词，构造隔字标点/空白容差模式 (如 "买·入", "买/入", "买 入", "低*吸", "建_仓")
            if len(term) >= 2 and all('\u4e00' <= c <= '\u9fff' for c in term[:2]):
                chars = list(term)
                pat = SEP_PATTERN.join(re.escape(c) for c in chars)
                m = re.search(pat, norm_combined_text)
                if m:
                    violations.append(
                        f"IllegalDirectiveViolation: Forbidden L5 trading directive term detected: '{term}' (matched snippet '{m.group(0)}')"
                    )
            else:
                if term in norm_combined_text or term in combined_text:
                    violations.append(
                        f"IllegalDirectiveViolation: Forbidden L5 trading directive term detected: '{term}'"
                    )

        # 3.3 隐蔽式间接交易指令正则匹配 (P0-2 变相交易诱导拦截)
        for reg_pat in INDIRECT_DIRECTIVE_REGEX:
            m = re.search(reg_pat, norm_combined_text)
            if m:
                matched_snippet = m.group(0)
                v_msg = f"IllegalDirectiveViolation: Indirect trading inducement detected matching pattern '{matched_snippet}'"
                if v_msg not in violations:
                    violations.append(v_msg)

        # 3.4 预测具体目标价 / 买卖点位扫描
        price_target_patterns = [
            r'目标价\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?\s*元?',
            r'上看\s*[0-9]+(?:\.[0-9]+)?\s*元',
            r'买入点\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?',
            r'止损价\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?',
        ]
        for pat in price_target_patterns:
            if re.search(pat, norm_combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Unverified price target / exact trading level prediction detected."
                )
                break

        # 3.5 创业板重复累加会计违规扫描 (REDUNDANT_DOUBLE_COUNT_CLAIMS)
        double_count_patterns = [
            r'加上创业板(?:后)?两市成交',
            r'总成交额加上创业板',
            r'两市加上创业板共',
        ]
        for pat in double_count_patterns:
            if re.search(pat, norm_combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Redundant double-count accounting claim detected "
                    "(ChiNext already included in Shenzhen turnover)."
                )

        # 3.6 主线事实化伪造声明 (COGNITION_TO_FACT_PROMOTION)
        fact_promotion_patterns = [
            r'主线已成为绝对客观事实',
            r'毫无疑问的绝对主线',
        ]
        for pat in fact_promotion_patterns:
            if re.search(pat, norm_combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Cognition-to-fact promotion detected "
                    "(L3 hypothesis promoted to L0 physical truth)."
                )

        # 3.7 伪造官方监管意图/交易所红头文件定性 (P0-3 事实语义纠偏：阻断主观推断向客观事实渗透)
        regulatory_fake_patterns = [
            r'交易所[^，。；\n]{0,15}?(?:重点监控|下发核查|实施核查|进行监管|明确核查|官方监控)',
            r'交易所[^，。；\n]{0,10}?(?:定性为|认定为)?严重异动',
            r'监管部门[^，。；\n]{0,10}?(?:定性为|特停|明确监管)',
        ]
        for pat in regulatory_fake_patterns:
            if re.search(pat, norm_combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Subjective promotion of commercial data vendor rule match "
                    "to official Exchange administrative surveillance detected."
                )
                break

        return violations

    # -------------------------------------------------------------------------
    # 审查项 4: 结构完整度与必备证据锚点审查 (Structure & Anchors)
    # -------------------------------------------------------------------------
    def _check_structure_and_anchors(
        self,
        text: str,
        battlegrounds: List[str],
        risks: List[str],
        observations: List[str],
        context: NarrativeContextContract,
        report_or_text: Optional[Any] = None,
    ) -> List[str]:
        violations: List[str] = []

        # 4.1 文本长度校验 (150 ~ 600 字，设计区间 250 ~ 350 字)
        clean_text = text.strip()
        if len(clean_text) < 150:
            violations.append(
                f"StructureViolation: Tactical briefing text is too short ({len(clean_text)} chars, minimum is 150)"
            )
        elif len(clean_text) > 600:
            violations.append(
                f"StructureViolation: Tactical briefing text is too long ({len(clean_text)} chars, maximum is 600)"
            )

        # 4.2 结构列表非空校验 (若审查完整报告，或调用方显式提供了结构化列表)
        if isinstance(report_or_text, TacticalBriefingReport):
            if not battlegrounds:
                violations.append("StructureViolation: 'key_battlegrounds' list cannot be empty")
            if not risks:
                violations.append("StructureViolation: 'risk_warnings' list cannot be empty")
            if not observations:
                violations.append("StructureViolation: 'next_day_observation_posts' list cannot be empty")

        # 4.3 必备证据锚点校验 (至少覆盖 3 个)
        anchors_found = 0
        # 锚点 A: 成交额
        if re.search(r'(?:成交额|成交金额|总成交)', clean_text):
            anchors_found += 1
        # 锚点 B: 空间最高板或连板高度
        if str(context.fact_layer.ladder.max_height) in clean_text or "空间" in clean_text:
            anchors_found += 1
        # 锚点 C: 炸板率或负反馈
        if "炸板" in clean_text or "跌停" in clean_text:
            anchors_found += 1
        # 锚点 D: 市场状态
        if context.cognition_layer.market_state.state_display_name in clean_text:
            anchors_found += 1
        # 锚点 E: 核心主线龙头
        if context.cognition_layer.candidate_mainlines:
            top_leader = context.cognition_layer.candidate_mainlines[0].leader_identity.canonical_name
            if top_leader in clean_text:
                anchors_found += 1

        if anchors_found < 3:
            violations.append(
                f"StructureViolation: Insufficient required evidence anchors satisfied (found {anchors_found}, required >= 3)"
            )

        return violations
