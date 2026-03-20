"""
智能 Agent API - 自动判断并执行操作
"""
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

from agent.agent_config import ActionType
from agent.intent.detector import IntentDetector, IntentResult
from agent.intent.enhanced_detector import (
    EnhancedIntentDetector as NewEnhancedDetector,
    EnhancedIntentResult,
    create_enhanced_detector,
)
from agent.cua_executor import get_cua_executor, ExecutionResult
from agent.file_executor import get_file_executor, FileResult
from agent.safety_assessor import (
    get_safety_assessor,
    SafetyAssessment,
    SafetyLevel,
    is_safe_action,
    requires_confirmation,
    assess_safety,
)
from agent.execution_monitor import (
    get_execution_monitor,
    record_execution,
    get_execution_stats,
    get_execution_alerts,
    ExecutionStatus,
)
from agent.friendly_errors import format_error_message, categorize_error

logger = logging.getLogger(__name__)

router = APIRouter()


class SmartAgentRequest(BaseModel):
    """智能 Agent 请求"""
    message: str = Field(..., description="用户消息")
    auto_execute: bool = Field(default=True, description="是否自动执行检测到的操作")
    auto_confirm_safe: bool = Field(default=False, description="自动确认安全操作（谨慎使用）")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")


class OperationFeedback(BaseModel):
    """操作反馈"""
    detected: bool = Field(..., description="是否检测到操作意图")
    action: Optional[str] = Field(None, description="检测到的操作类型")
    description: Optional[str] = Field(None, description="操作描述")
    confidence: float = Field(0.0, description="置信度")
    need_confirm: bool = Field(False, description="是否需要确认")
    
    executed: bool = Field(False, description="是否已执行")
    success: Optional[bool] = Field(None, description="执行是否成功")
    result_data: Optional[Dict[str, Any]] = Field(None, description="执行结果数据")
    feedback: str = Field("", description="执行反馈消息")
    error: Optional[str] = Field(None, description="错误信息")
    duration_ms: float = Field(0.0, description="执行耗时(毫秒)")


class MultiOperationResponse(BaseModel):
    """多操作响应"""
    operations: List[OperationFeedback] = Field(default_factory=list)
    summary: str = ""


_intent_detector: Optional[IntentDetector] = None
_enhanced_detector: Optional[NewEnhancedDetector] = None


def get_intent_detector() -> IntentDetector:
    """获取意图检测器（兼容旧版）"""
    global _intent_detector
    if _intent_detector is None:
        _intent_detector = IntentDetector()
    return _intent_detector


def get_enhanced_detector() -> NewEnhancedDetector:
    """获取增强版意图检测器"""
    global _enhanced_detector
    if _enhanced_detector is None:
        _enhanced_detector = create_enhanced_detector()
    return _enhanced_detector


def is_cua_action(action: ActionType) -> bool:
    """判断是否为 CUA 操作"""
    cua_actions = {
        ActionType.SCREENSHOT, ActionType.SCREEN_INFO,
        ActionType.MOUSE_CLICK, ActionType.MOUSE_MOVE, ActionType.MOUSE_DRAG,
        ActionType.MOUSE_SCROLL, ActionType.MOUSE_POSITION,
        ActionType.KEYBOARD_TYPE, ActionType.KEYBOARD_PRESS, ActionType.KEYBOARD_HOTKEY,
        ActionType.WINDOW_LIST, ActionType.WINDOW_ACTIVE, ActionType.WINDOW_ACTIVATE,
        ActionType.WINDOW_CLOSE, ActionType.WINDOW_MINIMIZE, ActionType.WINDOW_MAXIMIZE,
        ActionType.OCR_RECOGNIZE, ActionType.OCR_FIND_TEXT,
        ActionType.RECORD_START, ActionType.RECORD_STOP, ActionType.RECORD_PLAY,
    }
    return action in cua_actions


def is_file_action(action: ActionType) -> bool:
    """判断是否为文件操作"""
    file_actions = {
        ActionType.FILE_CREATE, ActionType.FILE_READ,
        ActionType.FILE_WRITE, ActionType.FILE_DELETE, ActionType.FILE_LIST,
    }
    return action in file_actions


