"""
Unit tests for Cognition Output -> Simulation Intent 预留接口契约
上位依据：
- Step 2 生产复盘运行时架构设计规范
- Phase 2B -> Phase 3 边界契约隔离原则
"""

import pytest
import json
from unittest.mock import MagicMock

from app.schemas.cognition import (
    SimulationIntent,
    SimulationIntentType,
    SimulationIntentStatus,
)
from app.cognition.simulation_gateway import CognitionSimulationGateway


def test_simulation_gateway_observe_only_without_hypothesis():
    intent = CognitionSimulationGateway.project_intent(
        market_date="2026-09-30",
        hypothesis=None,
        record_hash="obs_hash_1234567890",
        clock_now_iso="2026-09-30T15:35:00.000+08:00",
    )
    assert isinstance(intent, SimulationIntent)
    assert intent.market_date == "2026-09-30"
    assert intent.intent_type == SimulationIntentType.OBSERVE_ONLY
    assert intent.status == SimulationIntentStatus.PENDING_CONSUMPTION
    assert intent.source_hypothesis_id is None
    assert intent.source_record_hash == "obs_hash_1234567890"
    assert intent.risk_boundary.get("max_position_ratio") == 0.0


def test_simulation_gateway_ladder_tracking_intent():
    mock_hypo = MagicMock()
    mock_hypo.id = 42
    mock_hypo.hypothesis_type = "SENTIMENT_CYCLE"
    mock_hypo.target_asset = "全市场短线情绪"
    mock_hypo.expected_scenario = "ACCELERATION"
    mock_hypo.premise_logic = "09-30 连板梯队完整，高标抱团坚决"

    intent = CognitionSimulationGateway.project_intent(
        market_date="2026-09-30",
        hypothesis=mock_hypo,
        record_hash="record_hash_abcdef",
        clock_now_iso="2026-09-30T15:35:00.000+08:00",
    )
    assert intent.intent_type == SimulationIntentType.LADDER_TRACKING
    assert intent.source_hypothesis_id == 42
    assert intent.source_record_hash == "record_hash_abcdef"
    assert intent.confidence == 0.8
    assert intent.status == SimulationIntentStatus.PENDING_CONSUMPTION
    assert "ACCELERATION" in intent.rationale


def test_simulation_gateway_position_defense_intent():
    mock_hypo = MagicMock()
    mock_hypo.id = 43
    mock_hypo.hypothesis_type = "SENTIMENT_CYCLE"
    mock_hypo.target_asset = "全市场短线情绪"
    mock_hypo.expected_scenario = "DIVERGENCE"
    mock_hypo.premise_logic = "高标分歧退潮"

    intent = CognitionSimulationGateway.project_intent(
        market_date="2026-09-30",
        hypothesis=mock_hypo,
        record_hash="hash_defense_123",
    )
    assert intent.intent_type == SimulationIntentType.POSITION_DEFENSE
    assert intent.source_hypothesis_id == 43


def test_simulation_gateway_determinism():
    mock_hypo = MagicMock()
    mock_hypo.id = 100
    mock_hypo.hypothesis_type = "SECTOR_LEADER"
    mock_hypo.target_asset = "固态电池"
    mock_hypo.expected_scenario = "ROTATION"
    mock_hypo.premise_logic = "新能源板块轮动修复"

    i1 = CognitionSimulationGateway.project_intent(
        market_date="2026-09-30",
        hypothesis=mock_hypo,
        record_hash="hash_001",
        clock_now_iso="2026-09-30T15:35:00.000+08:00",
    )
    i2 = CognitionSimulationGateway.project_intent(
        market_date="2026-09-30",
        hypothesis=mock_hypo,
        record_hash="hash_001",
        clock_now_iso="2026-09-30T15:35:00.000+08:00",
    )
    assert i1.intent_id == i2.intent_id
    assert i1.intent_type == SimulationIntentType.SECTOR_FOCUS
    assert "固态电池" in i1.target_entities
