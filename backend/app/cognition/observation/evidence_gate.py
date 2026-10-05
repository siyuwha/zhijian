"""
Evidence Gating Engine (板块四维充分性证据门禁执行器)
上位依据：
1. SPEC-COGNITION-PHASE2C-20261005-V1.1 (第4节、第6节、第7节)
2. 董事会授权令：AUTH-PHASE2C5-20261005

核心铁律：
- 解耦 Membership 与 Strength：BLOCK_MAP 只能证明集合归属 (s ∈ S)，绝不代表走强
- 四维充分性证据矩阵：SectorEvidence(S) = <Membership, Breadth, Leadership, Persistence>
- 首板严禁计入持续性 (Persistence)：连板高度 >= 2 才能计入 Persistence
- 假说严格分流：
  - Pillar 1+2+3 齐备 (无连板，仅首板/异动) -> INITIAL_OUTBREAK (脉冲爆发)
  - Pillar 1+2+3+4 全齐备 (存在 >= 2 连板梯队) -> SECTOR_ROTATION (主线轮动)
  - 仅有归属或其他缺失 -> REJECTED (INSUFFICIENT_EVIDENCE)
- 维度刚性隔离：REGION 硬隔离、NOISE 硬清洗
- 严禁假 0 掩盖，缺失坦然标记 FactStatus.MISSING
- 确定性输出 RFC 8785 JCS evidence_fingerprint
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone, timedelta

from .contracts import EvidenceGateResult, FactStatus
from ...core.block_registry import BlockRegistry
from ..jcs import hash_jcs

BEIJING_TZ = timezone(timedelta(hours=8))


class EvidenceGatedEvaluator:
    """
    板块证据门禁执行器（纯函数、无状态、确定性）
    """

    @classmethod
    def evaluate_sector(
        cls,
        sector_code: str,
        sector_name: str,
        sector_stocks: List[Dict[str, Any]],
        limit_up_items: Optional[List[Dict[str, Any]]] = None,
        anomaly_facts: Optional[List[Dict[str, Any]]] = None,
        evaluated_at: Optional[str] = None,
    ) -> EvidenceGateResult:
        """
        对单个板块执行四维充分性证据矩阵判定
        """
        eval_time = evaluated_at or datetime.now(BEIJING_TZ).isoformat()
        rejection_reasons: List[str] = []

        # 1. 正交三维分类与噪音拦截
        category = BlockRegistry.categorize(sector_name, sector_code)

        # 1.1 REGION / NOISE 刚性隔离与阻断
        if category in ("FILTERED_NOISE", "REGION"):
            reason = f"板块类别 '{category}' 属于刚性隔离或统计噪音，严禁准入板块认知假说"
            rejection_reasons.append(reason)
            res = EvidenceGateResult(
                sector_code=sector_code,
                sector_name=sector_name,
                category=category,
                gate_status="REJECTED",
                admitted_hypothesis_type="NONE",
                pillar_membership=FactStatus.MISSING,
                pillar_breadth=FactStatus.MISSING,
                pillar_leadership=FactStatus.MISSING,
                pillar_persistence=FactStatus.MISSING,
                rejection_reasons=rejection_reasons,
                evaluated_at=eval_time,
                evidence_fingerprint="",
            )
            fp = hash_jcs(res.canonical_dict())
            return res.model_copy(update={"evidence_fingerprint": fp})

        # 2. Pillar 1: 集合归属 (Membership)
        # 必须具备客观成分股事实映射
        if sector_stocks and len(sector_stocks) > 0:
            pillar_membership = FactStatus.AVAILABLE
        else:
            pillar_membership = FactStatus.MISSING
            rejection_reasons.append("Pillar 1 (Membership): 该板块成分股映射事实缺失 (len=0)")

        # 整理板块成分股代码集合 (纯 6 位数字)
        clean_sector_symbols: Set[str] = set()
        for s in (sector_stocks or []):
            code = str(s.get("symbol") or s.get("code") or "").replace("s_", "")[-6:]
            if code:
                clean_sector_symbols.add(code)

        # 3. Pillar 2: 板块广度 (Breadth)
        # 来源：现有收盘涨停池中属于该板块的标的数量
        if limit_up_items is None:
            pillar_breadth = FactStatus.MISSING
            rejection_reasons.append("Pillar 2 (Breadth): 涨停池客观事实切片未注入 (limit_up_items is None)")
        else:
            lu_in_sector = []
            for item in limit_up_items:
                c = str(item.get("code") or item.get("symbol") or "").replace("s_", "")[-6:]
                if c in clean_sector_symbols:
                    lu_in_sector.append(item)

            if len(lu_in_sector) > 0:
                pillar_breadth = FactStatus.AVAILABLE
            else:
                pillar_breadth = FactStatus.EMPTY
                rejection_reasons.append(f"Pillar 2 (Breadth): 该板块在涨停池中无上榜标的 (count=0)")

        # 4. Pillar 3: 领军效应 (Leadership)
        # 来源：板块成分股是否出现严重异动事实 (ANOM:*) 或 涨停池首板/龙头
        if anomaly_facts is None and limit_up_items is None:
            pillar_leadership = FactStatus.MISSING
            rejection_reasons.append("Pillar 3 (Leadership): 异动与涨停事实源均不可用")
        else:
            has_anomaly_leader = False
            if anomaly_facts:
                for af in anomaly_facts:
                    sym = str(af.get("symbol") or "").replace("s_", "")[-6:]
                    if sym in clean_sector_symbols and af.get("status_flag", 0) >= 0:
                        has_anomaly_leader = True
                        break

            has_limit_up_leader = False
            if limit_up_items:
                for it in limit_up_items:
                    c = str(it.get("code") or it.get("symbol") or "").replace("s_", "")[-6:]
                    if c in clean_sector_symbols:
                        has_limit_up_leader = True
                        break

            if has_anomaly_leader or has_limit_up_leader:
                pillar_leadership = FactStatus.AVAILABLE
            else:
                pillar_leadership = FactStatus.EMPTY
                rejection_reasons.append("Pillar 3 (Leadership): 板块内无异动龙头或涨停标的")

        # 5. Pillar 4: 持续惯性 (Persistence)
        # 铁律：连板高度 >= 2 才能计入持续性！首板严禁计入！
        if limit_up_items is None:
            pillar_persistence = FactStatus.MISSING
            rejection_reasons.append("Pillar 4 (Persistence): 连板梯队事实源未注入")
        else:
            max_height = 0
            for item in limit_up_items:
                c = str(item.get("code") or item.get("symbol") or "").replace("s_", "")[-6:]
                if c in clean_sector_symbols:
                    h = int(item.get("board_count") or item.get("height") or item.get("lbc") or 1)
                    if h > max_height:
                        max_height = h

            if max_height >= 2:
                pillar_persistence = FactStatus.AVAILABLE
            else:
                pillar_persistence = FactStatus.EMPTY
                if max_height == 1:
                    rejection_reasons.append("Pillar 4 (Persistence): 板块内仅有首板，未形成连板梯队 (max_height=1 < 2)")
                else:
                    rejection_reasons.append(f"Pillar 4 (Persistence): 板块内无连板支撑 (max_height={max_height})")

        # 6. 门禁状态机判定 (Gating State Machine)
        if pillar_membership != FactStatus.AVAILABLE:
            gate_status = "REJECTED"
            admitted_hypothesis_type = "NONE"
        elif pillar_breadth == FactStatus.AVAILABLE and pillar_leadership == FactStatus.AVAILABLE:
            if pillar_persistence == FactStatus.AVAILABLE:
                gate_status = "ADMITTED"
                admitted_hypothesis_type = "SECTOR_ROTATION"
            else:
                gate_status = "ADMITTED"
                admitted_hypothesis_type = "INITIAL_OUTBREAK"
        else:
            gate_status = "REJECTED"
            admitted_hypothesis_type = "NONE"
            if pillar_breadth != FactStatus.AVAILABLE:
                rejection_reasons.append("Pillar 2 (Breadth) insufficient: 板块广度不满足准入条件")
            if pillar_leadership != FactStatus.AVAILABLE:
                rejection_reasons.append("Pillar 3 (Leadership) insufficient: 领军效应不满足准入条件")

        res = EvidenceGateResult(
            sector_code=sector_code,
            sector_name=sector_name,
            category=category,
            gate_status=gate_status,
            admitted_hypothesis_type=admitted_hypothesis_type,
            pillar_membership=pillar_membership,
            pillar_breadth=pillar_breadth,
            pillar_leadership=pillar_leadership,
            pillar_persistence=pillar_persistence,
            rejection_reasons=rejection_reasons,
            evaluated_at=eval_time,
            evidence_fingerprint="",
        )
        fp = hash_jcs(res.canonical_dict())
        return res.model_copy(update={"evidence_fingerprint": fp})

    @classmethod
    def evaluate_all_sectors(
        cls,
        sector_mapping: Dict[str, Dict[str, Any]],
        limit_up_items: Optional[List[Dict[str, Any]]] = None,
        anomaly_facts: Optional[List[Dict[str, Any]]] = None,
        evaluated_at: Optional[str] = None,
    ) -> List[EvidenceGateResult]:
        """
        批量评估一组板块（按 sector_code 字典序确定性返回）
        sector_mapping 结构示例：
        {
            "BK0896": {
                "name": "白酒",
                "category": "INDUSTRY",
                "stocks": [{"symbol": "600519", "name": "贵州茅台"}]
            }
        }
        """
        results: List[EvidenceGateResult] = []
        for s_code in sorted(sector_mapping.keys()):
            sec_info = sector_mapping[s_code]
            s_name = sec_info.get("name", s_code)
            s_stocks = sec_info.get("stocks", [])
            gate_res = cls.evaluate_sector(
                sector_code=s_code,
                sector_name=s_name,
                sector_stocks=s_stocks,
                limit_up_items=limit_up_items,
                anomaly_facts=anomaly_facts,
                evaluated_at=evaluated_at,
            )
            results.append(gate_res)
        return results