def check_operation_safety(action: ActionType, params: Dict[str, Any] = None) -> tuple:
    """
    检查操作安全性
    
    Returns:
        tuple: (is_safe, requires_confirmation, safety_assessment)
    """
    params = params or {}
    assessment = assess_safety(action, params)
    return assessment.is_safe, assessment.requires_confirmation, assessment


@router.post("/smart-execute", response_model=OperationFeedback)
async def smart_execute(request: SmartAgentRequest):
    """
    智能执行 - 自动检测意图并执行操作
    
    流程：
    1. 检测用户消息中的操作意图
    2. 评估操作安全级别
    3. 如果检测到且 auto_execute=True，根据安全级别决定是否执行
    4. 返回执行结果和反馈
    """
    start_time = time.time()
    action_type = None
    success = False
    error_msg = None
    error_category = None
    
    try:
        detector = get_enhanced_detector()
        
        intent: EnhancedIntentResult = detector.detect(request.message, request.context)
        
        if not intent.detected:
            feedback = OperationFeedback(
                detected=False,
                feedback="未检测到操作意图，这是一条普通消息"
            )
            if intent.clarification:
                feedback.feedback = intent.clarification.get("message", "")
                feedback.result_data = intent.clarification
            return feedback
        
        action_type = intent.action.value if intent.action else None
        feedback = OperationFeedback(
            detected=True,
            action=action_type,
            description=intent.description,
            confidence=intent.confidence,
            need_confirm=intent.need_confirm
        )
        
        if not request.auto_execute:
            feedback.feedback = f"检测到操作: {intent.description}，等待执行确认"
            return feedback
        
        safety_is_safe, safety_needs_confirm, safety_assessment = check_operation_safety(
            intent.action, intent.params
        )
        
        if safety_assessment.level == SafetyLevel.FORBIDDEN:
            feedback.feedback = f"❌ 操作被禁止: {safety_assessment.reason}"
            feedback.error = safety_assessment.reason
            feedback.result_data = {"suggestions": safety_assessment.suggestions}
            error_category = "operation_denied"
            return feedback
        
        if safety_needs_confirm and not request.auto_confirm_safe:
            feedback.feedback = f"⚠️ 需要确认: {safety_assessment.reason}"
            feedback.need_confirm = True
            feedback.result_data = {
                "suggestions": safety_assessment.suggestions,
                "safety_level": safety_assessment.level.value
            }
            return feedback
        
        if is_cua_action(intent.action):
            executor = get_cua_executor()
            result: ExecutionResult = await executor.execute(intent.action, intent.params or {})
            
            feedback.executed = True
            feedback.success = result.success
            feedback.result_data = result.data
            feedback.feedback = result.feedback
            feedback.error = result.error
            feedback.duration_ms = result.duration_ms
            success = result.success
            if not success and result.error:
                error_msg = result.error
                error_category = categorize_error(result.error)
        elif is_file_action(intent.action):
            executor = get_file_executor()
            result: FileResult = await executor.execute(intent.action, intent.params or {})
            
            feedback.executed = True
            feedback.success = result.success
            feedback.result_data = result.data
            feedback.feedback = result.feedback
            feedback.error = result.error
            success = result.success
            if not success and result.error:
                error_msg = result.error
                error_category = categorize_error(result.error)
        else:
            feedback.feedback = f"检测到操作: {intent.action.value}，暂不支持自动执行"
        
        return feedback
    
    except Exception as e:
        logger.error(f"智能执行失败: {e}", exc_info=True)
        error_msg = str(e)
        error_category = categorize_error(error_msg)
        
        return OperationFeedback(
            detected=True,
            action=action_type,
            feedback=format_error_message(error_category, error_msg),
            error=error_msg,
            executed=False,
            success=False
        )
    
    finally:
        duration_ms = (time.time() - start_time) * 1000
        if action_type:
            record_execution(
                action=action_type,
                success=success,
                duration_ms=duration_ms,
                error=error_msg,
                error_category=error_category
            )


