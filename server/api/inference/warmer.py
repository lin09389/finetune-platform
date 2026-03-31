"""
模型预热机制
应用启动时预加载常用模型，减少首次请求延迟
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WarmupConfig:
    models: list[str]
    warmup_prompt: str = "Hello"
    max_tokens: int = 10
    timeout: int = 300
    parallel: bool = False


@dataclass
class WarmupResult:
    model: str
    success: bool
    latency_ms: float
    error: str | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class ModelWarmer:
    """模型预热器"""

    def __init__(self, config: WarmupConfig | None = None):
        self.config = config or WarmupConfig(models=[])
        self._results: list[WarmupResult] = []
        self._is_warming = False

    async def warmup(self, models: list[str] | None = None) -> list[WarmupResult]:
        """
        预热模型
        
        Args:
            models: 要预热的模型列表，如果为None则使用配置中的模型
            
        Returns:
            预热结果列表
        """
        models = models or self.config.models
        if not models:
            logger.info("无预热模型配置，跳过预热")
            return []

        if self._is_warming:
            logger.warning("预热正在进行中，跳过")
            return self._results

        self._is_warming = True
        self._results = []

        logger.info(f"开始预热模型: {models}")
        start_time = asyncio.get_event_loop().time()

        try:
            if self.config.parallel:
                tasks = [self._warmup_model(model) for model in models]
                self._results = await asyncio.gather(*tasks, return_exceptions=True)
                self._results = [
                    r if isinstance(r, WarmupResult) else WarmupResult(
                        model=models[i],
                        success=False,
                        latency_ms=0,
                        error=str(r)
                    )
                    for i, r in enumerate(self._results)
                ]
            else:
                for model in models:
                    result = await self._warmup_model(model)
                    self._results.append(result)
                    if not result.success:
                        logger.warning(f"模型 {model} 预热失败: {result.error}")
        finally:
            self._is_warming = False

        total_time = (asyncio.get_event_loop().time() - start_time) * 1000
        success_count = sum(1 for r in self._results if r.success)

        logger.info(
            f"预热完成: {success_count}/{len(models)} 成功, "
            f"总耗时: {total_time:.0f}ms"
        )

        return self._results

    async def _warmup_model(self, model_name: str) -> WarmupResult:
        """预热单个模型"""
        start_time = asyncio.get_event_loop().time()

        try:
            from api.inference.scheduler import get_scheduler
            scheduler = get_scheduler()

            backend = await asyncio.wait_for(
                scheduler.get_backend(),
                timeout=self.config.timeout
            )

            if hasattr(backend, 'load_model'):
                await asyncio.wait_for(
                    backend.load_model(model_name),
                    timeout=self.config.timeout
                )

            try:
                from api.types import GenerationConfig
                config = GenerationConfig(max_tokens=self.config.max_tokens)

                await asyncio.wait_for(
                    backend.generate(self.config.warmup_prompt, config),
                    timeout=60
                )
            except Exception as e:
                logger.debug(f"预热推理跳过: {e}")

            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            logger.info(f"模型预热成功: {model_name} ({latency_ms:.0f}ms)")

            return WarmupResult(
                model=model_name,
                success=True,
                latency_ms=latency_ms
            )

        except asyncio.TimeoutError:
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            error = f"预热超时 ({self.config.timeout}s)"
            logger.error(f"模型预热超时: {model_name}")
            return WarmupResult(
                model=model_name,
                success=False,
                latency_ms=latency_ms,
                error=error
            )

        except Exception as e:
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            error = str(e)
            logger.error(f"模型预热失败: {model_name}, 错误: {e}")
            return WarmupResult(
                model=model_name,
                success=False,
                latency_ms=latency_ms,
                error=error
            )

    def get_results(self) -> list[WarmupResult]:
        return self._results

    def get_stats(self) -> dict[str, Any]:
        if not self._results:
            return {"status": "no_results"}

        success_count = sum(1 for r in self._results if r.success)
        total_latency = sum(r.latency_ms for r in self._results)

        return {
            "total_models": len(self._results),
            "success_count": success_count,
            "failed_count": len(self._results) - success_count,
            "total_latency_ms": total_latency,
            "avg_latency_ms": total_latency / len(self._results),
            "is_warming": self._is_warming
        }


_warmer: ModelWarmer | None = None


def get_warmer() -> ModelWarmer:
    global _warmer
    if _warmer is None:
        from core.config import get_settings
        settings = get_settings()
        warmup_models = getattr(settings, 'warmup_models', [])
        _warmer = ModelWarmer(WarmupConfig(models=warmup_models))
    return _warmer


async def startup_warmup():
    """应用启动时执行预热"""
    warmer = get_warmer()

    if not warmer.config.models:
        logger.info("无预热模型配置")
        return

    asyncio.create_task(warmer.warmup())
