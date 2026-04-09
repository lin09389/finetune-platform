"""
异步 OCR 服务
将 OCR 识别改为异步任务，支持任务状态查询和结果缓存
"""
import asyncio
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OCRTaskStatus(str, Enum):
    """OCR任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OCRTask:
    """OCR任务"""
    task_id: str
    status: OCRTaskStatus = OCRTaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds() * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result[:500] if self.result and len(self.result) > 500 else self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": round(self.duration_ms, 2),
            "metadata": self.metadata,
        }


class AsyncOCRService:
    """
    异步 OCR 服务

    支持异步OCR识别、任务状态查询、结果缓存
    """

    CACHE_MAX_SIZE = 200
    TASK_MAX_AGE_SECONDS = 3600

    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self._tasks: dict[str, OCRTask] = {}
        self._cache: dict[str, str] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._lock = threading.RLock()
        self._ocr = None
        self._initialized = False

        self._init_ocr()

    def _init_ocr(self):
        """初始化OCR引擎"""
        try:
            from cua.ocr import OCRRecognizer
            self._ocr = OCRRecognizer()
            self._initialized = True
            logger.info("异步OCR服务初始化成功")
        except Exception as e:
            logger.warning(f"OCR引擎初始化失败: {e}")
            self._initialized = False

    def is_available(self) -> bool:
        """检查OCR是否可用"""
        return self._initialized and self._ocr is not None

    def _generate_task_id(self, image_data: bytes, lang: str = None) -> str:
        """生成任务ID"""
        content = image_data + (lang or "chi_sim+eng").encode()
        return hashlib.md5(content).hexdigest()[:16]

    def _generate_cache_key(self, image_data: bytes, lang: str = None) -> str:
        """生成缓存键"""
        content = image_data + (lang or "chi_sim+eng").encode()
        return hashlib.sha256(content).hexdigest()

    def _get_cached_result(self, cache_key: str) -> str | None:
        """获取缓存结果"""
        with self._lock:
            if cache_key in self._cache:
                self._cache_timestamps[cache_key] = datetime.now()
                return self._cache[cache_key]
        return None

    def _set_cache_result(self, cache_key: str, result: str):
        """设置缓存结果"""
        with self._lock:
            if len(self._cache) >= self.CACHE_MAX_SIZE:
                oldest_key = min(self._cache_timestamps, key=self._cache_timestamps.get)
                del self._cache[oldest_key]
                del self._cache_timestamps[oldest_key]

            self._cache[cache_key] = result
            self._cache_timestamps[cache_key] = datetime.now()

    async def submit_task(
        self,
        image_data: bytes,
        lang: str = None,
        use_cache: bool = True,
        priority: int = 0,
    ) -> str:
        """
        提交OCR任务

        Args:
            image_data: 图像数据
            lang: 语言
            use_cache: 是否使用缓存
            priority: 优先级

        Returns:
            str: 任务ID
        """
        if not self.is_available():
            raise RuntimeError("OCR服务不可用")

        cache_key = self._generate_cache_key(image_data, lang)

        if use_cache:
            cached = self._get_cached_result(cache_key)
            if cached:
                task_id = self._generate_task_id(image_data, lang)
                task = OCRTask(
                    task_id=task_id,
                    status=OCRTaskStatus.COMPLETED,
                    result=cached,
                    metadata={"from_cache": True},
                )
                with self._lock:
                    self._tasks[task_id] = task
                return task_id

        task_id = self._generate_task_id(image_data, lang)
        task = OCRTask(
            task_id=task_id,
            metadata={"lang": lang, "priority": priority, "cache_key": cache_key},
        )

        with self._lock:
            self._tasks[task_id] = task

        asyncio.create_task(self._run_ocr_task(task_id, image_data, lang, cache_key, use_cache))

        return task_id

    async def _run_ocr_task(
        self,
        task_id: str,
        image_data: bytes,
        lang: str,
        cache_key: str,
        use_cache: bool,
    ):
        """执行OCR任务"""
        import io

        from PIL import Image

        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            task.status = OCRTaskStatus.RUNNING
            task.started_at = datetime.now()

        try:
            image = Image.open(io.BytesIO(image_data))

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._ocr.recognize,
                image,
                lang or "chi_sim+eng"
            )

            text = result if isinstance(result, str) else str(result)

            if use_cache:
                self._set_cache_result(cache_key, text)

            with self._lock:
                task.status = OCRTaskStatus.COMPLETED
                task.result = text
                task.completed_at = datetime.now()

            logger.info(f"OCR任务完成: {task_id}, 耗时 {task.duration_ms:.0f}ms")

        except Exception as e:
            logger.error(f"OCR任务失败: {task_id} - {e}")

            with self._lock:
                task.status = OCRTaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()

    def get_task_status(self, task_id: str) -> OCRTask | None:
        """获取任务状态"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_task_result(self, task_id: str) -> str | None:
        """获取任务结果"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == OCRTaskStatus.COMPLETED:
                return task.result
        return None

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status in (OCRTaskStatus.PENDING, OCRTaskStatus.RUNNING):
                task.status = OCRTaskStatus.CANCELLED
                task.completed_at = datetime.now()
                return True
        return False

    def cleanup_old_tasks(self):
        """清理旧任务"""
        now = datetime.now()
        to_remove = []

        with self._lock:
            for task_id, task in self._tasks.items():
                if task.completed_at:
                    age = (now - task.completed_at).total_seconds()
                    if age > self.TASK_MAX_AGE_SECONDS:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]

        if to_remove:
            logger.info(f"清理了 {len(to_remove)} 个旧OCR任务")

    async def recognize_immediate(
        self,
        image_data: bytes,
        lang: str = None,
        use_cache: bool = True,
        timeout: float = 30.0,
    ) -> str:
        """
        同步识别（等待结果）

        Args:
            image_data: 图像数据
            lang: 语言
            use_cache: 是否使用缓存
            timeout: 超时时间

        Returns:
            str: 识别结果
        """
        task_id = await self.submit_task(image_data, lang, use_cache)

        start_time = time.time()
        while time.time() - start_time < timeout:
            task = self.get_task_status(task_id)

            if task.status == OCRTaskStatus.COMPLETED:
                return task.result
            elif task.status == OCRTaskStatus.FAILED:
                raise RuntimeError(f"OCR识别失败: {task.error}")
            elif task.status == OCRTaskStatus.CANCELLED:
                raise RuntimeError("OCR任务被取消")

            await asyncio.sleep(0.1)

        raise TimeoutError(f"OCR识别超时 ({timeout}秒)")


_async_ocr_service: AsyncOCRService | None = None


def get_async_ocr_service() -> AsyncOCRService:
    """获取异步OCR服务单例"""
    global _async_ocr_service
    if _async_ocr_service is None:
        _async_ocr_service = AsyncOCRService()
    return _async_ocr_service


async def ocr_recognize_async(
    image_data: bytes,
    lang: str = None,
    use_cache: bool = True,
    timeout: float = 30.0,
) -> str:
    """便捷函数：异步OCR识别"""
    service = get_async_ocr_service()
    return await service.recognize_immediate(image_data, lang, use_cache, timeout)


async def ocr_submit_task(
    image_data: bytes,
    lang: str = None,
    use_cache: bool = True,
) -> str:
    """便捷函数：提交OCR任务"""
    service = get_async_ocr_service()
    return await service.submit_task(image_data, lang, use_cache)


def ocr_get_task_status(task_id: str) -> OCRTask | None:
    """便捷函数：获取任务状态"""
    return get_async_ocr_service().get_task_status(task_id)