@router.post("/smart-chat", response_model=MultiOperationResponse)
async def smart_chat(request: SmartAgentRequest):
    """
    智能聊天 - 支持多操作检测和执行
    
    可以从一条消息中提取多个操作并依次执行
    """
    detector = get_intent_detector()
    cua_executor = get_cua_executor()
    file_executor = get_file_executor()
    
    operations: List[OperationFeedback] = []
    
    sentences = request.message.replace("，", " ").replace("。", " ").replace("然后", " ").split()
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        intent = detector.detect(sentence)
        
        if not intent.detected:
            continue
        
        op_feedback = OperationFeedback(
            detected=True,
            action=intent.action.value if intent.action else None,
            description=intent.description,
            confidence=intent.confidence,
            need_confirm=intent.need_confirm
        )
        
        if request.auto_execute:
            _, safety_needs_confirm, safety_assessment = check_operation_safety(
                intent.action, intent.params
            )
            
            if is_cua_action(intent.action):
                if safety_needs_confirm and not request.auto_confirm_safe:
                    op_feedback.feedback = f"⚠️ 需要确认: {safety_assessment.reason}"
                    op_feedback.need_confirm = True
                else:
                    result = await cua_executor.execute(intent.action, intent.params or {})
                    op_feedback.executed = True
                    op_feedback.success = result.success
                    op_feedback.result_data = result.data
                    op_feedback.feedback = result.feedback
                    op_feedback.error = result.error
                    op_feedback.duration_ms = result.duration_ms
            elif is_file_action(intent.action):
                if safety_needs_confirm and not request.auto_confirm_safe:
                    op_feedback.feedback = f"⚠️ 需要确认: {safety_assessment.reason}"
                    op_feedback.need_confirm = True
                else:
                    result = await file_executor.execute(intent.action, intent.params or {})
                    op_feedback.executed = True
                    op_feedback.success = result.success
                    op_feedback.result_data = result.data
                    op_feedback.feedback = result.feedback
                    op_feedback.error = result.error
        
        operations.append(op_feedback)
    
    if not operations:
        return MultiOperationResponse(
            operations=[],
            summary="未检测到任何操作意图"
        )
    
    executed_count = sum(1 for op in operations if op.executed)
    success_count = sum(1 for op in operations if op.success)
    
    summary = f"检测到 {len(operations)} 个操作，执行 {executed_count} 个，成功 {success_count} 个"
    
    return MultiOperationResponse(
        operations=operations,
        summary=summary
    )


