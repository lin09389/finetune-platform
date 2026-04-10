"""
技能学习与优化模块

功能：
- 技能学习器
- 成功率统计
- 参数自动调优
- 操作建议生成
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillStatus(str, Enum):
    """技能状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    LEARNING = "learning"
    OPTIMIZING = "optimizing"
    ERROR = "error"


@dataclass
class SkillExecutionRecord:
    """技能执行记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    success: bool = False
    error: str | None = None
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    user_feedback: str | None = None
    user_id: str = "default"
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill_name": self.skill_name,
            "parameters": self.parameters,
            "result": self.result,
            "success": self.success,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp.isoformat(),
            "user_feedback": self.user_feedback,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }


@dataclass
class SkillStatistics:
    """技能统计"""
    skill_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_time_ms: float = 0.0
    avg_time_ms: float = 0.0
    success_rate: float = 0.0
    last_execution: datetime | None = None
    last_success: datetime | None = None
    last_failure: datetime | None = None
    recent_trend: str = "stable"

    def update(self, record: SkillExecutionRecord):
        """更新统计"""
        self.total_executions += 1
        self.total_time_ms += record.execution_time_ms
        self.avg_time_ms = self.total_time_ms / self.total_executions
        self.last_execution = record.timestamp

        if record.success:
            self.successful_executions += 1
            self.last_success = record.timestamp
        else:
            self.failed_executions += 1
            self.last_failure = record.timestamp

        self.success_rate = self.successful_executions / self.total_executions

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "total_time_ms": self.total_time_ms,
            "avg_time_ms": self.avg_time_ms,
            "success_rate": self.success_rate,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "recent_trend": self.recent_trend,
        }


@dataclass
class ParameterOptimization:
    """参数优化记录"""
    parameter_name: str
    original_value: Any
    optimized_value: Any
    improvement: float = 0.0
    confidence: float = 0.5
    samples: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "original_value": self.original_value,
            "optimized_value": self.optimized_value,
            "improvement": self.improvement,
            "confidence": self.confidence,
            "samples": self.samples,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class OperationSuggestion:
    """操作建议"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    skill_name: str = ""
    suggestion_type: str = "parameter"
    title: str = ""
    description: str = ""
    suggested_params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    reason: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill_name": self.skill_name,
            "suggestion_type": self.suggestion_type,
            "title": self.title,
            "description": self.description,
            "suggested_params": self.suggested_params,
            "confidence": self.confidence,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "applied": self.applied,
        }


