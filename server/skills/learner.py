from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict
import statistics
import hashlib
import json

from skills.operation_memory import OperationRecord, get_operation_memory_manager


@dataclass
class LearningResult:
    skill_name: str
    parameter_name: str
    suggested_value: Any
    confidence: float
    reason: str
    sample_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "parameter_name": self.parameter_name,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
            "reason": self.reason,
            "sample_count": self.sample_count,
        }


@dataclass
class OperationPattern:
    pattern_id: str
    skill_name: str
    parameters: Dict[str, Any]
    frequency: int
    success_rate: float
    last_used: datetime
    context_conditions: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "skill_name": self.skill_name,
            "parameters": self.parameters,
            "frequency": self.frequency,
            "success_rate": self.success_rate,
            "last_used": self.last_used.isoformat(),
            "context_conditions": self.context_conditions,
        }


class SkillLearner:
    def __init__(self, operation_memory_manager=None):
        self._memory_manager = operation_memory_manager or get_operation_memory_manager()
        self._parameter_history: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))
        self._success_history: Dict[str, List[bool]] = defaultdict(list)
        self._patterns: Dict[str, List[OperationPattern]] = defaultdict(list)
        self._learning_threshold = 3
        self._confidence_threshold = 0.6

    async def learn_parameter(
        self,
        user_id: str,
        skill_name: str,
        parameter_name: str,
        value: Any,
        success: bool
    ) -> Optional[LearningResult]:
        key = f"{user_id}:{skill_name}"
        self._parameter_history[key][parameter_name].append(value)
        self._success_history[key].append(success)
        
        return await self.get_parameter_suggestion(user_id, skill_name, parameter_name)

    async def get_parameter_suggestion(
        self,
        user_id: str,
        skill_name: str,
        parameter_name: str
    ) -> Optional[LearningResult]:
        key = f"{user_id}:{skill_name}"
        values = self._parameter_history[key].get(parameter_name, [])
        
        if len(values) < self._learning_threshold:
            return None
        
        success_history = self._success_history[key]
        if not success_history:
            return None
        
        recent_success_rate = sum(success_history[-10:]) / min(len(success_history), 10)
        
        mode_value = self._calculate_mode(values)
        if mode_value is None:
            return None
        
        confidence = self._calculate_confidence(values, mode_value)
        confidence *= recent_success_rate
        
        if confidence < self._confidence_threshold:
            return None
        
        return LearningResult(
            skill_name=skill_name,
            parameter_name=parameter_name,
            suggested_value=mode_value,
            confidence=confidence,
            reason=f"Based on {len(values)} successful operations",
            sample_count=len(values),
        )

    async def learn_pattern(
        self,
        user_id: str,
        skill_name: str,
        parameters: Dict[str, Any],
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[OperationPattern]:
        pattern_id = self._generate_pattern_id(skill_name, parameters)
        
        existing_patterns = [p for p in self._patterns[user_id] if p.pattern_id == pattern_id]
        
        if existing_patterns:
            pattern = existing_patterns[0]
            pattern.frequency += 1
            if success:
                pattern.success_rate = (
                    (pattern.success_rate * (pattern.frequency - 1) + 1.0) 
                    / pattern.frequency
                )
            else:
                pattern.success_rate = (
                    pattern.success_rate * (pattern.frequency - 1) 
                    / pattern.frequency
                )
            pattern.last_used = datetime.now()
            if context:
                pattern.context_conditions.update(context)
            return pattern
        
        pattern = OperationPattern(
            pattern_id=pattern_id,
            skill_name=skill_name,
            parameters=parameters,
            frequency=1,
            success_rate=1.0 if success else 0.0,
            last_used=datetime.now(),
            context_conditions=context or {},
        )
        
        self._patterns[user_id].append(pattern)
        return pattern

    def _generate_pattern_id(self, skill_name: str, parameters: Dict[str, Any]) -> str:
        param_str = json.dumps(parameters, sort_keys=True, ensure_ascii=False)
        hash_value = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"{skill_name}_{hash_value}"

    async def find_similar_patterns(
        self,
        user_id: str,
        skill_name: str,
        parameters: Dict[str, Any]
    ) -> List[OperationPattern]:
        patterns = self._patterns.get(user_id, [])
        
        similar = []
        for pattern in patterns:
            if pattern.skill_name != skill_name:
                continue
            
            similarity = self._parameters_similarity(parameters, pattern.parameters)
            if similarity >= 0.5:
                similar.append((pattern, similarity))
        
        similar.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in similar[:5]]

    async def suggest_optimization(
        self,
        user_id: str,
        skill_name: str,
        current_params: Dict[str, Any]
    ) -> Dict[str, LearningResult]:
        suggestions = {}
        
        for param_name in current_params.keys():
            suggestion = await self.get_parameter_suggestion(
                user_id, skill_name, param_name
            )
            if suggestion:
                suggestions[param_name] = suggestion
        
        similar_patterns = await self.find_similar_patterns(
            user_id, skill_name, current_params
        )
        
        for pattern in similar_patterns:
            if pattern.success_rate > 0.8:
                for param_name, value in pattern.parameters.items():
                    if param_name not in suggestions:
                        suggestions[param_name] = LearningResult(
                            skill_name=skill_name,
                            parameter_name=param_name,
                            suggested_value=value,
                            confidence=pattern.success_rate * 0.8,
                            reason=f"From similar successful pattern",
                            sample_count=pattern.frequency,
                        )
        
        return suggestions

    async def analyze_success_factors(
        self,
        user_id: str,
        skill_name: str
    ) -> Dict[str, Any]:
        patterns = self._patterns.get(user_id, [])
        skill_patterns = [p for p in patterns if p.skill_name == skill_name]
        
        if not skill_patterns:
            return {"factors": [], "recommendations": []}
        
        successful = [p for p in skill_patterns if p.success_rate > 0.7]
        
        factor_counts: Dict[str, int] = defaultdict(int)
        for pattern in successful:
            for key, value in pattern.parameters.items():
                factor_key = f"{key}={value}"
                factor_counts[factor_key] += pattern.frequency
        
        sorted_factors = sorted(
            factor_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        recommendations = []
        for factor, count in sorted_factors[:3]:
            key, value = factor.split("=", 1)
            recommendations.append({
                "parameter": key,
                "suggested_value": value,
                "confidence": count / sum(f.frequency for f in successful),
            })
        
        return {
            "factors": sorted_factors,
            "recommendations": recommendations,
            "total_patterns": len(skill_patterns),
            "successful_patterns": len(successful),
        }

    async def get_learning_report(
        self,
        user_id: str,
        skill_name: Optional[str] = None
    ) -> Dict[str, Any]:
        patterns = self._patterns.get(user_id, [])
        
        if skill_name:
            patterns = [p for p in patterns if p.skill_name == skill_name]
        
        if not patterns:
            return {
                "total_patterns": 0,
                "skills_learned": [],
                "top_patterns": [],
                "learning_progress": {},
            }
        
        skills_learned = list(set(p.skill_name for p in patterns))
        
        top_patterns = sorted(
            patterns, 
            key=lambda p: p.frequency * p.success_rate, 
            reverse=True
        )[:10]
        
        skill_progress = {}
        for skill in skills_learned:
            skill_patterns = [p for p in patterns if p.skill_name == skill]
            total_freq = sum(p.frequency for p in skill_patterns)
            avg_success = statistics.mean(p.success_rate for p in skill_patterns)
            skill_progress[skill] = {
                "pattern_count": len(skill_patterns),
                "total_usage": total_freq,
                "average_success_rate": avg_success,
            }
        
        return {
            "total_patterns": len(patterns),
            "skills_learned": skills_learned,
            "top_patterns": [p.to_dict() for p in top_patterns],
            "learning_progress": skill_progress,
        }

    def _calculate_mode(self, values: List[Any]) -> Any:
        if not values:
            return None
        
        counts: Dict[str, int] = defaultdict(int)
        for v in values:
            counts[str(v)] += 1
        
        if not counts:
            return None
        
        return max(counts.items(), key=lambda x: x[1])[0]

    def _calculate_confidence(self, values: List[Any], mode_value: str) -> float:
        if not values:
            return 0.0
        
        mode_count = sum(1 for v in values if str(v) == mode_value)
        return mode_count / len(values)

    def _parameters_similarity(
        self,
        params1: Dict[str, Any],
        params2: Dict[str, Any]
    ) -> float:
        all_keys = set(params1.keys()) | set(params2.keys())
        
        if not all_keys:
            return 1.0
        
        matches = 0
        for key in all_keys:
            if key in params1 and key in params2:
                if str(params1[key]) == str(params2[key]):
                    matches += 1
        
        return matches / len(all_keys)

    def clear_learning_data(self, user_id: str) -> None:
        key_prefix = f"{user_id}:"
        for key in list(self._parameter_history.keys()):
            if key.startswith(key_prefix):
                del self._parameter_history[key]
        
        self._success_history.pop(user_id, None)
        self._patterns.pop(user_id, None)


_skill_learner: Optional[SkillLearner] = None


def get_skill_learner() -> SkillLearner:
    global _skill_learner
    if _skill_learner is None:
        _skill_learner = SkillLearner()
    return _skill_learner


def reset_skill_learner() -> SkillLearner:
    global _skill_learner
    _skill_learner = SkillLearner()
    return _skill_learner
