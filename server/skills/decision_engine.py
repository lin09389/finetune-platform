# -*- coding: utf-8 -*-
"""
技能调用决策引擎

提供基于对话上下文的技能匹配、优先级排序、多技能调用等功能。
"""
import asyncio
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from .base import SkillBase
from .models import (
    SkillCategory,
    SkillExecution,
    SkillMetadata,
    SkillPriority,
    SkillResult,
    SkillStatus,
)
from .enhanced_registry import EnhancedSkillRegistry, get_enhanced_registry


class MatchType(str, Enum):
    """匹配类型"""
    EXACT = "exact"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    CONTEXT = "context"
    PATTERN = "pattern"


class ExecutionMode(str, Enum):
    """执行模式"""
    SINGLE = "single"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"


@dataclass
class SkillMatch:
    """技能匹配结果"""
    skill_name: str
    score: float
    match_type: MatchType
    matched_keywords: List[str] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    context_relevance: float = 0.0
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionContext:
    """决策上下文"""
    user_message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    available_context: Dict[str, Any] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    previous_skills: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionPlan:
    """执行计划"""
    skills: List[Tuple[str, Dict[str, Any], SkillPriority]]
    mode: ExecutionMode
    stop_on_error: bool = True
    max_parallel: int = 3
    timeout: float = 300.0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    results: List[SkillExecution] = field(default_factory=list)
    final_message: str = ""
    errors: List[str] = field(default_factory=list)
    total_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillMatcher:
    """技能匹配引擎"""

    def __init__(self, registry: Optional[EnhancedSkillRegistry] = None):
        self.registry = registry or get_enhanced_registry()
        self._keyword_index: Dict[str, Set[str]] = {}
        self._pattern_index: Dict[str, List[str]] = {}
        self._category_keywords: Dict[SkillCategory, Set[str]] = {}
        self._build_indexes()

    def _build_indexes(self):
        """构建索引"""
        all_metadata = self.registry.get_all_metadata()

        for name, metadata in all_metadata.items():
            keywords = set()
            keywords.add(name.lower())
            keywords.add(metadata.display_name.lower())
            keywords.update(tag.lower() for tag in metadata.tags)

            for word in metadata.description.lower().split():
                if len(word) > 2:
                    keywords.add(word)

            for param in metadata.parameters:
                keywords.add(param.name.lower())
                if param.description:
                    keywords.update(
                        word.lower() for word in param.description.split()
                        if len(word) > 2
                    )

            self._keyword_index[name] = keywords

            if metadata.category not in self._category_keywords:
                self._category_keywords[metadata.category] = set()
            self._category_keywords[metadata.category].update(keywords)

    def match_by_keywords(
        self,
        message: str,
        threshold: float = 0.3,
    ) -> List[SkillMatch]:
        """基于关键词匹配"""
        message_lower = message.lower()
        message_words = set(word for word in message_lower.split() if len(word) > 2)

        matches = []
        for skill_name, keywords in self._keyword_index.items():
            intersection = message_words & keywords
            if not intersection:
                continue

            score = len(intersection) / max(len(keywords), 1)
            if score >= threshold:
                matches.append(SkillMatch(
                    skill_name=skill_name,
                    score=score,
                    match_type=MatchType.KEYWORD,
                    matched_keywords=list(intersection),
                    confidence=min(score * 1.5, 1.0),
                ))

        return sorted(matches, key=lambda x: x.score, reverse=True)

    def match_by_patterns(
        self,
        message: str,
    ) -> List[SkillMatch]:
        """基于正则模式匹配"""
        patterns = {
            "text_transform": [
                r"(把|将|转换).*(大写|小写|首字母)",
                r"(转换|转换为).*(uppercase|lowercase)",
                r"文本.*转换",
            ],
            "word_count": [
                r"(统计|计算).*(字数|字符数|单词数)",
                r"(有多少|几个).*(字|字符|单词)",
                r"字数统计",
            ],
            "file_read": [
                r"(读取|查看|打开).*(文件|文档)",
                r"(显示|输出).*(文件|文档).*内容",
                r"cat\s+\S+",
            ],
            "file_write": [
                r"(写入|保存|修改).*(文件|文档)",
                r"(创建|新建).*文件",
                r"(把|将).*写入",
            ],
            "file_delete": [
                r"(删除|移除|清除).*(文件|文档)",
                r"rm\s+\S+",
            ],
            "file_list": [
                r"(列出|显示|查看).*(文件|目录|文件夹)",
                r"(有什么|有哪些).*文件",
                r"ls\s*",
            ],
        }

        matches = []
        for skill_name, skill_patterns in patterns.items():
            matched_patterns = []
            for pattern in skill_patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                matches.append(SkillMatch(
                    skill_name=skill_name,
                    score=len(matched_patterns) / len(skill_patterns),
                    match_type=MatchType.PATTERN,
                    matched_patterns=matched_patterns,
                    confidence=0.8,
                ))

        return sorted(matches, key=lambda x: x.score, reverse=True)

    def match_by_category(
        self,
        message: str,
        category: SkillCategory,
        threshold: float = 0.2,
    ) -> List[SkillMatch]:
        """按类别匹配技能"""
        if category not in self._category_keywords:
            return []

        message_lower = message.lower()
        message_words = set(word for word in message_lower.split() if len(word) > 2)
        category_keywords = self._category_keywords[category]

        intersection = message_words & category_keywords
        if not intersection:
            return []

        score = len(intersection) / max(len(category_keywords), 1)
        if score < threshold:
            return []

        skills_in_category = self.registry.list_skills_by_category(category)
        matches = []

        for skill_name in skills_in_category:
            skill_keywords = self._keyword_index.get(skill_name, set())
            skill_intersection = message_words & skill_keywords
            if skill_intersection:
                skill_score = len(skill_intersection) / max(len(skill_keywords), 1)
                matches.append(SkillMatch(
                    skill_name=skill_name,
                    score=skill_score,
                    match_type=MatchType.KEYWORD,
                    matched_keywords=list(skill_intersection),
                    metadata={"category": category.value},
                ))

        return sorted(matches, key=lambda x: x.score, reverse=True)

    def match(
        self,
        context: DecisionContext,
        top_k: int = 5,
        min_score: float = 0.2,
    ) -> List[SkillMatch]:
        """综合匹配"""
        all_matches: Dict[str, SkillMatch] = {}

        keyword_matches = self.match_by_keywords(context.user_message, min_score)
        for match in keyword_matches:
            if match.skill_name not in all_matches or match.score > all_matches[match.skill_name].score:
                all_matches[match.skill_name] = match

        pattern_matches = self.match_by_patterns(context.user_message)
        for match in pattern_matches:
            if match.skill_name not in all_matches:
                all_matches[match.skill_name] = match
            else:
                existing = all_matches[match.skill_name]
                existing.matched_patterns.extend(match.matched_patterns)
                existing.score = max(existing.score, match.score)
                existing.confidence = max(existing.confidence, match.confidence)

        if context.previous_skills:
            for prev_skill in context.previous_skills[-3:]:
                metadata = self.registry.get_metadata(prev_skill)
                if metadata:
                    for dep in metadata.dependencies:
                        if dep not in all_matches:
                            all_matches[dep] = SkillMatch(
                                skill_name=dep,
                                score=0.5,
                                match_type=MatchType.CONTEXT,
                                context_relevance=0.8,
                                metadata={"reason": "dependency"},
                            )

        sorted_matches = sorted(
            all_matches.values(),
            key=lambda x: (x.score, x.confidence),
            reverse=True
        )

        return sorted_matches[:top_k]


