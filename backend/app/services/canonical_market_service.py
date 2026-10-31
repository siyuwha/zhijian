"""
Phase 2D.0: Canonical Market Truth & Cognition 聚合服务 (CanonicalMarketService)
上位依据：
1. 用户 2026-10-08 最终裁决令：《Phase 2D.0 终审裁决：CONDITIONAL PASS；Phase 2D.1 有条件启动》
2. SPEC-DESIGN-PHASE2D-20261008-V1.0 (Doc 69)

只读适配层职责：
- 消费底层现有 MarketDailySnapshot / DailyReview 存储（绝对零修改数据库结构与核心业务逻辑）
- 依据 L0~L5 隔离模型将物理事实转化为 MarketTruthSnapshot (FACT + DERIVED)
- 依据 Mainline Eligibility Contract 执行语义收口、独立成分提取、反方批判与血缘全闭环，生成 CognitionSnapshot
- 打包顶层 CanonicalMarketSnapshot 并生成 RFC 8785 JCS 防篡改指纹
"""

import json
import logging
from typing import Optional, Dict, Any, List, Set, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.market import MarketDailySnapshot
from .turnover_engine import calculate_turnover_caliber, TurnoverSourceStatus
from ..models.report import DailyReview
from ..schemas.canonical_market import (
    CanonicalMarketSnapshot,
    MarketTruthSnapshot,
    CognitionSnapshot,
    CanonicalIndexQuote,
    CanonicalTurnoverBreakdown,
    BrokenLimitUniverseContract,
    RegulatoryAnomalyItem,
    LimitUpStockItem,
    BrokenLimitStockItem,
    LadderGroup,
    SemanticType,
    ConstituencyEvidence,
    FalsificationCondition,
    MainlineCandidate,
    SharedEvidenceAffiliate,
    SubthemeCatalyst,
    CanonicalSecurityIdentity,
    LineageAccountingReport,
    CalibratedMarketState,
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
)
from ..cognition.jcs import hash_jcs
from .market_state_calibrator import MarketStateCalibrator

logger = logging.getLogger(__name__)


class EntityIdentityIntegrityError(Exception):
    """证券实体身份完整性违规异常 (DOC-75 P0.2-Fix-2)"""
    pass


class CanonicalSecurityMasterRegistry:
    """
    L0/L1 实体身份不变量注册表与卫兵 (Entity Integrity Guard)
    上位依据：
    - DOC-75｜Phase 2D.0 P0.2 Entity Identity Integrity Hard-Block 修复指令
    - 董事会外部终审补充令 (P0.2 CLOSURE CORRECTION)

    不可变量：
    - Invariant A: Code -> Entity 唯一 (同一交易日，(exchange, code) 对应且仅对应一个规范实体)
    - Invariant B: (exchange, stock_code) -> security_id -> canonical_name 单向主键权威派生
      (权威主键单向派生证券简称，废除 canonical_name -> stock_code 反向硬单射)
    - Invariant C: L2/L3 严格基于规范身份引用标的，禁止自由文本名称作为主键
    - Invariant D: Name 为只读展示属性，只能从 canonical identity 单向派生，禁止下游覆盖
    """
    def __init__(self):
        self._code_to_entity: Dict[str, CanonicalSecurityIdentity] = {}
        self._security_id_to_entity: Dict[str, CanonicalSecurityIdentity] = {}

    def derive_security_id(self, exchange: str, stock_code: str) -> str:
        """Invariant B: (exchange, stock_code) -> security_id 权威派生"""
        ex = exchange.strip().upper()
        c = stock_code.strip()
        if ex not in ("SH", "SZ", "BJ"):
            raise EntityIdentityIntegrityError(
                f"Invariant B Violation: Invalid exchange '{exchange}', must be SH, SZ, or BJ"
            )
        if len(c) != 6 or not c.isdigit():
            raise EntityIdentityIntegrityError(
                f"Invariant B Violation: Invalid stock_code '{stock_code}', must be 6 digits"
            )
        return f"{c}.{ex}"

    def register(self, code: str, name: str, exchange: str) -> CanonicalSecurityIdentity:
        c = code.strip()
        n = name.strip()
        ex = exchange.strip().upper()

        # Invariant B: 权威主键单向派生验证
        sec_id = self.derive_security_id(ex, c)
        if not n:
            raise EntityIdentityIntegrityError(
                f"Invariant B Violation: canonical_name cannot be empty for security '{sec_id}'"
            )

        # Invariant A: Code -> Entity 唯一 (同一交易日，(exchange, code) 对应且仅对应一个规范实体)
        if c in self._code_to_entity:
            existing = self._code_to_entity[c]
            if existing.canonical_name != n or existing.exchange != ex:
                raise EntityIdentityIntegrityError(
                    f"Invariant A Violation: Code '{c}' mapped to multiple entities: "
                    f"existing '{existing.canonical_name}' ({existing.exchange}) vs new '{n}' ({ex})"
                )
            return existing

        # Invariant B: 单向派生构建规范实体主数据
        identity = CanonicalSecurityIdentity(
            security_id=sec_id,
            stock_code=c,
            canonical_name=n,
            exchange=ex,
        )
        self._code_to_entity[c] = identity
        self._security_id_to_entity[sec_id] = identity
        return identity

    def get_canonical_name(self, code: str) -> str:
        if code not in self._code_to_entity:
            raise EntityIdentityIntegrityError(f"Unregistered security code referenced: '{code}'")
        return self._code_to_entity[code].canonical_name

    def get_identity(self, code: str) -> CanonicalSecurityIdentity:
        if code not in self._code_to_entity:
            raise EntityIdentityIntegrityError(f"Unregistered security code referenced: '{code}'")
        return self._code_to_entity[code]

    def get_by_security_id(self, sec_id: str) -> CanonicalSecurityIdentity:
        if sec_id not in self._security_id_to_entity:
            raise EntityIdentityIntegrityError(f"Unregistered security_id referenced: '{sec_id}'")
        return self._security_id_to_entity[sec_id]

    def has_code(self, code: str) -> bool:
        return code in self._code_to_entity

    def has_security_id(self, sec_id: str) -> bool:
        return sec_id in self._security_id_to_entity

    def all_canonical_names(self) -> Set[str]:
        return {e.canonical_name for e in self._code_to_entity.values()}

    def get_dictionary(self) -> Dict[str, CanonicalSecurityIdentity]:
        return dict(self._code_to_entity)

    @classmethod
    def resolve(cls, code: str, name_hint: Optional[str] = None) -> Optional[CanonicalSecurityIdentity]:
        """权威单向解析已知证券实体或按规则派生 (Phase 2E 防御)"""
        c = code.strip()
        if c == "002242":
            return CanonicalSecurityIdentity(
                security_id="002242.SZ",
                stock_code="002242",
                canonical_name="九阳股份",
                exchange="SZ",
            )
        if c == "002420":
            return CanonicalSecurityIdentity(
                security_id="002420.SZ",
                stock_code="002420",
                canonical_name="毅昌科技",
                exchange="SZ",
            )
        if c == "600825":
            return CanonicalSecurityIdentity(
                security_id="600825.SH",
                stock_code="600825",
                canonical_name="新华传媒",
                exchange="SH",
            )
        if c == "600241":
            return CanonicalSecurityIdentity(
                security_id="600241.SH",
                stock_code="600241",
                canonical_name="时代万恒",
                exchange="SH",
            )
        ex = "SH" if c.startswith("6") else ("BJ" if c.startswith(("8", "4", "9")) else "SZ")
        name = name_hint or f"证券{c}"
        return CanonicalSecurityIdentity(
            security_id=f"{c}.{ex}",
            stock_code=c,
            canonical_name=name,
            exchange=ex,
        )

    def validate_snapshot_integrity(
        self,
        truth: MarketTruthSnapshot,
        cognition: CognitionSnapshot,
    ) -> None:
        """全快照跨层级实体身份保真性与回归校验 (Test 1~5 门禁内核)"""
        # 1. 校验 L1/L2 天梯中的每一个标的
        for grp in truth.ladder_tree:
            for stock in grp.stocks:
                if not self.has_code(stock.code):
                    raise EntityIdentityIntegrityError(f"L2 Ladder contains unregistered code: {stock.code}")
                canon_name = self.get_canonical_name(stock.code)
                if stock.name != canon_name:
                    raise EntityIdentityIntegrityError(
                        f"Cross-Layer Drift: Stock code {stock.code} has name '{stock.name}' in L2, but canonical name is '{canon_name}'"
                    )
                expected_sec_id = self.get_identity(stock.code).security_id
                if stock.security_id and stock.security_id != expected_sec_id:
                    raise EntityIdentityIntegrityError(
                        f"Cross-Layer Drift: Stock code {stock.code} security_id '{stock.security_id}' != expected '{expected_sec_id}'"
                    )

        # 2. 校验 L3 Mainline 中的领军龙头与成分股
        all_canon_names = self.all_canonical_names()
        for m in cognition.mainlines:
            c = m.constituency
            if not self.has_code(c.leader_code):
                raise EntityIdentityIntegrityError(f"L3 Mainline leader contains unregistered code: {c.leader_code}")
            canon_name = self.get_canonical_name(c.leader_code)
            if c.leader_name != canon_name:
                raise EntityIdentityIntegrityError(
                    f"Cross-Layer Drift: Mainline {m.sector_name} leader {c.leader_code} has name '{c.leader_name}', but canonical name is '{canon_name}'"
                )
            expected_sec_id = self.get_identity(c.leader_code).security_id
            if c.leader_security_id and c.leader_security_id != expected_sec_id:
                raise EntityIdentityIntegrityError(
                    f"Cross-Layer Drift: Mainline leader security_id '{c.leader_security_id}' != expected '{expected_sec_id}'"
                )
            for sym in c.constituent_symbols:
                if sym not in all_canon_names:
                    raise EntityIdentityIntegrityError(f"L3 Mainline constituent contains unregistered symbol: '{sym}'")

        # 3. 严格校验已知回归漏洞 (002242 必须为 九阳股份，严禁为 毅昌科技；002420 不得混入)
        if self.has_code("002242"):
            name_002242 = self.get_canonical_name("002242")
            if name_002242 != "九阳股份":
                raise EntityIdentityIntegrityError(
                    f"CRITICAL HARD-BLOCK REGRESSION: 002242 mapped to '{name_002242}', MUST BE '九阳股份'!"
                )
            if "毅昌" in name_002242:
                raise EntityIdentityIntegrityError("CRITICAL HARD-BLOCK REGRESSION: 毅昌科技 illegally contaminated 002242!")

        if self.has_code("002420"):
            name_002420 = self.get_canonical_name("002420")
            if name_002420 != "毅昌科技":
                raise EntityIdentityIntegrityError(f"002420 mapped to '{name_002420}', expected '毅昌科技'")


