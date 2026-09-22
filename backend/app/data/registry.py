import logging
from typing import Any, Callable, Coroutine, Dict, List
from .capabilities import DataQuality, DataResult

logger = logging.getLogger(__name__)

class ProviderRegistry:
    """
    Provider 注册中心
    - 管理 Capability → Provider 降级调用链
    - 运行时支持动态注册、替换与降级调用
    """

    def __init__(self):
        # capability -> list of (provider_name, provider_instance)
        self._registry: Dict[str, List[tuple[str, Any]]] = {}

    def register(self, capability: str, provider_name: str, provider_instance: Any, is_primary: bool = False):
        if capability not in self._registry:
            self._registry[capability] = []

        entry = (provider_name, provider_instance)
        if is_primary:
            self._registry[capability].insert(0, entry)
        else:
            self._registry[capability].append(entry)

        logger.info(f"Registered provider '{provider_name}' for capability '{capability}' (primary={is_primary})")

    async def execute_with_fallback(
        self,
        capability: str,
        func_name: str,
        *args,
        **kwargs
    ) -> DataResult:
        """
        按注册的降级链尝试执行指定能力的获取方法
        """
        providers = self._registry.get(capability, [])
        if not providers:
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                provider="none",
                error_message=f"No provider registered for capability: {capability}"
            )

        last_error = None
        for i, (provider_name, provider) in enumerate(providers):
            method: Callable[..., Coroutine[Any, Any, DataResult]] = getattr(provider, func_name, None)
            if not method:
                continue

            try:
                result: DataResult = await method(*args, **kwargs)
                if result and result.quality != DataQuality.FAILED:
                    if i > 0:
                        result.fallback_used = True
                    return result
                else:
                    last_error = result.error_message if result else "Unknown error"
                    logger.warning(f"Provider '{provider_name}' returned {result.quality}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Provider '{provider_name}' raised exception for '{capability}': {e}")

        return DataResult(
            data=None,
            quality=DataQuality.FAILED,
            provider="all_failed",
            error_message=f"All providers failed for capability '{capability}'. Last error: {last_error}"
        )

registry = ProviderRegistry()