class PriorityScheduler:
    """优先级调度器"""

    def __init__(self):
        self._priority_weights = {
            SkillPriority.CRITICAL: 100,
            SkillPriority.HIGH: 75,
            SkillPriority.NORMAL: 50,
            SkillPriority.LOW: 25,
        }
        self._category_weights = {
            SkillCategory.SYSTEM: 1.5,
            SkillCategory.FILE: 1.3,
            SkillCategory.CODE: 1.2,
            SkillCategory.ANALYSIS: 1.1,
            SkillCategory.DATA: 1.0,
            SkillCategory.COMMUNICATION: 0.9,
            SkillCategory.CUSTOM: 0.8,
        }

    def calculate_priority_score(
        self,
        match: SkillMatch,
        metadata: Optional[SkillMetadata] = None,
        context: Optional[DecisionContext] = None,
    ) -> float:
        """计算优先级分数"""
        base_score = match.score * 100

        type_bonus = {
            MatchType.EXACT: 20,
            MatchType.PATTERN: 15,
            MatchType.KEYWORD: 10,
            MatchType.SEMANTIC: 8,
            MatchType.CONTEXT: 5,
        }.get(match.match_type, 0)

        confidence_bonus = match.confidence * 10

        category_bonus = 0
        if metadata:
            category_bonus = self._category_weights.get(metadata.category, 1.0) * 5

        context_bonus = match.context_relevance * 10

        recent_bonus = 0
        if context and match.skill_name in context.previous_skills[-3:]:
            recent_bonus = 5

        return base_score + type_bonus + confidence_bonus + category_bonus + context_bonus + recent_bonus

    def sort_by_priority(
        self,
        matches: List[SkillMatch],
        registry: EnhancedSkillRegistry,
        context: Optional[DecisionContext] = None,
    ) -> List[Tuple[SkillMatch, float, SkillPriority]]:
        """按优先级排序"""
        scored_matches = []

        for match in matches:
            metadata = registry.get_metadata(match.skill_name)
            score = self.calculate_priority_score(match, metadata, context)

            if score >= 80:
                priority = SkillPriority.CRITICAL
            elif score >= 60:
                priority = SkillPriority.HIGH
            elif score >= 40:
                priority = SkillPriority.NORMAL
            else:
                priority = SkillPriority.LOW

            scored_matches.append((match, score, priority))

        return sorted(scored_matches, key=lambda x: x[1], reverse=True)

    def determine_execution_mode(
        self,
        matches: List[Tuple[SkillMatch, float, SkillPriority]],
    ) -> ExecutionMode:
        """确定执行模式"""
        if len(matches) == 0:
            return ExecutionMode.SINGLE

        if len(matches) == 1:
            return ExecutionMode.SINGLE

        high_priority_count = sum(
            1 for _, _, p in matches
            if p in (SkillPriority.CRITICAL, SkillPriority.HIGH)
        )

        if high_priority_count > 1:
            return ExecutionMode.SEQUENTIAL

        return ExecutionMode.PARALLEL


