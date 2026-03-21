# -*- coding: utf-8 -*-
"""
Agent API 路由
集成统一意图检测器、监控体系、错误处理机制
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import time
import json

from core.config import get_settings
from agent.config import AgentConfig, ActionType
from agent.executor import AgentExecutor
from agent.intent import (
    UnifiedIntentDetector,
    IntentResult,
    MultiIntentResult,
    DetectionMethod,
    ConfidenceLevel,
    IntentCategory,
    create_unified_detector,
    IntentMonitor,
    IntentEvaluator,
    create_monitor,
    get_default_monitor,
    IntentDetectionErrorManager,
    create_error_manager,
    get_error_manager,
    MultiTurnIntentProcessor,
    create_multi_turn_processor,
)
from agent.audit import get_audit_logger

logger = logging.getLogger(__name__)

router = APIRouter()

settings = get_settings()

_agent_config: Optional[AgentConfig] = None
_executor: Optional[AgentExecutor] = None
_unified_detector: Optional[UnifiedIntentDetector] = None
_intent_monitor: Optional[IntentMonitor] = None
_error_manager: Optional[IntentDetectionErrorManager] = None


def get_agent_config() -> AgentConfig:
    """获取 Agent 配置"""
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentConfig(
            working_dir=settings.base_dir,
            enable_confirm=True,
            enable_audit=True,
        )
    return _agent_config


def get_executor() -> AgentExecutor:
    """获取执行器"""
    global _executor
    if _executor is None:
        config = get_agent_config()
        _executor = AgentExecutor(config)
        
        audit_logger = get_audit_logger()
        _executor.set_audit_callback(
            lambda action, params, result, duration: audit_logger.log(
                action=action,
                params=params,
                result=result,
                duration=duration,
            )
        )
    return _executor


def get_unified_detector() -> UnifiedIntentDetector:
    """获取统一意图检测器（推荐使用）"""
    global _unified_detector
    if _unified_detector is None:
        _unified_detector = create_unified_detector(
            use_semantic=True,
            use_context=True,
            use_llm_fallback=True,
            use_bert=True,
            enable_metrics=True
        )
    return _unified_detector


def get_intent_monitor() -> IntentMonitor:
    """获取意图检测监控器"""
    global _intent_monitor
    if _intent_monitor is None:
        _intent_monitor = get_default_monitor()
    return _intent_monitor


def get_detection_error_manager() -> IntentDetectionErrorManager:
    """获取错误管理器"""
    global _error_manager
    if _error_manager is None:
        _error_manager = get_error_manager()
    return _error_manager


class DetectIntentRequest(BaseModel):
    """意图检测请求"""
    message: str = Field(..., description="用户消息")


class DetectIntentResponse(BaseModel):
    """意图检测响应"""
    detected: bool
    action: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    need_confirm: bool = False


class ExecuteRequest(BaseModel):
    """执行请求"""
    action: str = Field(..., description="操作类型")
    params: Dict[str, Any] = Field(default_factory=dict, description="操作参数")
    confirm: bool = Field(default=False, description="是否已确认危险操作")


class ExecuteResponse(BaseModel):
    """执行响应"""
    success: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    need_confirm: bool = False


class ChatExecuteRequest(BaseModel):
    """聊天执行请求（从聊天消息自动识别并执行）"""
    message: str = Field(..., description="用户消息")
    auto_confirm: bool = Field(default=False, description="自动确认危险操作")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息（如当前生成的内容）")


class ChatExecuteResponse(BaseModel):
    """聊天执行响应"""
    detected: bool
    action: Optional[str] = None
    description: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AuditStatsResponse(BaseModel):
    """审计统计响应"""
    total: int
    success: int
    failed: int
    by_action: Dict[str, Any]


class EnhancedDetectRequest(BaseModel):
    """增强版意图检测请求"""
    message: str = Field(..., description="用户消息")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")


class IntentParamResponse(BaseModel):
    """意图参数响应"""
    name: str
    value: Any
    param_type: str
    confidence: float
    raw_text: str = ""


class DetectedIntentResponse(BaseModel):
    """检测到的意图响应"""
    intent_type: str
    action: str
    params: List[IntentParamResponse]
    confidence: float
    description: str
    need_clarification: bool = False
    clarification_question: str = ""
    raw_match: str = ""


class ClarificationOptionResponse(BaseModel):
    """澄清选项响应"""
    label: str
    value: str
    action: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None


class ClarificationDialogResponse(BaseModel):
    """澄清对话响应"""
    dialog_id: str
    question: str
    options: List[ClarificationOptionResponse]
    context: Dict[str, Any]
    created_at: str


class EnhancedDetectResponse(BaseModel):
    """增强版意图检测响应"""
    detected: bool
    intents: List[DetectedIntentResponse] = []
    has_ambiguity: bool = False
    clarification_dialog: Optional[ClarificationDialogResponse] = None


class ClarificationResponseRequest(BaseModel):
    """澄清响应请求"""
    dialog_id: str = Field(..., description="对话ID")
    response: str = Field(..., description="用户响应")


class ClarificationResponseResult(BaseModel):
    """澄清响应结果"""
    success: bool
    selected_option: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MultiIntentDetectRequest(BaseModel):
    """多意图检测请求"""
    message: str = Field(..., description="用户消息（可能包含多个意图）")
    context: Optional[Dict[str, Any]] = Field(default=None, description="上下文信息")
    max_intents: int = Field(default=5, description="最大返回意图数")


class MultiIntentDetectResponse(BaseModel):
    """多意图检测响应"""
    detected: bool
    intent_count: int
    intents: List[DetectedIntentResponse]
    original_message: str
    split_messages: List[str] = []


class ExtractParamsRequest(BaseModel):
    """参数提取请求"""
    message: str = Field(..., description="用户消息")
    param_types: Optional[List[str]] = Field(default=None, description="要提取的参数类型")


class ExtractParamsResponse(BaseModel):
    """参数提取响应"""
    params: List[IntentParamResponse]
    found_types: List[str]


class UnifiedDetectRequest(BaseModel):
    """统一意图检测请求"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(default=None, description="会话ID（用于多轮对话）")
    context: Optional[Dict[str, Any]] = Field(default=None, description="额外上下文")


