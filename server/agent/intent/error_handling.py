"""
意图检测错误处理与降级机制
支持错误恢复、降级策略、重试机制、熔断保护
"""
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
import threading
import random

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """错误类型"""
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    MISSING_PARAMS = "missing_params"
    INVALID_INPUT = "invalid_input"
    SYSTEM_ERROR = "system_error"
    RATE_LIMIT = "rate_limit"


class FallbackLevel(str, Enum):
    """降级级别"""
    FULL = "full"
    REDUCED = "reduced"
    MINIMAL = "minimal"
    EMERGENCY = "emergency"


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ErrorRecord:
    """错误记录"""
    error_type: ErrorType
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution: str = ""


@dataclass
class FallbackConfig:
    """降级配置"""
    level: FallbackLevel
    enabled_methods: List[str]
    timeout_ms: int
    retry_count: int
    retry_delay_ms: int
    cache_enabled: bool
    llm_fallback_enabled: bool


class CircuitBreaker:
    """熔断器"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout_seconds: int = 30
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = threading.Lock()
    
    def record_success(self):
        """记录成功"""
        with self._lock:
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
                    logger.info("熔断器恢复: CLOSED")
    
    def record_failure(self):
        """记录失败"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            self.success_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning("熔断器打开: OPEN")
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"熔断器打开: OPEN (失败次数: {self.failure_count})")
    
    def can_execute(self) -> bool:
        """检查是否可以执行"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            
            if self.state == CircuitState.OPEN:
                if self.last_failure_time:
                    elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                    if elapsed >= self.timeout_seconds:
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                        logger.info("熔断器进入半开状态: HALF_OPEN")
                        return True
                return False
            
            if self.state == CircuitState.HALF_OPEN:
                return True
            
            return False
    
    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        with self._lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
            }


class RetryPolicy:
    """重试策略"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> int:
        """获取重试延迟"""
        delay = self.base_delay_ms * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay_ms)
        
        if self.jitter:
            delay = delay * (0.5 + random.random())
        
        return int(delay)
    
    def should_retry(self, attempt: int, error_type: ErrorType) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        
        retryable_errors = {
            ErrorType.TIMEOUT,
            ErrorType.MODEL_ERROR,
            ErrorType.SYSTEM_ERROR,
            ErrorType.RATE_LIMIT
        }
        
        return error_type in retryable_errors


class FallbackStrategy:
    """降级策略"""
    
    FALLBACK_CONFIGS = {
        FallbackLevel.FULL: FallbackConfig(
            level=FallbackLevel.FULL,
            enabled_methods=["rule", "semantic", "fuzzy", "context", "llm"],
            timeout_ms=5000,
            retry_count=3,
            retry_delay_ms=100,
            cache_enabled=True,
            llm_fallback_enabled=True
        ),
        FallbackLevel.REDUCED: FallbackConfig(
            level=FallbackLevel.REDUCED,
            enabled_methods=["rule", "fuzzy", "context"],
            timeout_ms=2000,
            retry_count=2,
            retry_delay_ms=50,
            cache_enabled=True,
            llm_fallback_enabled=False
        ),
        FallbackLevel.MINIMAL: FallbackConfig(
            level=FallbackLevel.MINIMAL,
            enabled_methods=["rule", "fuzzy"],
            timeout_ms=1000,
            retry_count=1,
            retry_delay_ms=20,
            cache_enabled=True,
            llm_fallback_enabled=False
        ),
        FallbackLevel.EMERGENCY: FallbackConfig(
            level=FallbackLevel.EMERGENCY,
            enabled_methods=["rule"],
            timeout_ms=500,
            retry_count=0,
            retry_delay_ms=0,
            cache_enabled=True,
            llm_fallback_enabled=False
        )
    }
    
    def __init__(self, initial_level: FallbackLevel = FallbackLevel.FULL):
        self.current_level = initial_level
        self.level_history: List[Tuple[FallbackLevel, datetime]] = [(initial_level, datetime.now())]
        self._lock = threading.Lock()
    
    def degrade(self) -> FallbackLevel:
        """降级"""
        with self._lock:
            levels = list(FallbackLevel)
            current_index = levels.index(self.current_level)
            
            if current_index < len(levels) - 1:
                self.current_level = levels[current_index + 1]
                self.level_history.append((self.current_level, datetime.now()))
                logger.warning(f"降级到: {self.current_level.value}")
            
            return self.current_level
    
    def recover(self) -> FallbackLevel:
        """恢复"""
        with self._lock:
            levels = list(FallbackLevel)
            current_index = levels.index(self.current_level)
            
            if current_index > 0:
                self.current_level = levels[current_index - 1]
                self.level_history.append((self.current_level, datetime.now()))
                logger.info(f"恢复到: {self.current_level.value}")
            
            return self.current_level
    
    def get_config(self) -> FallbackConfig:
        """获取当前配置"""
        return self.FALLBACK_CONFIGS[self.current_level]
    
    def should_use_method(self, method: str) -> bool:
        """判断是否使用该方法"""
        config = self.get_config()
        return method in config.enabled_methods


