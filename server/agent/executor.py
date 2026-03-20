"""
Agent 执行器 - 执行具体操作
集成升级后的安全模块、友好错误消息
"""
import os
import subprocess
import webbrowser
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from .config import AgentConfig, ActionType
from .security_old import SecurityValidator, ValidationResult
from .safety_assessor import SafetyAssessor, SafetyLevel, get_safety_assessor
from .friendly_errors import get_friendly_error, FriendlyError
from .execution_monitor import get_execution_monitor

logger = logging.getLogger(__name__)


class ExecutionResult:
    """执行结果"""
    
    def __init__(
        self,
        success: bool,
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.error = error
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AgentExecutor:
    """Agent 操作执行器 - 集成升级后的安全模块"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.validator = SecurityValidator(config.working_dir)
        self.safety_assessor = get_safety_assessor()
        self.monitor = get_execution_monitor()
        self._audit_callback = None
    
    def set_audit_callback(self, callback):
        """设置审计日志回调"""
        self._audit_callback = callback
    
    def _get_friendly_error(self, error_code: str, **kwargs) -> FriendlyError:
        """获取友好错误消息"""
        return get_friendly_error(error_code, **kwargs)
    
    async def execute(
        self,
        action: ActionType,
        params: Dict[str, Any]
    ) -> ExecutionResult:
        """
        执行操作的主入口
        
        流程：
        1. 安全评估
        2. 执行操作
        3. 记录监控数据
        4. 返回结果
        """
        start_time = datetime.now()
        
        try:
            # 1. 安全评估
            safety = self.safety_assessor.assess(action, params)
            
            if safety.level == SafetyLevel.FORBIDDEN:
                friendly = self._get_friendly_error(
                    "permission_denied",
                    action=action.value,
                    reason=safety.reason
                )
                return ExecutionResult(
                    False,
                    error=friendly.message,
                    data={
                        "error_code": friendly.code,
                        "solutions": friendly.solutions,
                    }
                )
            
            if safety.level == SafetyLevel.DANGEROUS:
                if not params.get("confirmed"):
                    return ExecutionResult(
                        False,
                        error=f"危险操作需要确认：{safety.reason}",
                        data={
                            "need_confirm": True,
                            "action": action.value,
                            "params": params,
                            "risk": safety.reason,
                        }
                    )
            
            # 2. 路由到具体操作
            action_map = {
                ActionType.FILE_CREATE: self._file_create,
                ActionType.FILE_READ: self._file_read,
                ActionType.FILE_WRITE: self._file_write,
                ActionType.FILE_DELETE: self._file_delete,
                ActionType.FILE_LIST: self._file_list,
                ActionType.APP_OPEN: self._app_open,
                ActionType.URL_OPEN: self._url_open,
            }
            
            if action not in action_map:
                return ExecutionResult(
                    False,
                    error=f"不支持的操作：{action}"
                )
            
            # 3. 执行操作
            result = await action_map[action](params)
            
            # 4. 记录监控数据
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self.monitor.record(
                action=action.value,
                status="success" if result.success else "failed",
                duration_ms=duration_ms,
                error=result.error,
            )
            
            # 5. 记录审计日志
            if self._audit_callback:
                await self._audit_callback(
                    action=action,
                    params=params,
                    result=result,
                    duration=(datetime.now() - start_time).total_seconds()
                )
            
            return result
            
        except Exception as e:
            logger.error(f"执行操作失败：{action} - {e}", exc_info=True)
            
            # 记录失败
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            self.monitor.record(
                action=action.value,
                status="error",
                duration_ms=duration_ms,
                error=str(e),
                error_category="exception",
            )
            
            return ExecutionResult(False, error=str(e))
    
    # ==================== 文件操作 ====================
    
    async def _file_create(self, params: Dict[str, Any]) -> ExecutionResult:
        """创建文件"""
        file_path = params.get("file_path", "")
        content = params.get("content", "")
        overwrite = params.get("overwrite", False)
        
        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_CREATE)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        # 内容验证
        content_validation = self.validator.validate_content(content, self.config.max_file_size)
        if not content_validation.is_valid:
            friendly = self._get_friendly_error("file_too_large", size=len(content), max_size=self.config.max_file_size)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        full_path = Path(validation.sanitized_value)
        
        # 检查文件是否存在
        if full_path.exists() and not overwrite:
            friendly = self._get_friendly_error("file_exists", path=file_path)
            return ExecutionResult(
                False, 
                error=friendly.message,
                data={"solutions": friendly.solutions, "need_confirm": True}
            )
        
        try:
            # 创建父目录
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"文件已创建：{full_path}")
            
            return ExecutionResult(
                True,
                message=f"文件已创建：{file_path}",
                data={
                    "path": str(full_path),
                    "size": len(content),
                }
            )
            
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"创建文件失败：{str(e)}")
    
    async def _file_read(self, params: Dict[str, Any]) -> ExecutionResult:
        """读取文件"""
        file_path = params.get("file_path", "")
        max_lines = params.get("max_lines", 1000)
        
        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_READ)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        full_path = Path(validation.sanitized_value)
        
        # 检查文件是否存在
        if not full_path.exists():
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        if not full_path.is_file():
            friendly = self._get_friendly_error("not_a_file", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        try:
            # 读取文件
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 限制行数
            content = ''.join(lines[:max_lines])
            total_lines = len(lines)
            
            return ExecutionResult(
                True,
                message=f"文件已读取：{file_path}",
                data={
                    "content": content,
                    "lines": min(total_lines, max_lines),
                    "total_lines": total_lines,
                    "truncated": total_lines > max_lines,
                }
            )
            
        except UnicodeDecodeError:
            friendly = self._get_friendly_error("encoding_error", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"读取文件失败：{str(e)}")
    
    async def _file_write(self, params: Dict[str, Any]) -> ExecutionResult:
        """写入文件"""
        file_path = params.get("file_path", "")
        content = params.get("content", "")
        mode = params.get("mode", "w")
        
        if mode == "append":
            mode = "a"
        elif mode not in ("w", "a", "r+", "w+"):
            mode = "w"
        
        # 安全验证
        validation = self.validator.validate_path(file_path, ActionType.FILE_WRITE)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        # 内容验证
        content_validation = self.validator.validate_content(content, self.config.max_file_size)
        if not content_validation.is_valid:
            friendly = self._get_friendly_error("file_too_large", size=len(content), max_size=self.config.max_file_size)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        full_path = Path(validation.sanitized_value)
        
        # 检查文件是否存在
        if not full_path.exists():
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        try:
            with open(full_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            action_text = "追加" if mode == "a" else "更新"
            logger.info(f"文件已{action_text}：{full_path}")
            
            return ExecutionResult(
                True,
                message=f"文件已{action_text}：{file_path}",
                data={
                    "path": str(full_path),
                    "size": full_path.stat().st_size,
                }
            )
            
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"写入文件失败：{str(e)}")
    
    async def _file_delete(self, params: Dict[str, Any]) -> ExecutionResult:
        """删除文件"""
        file_path = params.get("file_path", "")
        confirmed = params.get("confirmed", False)
        
        # 安全验证（额外检查）
        is_valid, error = self.validator.validate_delete(file_path)
        if not is_valid:
            friendly = self._get_friendly_error("invalid_path", path=file_path, reason=error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        # 需要确认
        if not confirmed:
            return ExecutionResult(
                False,
                error="删除操作需要确认",
                data={"need_confirm": True, "file_path": file_path}
            )
        
        full_path = Path(self.validator.validate_path(file_path, ActionType.FILE_DELETE).sanitized_value)
        
        try:
            full_path.unlink()
            logger.info(f"文件已删除：{full_path}")
            
            return ExecutionResult(
                True,
                message=f"文件已删除：{file_path}"
            )
            
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except FileNotFoundError:
            friendly = self._get_friendly_error("file_not_found", path=file_path)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"删除文件失败：{str(e)}")
    
    async def _file_list(self, params: Dict[str, Any]) -> ExecutionResult:
        """列出文件"""
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        include_hidden = params.get("include_hidden", False)
        
        # 安全验证
        validation = self.validator.validate_path(directory, ActionType.FILE_LIST)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_path", path=directory, reason=validation.error)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        full_path = Path(validation.sanitized_value)
        
        # 检查目录是否存在
        if not full_path.exists():
            friendly = self._get_friendly_error("directory_not_found", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        if not full_path.is_dir():
            friendly = self._get_friendly_error("not_a_directory", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        try:
            files = []
            for item in full_path.glob(pattern):
                # 跳过隐藏文件
                if not include_hidden and item.name.startswith('.'):
                    continue
                
                try:
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "path": str(item.relative_to(self.config.working_dir)),
                        "is_dir": item.is_dir(),
                        "size": stat.st_size if item.is_file() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                except Exception:
                    continue
            
            # 排序：目录在前，然后按名称
            files.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            
            return ExecutionResult(
                True,
                message=f"找到 {len(files)} 个项目",
                data={
                    "directory": str(full_path.relative_to(self.config.working_dir)),
                    "count": len(files),
                    "files": files,
                }
            )
            
        except PermissionError:
            friendly = self._get_friendly_error("permission_denied", path=directory)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"列出文件失败：{str(e)}")
    
    # ==================== 应用操作 ====================
    
    async def _app_open(self, params: Dict[str, Any]) -> ExecutionResult:
        """打开应用"""
        app_name = params.get("app_name", "")
        
        # 安全验证（白名单）
        validation = self.validator.validate_app(app_name)
        if not validation.is_valid:
            friendly = self._get_friendly_error("app_not_allowed", app=app_name)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        executable = validation.sanitized_value
        
        try:
            if os.name == 'nt':  # Windows
                subprocess.Popen(
                    [executable],
                    shell=False,  # 安全：不使用 shell
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:  # macOS / Linux
                subprocess.Popen(
                    ['open', '-a', executable],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            
            logger.info(f"应用已打开：{app_name}")
            
            return ExecutionResult(
                True,
                message=f"应用已打开：{app_name}"
            )
            
        except FileNotFoundError:
            friendly = self._get_friendly_error("app_not_found", app=app_name)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        except Exception as e:
            return ExecutionResult(False, error=f"打开应用失败：{str(e)}")
    
    # ==================== 浏览器操作 ====================
    
    async def _url_open(self, params: Dict[str, Any]) -> ExecutionResult:
        """打开 URL"""
        url = params.get("url", "")
        
        # 安全验证
        validation = self.validator.validate_url(url)
        if not validation.is_valid:
            friendly = self._get_friendly_error("invalid_url", url=url)
            return ExecutionResult(False, error=friendly.message, data={"solutions": friendly.solutions})
        
        try:
            webbrowser.open(validation.sanitized_value)
            logger.info(f"URL 已打开：{url}")
            
            return ExecutionResult(
                True,
                message=f"网页已打开：{url}"
            )
            
        except Exception as e:
            return ExecutionResult(False, error=f"打开网页失败：{str(e)}")
