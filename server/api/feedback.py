"""
用户反馈 API 路由
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent.feedback_manager import (
    FeedbackCategory,
    FeedbackType,
    get_feedback_manager,
    get_feedback_stats,
    submit_user_feedback,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackSubmitRequest(BaseModel):
    """反馈提交请求"""
    feedback_type: str = Field(..., description="反馈类型: positive, negative, neutral, bug_report, feature_request, improvement")
    category: str = Field(..., description="反馈类别: intent_detection, execution_result, error_message, user_experience, performance, safety, other")
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: str = Field("", description="评论内容")
    action: str = Field("", description="相关操作")
    intent_detected: str = Field("", description="检测到的意图")
    intent_correct: bool | None = Field(None, description="意图是否正确")
    execution_success: bool | None = Field(None, description="执行是否成功")
    error_message: str = Field("", description="错误信息")
    suggested_intent: str = Field("", description="建议的正确意图")
    suggested_improvement: str = Field("", description="改进建议")
    session_id: str = Field("", description="会话ID")
    user_id: str = Field("", description="用户ID")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class FeedbackResponse(BaseModel):
    """反馈响应"""
    success: bool
    feedback_id: str
    message: str


class FeedbackStatsResponse(BaseModel):
    """反馈统计响应"""
    total_feedback: int
    positive_count: int
    negative_count: int
    neutral_count: int
    avg_rating: float
    intent_accuracy: float
    execution_success_rate: float
    category_breakdown: dict[str, int]
    common_issues: list[str]


class IntentCorrection(BaseModel):
    """意图纠正"""
    feedback_id: str
    detected_intent: str
    correct_intent: str
    action: str
    comment: str
    timestamp: str


class ImprovementSuggestion(BaseModel):
    """改进建议"""
    feedback_id: str
    action: str
    suggestion: str
    timestamp: str


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackSubmitRequest):
    """
    提交用户反馈
    
    用户可以对操作结果进行反馈，包括：
    - 意图检测是否正确
    - 执行是否成功
    - 改进建议
    """
    try:
        feedback_type = FeedbackType(request.feedback_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的反馈类型: {request.feedback_type}")

    try:
        category = FeedbackCategory(request.category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的反馈类别: {request.category}")

    feedback = submit_user_feedback(
        feedback_type=feedback_type,
        category=category,
        rating=request.rating,
        comment=request.comment,
        action=request.action,
        intent_detected=request.intent_detected,
        intent_correct=request.intent_correct,
        execution_success=request.execution_success,
        error_message=request.error_message,
        suggested_intent=request.suggested_intent,
        suggested_improvement=request.suggested_improvement,
        session_id=request.session_id,
        user_id=request.user_id,
        metadata=request.metadata,
    )

    return FeedbackResponse(
        success=True,
        feedback_id=feedback.feedback_id,
        message="感谢您的反馈！我们会认真对待每一条建议。",
    )


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_stats(days: int = 7):
    """
    获取反馈统计
    
    返回最近几天的反馈统计数据
    """
    stats = get_feedback_stats(days)

    return FeedbackStatsResponse(
        total_feedback=stats.total_feedback,
        positive_count=stats.positive_count,
        negative_count=stats.negative_count,
        neutral_count=stats.neutral_count,
        avg_rating=stats.avg_rating,
        intent_accuracy=stats.intent_accuracy,
        execution_success_rate=stats.execution_success_rate,
        category_breakdown=stats.category_breakdown,
        common_issues=stats.common_issues,
    )


@router.get("/corrections", response_model=list[IntentCorrection])
async def get_intent_corrections():
    """
    获取意图纠正数据
    
    返回用户对意图检测的纠正记录
    """
    manager = get_feedback_manager()
    corrections = manager.get_intent_corrections()

    return [IntentCorrection(**c) for c in corrections]


@router.get("/suggestions", response_model=list[ImprovementSuggestion])
async def get_improvement_suggestions():
    """
    获取改进建议
    
    返回用户提交的改进建议
    """
    manager = get_feedback_manager()
    suggestions = manager.get_improvement_suggestions()

    return [ImprovementSuggestion(**s) for s in suggestions]


@router.get("/recent")
async def get_recent_feedbacks(limit: int = 50):
    """
    获取最近的反馈
    
    返回最近提交的反馈列表
    """
    manager = get_feedback_manager()
    feedbacks = manager.get_recent_feedbacks(limit)

    return {
        "count": len(feedbacks),
        "feedbacks": [f.to_dict() for f in feedbacks],
    }


@router.get("/{feedback_id}")
async def get_feedback(feedback_id: str):
    """
    获取特定反馈详情
    """
    manager = get_feedback_manager()
    feedback = manager.get_feedback(feedback_id)

    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")

    return feedback.to_dict()
