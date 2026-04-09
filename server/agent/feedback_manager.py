"""
用户反馈闭环模块
收集用户对操作结果的反馈，用于持续改进系统
"""
import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackType(str, Enum):
    """反馈类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    BUG_REPORT = "bug_report"
    FEATURE_REQUEST = "feature_request"
    IMPROVEMENT = "improvement"


class FeedbackCategory(str, Enum):
    """反馈类别"""
    INTENT_DETECTION = "intent_detection"
    EXECUTION_RESULT = "execution_result"
    ERROR_MESSAGE = "error_message"
    USER_EXPERIENCE = "user_experience"
    PERFORMANCE = "performance"
    SAFETY = "safety"
    OTHER = "other"


@dataclass
class UserFeedback:
    """用户反馈"""
    feedback_id: str
    feedback_type: FeedbackType
    category: FeedbackCategory
    rating: int
    comment: str = ""
    action: str = ""
    intent_detected: str = ""
    intent_correct: bool | None = None
    execution_success: bool | None = None
    error_message: str = ""
    suggested_intent: str = ""
    suggested_improvement: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "feedback_type": self.feedback_type.value,
            "category": self.category.value,
            "rating": self.rating,
            "comment": self.comment,
            "action": self.action,
            "intent_detected": self.intent_detected,
            "intent_correct": self.intent_correct,
            "execution_success": self.execution_success,
            "error_message": self.error_message,
            "suggested_intent": self.suggested_intent,
            "suggested_improvement": self.suggested_improvement,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


@dataclass
class FeedbackStats:
    """反馈统计"""
    total_feedback: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    avg_rating: float = 0.0
    intent_accuracy: float = 0.0
    execution_success_rate: float = 0.0
    category_breakdown: dict[str, int] = field(default_factory=dict)
    common_issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_feedback": self.total_feedback,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "neutral_count": self.neutral_count,
            "avg_rating": round(self.avg_rating, 2),
            "intent_accuracy": round(self.intent_accuracy, 2),
            "execution_success_rate": round(self.execution_success_rate, 2),
            "category_breakdown": self.category_breakdown,
            "common_issues": self.common_issues,
        }


class FeedbackManager:
    """
    反馈管理器

    收集、存储和分析用户反馈
    """

    MAX_FEEDBACK = 10000
    FEEDBACK_FILE = "user_feedback.json"

    def __init__(self, storage_path: str = None):
        self._lock = threading.RLock()
        self._feedbacks: list[UserFeedback] = []
        self._feedback_by_action: dict[str, list[UserFeedback]] = defaultdict(list)
        self._feedback_by_session: dict[str, list[UserFeedback]] = defaultdict(list)
        self._storage_path = Path(storage_path) if storage_path else Path.home() / ".finetune" / "feedback"

        self._load_feedbacks()

    def _generate_feedback_id(self) -> str:
        """生成反馈ID"""
        import hashlib
        import time
        content = f"{time.time()}{len(self._feedbacks)}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def submit_feedback(
        self,
        feedback_type: FeedbackType,
        category: FeedbackCategory,
        rating: int,
        comment: str = "",
        action: str = "",
        intent_detected: str = "",
        intent_correct: bool = None,
        execution_success: bool = None,
        error_message: str = "",
        suggested_intent: str = "",
        suggested_improvement: str = "",
        session_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] = None,
    ) -> UserFeedback:
        """
        提交反馈

        Args:
            feedback_type: 反馈类型
            category: 反馈类别
            rating: 评分 (1-5)
            comment: 评论
            action: 相关操作
            intent_detected: 检测到的意图
            intent_correct: 意图是否正确
            execution_success: 执行是否成功
            error_message: 错误信息
            suggested_intent: 建议的意图
            suggested_improvement: 改进建议
            session_id: 会话ID
            user_id: 用户ID
            metadata: 元数据

        Returns:
            UserFeedback: 创建的反馈
        """
        with self._lock:
            feedback = UserFeedback(
                feedback_id=self._generate_feedback_id(),
                feedback_type=feedback_type,
                category=category,
                rating=max(1, min(5, rating)),
                comment=comment,
                action=action,
                intent_detected=intent_detected,
                intent_correct=intent_correct,
                execution_success=execution_success,
                error_message=error_message,
                suggested_intent=suggested_intent,
                suggested_improvement=suggested_improvement,
                session_id=session_id,
                user_id=user_id,
                metadata=metadata or {},
            )

            self._feedbacks.append(feedback)

            if action:
                self._feedback_by_action[action].append(feedback)
            if session_id:
                self._feedback_by_session[session_id].append(feedback)

            if len(self._feedbacks) > self.MAX_FEEDBACK:
                self._feedbacks = self._feedbacks[-self.MAX_FEEDBACK:]

            self._save_feedbacks()

            logger.info(f"收到用户反馈: {feedback.feedback_id}, 类型: {feedback_type.value}, 评分: {rating}")

            return feedback

    def get_feedback(self, feedback_id: str) -> UserFeedback | None:
        """获取反馈"""
        with self._lock:
            for feedback in self._feedbacks:
                if feedback.feedback_id == feedback_id:
                    return feedback
        return None

    def get_feedbacks_by_action(self, action: str) -> list[UserFeedback]:
        """获取操作相关的反馈"""
        with self._lock:
            return list(self._feedback_by_action.get(action, []))

    def get_feedbacks_by_session(self, session_id: str) -> list[UserFeedback]:
        """获取会话相关的反馈"""
        with self._lock:
            return list(self._feedback_by_session.get(session_id, []))

    def get_recent_feedbacks(self, limit: int = 100) -> list[UserFeedback]:
        """获取最近的反馈"""
        with self._lock:
            return list(self._feedbacks[-limit:])

    def get_stats(self, days: int = 7) -> FeedbackStats:
        """
        获取反馈统计

        Args:
            days: 统计最近几天的数据

        Returns:
            FeedbackStats: 统计结果
        """
        with self._lock:
            cutoff = datetime.now()
            if days > 0:
                from datetime import timedelta
                cutoff = cutoff - timedelta(days=days)

            recent = [f for f in self._feedbacks if f.timestamp >= cutoff]

            if not recent:
                return FeedbackStats()

            stats = FeedbackStats()
            stats.total_feedback = len(recent)

            for feedback in recent:
                if feedback.feedback_type == FeedbackType.POSITIVE:
                    stats.positive_count += 1
                elif feedback.feedback_type == FeedbackType.NEGATIVE:
                    stats.negative_count += 1
                else:
                    stats.neutral_count += 1

                stats.avg_rating += feedback.rating

                category = feedback.category.value
                stats.category_breakdown[category] = stats.category_breakdown.get(category, 0) + 1

            stats.avg_rating /= len(recent)

            intent_correct_count = sum(1 for f in recent if f.intent_correct is True)
            intent_total = sum(1 for f in recent if f.intent_correct is not None)
            if intent_total > 0:
                stats.intent_accuracy = intent_correct_count / intent_total * 100

            exec_success_count = sum(1 for f in recent if f.execution_success is True)
            exec_total = sum(1 for f in recent if f.execution_success is not None)
            if exec_total > 0:
                stats.execution_success_rate = exec_success_count / exec_total * 100

            issue_counts: dict[str, int] = defaultdict(int)
            for feedback in recent:
                if feedback.feedback_type == FeedbackType.NEGATIVE:
                    if feedback.comment:
                        issue_counts[feedback.comment[:50]] += 1
                    if feedback.suggested_improvement:
                        issue_counts[feedback.suggested_improvement[:50]] += 1

            stats.common_issues = sorted(issue_counts.keys(), key=lambda x: issue_counts[x], reverse=True)[:5]

            return stats

    def get_improvement_suggestions(self) -> list[dict[str, Any]]:
        """获取改进建议"""
        with self._lock:
            suggestions = []

            for feedback in self._feedbacks:
                if feedback.suggested_improvement:
                    suggestions.append({
                        "feedback_id": feedback.feedback_id,
                        "action": feedback.action,
                        "suggestion": feedback.suggested_improvement,
                        "timestamp": feedback.timestamp.isoformat(),
                    })

            return suggestions[-50:]

    def get_intent_corrections(self) -> list[dict[str, Any]]:
        """获取意图纠正数据"""
        with self._lock:
            corrections = []

            for feedback in self._feedbacks:
                if feedback.intent_correct is False and feedback.suggested_intent:
                    corrections.append({
                        "feedback_id": feedback.feedback_id,
                        "detected_intent": feedback.intent_detected,
                        "correct_intent": feedback.suggested_intent,
                        "action": feedback.action,
                        "comment": feedback.comment,
                        "timestamp": feedback.timestamp.isoformat(),
                    })

            return corrections[-50:]

    def _save_feedbacks(self):
        """保存反馈"""
        if not self._storage_path:
            return

        try:
            self._storage_path.mkdir(parents=True, exist_ok=True)
            data = {
                "feedbacks": [f.to_dict() for f in self._feedbacks[-1000:]],
                "last_updated": datetime.now().isoformat(),
            }

            file_path = self._storage_path / self.FEEDBACK_FILE
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存反馈失败: {e}")

    def _load_feedbacks(self):
        """加载反馈"""
        if not self._storage_path:
            return

        try:
            file_path = self._storage_path / self.FEEDBACK_FILE
            if not file_path.exists():
                return

            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)

            for item in data.get("feedbacks", []):
                feedback = UserFeedback(
                    feedback_id=item["feedback_id"],
                    feedback_type=FeedbackType(item["feedback_type"]),
                    category=FeedbackCategory(item["category"]),
                    rating=item["rating"],
                    comment=item.get("comment", ""),
                    action=item.get("action", ""),
                    intent_detected=item.get("intent_detected", ""),
                    intent_correct=item.get("intent_correct"),
                    execution_success=item.get("execution_success"),
                    error_message=item.get("error_message", ""),
                    suggested_intent=item.get("suggested_intent", ""),
                    suggested_improvement=item.get("suggested_improvement", ""),
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    session_id=item.get("session_id", ""),
                    user_id=item.get("user_id", ""),
                    metadata=item.get("metadata", {}),
                )
                self._feedbacks.append(feedback)

                if feedback.action:
                    self._feedback_by_action[feedback.action].append(feedback)
                if feedback.session_id:
                    self._feedback_by_session[feedback.session_id].append(feedback)

            logger.info(f"加载了 {len(self._feedbacks)} 条用户反馈")
        except Exception as e:
            logger.error(f"加载反馈失败: {e}")


_feedback_manager: FeedbackManager | None = None


def get_feedback_manager() -> FeedbackManager:
    """获取反馈管理器单例"""
    global _feedback_manager
    if _feedback_manager is None:
        _feedback_manager = FeedbackManager()
    return _feedback_manager


def submit_user_feedback(
    feedback_type: FeedbackType,
    category: FeedbackCategory,
    rating: int,
    **kwargs,
) -> UserFeedback:
    """便捷函数：提交用户反馈"""
    return get_feedback_manager().submit_feedback(
        feedback_type=feedback_type,
        category=category,
        rating=rating,
        **kwargs,
    )


def get_feedback_stats(days: int = 7) -> FeedbackStats:
    """便捷函数：获取反馈统计"""
    return get_feedback_manager().get_stats(days)