class DecisionEngine:
    """技能调用决策引擎"""

    _instance: Optional["DecisionEngine"] = None
    _lock: threading.RLock = threading.RLock()

    def __new__(cls) -> "DecisionEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.registry = get_enhanced_registry()
        self.matcher = SkillMatcher(self.registry)
        self.scheduler = PriorityScheduler()
        self._decision_history: List[Tuple[DecisionContext, ExecutionPlan]] = []
        self._max_history = 100
        self._on_decision: Optional[Callable[[DecisionContext, ExecutionPlan], None]] = None
        self._on_execution: Optional[Callable[[ExecutionResult], None]] = None

    @classmethod
    def get_instance(cls) -> "DecisionEngine":
        """获取单例实例"""
        return cls()

    def analyze(
        self,
        context: DecisionContext,
        top_k: int = 5,
        min_score: float = 0.2,
    ) -> List[Tuple[SkillMatch, float, SkillPriority]]:
        """分析并返回匹配的技能"""
        matches = self.matcher.match(context, top_k, min_score)
        return self.scheduler.sort_by_priority(matches, self.registry, context)

    def create_execution_plan(
        self,
        context: DecisionContext,
        matches: Optional[List[Tuple[SkillMatch, float, SkillPriority]]] = None,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ExecutionPlan:
        """创建执行计划"""
        if matches is None:
            matches = self.analyze(context)

        if not matches:
            return ExecutionPlan(
                skills=[],
                mode=ExecutionMode.SINGLE,
            )

        skills = []
        for match, score, priority in matches:
            skill_params = parameters.get(match.skill_name, {}) if parameters else {}
            skills.append((match.skill_name, skill_params, priority))

        mode = self.scheduler.determine_execution_mode(matches)

        plan = ExecutionPlan(
            skills=skills,
            mode=mode,
            stop_on_error=True,
            max_parallel=3,
        )

        self._decision_history.append((context, plan))
        if len(self._decision_history) > self._max_history:
            self._decision_history = self._decision_history[-self._max_history:]

        if self._on_decision:
            self._on_decision(context, plan)

        return plan

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        context: DecisionContext,
    ) -> ExecutionResult:
        """执行计划"""
        import time
        start_time = time.time()

        result = ExecutionResult(success=True)

        if not plan.skills:
            result.final_message = "没有匹配的技能可以执行"
            return result

        if plan.mode == ExecutionMode.SINGLE:
            execution = await self._execute_single(plan, context)
            result.results.append(execution)
            result.success = execution.status == SkillStatus.COMPLETED
            if execution.result:
                result.final_message = execution.result.message or ""
                if execution.result.error:
                    result.errors.append(execution.result.error)

        elif plan.mode == ExecutionMode.SEQUENTIAL:
            executions = await self._execute_sequential(plan, context)
            result.results.extend(executions)
            result.success = all(
                e.status == SkillStatus.COMPLETED for e in executions
            )
            result.final_message = self._combine_messages(executions)
            result.errors.extend(
                e.result.error for e in executions
                if e.result and e.result.error
            )

        elif plan.mode == ExecutionMode.PARALLEL:
            executions = await self._execute_parallel(plan, context)
            result.results.extend(executions)
            result.success = all(
                e.status == SkillStatus.COMPLETED for e in executions
            )
            result.final_message = self._combine_messages(executions)
            result.errors.extend(
                e.result.error for e in executions
                if e.result and e.result.error
            )

        result.total_time = time.time() - start_time

        if self._on_execution:
            self._on_execution(result)

        return result

    async def _execute_single(
        self,
        plan: ExecutionPlan,
        context: DecisionContext,
    ) -> SkillExecution:
        """执行单个技能"""
        skill_name, params, priority = plan.skills[0]
        return await self.registry.execute(
            name=skill_name,
            parameters=params,
            user_id=context.user_id,
            session_id=context.session_id,
            priority=priority,
        )

    async def _execute_sequential(
        self,
        plan: ExecutionPlan,
        context: DecisionContext,
    ) -> List[SkillExecution]:
        """顺序执行多个技能"""
        executions = []

        for skill_name, params, priority in plan.skills:
            execution = await self.registry.execute(
                name=skill_name,
                parameters=params,
                user_id=context.user_id,
                session_id=context.session_id,
                priority=priority,
            )
            executions.append(execution)

            if plan.stop_on_error and execution.status == SkillStatus.FAILED:
                break

        return executions

    async def _execute_parallel(
        self,
        plan: ExecutionPlan,
        context: DecisionContext,
    ) -> List[SkillExecution]:
        """并行执行多个技能"""
        tasks = []

        for skill_name, params, priority in plan.skills[:plan.max_parallel]:
            task = self.registry.execute(
                name=skill_name,
                parameters=params,
                user_id=context.user_id,
                session_id=context.session_id,
                priority=priority,
            )
            tasks.append(task)

        return await asyncio.gather(*tasks)

    def _combine_messages(self, executions: List[SkillExecution]) -> str:
        """合并执行消息"""
        messages = []
        for execution in executions:
            if execution.result and execution.result.message:
                messages.append(f"[{execution.skill_name}] {execution.result.message}")
        return "\n".join(messages) if messages else "执行完成"

    async def decide_and_execute(
        self,
        context: DecisionContext,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> ExecutionResult:
        """决策并执行"""
        matches = self.analyze(context)
        plan = self.create_execution_plan(context, matches, parameters)
        return await self.execute_plan(plan, context)

    def set_on_decision(self, callback: Callable[[DecisionContext, ExecutionPlan], None]):
        """设置决策回调"""
        self._on_decision = callback

    def set_on_execution(self, callback: Callable[[ExecutionResult], None]):
        """设置执行回调"""
        self._on_execution = callback

    def get_decision_history(self, limit: int = 20) -> List[Tuple[DecisionContext, ExecutionPlan]]:
        """获取决策历史"""
        return self._decision_history[-limit:]

    def clear_history(self):
        """清空历史"""
        self._decision_history.clear()

    def rebuild_indexes(self):
        """重建索引"""
        self.matcher._build_indexes()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_decisions": len(self._decision_history),
            "registry_stats": self.registry.get_stats(),
            "indexed_skills": len(self.matcher._keyword_index),
        }


def get_decision_engine() -> DecisionEngine:
    """获取决策引擎实例"""
    return DecisionEngine.get_instance()