class SkillLearner:
    """
    技能学习器

    功能：
    - 执行记录收集
    - 成功率统计
    - 参数优化
    - 建议生成
    """

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or Path("data/skill_learning")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._execution_records: list[SkillExecutionRecord] = []
        self._statistics: dict[str, SkillStatistics] = {}
        self._optimizations: dict[str, list[ParameterOptimization]] = {}
        self._suggestions: list[OperationSuggestion] = []

        self._max_records = 10000
        self._min_samples_for_optimization = 5
        self._optimization_threshold = 0.1

    def record_execution(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        result: dict[str, Any] | None,
        success: bool,
        execution_time_ms: float = 0.0,
        error: str | None = None,
        user_id: str = "default",
        session_id: str | None = None,
    ) -> SkillExecutionRecord:
        """记录技能执行"""
        record = SkillExecutionRecord(
            skill_name=skill_name,
            parameters=parameters,
            result=result,
            success=success,
            execution_time_ms=execution_time_ms,
            error=error,
            user_id=user_id,
            session_id=session_id,
        )

        self._execution_records.append(record)

        if len(self._execution_records) > self._max_records:
            self._execution_records = self._execution_records[-self._max_records:]

        if skill_name not in self._statistics:
            self._statistics[skill_name] = SkillStatistics(skill_name=skill_name)

        self._statistics[skill_name].update(record)

        self._persist_record(record)

        logger.debug(f"记录技能执行: {skill_name}, 成功: {success}")

        return record

    def record_user_feedback(self, record_id: str, feedback: str):
        """记录用户反馈"""
        for record in self._execution_records:
            if record.id == record_id:
                record.user_feedback = feedback
                self._persist_record(record)
                break

    def get_statistics(self, skill_name: str) -> SkillStatistics | None:
        """获取技能统计"""
        return self._statistics.get(skill_name)

    def get_all_statistics(self) -> dict[str, SkillStatistics]:
        """获取所有技能统计"""
        return self._statistics.copy()

    def analyze_parameter_patterns(
        self,
        skill_name: str,
        parameter_name: str,
        min_samples: int = 5
    ) -> dict[str, Any] | None:
        """分析参数模式"""
        records = [
            r for r in self._execution_records
            if r.skill_name == skill_name and parameter_name in r.parameters
        ]

        if len(records) < min_samples:
            return None

        success_values = [
            r.parameters[parameter_name]
            for r in records
            if r.success
        ]

        failure_values = [
            r.parameters[parameter_name]
            for r in records
            if not r.success
        ]

        analysis = {
            "parameter_name": parameter_name,
            "total_samples": len(records),
            "success_samples": len(success_values),
            "failure_samples": len(failure_values),
        }

        if success_values and all(isinstance(v, (int, float)) for v in success_values):
            analysis["success_avg"] = sum(success_values) / len(success_values)
            analysis["success_min"] = min(success_values)
            analysis["success_max"] = max(success_values)

        return analysis

    def optimize_parameters(
        self,
        skill_name: str,
        min_samples: int = 5
    ) -> list[ParameterOptimization]:
        """优化参数"""
        records = [
            r for r in self._execution_records
            if r.skill_name == skill_name
        ]

        if len(records) < min_samples:
            return []

        optimizations = []

        if not records:
            return optimizations

        sample_params = records[0].parameters
        for param_name in sample_params:
            analysis = self.analyze_parameter_patterns(skill_name, param_name, min_samples)

            if not analysis:
                continue

            if "success_avg" in analysis:
                current_records = [
                    r for r in records
                    if param_name in r.parameters
                ]

                if current_records:
                    current_avg = sum(
                        r.parameters[param_name]
                        for r in current_records
                        if isinstance(r.parameters[param_name], (int, float))
                    ) / len([
                        r for r in current_records
                        if isinstance(r.parameters[param_name], (int, float))
                    ]) if any(isinstance(r.parameters[param_name], (int, float)) for r in current_records) else 0

                    improvement = abs(analysis["success_avg"] - current_avg) / max(abs(current_avg), 0.001)

                    if improvement > self._optimization_threshold:
                        optimization = ParameterOptimization(
                            parameter_name=param_name,
                            original_value=current_avg,
                            optimized_value=analysis["success_avg"],
                            improvement=improvement,
                            confidence=min(1.0, analysis["success_samples"] / 10),
                            samples=analysis["success_samples"],
                        )

                        optimizations.append(optimization)

                        if skill_name not in self._optimizations:
                            self._optimizations[skill_name] = []
                        self._optimizations[skill_name].append(optimization)

        return optimizations

    def generate_suggestions(
        self,
        skill_name: str,
        current_params: dict[str, Any],
        min_confidence: float = 0.5
    ) -> list[OperationSuggestion]:
        """生成操作建议"""
        suggestions = []

        stats = self._statistics.get(skill_name)
        if not stats or stats.total_executions < self._min_samples_for_optimization:
            return suggestions

        if stats.success_rate < 0.5:
            suggestion = OperationSuggestion(
                skill_name=skill_name,
                suggestion_type="warning",
                title="技能成功率较低",
                description=f"该技能的成功率为 {stats.success_rate:.1%}，建议检查参数配置",
                confidence=0.8,
                reason=f"基于 {stats.total_executions} 次执行统计",
            )
            suggestions.append(suggestion)

        optimizations = self._optimizations.get(skill_name, [])
        for opt in optimizations:
            if opt.confidence >= min_confidence and opt.parameter_name not in current_params:
                    suggestion = OperationSuggestion(
                        skill_name=skill_name,
                        suggestion_type="parameter",
                        title=f"建议添加参数 {opt.parameter_name}",
                        description=f"添加参数 {opt.parameter_name}={opt.optimized_value} 可能提升成功率",
                        suggested_params={opt.parameter_name: opt.optimized_value},
                        confidence=opt.confidence,
                        reason=f"基于 {opt.samples} 次成功执行分析",
                    )
                    suggestions.append(suggestion)

        recent_records = [
            r for r in self._execution_records
            if r.skill_name == skill_name and r.success
        ][-10:]

        if recent_records:
            common_params = {}
            for record in recent_records:
                for key, value in record.parameters.items():
                    if key not in common_params:
                        common_params[key] = {}
                    value_str = str(value)
                    common_params[key][value_str] = common_params[key].get(value_str, 0) + 1

            for key, value_counts in common_params.items():
                most_common = max(value_counts.items(), key=lambda x: x[1])
                if most_common[1] >= len(recent_records) * 0.7 and key not in current_params:
                        suggestion = OperationSuggestion(
                            skill_name=skill_name,
                            suggestion_type="parameter",
                            title=f"建议添加常用参数 {key}",
                            description=f"大多数成功执行使用了 {key}={most_common[0]}",
                            suggested_params={key: most_common[0]},
                            confidence=most_common[1] / len(recent_records),
                            reason=f"在最近 {len(recent_records)} 次成功执行中，{most_common[1]} 次使用了此参数",
                        )
                        suggestions.append(suggestion)

        self._suggestions.extend(suggestions)

        return suggestions

    def get_suggestions(
        self,
        skill_name: str | None = None,
        include_applied: bool = False
    ) -> list[OperationSuggestion]:
        """获取建议"""
        suggestions = self._suggestions

        if skill_name:
            suggestions = [s for s in suggestions if s.skill_name == skill_name]

        if not include_applied:
            suggestions = [s for s in suggestions if not s.applied]

        return suggestions

    def apply_suggestion(self, suggestion_id: str) -> bool:
        """应用建议"""
        for suggestion in self._suggestions:
            if suggestion.id == suggestion_id:
                suggestion.applied = True
                return True
        return False

    def dismiss_suggestion(self, suggestion_id: str) -> bool:
        """忽略建议"""
        self._suggestions = [
            s for s in self._suggestions if s.id != suggestion_id
        ]
        return True

    def get_execution_history(
        self,
        skill_name: str | None = None,
        user_id: str | None = None,
        limit: int = 100
    ) -> list[SkillExecutionRecord]:
        """获取执行历史"""
        records = self._execution_records

        if skill_name:
            records = [r for r in records if r.skill_name == skill_name]

        if user_id:
            records = [r for r in records if r.user_id == user_id]

        records = sorted(records, key=lambda x: x.timestamp, reverse=True)

        return records[:limit]

    def _persist_record(self, record: SkillExecutionRecord):
        """持久化执行记录"""
        date_str = record.timestamp.strftime("%Y-%m-%d")
        file_path = self.storage_path / f"executions_{date_str}.jsonl"

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"持久化执行记录失败: {e}")

    def get_learning_stats(self) -> dict[str, Any]:
        """获取学习统计"""
        total_executions = sum(s.total_executions for s in self._statistics.values())
        avg_success_rate = (
            sum(s.success_rate for s in self._statistics.values()) / len(self._statistics)
            if self._statistics else 0
        )

        return {
            "total_skills": len(self._statistics),
            "total_executions": total_executions,
            "avg_success_rate": avg_success_rate,
            "total_optimizations": sum(len(opts) for opts in self._optimizations.values()),
            "total_suggestions": len(self._suggestions),
            "pending_suggestions": sum(1 for s in self._suggestions if not s.applied),
        }


_skill_learner: SkillLearner | None = None


def get_skill_learner() -> SkillLearner:
    """获取技能学习器单例"""
    global _skill_learner
    if _skill_learner is None:
        _skill_learner = SkillLearner()
    return _skill_learner
