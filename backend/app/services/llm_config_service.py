"""
Phase 3: System LLM Configuration & OpenAI-Compatible Relay Service
==================================================================
管理与持久化用户自定义大语言模型 API 配置 (支持标准 OpenAI 中转站 / OneAPI / NewAPI / 直连)。
- 持久化至 data/llm_config.json，容器重启或 NAS 重新挂载不丢失；
- 热加载更新 settings 与 os.environ，全系统所有推演模块即刻无缝生效；
- 提供真实往返连通性测试 (Test Connection) 与延迟诊断；
- 遵循数据脱敏规范，绝不泄露完整 API Token。
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import httpx

from backend.app.config import PROJECT_ROOT, settings
from backend.app.schemas.system_llm import (
    LLMConfigResponse,
    LLMConfigUpdateRequest,
    LLMTestConnectionRequest,
    LLMTestConnectionResponse,
)

logger = logging.getLogger("system.llm_config")

CONFIG_FILE_PATH = PROJECT_ROOT / "data" / "llm_config.json"


class LLMConfigService:
    """系统 LLM 与 OpenAI 中转站接入管理服务"""

    @classmethod
    def _mask_api_key(cls, key: str) -> str:
        """脱敏 API Key"""
        if not key:
            return ""
        stripped = key.strip()
        if len(stripped) <= 8:
            return "****"
        return f"{stripped[:4]}****{stripped[-4:]}"

    @classmethod
    def _load_persisted_data(cls) -> Optional[Dict[str, Any]]:
        """从 data/llm_config.json 读取持久化配置"""
        try:
            if CONFIG_FILE_PATH.exists():
                text = CONFIG_FILE_PATH.read_text(encoding="utf-8")
                if text.strip():
                    return json.loads(text)
        except Exception as e:
            logger.warning(f"Failed to read {CONFIG_FILE_PATH}: {e}")
        return None

    @classmethod
    def get_active_config(cls) -> LLMConfigResponse:
        """获取当前系统生效的 LLM 配置"""
        persisted = cls._load_persisted_data()

        if persisted:
            raw_key = persisted.get("api_key") or ""
            return LLMConfigResponse(
                provider_type=persisted.get("provider_type", "openai_compatible"),
                base_url=persisted.get("base_url") or settings.LLM_BASE_URL,
                model=persisted.get("model") or settings.LLM_MODEL,
                api_key_masked=cls._mask_api_key(raw_key),
                has_api_key=bool(raw_key and len(raw_key) > 5),
                temperature=float(persisted.get("temperature", 0.2)),
                max_tokens=int(persisted.get("max_tokens", 4000)),
                timeout_seconds=float(persisted.get("timeout_seconds", 60.0)),
                is_customized=True,
                updated_at=persisted.get("updated_at"),
            )

        # 默认环境变量值
        default_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        return LLMConfigResponse(
            provider_type="openai_compatible",
            base_url=settings.LLM_BASE_URL or "https://api.deepseek.com/v1",
            model=settings.LLM_MODEL or "deepseek-chat",
            api_key_masked=cls._mask_api_key(default_key),
            has_api_key=bool(default_key and len(default_key) > 5),
            temperature=0.2,
            max_tokens=4000,
            timeout_seconds=60.0,
            is_customized=False,
            updated_at=None,
        )

    @classmethod
    def get_runtime_credentials(cls) -> Dict[str, Any]:
        """获取当前系统运行时调用的真实完整凭证与参数（含未脱敏 key）"""
        persisted = cls._load_persisted_data()
        if persisted and persisted.get("api_key"):
            return {
                "api_key": str(persisted.get("api_key", "")).strip(),
                "base_url": str(persisted.get("base_url") or settings.LLM_BASE_URL).rstrip("/"),
                "model": str(persisted.get("model") or settings.LLM_MODEL or "deepseek-chat").strip(),
                "temperature": float(persisted.get("temperature", 0.3)),
                "max_tokens": int(persisted.get("max_tokens", 4000)),
                "timeout_seconds": float(persisted.get("timeout_seconds", 60.0)),
            }

        default_key = settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        return {
            "api_key": default_key.strip(),
            "base_url": (settings.LLM_BASE_URL or "https://api.deepseek.com/v1").rstrip("/"),
            "model": (settings.LLM_MODEL or "deepseek-chat").strip(),
            "temperature": float(os.environ.get("LLM_TEMPERATURE", 0.3)),
            "max_tokens": 4000,
            "timeout_seconds": float(os.environ.get("LLM_TIMEOUT_SECONDS", 60.0)),
        }

    @classmethod
    def save_config(cls, req: LLMConfigUpdateRequest) -> LLMConfigResponse:
        """保存并热加载新 LLM 配置"""
        existing = cls._load_persisted_data() or {}
        
        # 处理 API Key：若前端传空或未传，则保留旧 Key
        new_key = req.api_key.strip() if req.api_key else ""
        if not new_key:
            new_key = existing.get("api_key") or settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""

        # 标准化 base_url 去除末尾斜杠
        clean_base_url = req.base_url.strip().rstrip("/")
        # 若用户误填了 /chat/completions，自动截断回退到基础端点
        if clean_base_url.endswith("/chat/completions"):
            clean_base_url = clean_base_url[:-17].rstrip("/")

        save_dict = {
            "provider_type": req.provider_type or "openai_compatible",
            "base_url": clean_base_url,
            "model": req.model.strip(),
            "api_key": new_key,
            "temperature": req.temperature if req.temperature is not None else 0.2,
            "max_tokens": req.max_tokens if req.max_tokens is not None else 4000,
            "timeout_seconds": req.timeout_seconds if req.timeout_seconds is not None else 60.0,
            "updated_at": datetime.now().isoformat(),
        }

        # 确保 data 目录存在并写入
        try:
            CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE_PATH.write_text(json.dumps(save_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Custom LLM configuration saved to {CONFIG_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to write {CONFIG_FILE_PATH}: {e}")

        # 热加载至系统环境变量与 settings 对象
        cls._apply_to_runtime(save_dict)

        return cls.get_active_config()

    @classmethod
    def reset_config(cls) -> LLMConfigResponse:
        """重置回系统环境变量默认配置"""
        try:
            if CONFIG_FILE_PATH.exists():
                CONFIG_FILE_PATH.unlink()
                logger.info(f"Removed custom config file: {CONFIG_FILE_PATH}")
        except Exception as e:
            logger.error(f"Failed to remove {CONFIG_FILE_PATH}: {e}")

        # 恢复默认 settings
        settings.LLM_BASE_URL = os.environ.get("ENV_DEFAULT_LLM_BASE_URL") or "https://api.deepseek.com/v1"
        settings.LLM_MODEL = os.environ.get("ENV_DEFAULT_LLM_MODEL") or "deepseek-chat"
        default_key = os.environ.get("ENV_DEFAULT_LLM_API_KEY") or os.environ.get("ENV_DEFAULT_DEEPSEEK_API_KEY") or ""
        settings.LLM_API_KEY = default_key
        settings.DEEPSEEK_API_KEY = default_key

        os.environ["LLM_BASE_URL"] = settings.LLM_BASE_URL
        os.environ["LLM_MODEL"] = settings.LLM_MODEL
        os.environ["LLM_API_KEY"] = default_key
        os.environ["DEEPSEEK_API_KEY"] = default_key

        return cls.get_active_config()

    @classmethod
    def _apply_to_runtime(cls, conf: Dict[str, Any]) -> None:
        """将配置实时注入系统 settings 和环境变量"""
        base_url = conf.get("base_url")
        model = conf.get("model")
        key = conf.get("api_key")
        temp = conf.get("temperature", 0.2)
        timeout = conf.get("timeout_seconds", 60.0)

        if base_url:
            settings.LLM_BASE_URL = base_url
            os.environ["LLM_BASE_URL"] = base_url
            os.environ["OPENAI_BASE_URL"] = base_url

        if model:
            settings.LLM_MODEL = model
            os.environ["LLM_MODEL"] = model

        if key:
            settings.LLM_API_KEY = key
            settings.DEEPSEEK_API_KEY = key
            os.environ["LLM_API_KEY"] = key
            os.environ["DEEPSEEK_API_KEY"] = key
            os.environ["OPENAI_API_KEY"] = key

        os.environ["LLM_TEMPERATURE"] = str(temp)
        os.environ["LLM_TIMEOUT_SECONDS"] = str(timeout)

        logger.info(f"[LLM HOT RELOAD] Active Model: {settings.LLM_MODEL}, Base URL: {settings.LLM_BASE_URL}, Key: {cls._mask_api_key(settings.LLM_API_KEY)}")

    @classmethod
    def load_and_apply_on_startup(cls) -> None:
        """服务启动时自动加载并应用持久化配置"""
        # 记录环境默认基准值用于 reset
        os.environ.setdefault("ENV_DEFAULT_LLM_BASE_URL", settings.LLM_BASE_URL)
        os.environ.setdefault("ENV_DEFAULT_LLM_MODEL", settings.LLM_MODEL)
        os.environ.setdefault("ENV_DEFAULT_LLM_API_KEY", settings.LLM_API_KEY)
        os.environ.setdefault("ENV_DEFAULT_DEEPSEEK_API_KEY", settings.DEEPSEEK_API_KEY)

        persisted = cls._load_persisted_data()
        if persisted:
            logger.info("Found custom persisted LLM configuration on startup. Applying...")
            cls._apply_to_runtime(persisted)
        else:
            logger.info("Using default environment LLM configuration.")

    @classmethod
    async def test_connection(cls, req: LLMTestConnectionRequest) -> LLMTestConnectionResponse:
        """
        向指定的中转站或官方 API 发起实际往返联通性测试
        - 自动规范化 /chat/completions 路由
        - 测量首包往返延迟 (ms)
        - 提取模型回复片段
        """
        clean_base = req.base_url.strip().rstrip("/")
        if clean_base.endswith("/chat/completions"):
            endpoint = clean_base
        else:
            endpoint = f"{clean_base}/chat/completions"

        # 若未提供 Key，回退使用已保存的 Key
        test_key = req.api_key.strip() if req.api_key else ""
        if not test_key:
            persisted = cls._load_persisted_data() or {}
            test_key = persisted.get("api_key") or settings.LLM_API_KEY or settings.DEEPSEEK_API_KEY or ""

        if not test_key:
            return LLMTestConnectionResponse(
                success=False,
                latency_ms=0,
                message="缺少 API Key，无法发起联通性握手",
                error="请提供 API Key 后再进行测试",
            )

        headers = {
            "Authorization": f"Bearer {test_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": req.model.strip(),
            "messages": [
                {"role": "system", "content": "You are a test ping bot."},
                {"role": "user", "content": "请回复'pong'"},
            ],
            "max_tokens": 15,
            "temperature": 0.1,
        }

        t0 = time.time()
        timeout = req.timeout_seconds or 20.0

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
            latency_ms = round((time.time() - t0) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                reply_text = choices[0].get("message", {}).get("content", "").strip() if choices else "无返回内容"
                return LLMTestConnectionResponse(
                    success=True,
                    latency_ms=latency_ms,
                    model_used=req.model,
                    reply_preview=reply_text[:100],
                    message=f"中转站 API 握手成功！模型 [{req.model}] 响应延迟 {latency_ms}ms",
                )
            elif resp.status_code == 401:
                return LLMTestConnectionResponse(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"HTTP 401 Unauthorized: 密钥无效或中转站拒绝访问",
                    message="鉴权失败：请检查 API Key 是否正确或额度是否充足",
                )
            elif resp.status_code == 404:
                return LLMTestConnectionResponse(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"HTTP 404 Not Found: 请求端点 [{endpoint}] 不存在",
                    message="端点路径错误：中转站 Base URL 通常需要带 /v1 (如 https://api.proxy.com/v1)",
                )
            else:
                raw_err = resp.text[:200]
                return LLMTestConnectionResponse(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"HTTP {resp.status_code}: {raw_err}",
                    message=f"中转站返回非正常状态码 {resp.status_code}",
                )

        except httpx.ConnectTimeout:
            latency_ms = round((time.time() - t0) * 1000)
            return LLMTestConnectionResponse(
                success=False,
                latency_ms=latency_ms,
                error="网络连接超时 (Connect Timeout)",
                message="无法连接至该 Base URL，请检查中转站地址或网络代理",
            )
        except httpx.ConnectError as ce:
            latency_ms = round((time.time() - t0) * 1000)
            return LLMTestConnectionResponse(
                success=False,
                latency_ms=latency_ms,
                error=f"连接被拒绝或主机不可达: {str(ce)}",
                message="中转站主机不可达，请检查域名拼写或端口",
            )
        except Exception as e:
            latency_ms = round((time.time() - t0) * 1000)
            return LLMTestConnectionResponse(
                success=False,
                latency_ms=latency_ms,
                error=str(e),
                message=f"测试发生异常: {str(e)}",
            )
