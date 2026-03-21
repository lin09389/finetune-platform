# -*- coding: utf-8 -*-
"""
技能系统模块
提供可扩展的技能框架，支持：
- 标准化技能接口定义
- 技能注册与发现
- 参数验证与执行管理
- 执行历史追踪
- 技能目录扫描
- 生命周期管理
- 执行环境隔离（沙箱）
- 执行结果缓存
- 技能执行器
- 技能调用决策系统
- 参数自动提取
- 结果解析与整合
"""

from .base import SkillBase, SkillContext
from .models import (
    SkillCategory,
    SkillChain,
    SkillExecution,
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillPriority,
    SkillResult,
    SkillStatus,
    SkillValidationResult,
)
from .registry import SkillRegistry, get_registry, register_skill
from .scanner import (
    ScanReport,
    ScanStatus,
    SkillDependency,
    SkillLoadStatus,
    SkillScanResult,
    SkillScanner,
    create_scanner,
)
from .enhanced_registry import (
    DependencyNode,
    EnhancedSkillRegistry,
    SkillRegistration,
    SkillRegistrationStatus,
    get_enhanced_registry,
    register_skill_enhanced,
)
from .lifecycle import (
    LifecycleEvent,
    LifecycleEventType,
    LoadResult,
    ReloadResult,
    SkillLifecycleManager,
    UnloadResult,
    create_lifecycle_manager,
    get_lifecycle_manager,
)
from .cache import (
    CacheEntry,
    CacheStats,
    CachedSkillExecutor,
    SkillExecutionCache,
    create_skill_cache,
    get_skill_cache,
)
from .sandbox import (
    ExecutionSandbox,
    ResourceLimits,
    SandboxConfig,
    SandboxPermission,
    SandboxResult,
    SandboxViolation,
    SandboxViolationError,
    SandboxViolationType,
    SkillSandbox,
    create_sandbox,
    get_default_sandbox,
)
from .executor import (
    ExecutionMode,
    ExecutorConfig,
    ExecutorStats,
    ExecutionTask,
    SkillExecutor,
    create_executor,
    execute_skill,
    get_executor,
)
from .decision_engine import (
    DecisionContext,
    DecisionEngine,
    ExecutionMode as DecisionExecutionMode,
    ExecutionPlan,
    ExecutionResult as DecisionExecutionResult,
    MatchType,
    PriorityScheduler,
    SkillMatch,
    SkillMatcher,
    get_decision_engine,
)
from .param_extractor import (
    ExtractionContext,
    ExtractionResult,
    LLMParamExtractor,
    ParamExtractor,
    RuleBasedExtractor,
    get_param_extractor,
)
from .result_processor import (
    MultiResultSummary,
    NaturalLanguageGenerator,
    OutputFormat,
    ProcessedResult,
    ResultParser,
    ResultProcessor,
    ResultType,
    get_result_processor,
)

from .implemented import ALL_SKILLS, register_all_skills

__all__ = [
    "SkillBase",
    "SkillContext",
    "SkillCategory",
    "SkillChain",
    "SkillExecution",
    "SkillMetadata",
    "SkillParameter",
    "SkillParameterType",
    "SkillPriority",
    "SkillResult",
    "SkillStatus",
    "SkillValidationResult",
    "SkillRegistry",
    "get_registry",
    "register_skill",
    "ScanReport",
    "ScanStatus",
    "SkillDependency",
    "SkillLoadStatus",
    "SkillScanResult",
    "SkillScanner",
    "create_scanner",
    "DependencyNode",
    "EnhancedSkillRegistry",
    "SkillRegistration",
    "SkillRegistrationStatus",
    "get_enhanced_registry",
    "register_skill_enhanced",
    "LifecycleEvent",
    "LifecycleEventType",
    "LoadResult",
    "ReloadResult",
    "SkillLifecycleManager",
    "UnloadResult",
    "create_lifecycle_manager",
    "get_lifecycle_manager",
    "CacheEntry",
    "CacheStats",
    "CachedSkillExecutor",
    "SkillExecutionCache",
    "create_skill_cache",
    "get_skill_cache",
    "ExecutionSandbox",
    "ResourceLimits",
    "SandboxConfig",
    "SandboxPermission",
    "SandboxResult",
    "SandboxViolation",
    "SandboxViolationError",
    "SandboxViolationType",
    "SkillSandbox",
    "create_sandbox",
    "get_default_sandbox",
    "ExecutionMode",
    "ExecutorConfig",
    "ExecutorStats",
    "ExecutionTask",
    "SkillExecutor",
    "create_executor",
    "execute_skill",
    "get_executor",
    "DecisionContext",
    "DecisionEngine",
    "DecisionExecutionMode",
    "ExecutionPlan",
    "DecisionExecutionResult",
    "MatchType",
    "PriorityScheduler",
    "SkillMatch",
    "SkillMatcher",
    "get_decision_engine",
    "ExtractionContext",
    "ExtractionResult",
    "LLMParamExtractor",
    "ParamExtractor",
    "RuleBasedExtractor",
    "get_param_extractor",
    "MultiResultSummary",
    "NaturalLanguageGenerator",
    "OutputFormat",
    "ProcessedResult",
    "ResultParser",
    "ResultProcessor",
    "ResultType",
    "get_result_processor",
    "ALL_SKILLS",
    "register_all_skills",
]


def init_skills():
    """初始化并注册所有内置技能"""
    registry = get_registry()
    register_all_skills(registry)

    try:
        from skills.md_skill_loader import load_md_skills
        md_skills = load_md_skills(registry)
        if md_skills:
            print(f"已加载 {len(md_skills)} 个 MD skills")
    except Exception as e:
        print(f"加载 MD skills 失败: {e}")

    return registry


_initialized = False


def ensure_skills_initialized():
    """确保技能已初始化"""
    global _initialized
    if not _initialized:
        init_skills()
        _initialized = True
