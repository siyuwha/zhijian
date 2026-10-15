import pytest
import os
import json
from unittest.mock import patch, MagicMock
from httpx import Response
from backend.app.schemas.system_llm import (
    LLMConfigUpdateRequest,
    LLMTestConnectionRequest,
)
from backend.app.services.llm_config_service import LLMConfigService, CONFIG_FILE_PATH
from backend.app.config import settings


@pytest.fixture(autouse=True)
def cleanup_config_file():
    """测试前后清理临时测试配置文件"""
    if CONFIG_FILE_PATH.exists():
        CONFIG_FILE_PATH.unlink()
    yield
    if CONFIG_FILE_PATH.exists():
        CONFIG_FILE_PATH.unlink()


def test_get_default_config():
    """验证获取默认配置"""
    conf = LLMConfigService.get_active_config()
    assert conf is not None
    assert conf.provider_type == "openai_compatible"
    assert conf.model in (settings.LLM_MODEL, "deepseek-chat")
    assert conf.is_customized is False


def test_save_and_hot_reload_config():
    """验证保存并热加载配置"""
    req = LLMConfigUpdateRequest(
        provider_type="openai_compatible",
        base_url="https://api.my-relay.com/v1",
        model="gpt-4o",
        api_key="sk-testsecretkey123456",
        temperature=0.3,
        timeout_seconds=45.0,
    )

    conf = LLMConfigService.save_config(req)
    assert conf.is_customized is True
    assert conf.base_url == "https://api.my-relay.com/v1"
    assert conf.model == "gpt-4o"
    assert conf.has_api_key is True
    assert conf.api_key_masked == "sk-t****3456"
    assert conf.temperature == 0.3
    assert conf.timeout_seconds == 45.0

    # 验证运行时 settings 和 os.environ 实时热生效
    assert settings.LLM_BASE_URL == "https://api.my-relay.com/v1"
    assert settings.LLM_MODEL == "gpt-4o"
    assert settings.LLM_API_KEY == "sk-testsecretkey123456"
    assert os.environ.get("LLM_MODEL") == "gpt-4o"


def test_base_url_normalization():
    """验证 base_url 自动去除末尾斜杠和多余 chat/completions"""
    req = LLMConfigUpdateRequest(
        base_url="https://api.proxy.com/v1/chat/completions",
        model="claude-3-5-sonnet",
        api_key="sk-test",
    )
    conf = LLMConfigService.save_config(req)
    assert conf.base_url == "https://api.proxy.com/v1"


def test_reset_config():
    """验证重置为默认配置"""
    req = LLMConfigUpdateRequest(
        base_url="https://api.temporary.com/v1",
        model="custom-model",
        api_key="sk-temp",
    )
    LLMConfigService.save_config(req)
    assert CONFIG_FILE_PATH.exists()

    res = LLMConfigService.reset_config()
    assert res.is_customized is False
    assert not CONFIG_FILE_PATH.exists()


@pytest.mark.asyncio
async def test_connection_success():
    """验证连通性测试成功场景 (Mock HTTP 200)"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {"message": {"role": "assistant", "content": "pong"}}
        ]
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        req = LLMTestConnectionRequest(
            base_url="https://api.relay.com/v1",
            api_key="sk-test123456",
            model="gpt-4o",
        )
        res = await LLMConfigService.test_connection(req)
        assert res.success is True
        assert res.reply_preview == "pong"
        assert res.model_used == "gpt-4o"
        assert "握手成功" in res.message


@pytest.mark.asyncio
async def test_connection_unauthorized():
    """验证连通性测试 401 鉴权失败场景"""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Invalid API Key"

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        req = LLMTestConnectionRequest(
            base_url="https://api.relay.com/v1",
            api_key="sk-badkey",
            model="gpt-4o",
        )
        res = await LLMConfigService.test_connection(req)
        assert res.success is False
        assert "401" in (res.error or "")
