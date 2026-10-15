import pytest
from unittest.mock import AsyncMock, patch
from backend.app.services.zhijian_transcendent_review_service import zhijian_transcendent_service

@pytest.mark.asyncio
async def test_entity_extraction_system_and_stock():
    # 1. 系统功能与日常提问应被识别为 SYSTEM_FEATURE，不误触发股票搜索
    ent_sys = await zhijian_transcendent_service._extract_target_entity("你到底可以做哪些事情")
    assert ent_sys is not None
    assert ent_sys.get("type") == "SYSTEM_FEATURE"

    ent_busy = await zhijian_transcendent_service._extract_target_entity("在干嘛？")
    assert ent_busy is not None
    assert ent_busy.get("type") == "SYSTEM_FEATURE"

    # 2. 6位代码识别
    ent_code = await zhijian_transcendent_service._extract_target_entity("300981")
    assert ent_code is not None
    assert ent_code.get("type") == "STOCK"
    assert ent_code.get("code") == "300981"

    # 3. 股票名称模糊识别 (清洗停用词后精准命中)
    ent_stock = await zhijian_transcendent_service._extract_target_entity("帮我分析中红医疗")
    assert ent_stock is not None
    assert ent_stock.get("type") == "STOCK"
    assert ent_stock.get("code") == "300981"
    assert "中红医疗" in ent_stock.get("name", "")

@pytest.mark.asyncio
async def test_no_mock_168_trillion_dogma_template():
    """验证彻底消除了 1.68万亿写死模版与教条八股文"""
    # 模拟 LLM 抛出异常的情况
    with patch.object(zhijian_transcendent_service, "_execute_llm_call", side_effect=RuntimeError("Connection timeout test")):
        ans = await zhijian_transcendent_service.ask_ai_cognitive_query(
            query="帮我分析中红医疗",
            review_context="今日大盘全天深V",
            target_date="2026-10-12"
        )
        # 绝不包含写死的假数据模版
        assert "今日盘面真实去重成交总额（1.68万亿）" not in ans
        assert "克制左侧冲动，紧盯前排核心梯队" not in ans
        # 必须诚实提示错误并包含真实调取的个股客观数据
        assert "大语言模型（LLM）API 调用未成功" in ans or "客观物理事实速报" in ans
        assert "中红医疗" in ans
        assert "300981" in ans

@pytest.mark.asyncio
async def test_normal_llm_response_without_dogma():
    """验证在真实或模拟 LLM 响应时，能给出自然专业的分析且不包含死板教条"""
    mock_resp = "中红医疗（300981）今日日内探底 21.06 元后暴力冲高至 24.22 元，振幅 13.74%，显示活跃资金博弈强烈。"
    with patch.object(zhijian_transcendent_service, "_execute_llm_call", return_value=mock_resp):
        ans = await zhijian_transcendent_service.ask_ai_cognitive_query(
            query="帮我分析中红医疗",
            review_context="基准复盘全文",
            target_date="2026-10-12"
        )
        assert ans == mock_resp
        assert "1.68万亿" not in ans