class ErrorHandler:
    """错误处理器"""
    
    ERROR_HANDLERS: Dict[ErrorType, Callable] = {}
    
    def __init__(self):
        self.errors: List[ErrorRecord] = []
        self.error_counts: Dict[ErrorType, int] = defaultdict(int)
        self.max_errors = 1000
        self._lock = threading.Lock()
        
        self._init_handlers()
    
    def _init_handlers(self):
        """初始化处理器"""
        self.ERROR_HANDLERS = {
            ErrorType.TIMEOUT: self._handle_timeout,
            ErrorType.MODEL_ERROR: self._handle_model_error,
            ErrorType.LOW_CONFIDENCE: self._handle_low_confidence,
            ErrorType.AMBIGUOUS_INTENT: self._handle_ambiguous_intent,
            ErrorType.MISSING_PARAMS: self._handle_missing_params,
            ErrorType.INVALID_INPUT: self._handle_invalid_input,
            ErrorType.SYSTEM_ERROR: self._handle_system_error,
            ErrorType.RATE_LIMIT: self._handle_rate_limit
        }
    
    def handle(
        self,
        error_type: ErrorType,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """处理错误"""
        record = ErrorRecord(
            error_type=error_type,
            message=message,
            context=context or {}
        )
        
        with self._lock:
            self.errors.append(record)
            self.error_counts[error_type] += 1
            
            if len(self.errors) > self.max_errors:
                self.errors = self.errors[-self.max_errors:]
        
        handler = self.ERROR_HANDLERS.get(error_type)
        if handler:
            result = handler(message, context or {})
            record.resolved = True
            record.resolution = result.get("resolution", "")
            return result
        
        return self._default_handler(message, context or {})
    
    def _handle_timeout(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理超时"""
        return {
            "resolution": "fallback",
            "action": "use_cached_or_rule",
            "message": "检测超时，已切换到规则匹配模式",
            "retry_suggested": True
        }
    
    def _handle_model_error(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理模型错误"""
        return {
            "resolution": "fallback",
            "action": "use_rule_matcher",
            "message": "模型暂时不可用，已切换到规则匹配",
            "retry_suggested": False
        }
    
    def _handle_low_confidence(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理低置信度"""
        alternatives = context.get("alternatives", [])
        
        if len(alternatives) > 1:
            return {
                "resolution": "clarification",
                "action": "ask_user",
                "message": "我不太确定您的意思，请选择：",
                "options": alternatives[:3],
                "retry_suggested": False
            }
        
        return {
            "resolution": "suggestion",
            "action": "provide_suggestions",
            "message": "我没有理解您的请求，您可以尝试：",
            "suggestions": context.get("suggestions", ["创建文件", "读取文件", "列出目录"]),
            "retry_suggested": False
        }
    
    def _handle_ambiguous_intent(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理意图歧义"""
        candidates = context.get("candidates", [])
        
        return {
            "resolution": "disambiguation",
            "action": "ask_clarification",
            "message": "检测到多个可能的意图，请确认：",
            "options": candidates[:3],
            "retry_suggested": False
        }
    
    def _handle_missing_params(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理缺失参数"""
        missing = context.get("missing_params", [])
        
        if missing:
            return {
                "resolution": "collect_params",
                "action": "ask_for_params",
                "message": f"请提供必要的信息：{missing[0]}",
                "missing_params": missing,
                "retry_suggested": False
            }
        
        return {
            "resolution": "unknown",
            "action": "ask_user",
            "message": "请提供更多信息",
            "retry_suggested": False
        }
    
    def _handle_invalid_input(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理无效输入"""
        return {
            "resolution": "reject",
            "action": "notify_user",
            "message": "输入无效，请重新描述您的需求",
            "retry_suggested": True
        }
    
    def _handle_system_error(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理系统错误"""
        return {
            "resolution": "emergency",
            "action": "use_emergency_mode",
            "message": "系统暂时繁忙，请稍后重试",
            "retry_suggested": True,
            "delay_ms": 1000
        }
    
    def _handle_rate_limit(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理速率限制"""
        return {
            "resolution": "throttle",
            "action": "wait_and_retry",
            "message": "请求过于频繁，请稍后重试",
            "retry_suggested": True,
            "delay_ms": 2000
        }
    
    def _default_handler(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """默认处理器"""
        return {
            "resolution": "unknown",
            "action": "ask_user",
            "message": "发生未知错误，请重试",
            "retry_suggested": True
        }
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计"""
        with self._lock:
            return {
                "total_errors": len(self.errors),
                "error_counts": dict(self.error_counts),
                "recent_errors": [
                    {
                        "type": e.error_type.value,
                        "message": e.message,
                        "timestamp": e.timestamp.isoformat(),
                        "resolved": e.resolved
                    }
                    for e in self.errors[-10:]
                ]
            }


class IntentDetectionErrorManager:
    """意图检测错误管理器"""
    
    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        fallback_strategy: Optional[FallbackStrategy] = None,
        retry_policy: Optional[RetryPolicy] = None,
        error_handler: Optional[ErrorHandler] = None
    ):
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.fallback_strategy = fallback_strategy or FallbackStrategy()
        self.retry_policy = retry_policy or RetryPolicy()
        self.error_handler = error_handler or ErrorHandler()
        
        self.cache: Dict[str, Any] = {}
        self.cache_ttl_seconds = 300
        self._lock = threading.Lock()
    
    def execute_with_protection(
        self,
        func: Callable,
        message: str,
        *args,
        **kwargs
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """
        带保护的执行
        
        Args:
            func: 要执行的函数
            message: 用户消息（用于缓存键）
            
        Returns:
            (result, error_info)
        """
        if not self.circuit_breaker.can_execute():
            return self._get_cached_result(message), {
                "error": True,
                "type": ErrorType.SYSTEM_ERROR.value,
                "message": "服务暂时不可用",
                "resolution": "circuit_open"
            }
        
        attempt = 0
        last_error = None
        
        while attempt <= self.retry_policy.max_retries:
            try:
                result = func(*args, **kwargs)
                
                self.circuit_breaker.record_success()
                self._cache_result(message, result)
                
                if self.fallback_strategy.current_level != FallbackLevel.FULL:
                    self.fallback_strategy.recover()
                
                return result, None
                
            except TimeoutError:
                last_error = ErrorType.TIMEOUT
                self.circuit_breaker.record_failure()
                
            except Exception as e:
                last_error = ErrorType.MODEL_ERROR
                self.circuit_breaker.record_failure()
                logger.error(f"意图检测执行失败: {e}")
            
            if last_error and self.retry_policy.should_retry(attempt, last_error):
                delay = self.retry_policy.get_delay(attempt)
                time.sleep(delay / 1000)
                attempt += 1
            else:
                break
        
        if self.fallback_strategy.current_level != FallbackLevel.EMERGENCY:
            self.fallback_strategy.degrade()
        
        error_info = self.error_handler.handle(
            last_error or ErrorType.SYSTEM_ERROR,
            f"执行失败，尝试次数: {attempt}",
            {"attempts": attempt}
        )
        
        cached = self._get_cached_result(message)
        if cached:
            error_info["cached_result"] = cached
        
        return None, error_info
    
    def _cache_result(self, key: str, result: Any):
        """缓存结果"""
        with self._lock:
            self.cache[key] = {
                "result": result,
                "timestamp": datetime.now()
            }
            
            self._cleanup_cache()
    
    def _get_cached_result(self, key: str) -> Optional[Any]:
        """获取缓存结果"""
        with self._lock:
            if key in self.cache:
                cached = self.cache[key]
                age = (datetime.now() - cached["timestamp"]).total_seconds()
                if age < self.cache_ttl_seconds:
                    return cached["result"]
                else:
                    del self.cache[key]
            return None
    
    def _cleanup_cache(self):
        """清理过期缓存"""
        now = datetime.now()
        expired_keys = [
            k for k, v in self.cache.items()
            if (now - v["timestamp"]).total_seconds() > self.cache_ttl_seconds
        ]
        for k in expired_keys:
            del self.cache[k]
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            "circuit_breaker": self.circuit_breaker.get_state(),
            "fallback_level": self.fallback_strategy.current_level.value,
            "fallback_config": {
                "level": self.fallback_strategy.get_config().level.value,
                "enabled_methods": self.fallback_strategy.get_config().enabled_methods,
                "timeout_ms": self.fallback_strategy.get_config().timeout_ms
            },
            "error_stats": self.error_handler.get_error_stats(),
            "cache_size": len(self.cache)
        }
    
    def reset(self):
        """重置状态"""
        self.circuit_breaker = CircuitBreaker()
        self.fallback_strategy = FallbackStrategy()
        with self._lock:
            self.cache.clear()


def create_error_manager(
    failure_threshold: int = 5,
    success_threshold: int = 3,
    circuit_timeout: int = 30,
    max_retries: int = 3
) -> IntentDetectionErrorManager:
    """创建错误管理器"""
    return IntentDetectionErrorManager(
        circuit_breaker=CircuitBreaker(
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout_seconds=circuit_timeout
        ),
        retry_policy=RetryPolicy(max_retries=max_retries)
    )


_default_error_manager: Optional[IntentDetectionErrorManager] = None


def get_error_manager() -> IntentDetectionErrorManager:
    """获取默认错误管理器"""
    global _default_error_manager
    if _default_error_manager is None:
        _default_error_manager = create_error_manager()
    return _default_error_manager
