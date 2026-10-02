"""
Phase 2B.2: 真实大语言模型沙箱驱动适配器 (LLMDriverAdapter)
上位依据：
1. 《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》
2. 《Phase 2B.2 基线封存与真实 LLM Sandbox Trial 执行指令》

核心职责：
- 严格遵循 OpenAI-compatible 规范接入外部大语言模型；
- 仅从安全环境变量 / .env 读取 API Key 与 Base URL，绝对杜绝源码与日志硬编码；
- 提供超时熔断 (Timeout)、有限指数退避重试 (Retry) 与错误隔离机制 (Error Isolation)；
- 具备密钥脱敏与日志清洗屏障，保证任何异常信息均不泄漏 API Token。
"""

import os
import time
import logging
from typing import Dict, Any, Optional
import httpx
from dotenv import load_dotenv

# 预加载 .env (若存在且未在当前进程注入环境变量)，但保持 override=False
load_dotenv(override=False)

logger = logging.getLogger("cognition.llm_driver")


class SandboxLLMError(Exception):
    """受约束沙箱 LLM 驱动受控异常"""
    pass


class LLMDriverAdapter:
    """真实 LLM 沙箱驱动适配器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        temperature: Optional[float] = None,
        max_retries: int = 2,
    ):
        # 优先读取显式参数，其次读取统一环境变量，最后回退至常用提供商环境变量
        self._api_key = (
            api_key
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        ).strip()

        raw_base_url = (
            base_url
            or os.environ.get("LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).strip()

        # 标准化 base_url 去除末尾斜杠
        self.base_url = raw_base_url.rstrip("/")

        self.model = (
            model
            or os.environ.get("LLM_MODEL")
            or "deepseek-chat"
        ).strip()

        self.timeout_seconds = timeout_seconds or float(os.environ.get("LLM_TIMEOUT_SECONDS", "45.0"))
        self.temperature = temperature if temperature is not None else float(os.environ.get("LLM_TEMPERATURE", "0.2"))
        self.max_retries = max_retries

    @property
    def is_configured(self) -> bool:
        """检查 API Key 是否已配置"""
        return bool(self._api_key and len(self._api_key) > 5)

    def sanitize_secret(self, text: str) -> str:
        """从字符串中严格剔除 API 密钥痕迹"""
        if not text or not self._api_key:
            return text
        return text.replace(self._api_key, "***REDACTED_API_KEY***")

    def get_public_metadata(self) -> Dict[str, Any]:
        """获取不含私密信息的驱动配置元数据"""
        return {
            "is_configured": self.is_configured,
            "base_url": self.base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "max_retries": self.max_retries,
        }

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        向真实 LLM 发起受控推演调用
        - 强制受控重试
        - 捕获全部网络与服务端异常，转换为安全的 SandboxLLMError
        - 绝不泄露 API Token
        """
        if not self.is_configured:
            raise SandboxLLMError(
                "LLM API Key 尚未配置。请通过环境变量 LLM_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY 注入安全凭证。"
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
        }

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(endpoint, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise SandboxLLMError("LLM 响应 choices 为空，无有效内容生成")
                    msg_content = choices[0].get("message", {}).get("content", "")
                    if not msg_content:
                        raise SandboxLLMError("LLM 返回消息内容为空")
                    return str(msg_content).strip()

                # 可重试状态码: 429 (Rate Limit) 或 5xx (Server Error)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue

                # 4xx 客户端错误 (如 401 鉴权失败、400 格式错误) 直接中断
                err_body = self.sanitize_secret(resp.text[:300])
                raise SandboxLLMError(
                    f"LLM 接口调用返回错误状态码 {resp.status_code}: {err_body}"
                )

            except httpx.TimeoutException as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                raise SandboxLLMError(f"LLM 请求超时 ({self.timeout_seconds}s): {str(e)}")

            except httpx.RequestError as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                clean_msg = self.sanitize_secret(str(e))
                raise SandboxLLMError(f"LLM 网络连接异常: {clean_msg}")

            except SandboxLLMError:
                raise

            except Exception as e:
                clean_msg = self.sanitize_secret(str(e))
                raise SandboxLLMError(f"LLM 调用未知异常: {clean_msg}")

        raise SandboxLLMError(f"LLM 重试耗尽失败: {self.sanitize_secret(str(last_err))}")

    def ping(self) -> Dict[str, Any]:
        """最小化连通性测试"""
        start_t = time.time()
        reply = self.generate(
            system_prompt="You are a system health checker.",
            user_prompt="Reply with exactly 'PONG'",
        )
        elapsed_ms = (time.time() - start_t) * 1000
        return {
            "status": "OK",
            "reply": reply,
            "latency_ms": round(elapsed_ms, 2),
            "model": self.model,
        }