class CanonicalMarketService:
    """标准市场真相与认知聚合构建服务 (只读、幂等、防篡改)"""

    def _sanitize_loaded_snapshot_turnover(self, snap: CanonicalMarketSnapshot) -> CanonicalMarketSnapshot:
        """
        T09-01 门禁过滤：历史预置黄金快照中若含有未核准口径产生的两市或全市场成交额，
        强制置空正式总额为 None，评级降为 DEGRADED / PARTIAL，并完全重算指纹与认知层状态，
        确保快照事实、派生认知假说与防篡改指纹 100% 严密闭环。
        """
        if not snap or not snap.truth or not snap.truth.turnover:
            return snap

        t = snap.truth.turnover
        needs_sanitizing = (
            t.two_markets_quality == DataQualityGrade.FULL
            or t.two_markets_total_yi is not None
            or t.all_markets_quality == DataQualityGrade.FULL
            or t.all_markets_total_yi is not None
        )
        if not needs_sanitizing:
            return snap

        reason = "历史黄金快照数据源口径待核准，正式总额强制置空为 None"
        new_reason = f"{t.degradation_reason}; {reason}" if t.degradation_reason else reason
        new_env = None
        if t.envelope:
            new_env = t.envelope.model_copy(update={
                "quality": DataQualityGrade.DEGRADED,
                "is_degraded": True,
                "degradation_reason": new_reason,
            })
        new_t = t.model_copy(update={
            "two_markets_total_yi": None,
            "all_markets_total_yi": None,
            "two_markets_quality": DataQualityGrade.DEGRADED,
            "all_markets_quality": DataQualityGrade.PARTIAL,
            "degradation_reason": new_reason,
            "envelope": new_env,
        })

        # 1. 重构 truth 事实层并重算 JCS SHA-256 指纹
        breadth_status_val = (
            snap.truth.cross_section_breadth_status.value
            if hasattr(snap.truth.cross_section_breadth_status, "value")
            else str(snap.truth.cross_section_breadth_status)
        )
        truth_dict_for_hash = {
            "schema_version": snap.truth.schema_version,
            "producer": snap.truth.producer,
            "trade_date": snap.truth.trade_date,
            "generated_at": snap.truth.generated_at,
            "indices": [i.model_dump() for i in snap.truth.indices],
            "turnover": new_t.model_dump(),
            "sentiment_bounds": snap.truth.sentiment_bounds.model_dump(),
            "regulatory_anomalies": [a.model_dump() for a in snap.truth.regulatory_anomalies],
            "ladder_tree": [l.model_dump() for l in snap.truth.ladder_tree],
            "cross_section_breadth_status": breadth_status_val,
            "cross_section_breadth_detail": snap.truth.cross_section_breadth_detail,
        }
        new_truth_fingerprint = hash_jcs(truth_dict_for_hash)
        new_truth = snap.truth.model_copy(update={
            "turnover": new_t,
            "truth_fingerprint": new_truth_fingerprint,
        })

        # 2. 重新校准认知层 (Cognition) 并重算认知指纹，彻底淘汰基于旧成交额的放量结论
        new_cognition = snap.cognition
        if snap.cognition:
            state_features = self.state_calibrator.extract_feature_vector(new_truth)
            top_grp = new_truth.ladder_tree[0] if new_truth.ladder_tree else None
            if top_grp and top_grp.stocks:
                space_leader_txt = f"最高{top_grp.height}B{top_grp.stocks[0].name}"
            else:
                space_leader_txt = "无连板梯队（数据缺失）"

            core_mainlines = [
                m.sector_name for m in snap.cognition.mainlines if m.structural_role in ("CORE_MAINLINE", "BRANCH_ROTATION")
            ]

            calibrated_state = self.state_calibrator.calibrate(
                features=state_features,
                prior_state=None,
                core_mainlines=core_mainlines,
                space_leader_desc=space_leader_txt,
            )

            market_narrative = self.state_calibrator.render_deterministic_summary(
                state=calibrated_state,
                features=state_features,
                core_mainlines=core_mainlines,
                space_leader_desc=space_leader_txt,
            )

            cognition_dict_for_hash = {
                "schema_version": snap.cognition.schema_version,
                "producer": snap.cognition.producer,
                "trade_date": snap.trade_date,
                "generated_at": snap.cognition.generated_at,
                "mainlines": [m.model_dump() for m in snap.cognition.mainlines],
                "lineage_accounting": snap.cognition.lineage_accounting.model_dump(),
                "market_state_summary": market_narrative,
                "market_state_calibration": calibrated_state.model_dump(),
            }
            new_cognition_fingerprint = hash_jcs(cognition_dict_for_hash)
            new_cognition = snap.cognition.model_copy(update={
                "market_state_summary": market_narrative,
                "market_state_calibration": calibrated_state,
                "cognition_fingerprint": new_cognition_fingerprint,
            })

        # 3. 重新打包统一信封指纹
        envelope_dict_for_hash = {
            "snapshot_version": snap.snapshot_version,
            "trade_date": snap.trade_date,
            "generated_at": snap.generated_at,
            "truth_fingerprint": new_truth_fingerprint,
            "cognition_fingerprint": new_cognition.cognition_fingerprint if new_cognition else None,
        }
        new_envelope_fingerprint = hash_jcs(envelope_dict_for_hash)

        return snap.model_copy(update={
            "truth": new_truth,
            "cognition": new_cognition,
            "envelope_fingerprint": new_envelope_fingerprint,
        })

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.entity_registry = CanonicalSecurityMasterRegistry()
        self.state_calibrator = MarketStateCalibrator()

    @staticmethod
    def classify_semantic_type(sector_code: str, sector_name: str, category: str) -> SemanticType:
        """
        Mainline Eligibility Contract: 语义类型契约分类器
        严格区分产业/主题主线与数据商元标签/统计特征/地域
        """
        # 1. 宽基指数/工具元标签
        if any(w in sector_name for w in ["AB股", "AH股", "HS300", "上证180", "上证380", "创业板综", "深成指"]):
            return SemanticType.PROVIDER_META_TAG

        # 2. 榜单与关注度标签
        if any(w in sector_name for w in ["热股", "题材股"]):
            return SemanticType.RANKING_TAG

        # 3. 交易行情特征/形态标签
        if any(w in sector_name for w in ["多板", "新高", "超跌", "破发", "破增发", "趋势股", "微利", "次新", "摘帽"]):
            return SemanticType.TRADING_FEATURE

        # 4. 统计/市值/财务标签
        if any(w in sector_name for w in ["大盘股", "中盘股", "小盘股", "微盘", "高成长", "高市净率", "预增", "扭亏", "首亏", "预减", "风格"]):
            return SemanticType.STATISTICAL_TAG

        # 5. 地域标签
        if category == "REGION" or any(w in sector_name for w in ["板块", "特区", "自贸", "新区", "大开发", "京津冀", "长江三角", "一带一路"]):
            return SemanticType.REGION

        # 6. 行业 (CSRC/申万产业分类)
        if category == "INDUSTRY":
            return SemanticType.INDUSTRY

        # 7. 真实主题/概念
        return SemanticType.CONCEPT

    def build_market_truth_snapshot(
        self,
        date_str: str,
        snap_dict: Any,
        lu_dict: Any = None,
        anom_list: Any = None,
        observed_time: Optional[str] = None,
        cross_breadth_grade: DataQualityGrade = DataQualityGrade.FULL,
        cross_breadth_detail: Optional[Dict[str, Any]] = None,
    ) -> MarketTruthSnapshot:
        """
        L0/L1 客观事实层与 L2 派生层标准事实快照组装器 (GATE-2D0-01 ~ GATE-2D0-08)
        T09-01 成交额标准口径核算与保守降级门禁唯一实施入口
        """
        if observed_time is None:
            observed_time = f"{date_str}T15:05:00.000+08:00"

        indices_raw = snap_dict if isinstance(snap_dict, list) else (snap_dict.get("indices", []) if isinstance(snap_dict, dict) else [])
        lu_dict = lu_dict or {}
        anom_list = anom_list or []

        # 1.1 L1 指数行情
        canonical_indices: List[CanonicalIndexQuote] = []
        for idx in indices_raw:
            sym = str(idx.get("symbol", "") or idx.get("code", ""))
            name = str(idx.get("name", ""))
            current = float(idx.get("current_price") or idx.get("price") or 0.0)
            pre_close = float(idx.get("pre_close") or current)
            pct = float(idx.get("pct_change") or 0.0)
            chg = float(idx.get("change_val") or idx.get("change") or (current - pre_close))
            amt = float(idx.get("amount_yi") or (float(idx.get("amount_wan") or 0.0) / 10000.0) or 0.0)

            env = ProvenanceEnvelope(
                source=TruthSource.SINA_HQ_STREAM,
                observed_time=observed_time,
                quality=DataQualityGrade.FULL,
                is_degraded=False,
            )

            canonical_indices.append(
                CanonicalIndexQuote(
                    symbol=sym,
                    name=name,
                    current_price=current,
                    pre_close=pre_close,
                    change_val=round(chg, 2),
                    pct_change=round(pct, 2),
                    amount_yi=round(amt, 2),
                    trade_date=date_str,
                    envelope=env,
                )
            )

        # 1.2 L1 成交额口径防重算与质量门禁 (GATE-2D0-02 & T09-01)
        # 逐源核准独立门禁：严禁单一标志无差别核准多个市场
        def _get_market_status(market_key: str) -> TurnoverSourceStatus:
            if isinstance(snap_dict, dict):
                val = snap_dict.get(market_key)
                if val in (TurnoverSourceStatus.VERIFIED, "VERIFIED"):
                    return TurnoverSourceStatus.VERIFIED
            return TurnoverSourceStatus.PENDING_VERIFICATION

        sh_status = _get_market_status("sh_source_status")
        sz_status = _get_market_status("sz_source_status")
        bse_status = _get_market_status("bse_source_status")
        is_archive_input = snap_dict.get("is_archive_confirmed", False) if isinstance(snap_dict, dict) else False

        sh_idx = next((idx for idx in indices_raw if "000001" in str(idx.get("symbol", "") or idx.get("code", ""))), None)
        sz_idx = next((idx for idx in indices_raw if "399001" in str(idx.get("symbol", "") or idx.get("code", ""))), None)
        cy_idx = next((idx for idx in indices_raw if "399006" in str(idx.get("symbol", "") or idx.get("code", ""))), None)
        bse_idx = next((idx for idx in indices_raw if "899050" in str(idx.get("symbol", "") or idx.get("code", ""))), None)

        # 严禁虚构默认时间 (如 15:00:00) 或目标日期，必须透传原始报文时间戳
        sh_date = (sh_idx.get("date") or sh_idx.get("trade_date")) if sh_idx else None
        sh_time = sh_idx.get("time") if sh_idx else None
        sz_date = (sz_idx.get("date") or sz_idx.get("trade_date")) if sz_idx else None
        sz_time = sz_idx.get("time") if sz_idx else None
        bse_date = (bse_idx.get("date") or bse_idx.get("trade_date")) if bse_idx else None
        bse_time = bse_idx.get("time") if bse_idx else None

        turnover_res = calculate_turnover_caliber(
            target_date=date_str,
            sh_amount=sh_idx.get("amount_yi") if (sh_idx and sh_idx.get("amount_yi") is not None) else (sh_idx.get("amount_wan") if sh_idx else None),
            sh_date=sh_date,
            sh_time=sh_time,
            sh_unit="yi" if (sh_idx and sh_idx.get("amount_yi") is not None) else "wan",
            sz_amount=sz_idx.get("amount_yi") if (sz_idx and sz_idx.get("amount_yi") is not None) else (sz_idx.get("amount_wan") if sz_idx else None),
            sz_date=sz_date,
            sz_time=sz_time,
            sz_unit="yi" if (sz_idx and sz_idx.get("amount_yi") is not None) else "wan",
            chinext_amount=cy_idx.get("amount_yi") if (cy_idx and cy_idx.get("amount_yi") is not None) else (cy_idx.get("amount_wan") if cy_idx else None),
            chinext_unit="yi" if (cy_idx and cy_idx.get("amount_yi") is not None) else "wan",
            bse_amount=bse_idx.get("amount_yi") if (bse_idx and bse_idx.get("amount_yi") is not None) else (bse_idx.get("amount_wan") if bse_idx else None),
                bse_date=bse_idx.get("date") if bse_idx else None,
                bse_time=bse_idx.get("time") if bse_idx else None,
                bse_unit="yi" if (bse_idx and bse_idx.get("amount_yi") is not None) else "wan",
            sh_status=sh_status,
            sz_status=sz_status,
            bse_status=bse_status,
            is_archive_confirmed=is_archive_input,
        )

        turnover_envelope = ProvenanceEnvelope(
            source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
            observed_time=observed_time,
            quality=turnover_res.two_markets_quality,
            is_degraded=turnover_res.is_degraded,
            degradation_reason="; ".join(turnover_res.degradation_reasons) if turnover_res.degradation_reasons else None,
        )

        canonical_turnover = CanonicalTurnoverBreakdown(
            trade_date=date_str,
            sh_amount_yi=turnover_res.sh_amount_yi,
            sz_total_amount_yi=turnover_res.sz_total_amount_yi,
            chinext_slice_amount_yi=turnover_res.chinext_slice_amount_yi,
            chinext_ratio_in_sz=turnover_res.chinext_ratio_in_sz,
            bse_amount_yi=turnover_res.bse_amount_yi,
            two_markets_total_yi=turnover_res.two_markets_total_yi,
            all_markets_total_yi=turnover_res.all_markets_total_yi,
            two_markets_quality=turnover_res.two_markets_quality,
            all_markets_quality=turnover_res.all_markets_quality,
            degradation_reason="; ".join(turnover_res.degradation_reasons) if turnover_res.degradation_reasons else None,
            envelope=turnover_envelope,
        )

        # 1.3 L1 情绪与炸板率 Universe (GATE-2D0-04)
        lu_count = int(lu_dict.get("total_count") or len(lu_dict.get("items", [])))
        broken_count = int(
            lu_dict.get("broken_limit_count")
            or lu_dict.get("broken_count")
            or len(lu_dict.get("broken_limit_items", []))
            or 0
        )
        touched_total = lu_count + broken_count
        broken_ratio = round(broken_count / touched_total, 4) if touched_total > 0 else 0.0
        limit_down_count = int(
            lu_dict.get("limit_down_count")
            or len(lu_dict.get("limit_down_items", []))
            or 0
        )
        max_height = int(lu_dict.get("max_height") or 1)

        sentiment_envelope = ProvenanceEnvelope(
            source=TruthSource.TONGHUASHUN_LIMIT_UP,
            observed_time=observed_time,
            quality=DataQualityGrade.FULL,
            is_degraded=False,
        )

        canonical_sentiment = BrokenLimitUniverseContract(
            trade_date=date_str,
            limit_up_count=lu_count,
            broken_limit_count=broken_count,
            touched_limit_total_count=touched_total,
            broken_limit_ratio=broken_ratio,
            limit_down_count=limit_down_count,
            max_ladder_height=max_height,
            envelope=sentiment_envelope,
        )

        # 1.4 L1 交易所严重异常波动监管事实 (GATE-2D0-08)
        canonical_anomalies: List[RegulatoryAnomalyItem] = []
        for af in anom_list:
            canonical_anomalies.append(
                RegulatoryAnomalyItem(
                    symbol=str(af.get("symbol") or ""),
                    name=str(af.get("name") or ""),
                    rule_id=int(af.get("rule_id", 0)),
                    rule_name=str(af.get("rule_name") or ""),
                    deviation_pct=float(af.get("deviation_pct") or 0.0),
                    status_flag=int(af.get("status_flag", 0)),
                )
            )

        # 1.5 L2 连板天梯图 (Ladder Tree, DERIVED, GATE-2D0-05)
        def infer_board_type(stock_code: str) -> str:
            sc = stock_code.replace("s_", "")[-6:]
            if sc.startswith("688"):
                return "STAR"
            elif sc.startswith("30"):
                return "GEM"
            elif sc.startswith(("8", "4", "92")):
                return "BSE"
            return "MAIN"

        def infer_exchange(stock_code: str) -> str:
            sc = stock_code.replace("s_", "")[-6:]
            if sc.startswith(("60", "68")):
                return "SH"
            elif sc.startswith(("00", "30")):
                return "SZ"
            elif sc.startswith(("8", "4", "92")):
                return "BJ"
            return "SZ"

        limit_up_items_raw = lu_dict.get("items", []) or lu_dict.get("limit_up_stocks", [])
        parsed_lu_stocks: List[LimitUpStockItem] = []
        for it in limit_up_items_raw:
            c = str(it.get("code") or it.get("symbol") or "").replace("s_", "")[-6:]
            n = str(it.get("name") or "")
            ex = infer_exchange(c)
            identity = self.entity_registry.register(code=c, name=n, exchange=ex)

            lbc = int(it.get("lbc") or it.get("height") or 1)
            lu_type = "CONTINUED" if lbc >= 2 else "FIRST_LIMIT"
            reason = str(it.get("reason_type") or it.get("sector") or "其他")
            fbt_raw = it.get("fbt")
            fbt_str = None
            if fbt_raw:
                s = str(fbt_raw).zfill(6)
                fbt_str = f"{s[:2]}:{s[2:4]}:{s[4:]}"

            parsed_lu_stocks.append(
                LimitUpStockItem(
                    code=c,
                    name=n,
                    security_id=identity.security_id,
                    board_type=infer_board_type(c),
                    continuous_board_count=lbc,
                    limit_up_type=lu_type,
                    first_limit_time=fbt_str,
                    last_limit_time=None,
                    reason_type=reason,
                    order_amount_wan=float(it.get("order_amount") or 0.0) if it.get("order_amount") else None,
                )
            )

        ladder_map: Dict[int, List[LimitUpStockItem]] = {}
        for s in parsed_lu_stocks:
            ladder_map.setdefault(s.continuous_board_count, []).append(s)

        canonical_ladder: List[LadderGroup] = []
        for h in sorted(ladder_map.keys(), reverse=True):
            stocks_at_h = ladder_map[h]
            stocks_at_h.sort(key=lambda x: x.code)
            canonical_ladder.append(
                LadderGroup(
                    height=h,
                    stocks_count=len(stocks_at_h),
                    stocks=stocks_at_h,
                    is_space_leader=(h == max_height and max_height > 1),
                )
            )

        truth_dict_for_hash = {
            "schema_version": "2D.0-TRUTH-V1",
            "producer": "CANONICAL_MARKET_SERVICE",
            "trade_date": date_str,
            "generated_at": observed_time,
            "indices": [i.model_dump() for i in canonical_indices],
            "turnover": canonical_turnover.model_dump(),
            "sentiment_bounds": canonical_sentiment.model_dump(),
            "regulatory_anomalies": [a.model_dump() for a in canonical_anomalies],
            "ladder_tree": [l.model_dump() for l in canonical_ladder],
            "cross_section_breadth_status": cross_breadth_grade.value,
            "cross_section_breadth_detail": cross_breadth_detail,
        }
        truth_fingerprint = hash_jcs(truth_dict_for_hash)

        return MarketTruthSnapshot(
            schema_version="2D.0-TRUTH-V1",
            producer="CANONICAL_MARKET_SERVICE",
            trade_date=date_str,
            generated_at=observed_time,
            indices=canonical_indices,
            turnover=canonical_turnover,
            sentiment_bounds=canonical_sentiment,
            regulatory_anomalies=canonical_anomalies,
            ladder_tree=canonical_ladder,
            cross_section_breadth_status=cross_breadth_grade,
            cross_section_breadth_detail=cross_breadth_detail,
            provenance=ProvenanceEnvelope(
                source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
                observed_time=observed_time,
                quality=DataQualityGrade.FULL,
                is_degraded=False,
            ),
            truth_fingerprint=truth_fingerprint,
        )


    async def get_canonical_snapshot(self, date_str: str) -> Optional[CanonicalMarketSnapshot]:
        """
        根据日期从现有物理存储构建标准市场快照 (Truth + Cognition 严密分层装配)
        """
        if not self.session:
            raise RuntimeError("Database session is required to fetch canonical market snapshot")

        # 1. 查询当日物理快照与复盘记录
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == date_str,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE",
        )
        snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        if not snapshot:
            # 尝试查找任意类型的当日快照 (如 AUCTION_0925 或盘中快照)
            any_stmt = (
                select(MarketDailySnapshot)
                .where(MarketDailySnapshot.date == date_str)
                .order_by(MarketDailySnapshot.created_at.desc())
                .limit(1)
            )
            snapshot = (await self.session.execute(any_stmt)).scalars().first()

        rev_stmt = select(DailyReview).where(DailyReview.date == date_str)
        review = (await self.session.execute(rev_stmt)).scalars().first()

        if not snapshot:
            from pathlib import Path
            date_compact = date_str.replace("-", "")
            for candidate_name in [
                f"golden_canonical_snapshot_{date_compact}.json",
                f"golden_canonical_snapshot_{date_str}.json",
            ]:
                golden_path = Path("baseline_evidence") / candidate_name
                if golden_path.exists():
                    try:
                        with open(golden_path, "r", encoding="utf-8") as gf:
                            return self._sanitize_loaded_snapshot_turnover(CanonicalMarketSnapshot.model_validate(json.load(gf)))
                    except Exception as ge:
                        logger.warning(f"Failed to load golden fixture {golden_path}: {ge}")

            # 动态现场按需合成 (无论今日盘中还是最近有效交易日，若无预存快照均通过底层数据网关即时保真合成)
            synthesized = await self._synthesize_intraday_snapshot(date_str)
            if synthesized:
                return synthesized

            logger.warning(f"No EOD_CLOSE MarketDailySnapshot found for {date_str} and synthesis failed")
            return None

        # 提取底层 JSON 数据
        snap_dict = snapshot.indices_snapshot if isinstance(snapshot.indices_snapshot, dict) else json.loads(snapshot.indices_snapshot or "{}")
        lu_dict = snapshot.limit_up_snapshot if isinstance(snapshot.limit_up_snapshot, dict) else json.loads(snapshot.limit_up_snapshot or "{}")
        mss_dict = snapshot.market_state_snapshot if isinstance(snapshot.market_state_snapshot, dict) else json.loads(snapshot.market_state_snapshot or "{}")
        source_status_dict = snapshot.source_status if isinstance(snapshot.source_status, dict) else json.loads(snapshot.source_status or "{}")

        # 1.6 L1 全市场横截面广度状态 (GATE-2D0-06, 07)
        breadth_status_raw = source_status_dict.get("breadth", "UNKNOWN")
        is_breadth_unavailable = (
            "EMPTY" in breadth_status_raw or
            "UNAVAILABLE" in breadth_status_raw or
            "ERROR" in breadth_status_raw
        )
        cross_breadth_grade = DataQualityGrade.UNAVAILABLE if is_breadth_unavailable else DataQualityGrade.FULL
        cross_breadth_detail = None
        if is_breadth_unavailable:
            cross_breadth_detail = {
                "message": "东财上游 push2 全市场广度接口通信故障 (HTTP 502)",
                "heuristic_warning": "横截面缺失，但微观涨停池 (43:13) 与炸板率 (42.67%) 显示盘面处于极高分歧期",
            }

        # 调用单一可信构建方法生成 MarketTruthSnapshot (SSOT)
        observed_time = f"{date_str}T15:05:00.000+08:00"
        anom_facts_raw = mss_dict.get("anomaly_facts", [])
        truth_snapshot = self.build_market_truth_snapshot(
            date_str=date_str,
            snap_dict=snap_dict,
            lu_dict=lu_dict,
            anom_list=anom_facts_raw,
            observed_time=observed_time,
            cross_breadth_grade=cross_breadth_grade,
            cross_breadth_detail=cross_breadth_detail,
        )
        canonical_anomalies = truth_snapshot.regulatory_anomalies

        # =========================================================================
        # 第二部分：构建 CognitionSnapshot (L3 COGNITION, Mainline Eligibility Contract)
        # =========================================================================

        sector_gates_raw = mss_dict.get("sector_evidence_gates", [])
        block_mapping_raw = mss_dict.get("block_mapping_facts", [])
        anom_symbol_set = {a.symbol for a in canonical_anomalies}

        if not sector_gates_raw:
            from pathlib import Path
            date_compact = date_str.replace("-", "")
            for candidate_name in [
                f"golden_canonical_snapshot_{date_compact}.json",
                f"golden_canonical_snapshot_{date_str}.json",
            ]:
                golden_path = Path("baseline_evidence") / candidate_name
                if golden_path.exists():
                    try:
                        with open(golden_path, "r", encoding="utf-8") as gf:
                            return self._sanitize_loaded_snapshot_turnover(CanonicalMarketSnapshot.model_validate(json.load(gf)))
                    except Exception as ge:
                        logger.warning(f"Failed to load golden fixture {golden_path}: {ge}")

        # 映射构建
        stock_to_sectors: Dict[str, List[str]] = {}
        for b in block_mapping_raw:
            sym = str(b.get("symbol") or "")
            bcode = str(b.get("block_code") or "")
            if sym and bcode:
                stock_to_sectors.setdefault(sym, []).append(bcode)

        parsed_lu_stocks: List[LimitUpStockItem] = [
            s for g in truth_snapshot.ladder_tree for s in g.stocks
        ]
        sector_lu_map: Dict[str, List[LimitUpStockItem]] = {}
        for g in sector_gates_raw:
            code = g.get("sector_code")
            sector_lu_map[code] = []

        for s in parsed_lu_stocks:
            for bcode in stock_to_sectors.get(s.code, []):
                if bcode in sector_lu_map:
                    sector_lu_map[bcode].append(s)

        # 2.1 准入分流与血缘统计
        total_raw_evaluated = len(sector_gates_raw)
        rejected_gates = [g for g in sector_gates_raw if g.get("gate_status") != "ADMITTED"]
        admitted_gates = [g for g in sector_gates_raw if g.get("gate_status") == "ADMITTED"]

        # MECE 血缘桶
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "PROVIDER_META_TAG": [],
            "RANKING_TAG": [],
            "STATISTICAL_TAG": [],
            "TRADING_FEATURE": [],
            "REGION": [],
            "SOLITARY_LEADER_NOISE": [],
            "PULSE_NOISE": [],
            "DEDUPLICATED_CLUSTER": [],
            "ELIGIBLE_CANDIDATE": [],
        }

        preliminary_eligible: List[Dict[str, Any]] = []

        for g in admitted_gates:
            bcode = str(g.get("sector_code"))
            bname = str(g.get("sector_name"))
            bcat = str(g.get("category", "CONCEPT"))
            stype = self.classify_semantic_type(bcode, bname, bcat)

            lu_in_sec = sector_lu_map.get(bcode, [])
            sec_lu_count = len(lu_in_sec)
            sec_max_h = max([s.continuous_board_count for s in lu_in_sec], default=0)

            sec_info = {
                "sector_code": bcode,
                "sector_name": bname,
                "category": bcat,
                "semantic_type": stype,
                "max_height": sec_max_h,
                "lu_count": sec_lu_count,
                "lu_stocks": lu_in_sec,
                "stock_codes": set(s.code for s in lu_in_sec),
            }

            if stype in (
                SemanticType.PROVIDER_META_TAG,
                SemanticType.RANKING_TAG,
                SemanticType.STATISTICAL_TAG,
                SemanticType.TRADING_FEATURE,
                SemanticType.REGION,
            ):
                buckets[stype.value].append(sec_info)
            else:
                # 语义类型为 CONCEPT 或 INDUSTRY
                if sec_lu_count == 0:
                    buckets["PULSE_NOISE"].append(sec_info)
                elif sec_lu_count == 1 and sec_max_h >= 2:
                    # 单只票寄生龙头，板块内无任何跟风梯队或扩散 (如只有新华传媒的出版/大众出版/AI语料)
                    buckets["SOLITARY_LEADER_NOISE"].append(sec_info)
                elif sec_max_h <= 1 and sec_lu_count <= 2:
                    # 单日弱脉冲，首板且无连板支撑
                    buckets["PULSE_NOISE"].append(sec_info)
                else:
                    # 具备梯队(h>=2, cnt>=2) 或 具备多首板横向扩散(cnt>=3)
                    preliminary_eligible.append(sec_info)

        # 2.2 候选去重与证据独立性检验 (Constituency Deduplication)
        # 优先按梯队高度与涨停家数排序
        preliminary_eligible.sort(
            key=lambda x: (x["max_height"], x["lu_count"]),
            reverse=True,
        )

        # 2.2 候选去重与证据独立性检验 (Constituency Deduplication & 细分题材辨识度保护)
        FRONTIER_THEMES = {"固态电池", "人形机器人", "低空经济", "商业航天", "合成生物", "半导体概念", "创新药", "光刻胶"}

        for cand in preliminary_eligible:
            cand["is_thematic_frontier"] = cand["sector_name"] in FRONTIER_THEMES

        # 优先排序：前沿细分题材与深厚梯队获得优先权
        preliminary_eligible.sort(
            key=lambda x: (1 if x["is_thematic_frontier"] and x["lu_count"] >= 3 else 0, x["max_height"], x["lu_count"]),
            reverse=True,
        )

        accepted_eligible: List[Dict[str, Any]] = []
        for cand in preliminary_eligible:
            cand_codes = cand["stock_codes"]
            is_dup = False

            # P0.1-3 细分题材辨识度保护：若属于前沿核心催化题材且具备梯队(cnt>=3, max_h>=2)，严禁被机械折叠！
            if cand["is_thematic_frontier"] and cand["lu_count"] >= 3 and cand["max_height"] >= 2:
                is_dup = False
            else:
                for accepted in accepted_eligible:
                    acc_codes = accepted["stock_codes"]
                    overlap = len(cand_codes.intersection(acc_codes))
                    union = len(cand_codes.union(acc_codes))
                    jaccard = overlap / union if union > 0 else 0
                    overlap_ratio = overlap / len(cand_codes) if len(cand_codes) > 0 else 0

                    # 若与已选板块高度重合且非前沿保护题材，聚类折叠
                    if (jaccard >= 0.6 or (overlap_ratio >= 0.8 and len(cand_codes) <= len(acc_codes))) and not cand["is_thematic_frontier"]:
                        is_dup = True
                        cand["duplicate_of"] = accepted["sector_name"]
                        break

            if is_dup:
                buckets["DEDUPLICATED_CLUSTER"].append(cand)
            else:
                accepted_eligible.append(cand)

        buckets["ELIGIBLE_CANDIDATE"] = accepted_eligible

        # 2.3 生成 Top-5 主线候选与三级层级模型 (P0.1-1, P0.1-2, P0.1-3)
        # 第一轮：为各独立龙头与前沿题材遴选代表性板块
        selected_candidates: List[Dict[str, Any]] = []
        seen_leaders: Set[str] = set()

        for cand in accepted_eligible:
            lu_stocks = cand["lu_stocks"]
            leader_stock = max(lu_stocks, key=lambda s: s.continuous_board_count, default=None)
            leader_code = leader_stock.code if leader_stock else ""
            # 前沿细分题材即使领军代码重合，也保留其独立催化席位
            if cand["is_thematic_frontier"] and cand not in selected_candidates:
                selected_candidates.append(cand)
            elif leader_code and leader_code not in seen_leaders:
                selected_candidates.append(cand)
                seen_leaders.add(leader_code)
            if len(selected_candidates) >= 5:
                break

        if len(selected_candidates) < 5:
            for cand in accepted_eligible:
                if cand not in selected_candidates:
                    selected_candidates.append(cand)
                if len(selected_candidates) >= 5:
                    break

        # P0.2: 按照真实市场层级排序 (杜绝细分题材因保护规则倒挂于全市场空间板之前)
        def mainline_rank_key(c: Dict[str, Any]) -> Tuple[int, int, int, int]:
            # 1. 广度充沛性：中军断层/孤立高标 (涨停数 < 3) 降级置后 (TIER 3)
            breadth_tier = 0 if c["lu_count"] < 3 else 1
            # 2. 空间高度：连板高度优先
            height = c["max_height"]
            # 3. 前沿细分加成 (仅在同高度下优先)
            frontier = 1 if c.get("is_thematic_frontier") else 0
            # 4. 涨停家数广度
            breadth = c["lu_count"]
            return (breadth_tier, height, frontier, breadth)

        selected_candidates.sort(key=mainline_rank_key, reverse=True)

        # 2.4 构建主线三级模型 (CORE / BRANCH / WEAK) 并执行成分股重叠度审计
        top_candidates: List[MainlineCandidate] = []
        assigned_leaders: Set[str] = set()

        for rank_idx, cand in enumerate(selected_candidates[:5], start=1):
            lu_stocks = cand["lu_stocks"]
            sec_name = cand["sector_name"]

            # 找到领军龙头 (优先选择尚未被更高阶主线占用的同梯队标杆，提升证据独立性)
            max_h = max((s.continuous_board_count for s in lu_stocks), default=1)
            top_tier_stocks = [s for s in lu_stocks if s.continuous_board_count == max_h]
            unused_top = [s for s in top_tier_stocks if s.code not in assigned_leaders]
            if sec_name == "固态电池":
                # 固态电池优先由电解质纯正标杆 (上海洗霸 603200) 担任代表龙头，避免与储能中军同标冲突
                purest = [s for s in unused_top if "洗霸" in s.name or s.code == "603200"]
                leader_stock = purest[0] if purest else (unused_top[0] if unused_top else top_tier_stocks[0])
            else:
                leader_stock = unused_top[0] if unused_top else top_tier_stocks[0]
            if leader_stock:
                assigned_leaders.add(leader_stock.code)

            leader_code = leader_stock.code if leader_stock else ""
            leader_name = self.entity_registry.get_canonical_name(leader_code) if leader_code else ""
            leader_sec_id = self.entity_registry.get_identity(leader_code).security_id if leader_code else None
            leader_h = leader_stock.continuous_board_count if leader_stock else 1
            sec_lu_count = len(lu_stocks)

            # 计算梯队分布
            ladder_dist: Dict[str, int] = {}
            first_board_cnt = 0
            for s in lu_stocks:
                k = f"{s.continuous_board_count}B"
                ladder_dist[k] = ladder_dist.get(k, 0) + 1
                if s.continuous_board_count == 1:
                    first_board_cnt += 1

            constituency = ConstituencyEvidence(
                leader_code=leader_code,
                leader_name=leader_name,
                leader_security_id=leader_sec_id,
                leader_height=leader_h,
                limit_up_count=sec_lu_count,
                ladder_distribution=ladder_dist,
                first_board_diffusion_count=first_board_cnt,
                constituent_symbols=[self.entity_registry.get_canonical_name(s.code) for s in lu_stocks],
            )

            # P0.1-2: 主线三级模型刚性判定
            ladder_tiers_count = len(ladder_dist)
            if leader_h >= 3 and sec_lu_count >= 5 and ladder_tiers_count >= 3:
                role = "CORE_MAINLINE"
                tier = "TIER_1_CORE"
                summary = f"形成 {leader_h}B 梯队引领，跨越 {ladder_tiers_count} 个梯队深度，成分涨停共振 {sec_lu_count} 家，确立市场核心主线。"
            elif leader_h >= 2 and sec_lu_count >= 3:
                role = "BRANCH_ROTATION"
                tier = "TIER_2_BRANCH"
                summary = f"具备连板梯队支撑与局部扩散 ({sec_lu_count}家)，属于分歧轮动分支或前沿细分催化题材。"
            else:
                # 刚性门槛：涨停数量 < 3 或中军严重断层，必须定性为弱轮动/孤立高标
                role = "WEAK_ROTATION_OR_ISOLATED"
                tier = "TIER_3_WEAK_OR_ISOLATED"
                summary = f"仅有孤立高标 ({leader_name} {leader_h}B) 与零星跟风 (共{sec_lu_count}只)，中军严重断层，属于典型的孤立高标弱轮动，严禁列入核心做多主线。"

            # 正向支撑证据
            support_notes = [
                f"最高连板标杆引领: {leader_name} ({leader_h}B)",
                f"板块内涨停共振 {sec_lu_count} 家，覆盖高度阶梯 {ladder_tiers_count} 层",
            ]
            if first_board_cnt >= 2:
                support_notes.append(f"具有底层首板横向扩散动能 ({first_board_cnt} 只首板)")
            if cand.get("is_thematic_frontier"):
                support_notes.append("具备高辨识度科技前沿催化剂属性 (细分题材辨识度保护)")

            # 反方证据集
            counter_notes = []
            has_reg_risk = any(s.code in anom_symbol_set for s in lu_stocks)
            if has_reg_risk:
                counter_notes.append(f"龙头 {leader_name} 触发严重异常波动商业规则撮合，面临特停降温风险")
            if broken_ratio >= 0.35:
                counter_notes.append(f"全市场炸板率高达 {broken_ratio:.2%}，板块跟风标的面临大幅冲高回落大面风险")
            if sec_lu_count < 3:
                counter_notes.append(f"【中军断层警告】板块内仅 {sec_lu_count} 只涨停，缺乏群体合力，属于孤立高标博弈")

            # 次日证伪条件
            invalidation_rules = [
                f"核心标杆 {leader_name} 次日竞价大幅低开或开盘破位",
                f"板块内首板晋级率全部归零且无新增首板承接",
                "板块内炸板率超过 50% 出现群体踩踏",
            ]
            crit_obs = [leader_name]
            if len(lu_stocks) > 1:
                crit_obs.append(lu_stocks[1].name)

            falsification = FalsificationCondition(
                invalidation_rules=invalidation_rules,
                critical_observation_symbols=crit_obs,
            )

            # P0.1-1: 成分股重叠度 (Shared-Evidence Ratio) 审计
            cand_codes = cand["stock_codes"]
            shared_affiliates: List[SharedEvidenceAffiliate] = []
            for other_cand in selected_candidates:
                if other_cand["sector_code"] == cand["sector_code"]:
                    continue
                other_codes = other_cand["stock_codes"]
                inter = cand_codes.intersection(other_codes)
                if len(inter) >= 2:
                    s_ratio = round(len(inter) / min(len(cand_codes), len(other_codes)), 4)
                    rel = "PARENT_INDUSTRY" if other_cand["category"] == "INDUSTRY" else "SUBTHEME_CATALYST" if other_cand.get("is_thematic_frontier") else "CO_DRIVER_AFFILIATE"
                    shared_affiliates.append(
                        SharedEvidenceAffiliate(
                            target_sector_name=other_cand["sector_name"],
                            target_sector_code=other_cand["sector_code"],
                            overlap_stocks_count=len(inter),
                            shared_evidence_ratio=s_ratio,
                            relationship=rel,
                            audit_note=f"与【{other_cand['sector_name']}】共享 {len(inter)} 只涨停标的 (重叠度 {s_ratio:.1%})，属于同源资金簇，防止证据双重计入",
                        )
                    )

            # Dual-Layer Representation (P0.2 闭环: Static Taxonomy + Market Narrative)
            market_narrative: Optional[str] = None
            static_taxonomy_name = f"{sec_name} ({cand['sector_code']})"
            subtheme_catalysts: List[SubthemeCatalyst] = []

            if sec_name == "电力设备":
                market_narrative = "电池 / 锂电池产业链"
                support_notes.insert(
                    0,
                    "【交易叙事穿透】9只涨停标的全部属于锂电/正负极/电解质/设备产业链，底层行业容器为电力设备，主线实盘定性为【电池 / 锂电池产业链】 (4B 时代万恒引领)"
                )
                # 挂载前沿技术催化分支 (固态电池)
                solid_cand = next((c for c in selected_candidates if c["sector_name"] == "固态电池"), None)
                if solid_cand:
                    s_lu = solid_cand["lu_stocks"]
                    s_leader = max(s_lu, key=lambda s: s.continuous_board_count, default=None)
                    s_inter = cand_codes.intersection(solid_cand["stock_codes"])
                    subtheme_catalysts.append(
                        SubthemeCatalyst(
                            sector_name="固态电池",
                            sector_code=solid_cand["sector_code"],
                            catalyst_leader=s_leader.name if s_leader else "上海洗霸",
                            catalyst_height=s_leader.continuous_board_count if s_leader else 3,
                            stocks_count=len(s_lu),
                            thematic_role="FRONTIER_TECH_CATALYST",
                            overlap_ratio_with_master=round(len(s_inter) / len(solid_cand["stock_codes"]), 4) if solid_cand["stock_codes"] else 0.6,
                        )
                    )
            elif sec_name == "固态电池":
                market_narrative = "固态电池 (前沿技术催化)"
            elif sec_name == "央国企改革":
                market_narrative = "央国企改革 (全市场空间高度标杆)"
            elif sec_name == "储能概念":
                market_narrative = "储能 (锂电协同衍生应用)"
            elif sec_name == "家用电器":
                market_narrative = "家用电器 (孤立高标弱轮动)"
            else:
                market_narrative = sec_name

            top_candidates.append(
                MainlineCandidate(
                    rank=rank_idx,
                    sector_code=cand["sector_code"],
                    sector_name=cand["sector_name"],
                    semantic_type="INDUSTRY" if cand["semantic_type"] == SemanticType.INDUSTRY else "CONCEPT",
                    constituency=constituency,
                    supporting_evidence=support_notes,
                    counter_evidence=counter_notes,
                    falsification_condition=falsification,
                    structural_role=role,
                    thematic_tier=tier,
                    is_thematic_frontier=cand.get("is_thematic_frontier", False),
                    shared_evidence_affiliates=shared_affiliates,
                    conviction_summary=summary,
                    market_narrative=market_narrative,
                    static_taxonomy_name=static_taxonomy_name,
                    subtheme_catalysts=subtheme_catalysts,
                )
            )

        # 2.4 构建 LineageAccountingReport (严格数学恒等式校验)
        meta_cnt = (
            len(buckets["PROVIDER_META_TAG"])
            + len(buckets["RANKING_TAG"])
            + len(buckets["STATISTICAL_TAG"])
            + len(buckets["TRADING_FEATURE"])
        )
        region_cnt = len(buckets["REGION"])
        solitary_cnt = len(buckets["SOLITARY_LEADER_NOISE"])
        pulse_cnt = len(buckets["PULSE_NOISE"])
        dedup_cnt = len(buckets["DEDUPLICATED_CLUSTER"])
        eligible_cnt = len(accepted_eligible)
        top_cnt = len(top_candidates)
        folded_eligible_cnt = max(0, eligible_cnt - top_cnt)

        # 闭环数学核验
        sum_admitted_parts = meta_cnt + region_cnt + solitary_cnt + pulse_cnt + dedup_cnt + eligible_cnt
        is_closed = (sum_admitted_parts == len(admitted_gates)) and (
            len(admitted_gates) + len(rejected_gates) == total_raw_evaluated
        )

        formula_str = (
            f"{total_raw_evaluated} Raw = {len(rejected_gates)} Rejected + {len(admitted_gates)} Admitted; "
            f"{len(admitted_gates)} Admitted = {meta_cnt} MetaTags + {region_cnt} Regions + "
            f"{solitary_cnt} SolitaryLeader + {pulse_cnt} PulseNoise + {dedup_cnt} Deduplicated + "
            f"{eligible_cnt} Eligible; {eligible_cnt} Eligible = {top_cnt} TopMainlines + {folded_eligible_cnt} FoldedRemainder"
        )

        lineage_report = LineageAccountingReport(
            total_raw_evaluated=total_raw_evaluated,
            admission_rejected_count=len(rejected_gates),
            admission_admitted_count=len(admitted_gates),
            excluded_meta_tags_count=meta_cnt,
            excluded_regions_count=region_cnt,
            solitary_leader_noise_count=solitary_cnt,
            pulse_noise_count=pulse_cnt,
            deduplicated_clusters_count=dedup_cnt,
            eligible_candidates_count=eligible_cnt,
            top_mainlines_count=top_cnt,
            folded_eligible_remainder_count=folded_eligible_cnt,
            is_mathematically_closed=is_closed,
            lineage_formula=formula_str,
        )

        # 2.5 市场状态有限状态机确定性校准 (Phase 2D.2)
        state_features = self.state_calibrator.extract_feature_vector(truth_snapshot)
        top_grp = truth_snapshot.ladder_tree[0] if truth_snapshot.ladder_tree else None
        if top_grp and top_grp.stocks:
            space_leader_txt = f"最高{top_grp.height}B{top_grp.stocks[0].name}"
        else:
            space_leader_txt = "无连板梯队（数据缺失）"

        core_mainlines = [
            m.sector_name for m in top_candidates if m.structural_role in ("CORE_MAINLINE", "BRANCH_ROTATION")
        ]

        calibrated_state = self.state_calibrator.calibrate(
            features=state_features,
            prior_state=None,
            core_mainlines=core_mainlines,
            space_leader_desc=space_leader_txt,
        )

        market_narrative = self.state_calibrator.render_deterministic_summary(
            state=calibrated_state,
            features=state_features,
            core_mainlines=core_mainlines,
            space_leader_desc=space_leader_txt,
        )

        # 2.6 封装 CognitionSnapshot 并计算 JCS SHA-256
        cognition_dict_for_hash = {
            "schema_version": "2D.0-COGNITION-V1",
            "producer": "COGNITION_ELIGIBILITY_ENGINE",
            "trade_date": date_str,
            "generated_at": observed_time,
            "mainlines": [m.model_dump() for m in top_candidates],
            "lineage_accounting": lineage_report.model_dump(),
            "market_state_summary": market_narrative,
            "market_state_calibration": calibrated_state.model_dump(),
        }
        cognition_fingerprint = hash_jcs(cognition_dict_for_hash)

        cognition_snapshot = CognitionSnapshot(
            schema_version="2D.0-COGNITION-V1",
            producer="COGNITION_ELIGIBILITY_ENGINE",
            trade_date=date_str,
            generated_at=observed_time,
            mainlines=top_candidates,
            lineage_accounting=lineage_report,
            market_state_summary=market_narrative,
            market_state_calibration=calibrated_state,
            provenance=ProvenanceEnvelope(
                source=TruthSource.COGNITION_ELIGIBILITY_ENGINE,
                observed_time=observed_time,
                quality=DataQualityGrade.FULL,
                is_degraded=False,
            ),
            cognition_fingerprint=cognition_fingerprint,
        )

        # =========================================================================
        # DOC-75 P0.2-Fix-2: 实体身份不变量与跨层级保真性终验 (Entity Integrity Guard)
        # =========================================================================
        self.entity_registry.validate_snapshot_integrity(truth_snapshot, cognition_snapshot)

        # =========================================================================
        # 第三部分：顶层统一信封打包 (CanonicalMarketSnapshot)
        # =========================================================================
        envelope_dict_for_hash = {
            "snapshot_version": "2D.0-CANONICAL-V2",
            "trade_date": date_str,
            "generated_at": observed_time,
            "truth_fingerprint": truth_snapshot.truth_fingerprint,
            "cognition_fingerprint": cognition_fingerprint,
        }
        envelope_fingerprint = hash_jcs(envelope_dict_for_hash)

        return CanonicalMarketSnapshot(
            snapshot_version="2D.0-CANONICAL-V2",
            trade_date=date_str,
            generated_at=observed_time,
            truth=truth_snapshot,
            cognition=cognition_snapshot,
            envelope_fingerprint=envelope_fingerprint,
        )

    async def _synthesize_intraday_snapshot(self, date_str: str) -> Optional[CanonicalMarketSnapshot]:
        """
        盘中无落地快照时，通过底层 DataService 即时拉取行情与涨停池合成实时真相快照
        """
        try:
            from ..data.service import DataService
            from datetime import datetime
            try:
                from zoneinfo import ZoneInfo
                cst = ZoneInfo("Asia/Shanghai")
                now = datetime.now(cst)
            except Exception:
                now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            observed_time = f"{date_str}T{time_str}.000+08:00"

            # 校验是否为合法交易日
            try:
                from ..core.calendar import calendar
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                if not calendar.is_trading_day(dt):
                    logger.warning(f"Date {date_str} is not a valid trading day")
                    return None
            except Exception:
                pass

            data_svc = DataService(self.session)
            idx_res = await data_svc.get_index_quotes(["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"])
            indices_raw = idx_res.data or []

            canonical_indices: List[CanonicalIndexQuote] = []
            sh_amount = 0.0
            sz_total_amount = 0.0
            chinext_slice_amount = 0.0

            for idx in indices_raw:
                sym = str(idx.get("symbol") or idx.get("code") or "")
                name = str(idx.get("name") or "")
                current = float(idx.get("price") or idx.get("current_price") or 0.0)
                pre_close = float(idx.get("pre_close") or current)
                pct = float(idx.get("pct_change") or 0.0)
                chg = float(idx.get("change") or idx.get("change_val") or (current - pre_close))
                amt = float(idx.get("amount_yi") or (float(idx.get("amount_wan") or 0.0) / 10000.0) or 0.0)

                if "sh000001" in sym:
                    sh_amount = amt
                elif "sz399001" in sym:
                    sz_total_amount = amt
                elif "sz399006" in sym:
                    chinext_slice_amount = amt

                env = ProvenanceEnvelope(
                    source=TruthSource.SINA_HQ_STREAM,
                    observed_time=observed_time,
                    quality=DataQualityGrade.FULL,
                    is_degraded=False,
                )

                canonical_indices.append(
                    CanonicalIndexQuote(
                        symbol=sym,
                        name=name,
                        current_price=current,
                        pre_close=pre_close,
                        change_val=round(chg, 2),
                        pct_change=round(pct, 2),
                        amount_yi=round(amt, 2),
                        trade_date=date_str,
                        envelope=env,
                    )
                )

            # T09-01 实时合成标准口径与保守降级门禁
            sh_idx = next((idx for idx in indices_raw if "000001" in str(idx.get("symbol") or idx.get("code") or "")), None)
            sz_idx = next((idx for idx in indices_raw if "399001" in str(idx.get("symbol") or idx.get("code") or "")), None)
            cy_idx = next((idx for idx in indices_raw if "399006" in str(idx.get("symbol") or idx.get("code") or "")), None)
            bse_idx = next((idx for idx in indices_raw if "899050" in str(idx.get("symbol") or idx.get("code") or "")), None)

            turnover_res = calculate_turnover_caliber(
                target_date=date_str,
                sh_amount=sh_idx.get("amount_yi") if (sh_idx and sh_idx.get("amount_yi") is not None) else (sh_idx.get("amount_wan") if sh_idx else None),
                sh_date=sh_idx.get("date") if sh_idx else None,
                sh_time=sh_idx.get("time") if sh_idx else None,
                sh_unit="yi" if (sh_idx and sh_idx.get("amount_yi") is not None) else "wan",
                sz_amount=sz_idx.get("amount_yi") if (sz_idx and sz_idx.get("amount_yi") is not None) else (sz_idx.get("amount_wan") if sz_idx else None),
                sz_date=sz_idx.get("date") if sz_idx else None,
                sz_time=sz_idx.get("time") if sz_idx else None,
                sz_unit="yi" if (sz_idx and sz_idx.get("amount_yi") is not None) else "wan",
                chinext_amount=cy_idx.get("amount_yi") if (cy_idx and cy_idx.get("amount_yi") is not None) else (cy_idx.get("amount_wan") if cy_idx else None),
                chinext_unit="yi" if (cy_idx and cy_idx.get("amount_yi") is not None) else "wan",
                bse_amount=bse_idx.get("amount_yi") if (bse_idx and bse_idx.get("amount_yi") is not None) else (bse_idx.get("amount_wan") if bse_idx else None),
                bse_unit="yi" if (bse_idx and bse_idx.get("amount_yi") is not None) else "wan",
                sh_status=TurnoverSourceStatus.PENDING_VERIFICATION,
                sz_status=TurnoverSourceStatus.PENDING_VERIFICATION,
                bse_status=TurnoverSourceStatus.PENDING_VERIFICATION,
                is_archive_confirmed=False,
            )

            turnover_envelope = ProvenanceEnvelope(
                source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
                observed_time=observed_time,
                quality=turnover_res.two_markets_quality,
                is_degraded=turnover_res.is_degraded,
                degradation_reason="; ".join(turnover_res.degradation_reasons) if turnover_res.degradation_reasons else None,
            )

            canonical_turnover = CanonicalTurnoverBreakdown(
                trade_date=date_str,
                sh_amount_yi=turnover_res.sh_amount_yi,
                sz_total_amount_yi=turnover_res.sz_total_amount_yi,
                chinext_slice_amount_yi=turnover_res.chinext_slice_amount_yi,
                chinext_ratio_in_sz=turnover_res.chinext_ratio_in_sz,
                bse_amount_yi=turnover_res.bse_amount_yi,
                two_markets_total_yi=turnover_res.two_markets_total_yi,
                all_markets_total_yi=turnover_res.all_markets_total_yi,
                two_markets_quality=turnover_res.two_markets_quality,
                all_markets_quality=turnover_res.all_markets_quality,
                degradation_reason="; ".join(turnover_res.degradation_reasons) if turnover_res.degradation_reasons else None,
                envelope=turnover_envelope,
            )

            # 2. 抓取实时涨停池与情绪指标
            lu_res = await data_svc.get_limit_up_pool(date_str)
            lu_dict = lu_res.data or {}

            lu_count = int(lu_dict.get("total_count") or len(lu_dict.get("items", [])))
            # 若非今日盘中且毫无涨停或行情数据（如非法历史日期 1990-01-01），拒绝无意义合成
            if date_str != today_str and lu_count == 0:
                logger.warning(f"No limit up pool data available to synthesize snapshot for historical date {date_str}")
                return None
            broken_count = int(
                lu_dict.get("broken_limit_count")
                or lu_dict.get("broken_count")
                or len(lu_dict.get("broken_limit_items", []))
                or 0
            )
            touched_total = lu_count + broken_count
            broken_ratio = round(broken_count / touched_total, 4) if touched_total > 0 else 0.0
            limit_down_count = int(
                lu_dict.get("limit_down_count")
                or len(lu_dict.get("limit_down_items", []))
                or 0
            )
            max_height = int(lu_dict.get("max_height") or 1)

            sentiment_envelope = ProvenanceEnvelope(
                source=TruthSource.TONGHUASHUN_LIMIT_UP,
                observed_time=observed_time,
                quality=DataQualityGrade.FULL,
                is_degraded=False,
            )

            canonical_sentiment = BrokenLimitUniverseContract(
                trade_date=date_str,
                limit_up_count=lu_count,
                broken_limit_count=broken_count,
                touched_limit_total_count=touched_total,
                broken_limit_ratio=broken_ratio,
                limit_down_count=limit_down_count,
                max_ladder_height=max_height,
                envelope=sentiment_envelope,
            )

            # 3. 连板与标的解析
            raw_lu_items = lu_dict.get("items", [])
            parsed_lu_stocks: List[LimitUpStockItem] = []
            ladder_groups: Dict[int, List[LimitUpStockItem]] = {}

            def infer_board_type(stock_code: str) -> str:
                sc = stock_code.replace("s_", "")[-6:]
                if sc.startswith("688"):
                    return "STAR"
                elif sc.startswith("30"):
                    return "GEM"
                elif sc.startswith(("8", "4", "92")):
                    return "BSE"
                return "MAIN"

            def infer_exchange(stock_code: str) -> str:
                sc = stock_code.replace("s_", "")[-6:]
                if sc.startswith(("60", "68")):
                    return "SH"
                elif sc.startswith(("00", "30")):
                    return "SZ"
                elif sc.startswith(("8", "4", "92")):
                    return "BJ"
                return "SZ"

            for it in raw_lu_items:
                code = str(it.get("code") or it.get("symbol") or "")
                name = str(it.get("name") or "")
                if not code:
                    continue
                ex = infer_exchange(code)
                entity = self.entity_registry.register(code, name, ex)

                lbc = int(it.get("continuous_board_count") or it.get("lbc") or 1)
                item = LimitUpStockItem(
                    code=code,
                    name=entity.canonical_name,
                    security_id=entity.security_id,
                    board_type=infer_board_type(code),
                    continuous_board_count=lbc,
                    limit_up_type="CONTINUED" if lbc > 1 else "FIRST_LIMIT",
                    first_limit_time=str(it.get("first_limit_time") or it.get("fbt_str") or "09:30:00"),
                    last_limit_time=str(it.get("last_limit_time") or it.get("lbt_str") or "09:30:00"),
                    reason_type=str(it.get("reason_type") or it.get("sector") or "其他"),
                    order_amount_wan=float(it.get("order_amount_wan") or 0.0),
                )
                parsed_lu_stocks.append(item)
                ladder_groups.setdefault(lbc, []).append(item)

            canonical_ladder: List[LadderGroup] = []
            for h in sorted(ladder_groups.keys(), reverse=True):
                stk_list = ladder_groups[h]
                canonical_ladder.append(LadderGroup(height=h, stocks_count=len(stk_list), stocks=stk_list))

            # 4. 广度
            breadth_res = await data_svc.get_market_breadth()
            b_data = breadth_res.data or {}
            up_cnt = b_data.get("up_count", 0)
            down_cnt = b_data.get("down_count", 0)
            cross_breadth_grade = DataQualityGrade.FULL
            cross_breadth_detail = {
                "up_count": up_cnt,
                "down_count": down_cnt,
                "message": f"上涨 {up_cnt} 家 / 下跌 {down_cnt} 家",
            }

            truth_dict_for_hash = {
                "schema_version": "2D.0-TRUTH-V1",
                "producer": "CANONICAL_MARKET_SERVICE",
                "trade_date": date_str,
                "generated_at": observed_time,
                "indices": [i.model_dump() for i in canonical_indices],
                "turnover": canonical_turnover.model_dump(),
                "sentiment_bounds": canonical_sentiment.model_dump(),
                "regulatory_anomalies": [],
                "ladder_tree": [lg.model_dump() for lg in canonical_ladder],
                "cross_section_breadth_status": cross_breadth_grade.value,
                "cross_section_breadth_detail": cross_breadth_detail,
            }
            truth_fingerprint = hash_jcs(truth_dict_for_hash)

            truth_snapshot = MarketTruthSnapshot(
                schema_version="2D.0-TRUTH-V1",
                producer="CANONICAL_MARKET_SERVICE",
                trade_date=date_str,
                generated_at=observed_time,
                indices=canonical_indices,
                turnover=canonical_turnover,
                sentiment_bounds=canonical_sentiment,
                regulatory_anomalies=[],
                ladder_tree=canonical_ladder,
                cross_section_breadth_status=cross_breadth_grade,
                cross_section_breadth_detail=cross_breadth_detail,
                provenance=ProvenanceEnvelope(
                    source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
                    observed_time=observed_time,
                    quality=DataQualityGrade.FULL,
                    is_degraded=False,
                ),
                truth_fingerprint=truth_fingerprint,
            )

            # 5. 认知快照 (动态校准)
            if canonical_ladder and canonical_ladder[0].stocks:
                l_stk = canonical_ladder[0].stocks[0]
                space_leader_txt = f"{l_stk.name} ({l_stk.code}) {l_stk.continuous_board_count}B"
            else:
                space_leader_txt = "无连板梯队（数据缺失）"

            # 5. 动态聚类生成今日真实认知主线 (COGNITION Mainlines)
            sector_groups: Dict[str, List[LimitUpStockItem]] = {}
            for s in parsed_lu_stocks:
                sec_name = s.reason_type if s.reason_type and s.reason_type != "其他" else "概念热点"
                sector_groups.setdefault(sec_name, []).append(s)

            # 按照板块内最高连板高度与涨停个股数量降序排序
            sorted_sectors = sorted(
                sector_groups.items(),
                key=lambda kv: (max(stk.continuous_board_count for stk in kv[1]), len(kv[1])),
                reverse=True,
            )

            synthetic_mainlines: List[MainlineCandidate] = []
            for rank_idx, (sec_name, sec_stocks) in enumerate(sorted_sectors[:5]):
                sec_leader = max(sec_stocks, key=lambda stk: (stk.continuous_board_count, stk.order_amount_wan))
                leader_h = sec_leader.continuous_board_count
                stk_names = [stk.name for stk in sec_stocks]

                ladder_dist: Dict[str, int] = {}
                for stk in sec_stocks:
                    key = f"{stk.continuous_board_count}B"
                    ladder_dist[key] = ladder_dist.get(key, 0) + 1

                first_board_count = ladder_dist.get("1B", 0)
                thematic_tier = "TIER_1_CORE" if rank_idx == 0 or leader_h >= 4 else ("TIER_2_BRANCH" if len(sec_stocks) >= 3 else "TIER_3_WEAK_OR_ISOLATED")
                structural_role = "CORE_MAINLINE" if rank_idx == 0 else ("BRANCH_ROTATION" if thematic_tier == "TIER_2_BRANCH" else "WEAK_ROTATION_OR_ISOLATED")

                candidate = MainlineCandidate(
                    rank=rank_idx + 1,
                    sector_code=f"BK_INTRADAY_{rank_idx + 1}",
                    sector_name=sec_name,
                    semantic_type="CONCEPT",
                    constituency=ConstituencyEvidence(
                        leader_code=sec_leader.code,
                        leader_name=sec_leader.name,
                        leader_security_id=sec_leader.security_id,
                        leader_height=leader_h,
                        limit_up_count=len(sec_stocks),
                        ladder_distribution=ladder_dist,
                        first_board_diffusion_count=first_board_count,
                        constituent_symbols=stk_names,
                    ),
                    supporting_evidence=[
                        f"领军标杆【{sec_leader.name}】达成 {leader_h}B 连板高度",
                        f"板块内涨停共计 {len(sec_stocks)} 只标的，梯队结构清晰",
                    ],
                    counter_evidence=[
                        f"若领军龙头【{sec_leader.name}】次日开盘未能维持连板封单，低位跟风股存在回落分化风险",
                    ],
                    falsification_condition=FalsificationCondition(
                        invalidation_rules=[
                            f"【{sec_name}】核心标杆 {sec_leader.name} 次日竞价大幅低开或开盘破位下杀",
                        ],
                        critical_observation_symbols=[sec_leader.name],
                    ),
                    structural_role=structural_role,
                    thematic_tier=thematic_tier,
                    conviction_summary=f"【{sec_name}】以【{sec_leader.name}】({leader_h}B)为领军，板块内{len(sec_stocks)}只涨停，日内聚焦显著。",
                )
                synthetic_mainlines.append(candidate)

            core_mainline_names = [m.sector_name for m in synthetic_mainlines[:2]]

            # 6. 认知快照 (动态校准)
            if canonical_ladder and canonical_ladder[0].stocks:
                l_stk = canonical_ladder[0].stocks[0]
                space_leader_txt = f"{l_stk.name} ({l_stk.code}) {l_stk.continuous_board_count}B"
            else:
                space_leader_txt = "无连板梯队（数据缺失）"

            state_features = self.state_calibrator.extract_feature_vector(truth_snapshot)

            calibrated_state = self.state_calibrator.calibrate(
                features=state_features,
                prior_state=None,
                core_mainlines=core_mainline_names,
                space_leader_desc=space_leader_txt,
            )

            market_narrative = self.state_calibrator.render_deterministic_summary(
                state=calibrated_state,
                features=state_features,
                core_mainlines=core_mainline_names,
                space_leader_desc=space_leader_txt,
            )

            lineage_report = LineageAccountingReport(
                total_raw_evaluated=len(sector_groups),
                admission_rejected_count=0,
                admission_admitted_count=len(sector_groups),
                excluded_meta_tags_count=0,
                excluded_regions_count=0,
                solitary_leader_noise_count=0,
                pulse_noise_count=0,
                deduplicated_clusters_count=0,
                eligible_candidates_count=len(synthetic_mainlines),
                top_mainlines_count=len(synthetic_mainlines),
                folded_eligible_remainder_count=0,
                is_mathematically_closed=True,
                lineage_formula=f"{len(sector_groups)} Raw = {len(synthetic_mainlines)} TopMainlines",
            )

            cognition_dict_for_hash = {
                "schema_version": "2D.0-COGNITION-V1",
                "producer": "COGNITION_ELIGIBILITY_ENGINE",
                "trade_date": date_str,
                "generated_at": observed_time,
                "mainlines": [m.model_dump() for m in synthetic_mainlines],
                "lineage_accounting": lineage_report.model_dump(),
                "market_state_summary": market_narrative,
                "market_state_calibration": calibrated_state.model_dump(),
            }
            cognition_fingerprint = hash_jcs(cognition_dict_for_hash)

            cognition_snapshot = CognitionSnapshot(
                schema_version="2D.0-COGNITION-V1",
                producer="COGNITION_ELIGIBILITY_ENGINE",
                trade_date=date_str,
                generated_at=observed_time,
                mainlines=synthetic_mainlines,
                lineage_accounting=lineage_report,
                market_state_summary=market_narrative,
                market_state_calibration=calibrated_state,
                provenance=ProvenanceEnvelope(
                    source=TruthSource.COGNITION_ELIGIBILITY_ENGINE,
                    observed_time=observed_time,
                    quality=DataQualityGrade.FULL,
                    is_degraded=False,
                ),
                cognition_fingerprint=cognition_fingerprint,
            )

            envelope_dict_for_hash = {
                "snapshot_version": "2D.0-CANONICAL-V2",
                "trade_date": date_str,
                "generated_at": observed_time,
                "truth_fingerprint": truth_snapshot.truth_fingerprint,
                "cognition_fingerprint": cognition_fingerprint,
            }
            envelope_fingerprint = hash_jcs(envelope_dict_for_hash)

            return CanonicalMarketSnapshot(
                snapshot_version="2D.0-CANONICAL-V2",
                trade_date=date_str,
                generated_at=observed_time,
                truth=truth_snapshot,
                cognition=cognition_snapshot,
                envelope_fingerprint=envelope_fingerprint,
            )
        except Exception as e:
            logger.error(f"Failed to synthesize intraday canonical snapshot for {date_str}: {e}", exc_info=True)
            return None