@router.get("/supported-operations")
async def get_supported_operations():
    """获取支持的操作列表"""
    return {
        "cua_operations": [
            {
                "action": "screenshot",
                "description": "截取屏幕截图",
                "examples": ["截图", "截屏", "拍张屏幕照片"],
                "safe": True
            },
            {
                "action": "mouse_click",
                "description": "鼠标点击",
                "examples": ["点击坐标 (100, 200)", "双击 (500, 300)", "右键点击 (100, 100)"],
                "safe": False
            },
            {
                "action": "mouse_move",
                "description": "移动鼠标",
                "examples": ["移动到 (100, 200)", "移动鼠标到坐标 100,200"],
                "safe": False
            },
            {
                "action": "mouse_position",
                "description": "获取鼠标位置",
                "examples": ["鼠标在哪里", "获取鼠标位置"],
                "safe": True
            },
            {
                "action": "keyboard_type",
                "description": "键盘输入",
                "examples": ["输入 \"Hello World\"", "键盘输入 \"测试文本\""],
                "safe": False
            },
            {
                "action": "window_list",
                "description": "列出所有窗口",
                "examples": ["列出窗口", "显示所有打开的窗口"],
                "safe": True
            },
            {
                "action": "window_active",
                "description": "获取活动窗口",
                "examples": ["获取活动窗口", "当前窗口是什么"],
                "safe": True
            },
            {
                "action": "window_activate",
                "description": "激活窗口",
                "examples": ["激活 VS Code 窗口", "切换到记事本窗口"],
                "safe": False
            },
            {
                "action": "window_close",
                "description": "关闭窗口",
                "examples": ["关闭记事本窗口"],
                "safe": False
            },
            {
                "action": "ocr_recognize",
                "description": "OCR 识别屏幕文字",
                "examples": ["识别屏幕文字", "OCR识别"],
                "safe": True
            },
            {
                "action": "ocr_find_text",
                "description": "查找屏幕上的文字",
                "examples": ["查找文字 \"确定\"", "在屏幕上找 \"保存\""],
                "safe": True
            },
            {
                "action": "record_start",
                "description": "开始录制操作",
                "examples": ["开始录制", "开始记录操作"],
                "safe": True
            },
            {
                "action": "record_stop",
                "description": "停止录制",
                "examples": ["停止录制"],
                "safe": True
            },
            {
                "action": "record_play",
                "description": "回放录制的操作",
                "examples": ["回放操作", "播放录制的操作"],
                "safe": False
            }
        ],
        "file_operations": [
            {
                "action": "file_create",
                "description": "创建文件",
                "examples": ["创建 test.txt 文件", "新建一个文件 test.txt"],
                "safe": False
            },
            {
                "action": "file_read",
                "description": "读取文件",
                "examples": ["读取 test.txt", "查看 test.txt 的内容"],
                "safe": True
            },
            {
                "action": "file_write",
                "description": "写入文件",
                "examples": ["把 test.txt 的内容改成 Hello", "写入 Hello 到 test.txt"],
                "safe": False
            },
            {
                "action": "file_delete",
                "description": "删除文件",
                "examples": ["删除 test.txt", "移除 test.txt 文件"],
                "safe": False
            },
            {
                "action": "file_list",
                "description": "列出文件",
                "examples": ["列出当前目录文件", "显示目录内容"],
                "safe": True
            }
        ],
        "total_cua": 14,
        "total_file": 5,
        "safe_count": 9
    }


@router.get("/execution-stats")
async def get_stats(action: str = None):
    """
    获取执行统计
    
    Args:
        action: 操作类型，为空时返回所有统计
    """
    return get_execution_stats(action)


@router.get("/execution-alerts")
async def get_alerts(limit: int = 100):
    """获取执行告警"""
    return {"alerts": get_execution_alerts(limit)}


@router.get("/execution-records")
async def get_records(limit: int = 100):
    """获取最近执行记录"""
    return {"records": get_execution_monitor().get_recent_records(limit)}


@router.get("/error-analysis")
async def get_errors():
    """获取错误分析"""
    return get_execution_monitor().get_error_analysis()


from fastapi.responses import StreamingResponse
from agent.progress_tracker import (
    get_progress_tracker,
    ProgressStatus,
)


@router.get("/progress/{task_id}")
async def get_task_progress(task_id: str):
    """获取任务进度"""
    tracker = get_progress_tracker()
    info = tracker.get_progress(task_id)
    
    if not info:
        return {"error": "任务不存在", "task_id": task_id}
    
    return info.to_dict()


@router.get("/progress/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """
    SSE 进度流
    
    实时推送任务进度更新
    """
    tracker = get_progress_tracker()
    
    async def event_generator():
        queue = tracker.subscribe(task_id)
        
        try:
            while True:
                try:
                    info = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield info.to_sse()
                    
                    if info.status in (ProgressStatus.COMPLETED, ProgressStatus.FAILED, ProgressStatus.CANCELLED):
                        break
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
                    
                    if tracker.is_cancelled(task_id):
                        break
        except asyncio.CancelledError:
            pass
        finally:
            tracker.unsubscribe(task_id, queue)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/progress/{task_id}/cancel")
async def cancel_task_progress(task_id: str):
    """取消任务"""
    tracker = get_progress_tracker()
    
    if tracker.cancel_task(task_id):
        return {"success": True, "message": f"任务 {task_id} 已取消"}
    else:
        return {"success": False, "message": f"任务 {task_id} 不存在"}


import asyncio