class UnifiedIntentResponse(BaseModel):
    """统一意图检测响应"""
    detected: bool
    intent_type: str = ""
    action: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    confidence: float = 0.0
    confidence_level: str = "unknown"
    method: str = "rule"
    need_confirm: bool = False
    alternatives: List[List[Any]] = Field(default_factory=list)
    category: str = "unknown"


class UnifiedMultiIntentResponse(BaseModel):
    """统一多意图检测响应"""
    detected: bool
    intents: List[UnifiedIntentResponse] = Field(default_factory=list)
    has_ambiguity: bool = False
    clarification_dialog: Optional[Dict[str, Any]] = None


class IntentMetricsResponse(BaseModel):
    """意图检测指标响应"""
    total_requests: int
    successful_detections: int
    failed_detections: int
    success_rate: float
    average_response_time_ms: float
    method_usage: Dict[str, int]
    intent_distribution: Dict[str, int]
    confidence_distribution: Dict[str, int]


class ErrorManagerStatusResponse(BaseModel):
    """错误管理器状态响应"""
    circuit_breaker: Dict[str, Any]
    fallback_level: str
    error_stats: Dict[str, Any]
    cache_size: int


@router.post("/detect-intent", response_model=DetectIntentResponse)
async def detect_intent(request: DetectIntentRequest):
    """检测用户消息中的意图"""
    detector = get_unified_detector()
    result = detector.detect(request.message)

    return DetectIntentResponse(
        detected=result.detected,
        action=result.action,
        params=result.params,
        description=result.description,
        need_confirm=result.need_confirm,
    )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_action(request: ExecuteRequest):
    """执行 Agent 操作"""
    try:
        try:
            action = ActionType(request.action)
        except ValueError:
            raise HTTPException(400, f"不支持的操作类型：{request.action}")
        
        executor = get_executor()
        if executor.validator.is_dangerous_action(action) and not request.confirm:
            return ExecuteResponse(
                success=False,
                error="此操作需要确认",
                need_confirm=True,
            )
        
        params = request.params.copy()
        if action == ActionType.FILE_DELETE:
            params["confirmed"] = request.confirm
        
        result = await executor.execute(action, params)
        
        return ExecuteResponse(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行操作失败：{e}", exc_info=True)
        raise HTTPException(500, f"执行失败：{str(e)}")


@router.post("/chat-execute", response_model=ChatExecuteResponse)
async def chat_execute(request: ChatExecuteRequest):
    """从聊天消息自动识别并执行操作"""
    detector = get_unified_detector()
    intent = detector.detect(request.message, context=request.context)
    
    if not intent.detected:
        response = ChatExecuteResponse(
            detected=False,
            result={"clarification": intent.clarification.get("message", "") if intent.clarification else ""}
        )
        return response
    
    if intent.need_confirm and not request.auto_confirm:
        return ChatExecuteResponse(
            detected=True,
            action=intent.action,
            description=f"{intent.description}（需要确认）",
            result={"need_confirm": True, "params": intent.params},
        )
    
    executor = get_executor()
    
    params = intent.params.copy() if intent.params else {}
    
    try:
        action = ActionType(intent.action)
    except ValueError:
        return ChatExecuteResponse(
            detected=True,
            action=intent.action,
            description=intent.description,
            error=f"不支持的操作类型：{intent.action}"
        )
    
    if action == ActionType.FILE_DELETE:
        params["confirmed"] = request.auto_confirm
    
    result = await executor.execute(action, params)
    
    return ChatExecuteResponse(
        detected=True,
        action=intent.action,
        description=intent.description,
        result=result.to_dict(),
        error=result.error if not result.success else None,
    )


@router.get("/capabilities")
async def get_capabilities():
    """获取 Agent 支持的操作能力"""
    return {
        "actions": [
            {
                "type": "file_create",
                "description": "创建文件",
                "params": ["file_path", "content", "overwrite"],
                "example": "创建 test.py 文件",
            },
            {
                "type": "file_read",
                "description": "读取文件",
                "params": ["file_path", "max_lines"],
                "example": "读取 README.md",
            },
            {
                "type": "file_write",
                "description": "写入文件",
                "params": ["file_path", "content", "mode"],
                "example": "把 config.json 改成 {...}",
            },
            {
                "type": "file_delete",
                "description": "删除文件（需确认）",
                "params": ["file_path"],
                "example": "删除 temp.txt",
                "dangerous": True,
            },
            {
                "type": "file_list",
                "description": "列出文件",
                "params": ["directory", "pattern"],
                "example": "列出当前目录的文件",
            },
            {
                "type": "app_open",
                "description": "打开应用",
                "params": ["app_name"],
                "example": "打开 VS Code",
            },
            {
                "type": "url_open",
                "description": "打开网址",
                "params": ["url"],
                "example": "打开 https://github.com",
            },
        ],
        "allowed_apps": list(set(settings.__class__.__module__)),
    }


@router.get("/audit/stats", response_model=AuditStatsResponse)
async def get_audit_stats():
    """获取审计统计信息"""
    audit_logger = get_audit_logger()
    stats = audit_logger.get_stats()
    
    return AuditStatsResponse(**stats)


@router.get("/audit/recent")
async def get_audit_recent(limit: int = 50):
    """获取最近的审计日志"""
    audit_logger = get_audit_logger()
    entries = audit_logger.get_recent_entries(limit)
    
    return {"entries": entries, "count": len(entries)}


@router.post("/audit/clear")
async def clear_audit():
    """清空审计日志缓存"""
    audit_logger = get_audit_logger()
    audit_logger.clear()
    
    return {"message": "审计日志缓存已清空"}


@router.post("/detect-intent-enhanced", response_model=EnhancedDetectResponse)
async def detect_intent_enhanced(request: EnhancedDetectRequest):
    """增强版意图检测"""
    detector = get_unified_detector()
    result = detector.detect_multi(request.message, context=request.context)
    
    if not result.detected:
        return EnhancedDetectResponse(detected=False)
    
    intents = []
    for intent in result.intents:
        params = [
            IntentParamResponse(
                name=p.get("name", ""),
                value=p.get("value"),
                param_type=p.get("param_type", "unknown"),
                confidence=p.get("confidence", 1.0),
                raw_text=p.get("raw_text", "")
            )
            for p in (intent.params.items() if isinstance(intent.params, dict) else [])
        ]
        
        intents.append(DetectedIntentResponse(
            intent_type=intent.intent_type,
            action=intent.action,
            params=params,
            confidence=intent.confidence,
            description=intent.description,
            need_clarification=intent.confidence < 0.7,
            clarification_question=intent.clarification.get("message", "") if intent.clarification else "",
            raw_match=""
        ))
    
    clarification_dialog = None
    if result.clarification_dialog:
        options = [
            ClarificationOptionResponse(
                label=opt.get("label", ""),
                value=opt.get("value", ""),
                action=opt.get("action"),
                intent=opt.get("intent")
            )
            for opt in result.clarification_dialog.get("options", [])
        ]
        clarification_dialog = ClarificationDialogResponse(
            dialog_id=result.clarification_dialog.get("dialog_id", ""),
            question=result.clarification_dialog.get("message", ""),
            options=options,
            context=result.clarification_dialog.get("context", {}),
            created_at=datetime.now().isoformat()
        )
    
    return EnhancedDetectResponse(
        detected=True,
        intents=intents,
        has_ambiguity=result.has_ambiguity,
        clarification_dialog=clarification_dialog
    )


@router.post("/detect-multi-intent", response_model=MultiIntentDetectResponse)
async def detect_multi_intent(request: MultiIntentDetectRequest):
    """多意图并行检测"""
    detector = get_unified_detector()
    result: MultiIntentResult = detector.detect_multi(request.message, context=request.context)
    
    intents = []
    for intent in result.intents[:request.max_intents]:
        params = [
            IntentParamResponse(
                name=p.name,
                value=p.value,
                param_type=p.param_type.value,
                confidence=p.confidence,
                raw_text=p.raw_text
            )
            for p in intent.params
        ]
        
        intents.append(DetectedIntentResponse(
            intent_type=intent.intent_type.value,
            action=intent.action,
            params=params,
            confidence=intent.confidence,
            description=intent.description,
            need_clarification=intent.need_clarification,
            clarification_question=intent.clarification_question,
            raw_match=intent.raw_match
        ))
    
    split_messages = detector._split_multi_intent(request.message)
    
    return MultiIntentDetectResponse(
        detected=result.detected,
        intent_count=len(intents),
        intents=intents,
        original_message=request.message,
        split_messages=split_messages
    )


@router.post("/clarification/respond", response_model=ClarificationResponseResult)
async def handle_clarification_response(request: ClarificationResponseRequest):
    """处理澄清对话响应"""
    detector = get_unified_detector()
    success, option = detector.handle_clarification_response(
        request.dialog_id,
        request.response
    )
    
    return ClarificationResponseResult(
        success=success,
        selected_option=option if success else None,
        error=option.get("error") if not success else None
    )


@router.get("/clarification/{dialog_id}")
async def get_clarification_dialog(dialog_id: str):
    """获取澄清对话详情"""
    detector = get_unified_detector()
    dialog = detector.get_clarification_dialog(dialog_id)
    
    if not dialog:
        raise HTTPException(404, f"澄清对话不存在: {dialog_id}")
    
    return dialog


@router.post("/extract-params", response_model=ExtractParamsResponse)
async def extract_params(request: ExtractParamsRequest):
    """从自然语言中提取结构化参数"""
    from core.intent_detector import ParameterExtractor
    
    extractor = ParameterExtractor()
    all_params = extractor.extract_all(request.message)
    
    if request.param_types:
        filtered_params = [
            p for p in all_params
            if p.param_type.value in request.param_types
        ]
    else:
        filtered_params = all_params
    
    params = [
        IntentParamResponse(
            name=p.name,
            value=p.value,
            param_type=p.param_type.value,
            confidence=p.confidence,
            raw_text=p.raw_text
        )
        for p in filtered_params
    ]
    
    found_types = list(set(p.param_type for p in filtered_params))
    
    return ExtractParamsResponse(
        params=params,
        found_types=found_types
    )


@router.get("/intent-types")
async def get_intent_types():
    """获取支持的意图类型列表"""
    return {
        "intent_types": [],
        "param_types": []
    }


@router.post("/intent-confidence")
async def evaluate_intent_confidence(request: EnhancedDetectRequest):
    """评估意图置信度详情"""
    detector = get_unified_detector()
    result = detector.detect(request.message, request.context)
    
    if not result.detected:
        return {
            "detected": False,
            "message": "未检测到意图"
        }
    
    confidence_details = []
    details = {
        "action": result.action,
        "description": result.description,
        "confidence": result.confidence,
        "confidence_level": "high" if result.confidence >= 0.9 else
                           "medium" if result.confidence >= 0.7 else "low",
        "need_clarification": result.confidence < 0.7,
        "factors": {
            "match_coverage": 0.0,
            "keyword_match": 0.0,
            "param_completeness": 0.0
        }
    }
    
    confidence_details.append(details)
    
    return {
        "detected": True,
        "intents": confidence_details,
        "recommendation": "proceed" if result.confidence >= 0.7 else "clarify"
    }


@router.get("/system/processes")
async def list_processes():
    """列出所有进程"""
    from agent.operations.system import ProcessManager
    manager = ProcessManager()
    processes = await manager.list_processes()
    return {"processes": processes, "count": len(processes)}


@router.get("/system/processes/{pid}")
async def get_process_info(pid: int):
    """获取进程详情"""
    from agent.operations.system import ProcessManager
    manager = ProcessManager()
    info = await manager.get_process_info(pid)
    if not info:
        raise HTTPException(404, f"进程不存在: {pid}")
    return info


@router.post("/system/processes/{pid}/kill")
async def kill_process(pid: int, confirm: bool = False):
    """终止进程"""
    if not confirm:
        return {"need_confirm": True, "message": f"确定要终止进程 {pid} 吗？"}
    
    from agent.operations.system import ProcessManager
    manager = ProcessManager()
    success = await manager.kill_process(pid)
    return {"success": success, "pid": pid}


@router.get("/system/services")
async def list_services():
    """列出所有服务（Windows）"""
    from agent.operations.system import ServiceManager
    manager = ServiceManager()
    services = await manager.list_services()
    return {"services": services, "count": len(services)}


@router.get("/system/services/{name}")
async def get_service_info(name: str):
    """获取服务详情"""
    from agent.operations.system import ServiceManager
    manager = ServiceManager()
    info = await manager.get_service_info(name)
    if not info:
        raise HTTPException(404, f"服务不存在: {name}")
    return info


@router.post("/system/services/{name}/start")
async def start_service(name: str, confirm: bool = False):
    """启动服务"""
    if not confirm:
        return {"need_confirm": True, "message": f"确定要启动服务 {name} 吗？"}
    
    from agent.operations.system import ServiceManager
    manager = ServiceManager()
    success = await manager.start_service(name)
    return {"success": success, "service": name}


@router.post("/system/services/{name}/stop")
async def stop_service(name: str, confirm: bool = False):
    """停止服务"""
    if not confirm:
        return {"need_confirm": True, "message": f"确定要停止服务 {name} 吗？"}
    
    from agent.operations.system import ServiceManager
    manager = ServiceManager()
    success = await manager.stop_service(name)
    return {"success": success, "service": name}


@router.get("/system/environment")
async def get_environment_variables():
    """获取环境变量"""
    from agent.operations.system import EnvironmentManager
    manager = EnvironmentManager()
    variables = await manager.get_all()
    return {"variables": variables}


@router.get("/system/info")
async def get_system_info():
    """获取系统信息"""
    from agent.operations.system import SystemInfo
    info = SystemInfo()
    return await info.get_all()


@router.get("/hardware/status")
async def get_hardware_status():
    """获取所有硬件状态"""
    from agent.operations.hardware import HardwareMonitor
    monitor = HardwareMonitor()
    return await monitor.get_status()


@router.get("/hardware/cpu")
async def get_cpu_info():
    """获取 CPU 信息"""
    from agent.operations.hardware import CPUMonitor
    monitor = CPUMonitor()
    return await monitor.get_info()


@router.get("/hardware/memory")
async def get_memory_info():
    """获取内存信息"""
    from agent.operations.hardware import MemoryMonitor
    monitor = MemoryMonitor()
    return await monitor.get_info()


@router.get("/hardware/disk")
async def get_disk_info():
    """获取磁盘信息"""
    from agent.operations.hardware import DiskMonitor
    monitor = DiskMonitor()
    return await monitor.get_info()


@router.get("/hardware/network")
async def get_network_info():
    """获取网络信息"""
    from agent.operations.hardware import NetworkMonitor
    monitor = NetworkMonitor()
    return await monitor.get_info()


@router.get("/permissions/roles")
async def list_roles():
    """列出所有角色"""
    from agent.security.rbac import get_rbac_manager
    manager = get_rbac_manager()
    return {"roles": [r.value for r in manager.get_all_roles()]}


@router.get("/permissions/user/{user_id}")
async def get_user_permissions(user_id: str):
    """获取用户权限"""
    from agent.security.rbac import get_rbac_manager
    manager = get_rbac_manager()
    role = await manager.get_user_role(user_id)
    permissions = await manager.get_user_permissions(user_id)
    return {"user_id": user_id, "role": role.value, "permissions": [p.value for p in permissions]}


@router.post("/permissions/assign")
async def assign_role(user_id: str, role: str):
    """分配角色"""
    from agent.security.rbac import get_rbac_manager, Role
    manager = get_rbac_manager()
    try:
        role_enum = Role(role)
        assignment = await manager.assign_role(user_id, role_enum)
        return {"success": True, "assignment": assignment.model_dump()}
    except ValueError:
        raise HTTPException(400, f"无效的角色: {role}")


@router.get("/audit/query")
async def query_audit_logs(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = 100,
):
    """查询审计日志"""
    from agent.audit import get_audit_logger
    
    audit_logger = get_audit_logger()
    
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    
    entries = audit_logger.query(
        start_time=start,
        end_time=end,
        user_id=user_id,
        action=action,
        success=success,
        limit=limit,
    )
    
    return {"entries": entries, "count": len(entries)}


@router.get("/audit/export/json")
async def export_audit_json(start_time: Optional[str] = None, end_time: Optional[str] = None):
    """导出审计日志为 JSON"""
    from agent.audit import get_audit_logger
    
    audit_logger = get_audit_logger()
    
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    
    json_data = audit_logger.export_json(start, end)
    return {"data": json.loads(json_data)}


@router.get("/audit/export/csv")
async def export_audit_csv(start_time: Optional[str] = None, end_time: Optional[str] = None):
    """导出审计日志为 CSV"""
    from agent.audit import get_audit_logger
    from fastapi.responses import PlainTextResponse
    
    audit_logger = get_audit_logger()
    
    start = datetime.fromisoformat(start_time) if start_time else None
    end = datetime.fromisoformat(end_time) if end_time else None
    
    csv_data = audit_logger.export_csv(start, end)
    return PlainTextResponse(csv_data, media_type="text/csv")


@router.get("/plugins")
async def list_plugins():
    """列出所有插件"""
    from agent.plugins import get_plugin_loader
    loader = get_plugin_loader()
    registry = loader.get_registry()
    return {"plugins": [p.model_dump() for p in registry.list_plugins()]}


@router.post("/plugins/discover")
async def discover_plugins():
    """发现插件"""
    from agent.plugins import get_plugin_loader
    loader = get_plugin_loader()
    discovered = loader.discover_plugins()
    return {"discovered": [p.model_dump() for p in discovered]}


@router.post("/plugins/{plugin_id}/load")
async def load_plugin(plugin_id: str):
    """加载插件"""
    from agent.plugins import get_plugin_loader
    loader = get_plugin_loader()
    success = await loader.load_plugin(plugin_id)
    return {"success": success, "plugin_id": plugin_id}


@router.post("/plugins/{plugin_id}/unload")
async def unload_plugin(plugin_id: str):
    """卸载插件"""
    from agent.plugins import get_plugin_loader
    loader = get_plugin_loader()
    success = await loader.unload_plugin(plugin_id)
    return {"success": success, "plugin_id": plugin_id}


@router.get("/plugins/actions")
async def list_plugin_actions():
    """列出所有插件操作"""
    from agent.plugins import get_plugin_loader
    loader = get_plugin_loader()
    registry = loader.get_registry()
    return {"actions": registry.list_actions()}


@router.get("/operations/aliases")
async def list_operation_aliases():
    """列出所有操作别名"""
    from agent.config.operations import get_config_manager
    manager = get_config_manager()
    aliases = manager.list_aliases()
    return {"aliases": [{"alias": a.alias, "target": a.target_command, "description": a.description} for a in aliases]}


@router.post("/operations/aliases")
async def add_operation_alias(alias: str, target: str, params: Dict[str, Any] = None, description: str = ""):
    """添加操作别名"""
    from agent.config.operations import get_config_manager, CommandAlias
    manager = get_config_manager()
    new_alias = CommandAlias(alias=alias, target_command=target, params=params or {}, description=description)
    manager.add_alias(new_alias)
    return {"success": True, "alias": alias}


@router.delete("/operations/aliases/{alias}")
async def remove_operation_alias(alias: str):
    """移除操作别名"""
    from agent.config.operations import get_config_manager
    manager = get_config_manager()
    success = manager.remove_alias(alias)
    return {"success": success, "alias": alias}


@router.get("/operations/templates")
async def list_operation_templates():
    """列出所有操作模板"""
    from agent.config.operations import get_config_manager
    manager = get_config_manager()
    templates = manager.list_templates()
    return {"templates": [{"id": t.template_id, "name": t.name, "description": t.description} for t in templates]}


@router.post("/operations/templates/{template_id}/execute")
async def execute_operation_template(template_id: str, params: Dict[str, Any] = None):
    """执行操作模板"""
    from agent.config.operations import get_config_manager
    from agent.executor import get_executor
    
    manager = get_config_manager()
    executor = get_executor()
    
    async def execute_action(action: str, action_params: Dict):
        return await executor.execute(action, action_params)
    
    results = await manager.execute_template(template_id, execute_action, params)
    return {"template_id": template_id, "results": results}


@router.post("/risk/evaluate")
async def evaluate_risk(operation: str, params: Dict[str, Any] = None):
    """评估操作风险"""
    from agent.security.risk import RiskScorer
    scorer = RiskScorer()
    context = {"operation": operation, **(params or {})}
    score = scorer.calculate_score(context)
    return score.to_dict()


@router.get("/risk/alerts")
async def list_risk_alerts(limit: int = 100):
    """列出风险告警"""
    from agent.security.risk import get_alert_manager
    manager = get_alert_manager()
    alerts = manager.get_alerts(limit=limit)
    return {"alerts": [a.to_dict() for a in alerts]}


@router.post("/risk/alerts/{alert_id}/acknowledge")
async def acknowledge_risk_alert(alert_id: str, acknowledged_by: str):
    """确认风险告警"""
    from agent.security.risk import get_alert_manager
    manager = get_alert_manager()
    success = await manager.acknowledge_alert(alert_id, acknowledged_by)
    return {"success": success, "alert_id": alert_id}


@router.post("/detect-unified", response_model=UnifiedIntentResponse)
async def detect_intent_unified(request: UnifiedDetectRequest):
    """统一意图检测（推荐使用）"""
    detector = get_unified_detector()
    error_manager = get_detection_error_manager()
    monitor = get_intent_monitor()
    
    start_time = time.time()
    
    result, error_info = error_manager.execute_with_protection(
        detector.detect,
        request.message,
        request.message,
        request.session_id,
        request.context
    )
    
    latency_ms = (time.time() - start_time) * 1000
    
    if error_info and not result:
        return UnifiedIntentResponse(
            detected=False,
            confidence=0.0,
            confidence_level="unknown",
            description=error_info.get("message", "检测失败")
        )
    
    if result:
        monitor.record_detection(
            predicted_intent=result.intent_type,
            actual_intent=None,
            confidence=result.confidence,
            latency_ms=latency_ms,
            method=result.method.value if hasattr(result.method, 'value') else str(result.method),
            success=True,
            session_id=request.session_id
        )
        
        return UnifiedIntentResponse(
            detected=result.detected,
            intent_type=result.intent_type,
            action=result.action,
            params=result.params,
            description=result.description,
            confidence=result.confidence,
            confidence_level=result.confidence_level.value if hasattr(result.confidence_level, 'value') else str(result.confidence_level),
            method=result.method.value if hasattr(result.method, 'value') else str(result.method),
            need_confirm=result.need_confirm,
            alternatives=result.alternatives,
            category=result.category.value if hasattr(result.category, 'value') else str(result.category)
        )
    
    return UnifiedIntentResponse(detected=False)


@router.post("/detect-multi-unified", response_model=UnifiedMultiIntentResponse)
async def detect_multi_intent_unified(request: UnifiedDetectRequest):
    """多意图检测（升级版）"""
    detector = get_unified_detector()
    result = detector.detect_multi(request.message, request.session_id, request.context)
    
    intents = []
    for intent in result.intents:
        intents.append(UnifiedIntentResponse(
            detected=intent.detected,
            intent_type=intent.intent_type,
            action=intent.action,
            params=intent.params,
            description=intent.description,
            confidence=intent.confidence,
            confidence_level=intent.confidence_level.value if hasattr(intent.confidence_level, 'value') else str(intent.confidence_level),
            method=intent.method.value if hasattr(intent.method, 'value') else str(intent.method),
            need_confirm=intent.need_confirm,
            alternatives=intent.alternatives,
            category=intent.category.value if hasattr(intent.category, 'value') else str(intent.category)
        ))
    
    return UnifiedMultiIntentResponse(
        detected=result.detected,
        intents=intents,
        has_ambiguity=result.has_ambiguity,
        clarification_dialog=result.clarification_dialog
    )


@router.get("/intent/metrics", response_model=IntentMetricsResponse)
async def get_intent_metrics():
    """获取意图检测性能指标"""
    monitor = get_intent_monitor()
    report = monitor.get_real_time_stats()
    
    return IntentMetricsResponse(
        total_requests=report.get("total_detections", 0),
        successful_detections=report.get("correct_detections", 0),
        failed_detections=report.get("failed_detections", 0),
        success_rate=report.get("accuracy", 0),
        average_response_time_ms=report.get("average_latency_ms", 0),
        method_usage={},
        intent_distribution={},
        confidence_distribution={}
    )


@router.get("/intent/report")
async def get_intent_evaluation_report():
    """获取意图检测评估报告"""
    monitor = get_intent_monitor()
    return monitor.get_evaluation_report()


@router.get("/intent/error-status", response_model=ErrorManagerStatusResponse)
async def get_error_manager_status():
    """获取错误管理器状态"""
    error_manager = get_detection_error_manager()
    status = error_manager.get_status()
    
    return ErrorManagerStatusResponse(
        circuit_breaker=status.get("circuit_breaker", {}),
        fallback_level=status.get("fallback_level", "full"),
        error_stats=status.get("error_stats", {}),
        cache_size=status.get("cache_size", 0)
    )


@router.post("/intent/feedback")
async def record_intent_feedback(
    session_id: str,
    predicted_intent: str,
    is_correct: bool,
    actual_intent: Optional[str] = None
):
    """记录用户反馈"""
    detector = get_unified_detector()
    detector.record_feedback(session_id, predicted_intent, is_correct, actual_intent)
    
    return {"success": True, "message": "反馈已记录"}


@router.post("/intent/reset-metrics")
async def reset_intent_metrics():
    """重置意图检测指标"""
    monitor = get_intent_monitor()
    monitor.reset()
    
    detector = get_unified_detector()
    detector.reset_metrics()
    
    return {"success": True, "message": "指标已重置"}


@router.delete("/intent/session/{session_id}")
async def clear_intent_session(session_id: str):
    """清除会话上下文"""
    detector = get_unified_detector()
    detector.clear_session(session_id)
    
    return {"success": True, "message": f"会话 {session_id} 已清除"}
