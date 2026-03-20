"""
风险评分算法
"""
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from .rules import RiskRuleEngine, RiskCategory


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskScore:
    """风险评分"""
    total_score: float
    level: RiskLevel
    category_scores: Dict[str, float] = field(default_factory=dict)
    contributing_factors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "total_score": self.total_score,
            "level": self.level.value,
            "category_scores": self.category_scores,
            "contributing_factors": self.contributing_factors,
            "timestamp": self.timestamp.isoformat(),
            "recommendations": self.recommendations,
        }


class RiskScorer:
    """风险评分器"""
    
    LEVEL_THRESHOLDS = {
        RiskLevel.LOW: 25.0,
        RiskLevel.MEDIUM: 50.0,
        RiskLevel.HIGH: 75.0,
        RiskLevel.CRITICAL: 100.0,
    }
    
    def __init__(self, rule_engine: Optional[RiskRuleEngine] = None):
        self._rule_engine = rule_engine or RiskRuleEngine()
        self._score_history: List[RiskScore] = []
        self._max_history = 1000
    
    def calculate_score(self, context: Dict) -> RiskScore:
        """计算风险评分"""
        rule_scores = self._rule_engine.evaluate_all(context)
        
        total_score = 0.0
        category_scores: Dict[str, float] = {}
        contributing_factors: List[str] = []
        
        for rule_id, score in rule_scores.items():
            if score > 0:
                total_score += score
                rule = self._rule_engine.get_rule(rule_id)
                if rule:
                    category = rule.category.value
                    if category not in category_scores:
                        category_scores[category] = 0.0
                    category_scores[category] += score
                    
                    for factor in rule.factors:
                        evaluator = self._rule_engine._factor_evaluators.get(factor.name)
                        if evaluator and evaluator(context):
                            contributing_factors.append(factor.description or factor.name)
        
        total_score = min(total_score, 100.0)
        
        level = self._determine_level(total_score)
        
        recommendations = self._generate_recommendations(level, contributing_factors)
        
        risk_score = RiskScore(
            total_score=total_score,
            level=level,
            category_scores=category_scores,
            contributing_factors=list(set(contributing_factors)),
            recommendations=recommendations,
        )
        
        self._add_to_history(risk_score)
        
        return risk_score
    
    def _determine_level(self, score: float) -> RiskLevel:
        """确定风险等级"""
        if score < self.LEVEL_THRESHOLDS[RiskLevel.LOW]:
            return RiskLevel.LOW
        elif score < self.LEVEL_THRESHOLDS[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        elif score < self.LEVEL_THRESHOLDS[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
    
    def _generate_recommendations(self, level: RiskLevel, factors: List[str]) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if level == RiskLevel.CRITICAL:
            recommendations.append("建议拒绝此操作或要求管理员审批")
        elif level == RiskLevel.HIGH:
            recommendations.append("建议进行二次验证")
        elif level == RiskLevel.MEDIUM:
            recommendations.append("建议记录详细日志")
        
        if "删除操作" in factors or "批量操作" in factors:
            recommendations.append("建议确认操作范围")
        
        if "敏感路径" in factors or "系统路径" in factors:
            recommendations.append("建议检查路径是否正确")
        
        if "夜间操作" in factors or "周末操作" in factors:
            recommendations.append("建议在工作时间执行")
        
        return recommendations
    
    def _add_to_history(self, score: RiskScore) -> None:
        """添加到历史记录"""
        self._score_history.append(score)
        if len(self._score_history) > self._max_history:
            self._score_history = self._score_history[-self._max_history:]
    
    def get_score_history(self, limit: int = 100) -> List[RiskScore]:
        """获取评分历史"""
        return self._score_history[-limit:]
    
    def get_average_score(self, category: Optional[str] = None) -> float:
        """获取平均评分"""
        if not self._score_history:
            return 0.0
        
        if category:
            scores = [
                s.category_scores.get(category, 0.0)
                for s in self._score_history
                if category in s.category_scores
            ]
        else:
            scores = [s.total_score for s in self._score_history]
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def get_score_trend(self, window: int = 10) -> str:
        """获取评分趋势"""
        if len(self._score_history) < 2:
            return "stable"
        
        recent_scores = [s.total_score for s in self._score_history[-window:]]
        
        if len(recent_scores) < 2:
            return "stable"
        
        first_half = sum(recent_scores[:len(recent_scores)//2]) / (len(recent_scores)//2)
        second_half = sum(recent_scores[len(recent_scores)//2:]) / (len(recent_scores) - len(recent_scores)//2)
        
        diff = second_half - first_half
        
        if diff > 10:
            return "increasing"
        elif diff < -10:
            return "decreasing"
        else:
            return "stable"
    
    def get_high_risk_operations(self, threshold: float = 75.0) -> List[RiskScore]:
        """获取高风险操作"""
        return [s for s in self._score_history if s.total_score >= threshold]
    
    def clear_history(self) -> None:
        """清除历史记录"""
        self._score_history.clear()
