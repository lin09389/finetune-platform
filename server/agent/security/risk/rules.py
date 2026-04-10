"""
风险评估规则
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class RiskCategory(str, Enum):
    """风险类别"""
    OPERATION = "operation"
    RESOURCE = "resource"
    BEHAVIOR = "behavior"
    TIME = "time"
    ENVIRONMENT = "environment"
    USER = "user"


@dataclass
class RiskFactor:
    """风险因素"""
    name: str
    category: RiskCategory
    weight: float
    description: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskRule:
    """风险规则"""
    rule_id: str
    name: str
    description: str
    category: RiskCategory
    factors: list[RiskFactor]
    base_score: float = 0.0
    max_score: float = 100.0
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)


class RiskRuleEngine:
    """风险规则引擎"""

    DEFAULT_RULES: dict[str, RiskRule] = {}

    def __init__(self):
        self._rules: dict[str, RiskRule] = dict(self.DEFAULT_RULES)
        self._custom_rules: dict[str, RiskRule] = {}
        self._factor_evaluators: dict[str, Callable] = {}

        self._register_default_rules()
        self._register_default_evaluators()

    def _register_default_rules(self):
        """注册默认规则"""
        self.DEFAULT_RULES.update({
            "destructive_operation": RiskRule(
                rule_id="destructive_operation",
                name="破坏性操作风险",
                description="评估破坏性操作的风险",
                category=RiskCategory.OPERATION,
                factors=[
                    RiskFactor("is_delete", RiskCategory.OPERATION, 30.0, "删除操作"),
                    RiskFactor("is_batch", RiskCategory.OPERATION, 20.0, "批量操作"),
                    RiskFactor("is_system_path", RiskCategory.RESOURCE, 25.0, "系统路径"),
                ],
                base_score=0.0,
            ),
            "system_modification": RiskRule(
                rule_id="system_modification",
                name="系统修改风险",
                description="评估系统修改操作的风险",
                category=RiskCategory.OPERATION,
                factors=[
                    RiskFactor("is_service_control", RiskCategory.OPERATION, 25.0, "服务控制"),
                    RiskFactor("is_process_kill", RiskCategory.OPERATION, 20.0, "进程终止"),
                    RiskFactor("is_env_modify", RiskCategory.OPERATION, 15.0, "环境变量修改"),
                ],
                base_score=10.0,
            ),
            "privilege_escalation": RiskRule(
                rule_id="privilege_escalation",
                name="权限提升风险",
                description="评估权限提升操作的风险",
                category=RiskCategory.USER,
                factors=[
                    RiskFactor("is_admin_op", RiskCategory.USER, 40.0, "管理员操作"),
                    RiskFactor("is_role_change", RiskCategory.USER, 35.0, "角色变更"),
                ],
                base_score=20.0,
            ),
            "unusual_time": RiskRule(
                rule_id="unusual_time",
                name="异常时间风险",
                description="评估非工作时间操作的风险",
                category=RiskCategory.TIME,
                factors=[
                    RiskFactor("is_night", RiskCategory.TIME, 15.0, "夜间操作"),
                    RiskFactor("is_weekend", RiskCategory.TIME, 10.0, "周末操作"),
                ],
                base_score=0.0,
            ),
            "sensitive_resource": RiskRule(
                rule_id="sensitive_resource",
                name="敏感资源风险",
                description="评估访问敏感资源的风险",
                category=RiskCategory.RESOURCE,
                factors=[
                    RiskFactor("is_sensitive_path", RiskCategory.RESOURCE, 30.0, "敏感路径"),
                    RiskFactor("is_large_file", RiskCategory.RESOURCE, 10.0, "大文件"),
                    RiskFactor("is_config_file", RiskCategory.RESOURCE, 20.0, "配置文件"),
                ],
                base_score=5.0,
            ),
            "behavior_pattern": RiskRule(
                rule_id="behavior_pattern",
                name="行为模式风险",
                description="评估异常行为模式的风险",
                category=RiskCategory.BEHAVIOR,
                factors=[
                    RiskFactor("high_frequency", RiskCategory.BEHAVIOR, 20.0, "高频操作"),
                    RiskFactor("unusual_pattern", RiskCategory.BEHAVIOR, 25.0, "异常模式"),
                ],
                base_score=0.0,
            ),
        })
        self._rules = dict(self.DEFAULT_RULES)

    def _register_default_evaluators(self):
        """注册默认评估器"""
        destructive_ops = {"file_delete", "directory_delete", "batch_delete"}
        batch_ops = {"batch_delete", "batch_copy", "batch_move"}
        system_paths = {"/etc", "/root", "/sys", "/proc", "C:\\Windows\\System32"}
        service_ops = {"service_start", "service_stop", "service_restart"}
        config_extensions = {".env", ".conf", ".config", ".yaml", ".yml", ".json"}

        self._factor_evaluators = {
            "is_delete": lambda ctx: ctx.get("operation") in destructive_ops,
            "is_batch": lambda ctx: ctx.get("operation") in batch_ops or ctx.get("batch_size", 0) > 1,
            "is_system_path": lambda ctx: any(p in ctx.get("path", "") for p in system_paths),
            "is_service_control": lambda ctx: ctx.get("operation") in service_ops,
            "is_process_kill": lambda ctx: ctx.get("operation") == "process_kill",
            "is_env_modify": lambda ctx: ctx.get("operation") == "environment_write",
            "is_admin_op": lambda ctx: ctx.get("requires_admin", False),
            "is_role_change": lambda ctx: ctx.get("operation") in {"role_assign", "role_revoke"},
            "is_night": lambda _ctx: datetime.now().hour < 6 or datetime.now().hour > 22,
            "is_weekend": lambda _ctx: datetime.now().weekday() >= 5,
            "is_sensitive_path": lambda ctx: any(p in ctx.get("path", "") for p in system_paths),
            "is_large_file": lambda ctx: ctx.get("file_size", 0) > 100 * 1024 * 1024,
            "is_config_file": lambda ctx: any(ctx.get("path", "").endswith(ext) for ext in config_extensions),
            "high_frequency": lambda ctx: ctx.get("operation_count", 0) > 100,
            "unusual_pattern": lambda ctx: ctx.get("pattern_anomaly", False),
        }

    def register_rule(self, rule: RiskRule) -> None:
        """注册规则"""
        self._custom_rules[rule.rule_id] = rule

    def unregister_rule(self, rule_id: str) -> bool:
        """注销规则"""
        if rule_id in self._custom_rules:
            del self._custom_rules[rule_id]
            return True
        return False

    def register_evaluator(self, factor_name: str, evaluator: Callable) -> None:
        """注册评估器"""
        self._factor_evaluators[factor_name] = evaluator

    def evaluate_rule(self, rule: RiskRule, context: dict) -> float:
        """评估规则"""
        if not rule.enabled:
            return 0.0

        score = rule.base_score

        for factor in rule.factors:
            evaluator = self._factor_evaluators.get(factor.name)
            if evaluator and evaluator(context):
                score += factor.weight

        return min(score, rule.max_score)

    def evaluate_all(self, context: dict) -> dict[str, float]:
        """评估所有规则"""
        all_rules = {**self._rules, **self._custom_rules}
        return {
            rule_id: self.evaluate_rule(rule, context)
            for rule_id, rule in all_rules.items()
        }

    def get_applicable_rules(self, context: dict) -> list[RiskRule]:
        """获取适用的规则"""
        all_rules = {**self._rules, **self._custom_rules}
        applicable = []
        for rule in all_rules.values():
            if not rule.enabled:
                continue

            for factor in rule.factors:
                evaluator = self._factor_evaluators.get(factor.name)
                if evaluator and evaluator(context):
                    applicable.append(rule)
                    break

        return applicable

    def get_rule(self, rule_id: str) -> RiskRule | None:
        """获取规则"""
        all_rules = {**self._rules, **self._custom_rules}
        return all_rules.get(rule_id)

    def get_all_rules(self) -> dict[str, RiskRule]:
        """获取所有规则"""
        return {**self._rules, **self._custom_rules}
