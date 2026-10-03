"""
Cognition Output -> Simulation Intent 预留网关 (Cognition Simulation Gateway)
上位依据：
- Phase 2B -> Phase 3 边界契约规范
- BOARD-RULE: 认知层只读投影，绝不接触资金或直接调用下单

核心职责：
1. 从不可变认知记录（CognitionRecord）及市场推演假说（MarketHypothesis）中，确定性投影出 SimulationIntent；
2. 保持严格因果可审计性：保留 source_hypothesis_id 与 source_record_hash；
3. 为 Step 3 (Simulation Trading) 预留标准消费槽位，实现风控与资金隔离。
"""

import json
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime

from ..schemas.cognition import (
    SimulationIntent,
    SimulationIntentType,
    SimulationIntentStatus,
)


class CognitionSimulationGateway:
    """认知意图投影网关（纯确定性函数，无外部写入副作用）"""

    @classmethod
    def project_intent(
        cls,
        market_date: str,
        hypothesis: Optional[Any] = None,
        record_hash: Optional[str] = None,
        clock_now_iso: Optional[str] = None,
    ) -> SimulationIntent:
        """
        根据推演假说确定性投影生成 SimulationIntent
        """
        now_str = clock_now_iso or datetime.now().strftime("%Y-%m-%dT%H:%M:%S.000+08:00")

        if not hypothesis:
            # 当日无有效假说，输出只读观察意图
            intent_hash = hashlib.sha256(f"{market_date}_NO_HYPOTHESIS".encode("utf-8")).hexdigest()[:12]
            return SimulationIntent(
                intent_id=f"intent_{market_date.replace('-', '')}_{intent_hash}",
                market_date=market_date,
                source_hypothesis_id=None,
                source_record_hash=record_hash,
                intent_type=SimulationIntentType.OBSERVE_ONLY,
                target_entities=[],
                confidence=0.5,
                rationale="当日无推演假说，前向模拟交易保持空仓或纯观察状态。",
                risk_boundary={"max_position_ratio": 0.0, "stop_loss_pct": 0.0},
                status=SimulationIntentStatus.PENDING_CONSUMPTION,
                created_at=now_str,
            )

        hyp_id = getattr(hypothesis, "id", None)
        hyp_type = str(getattr(hypothesis, "hypothesis_type", "UNKNOWN"))
        target_asset = str(getattr(hypothesis, "target_asset", ""))
        scenario = str(getattr(hypothesis, "expected_scenario", ""))
        premise = str(getattr(hypothesis, "premise_logic", ""))

        # 确定意图类型
        if "SENTIMENT" in hyp_type or "LADDER" in hyp_type:
            if "DIVERGENCE" in scenario or "DEFENSE" in scenario or "DROP" in scenario:
                intent_type = SimulationIntentType.POSITION_DEFENSE
            else:
                intent_type = SimulationIntentType.LADDER_TRACKING
        elif "SECTOR" in hyp_type:
            intent_type = SimulationIntentType.SECTOR_FOCUS
        elif "INDEX" in hyp_type:
            if "REBOUND" in scenario or "ACCELERATION" in scenario:
                intent_type = SimulationIntentType.SECTOR_FOCUS
            else:
                intent_type = SimulationIntentType.POSITION_DEFENSE
        else:
            intent_type = SimulationIntentType.OBSERVE_ONLY

        # 提取标的实体
        entities: List[str] = []
        if target_asset and target_asset != "全市场短线情绪" and target_asset != "全市场":
            entities.append(target_asset)

        # 确定性指纹 ID
        seed = f"{market_date}_{hyp_id}_{hyp_type}_{scenario}"
        intent_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        intent_id = f"intent_{market_date.replace('-', '')}_{intent_hash}"

        # 置信度与风控红线
        risk_bounds: Dict[str, Any] = {
            "max_position_ratio": 0.3 if intent_type != SimulationIntentType.OBSERVE_ONLY else 0.0,
            "stop_loss_pct": -0.05,
            "target_scenario": scenario,
        }

        rationale = f"基于 [{hyp_type}] 推演：{premise}，预期形态为 {scenario}。"

        return SimulationIntent(
            intent_id=intent_id,
            market_date=market_date,
            source_hypothesis_id=hyp_id,
            source_record_hash=record_hash,
            intent_type=intent_type,
            target_entities=entities,
            confidence=0.8,
            rationale=rationale,
            risk_boundary=risk_bounds,
            status=SimulationIntentStatus.PENDING_CONSUMPTION,
            created_at=now_str,
        )
