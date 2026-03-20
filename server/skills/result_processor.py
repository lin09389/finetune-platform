"""
结果处理�?
解析技能执行结果并整合为自然语言响应�?"""
import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .models import (
    SkillCategory,
    SkillExecution,
    SkillResult,
    SkillStatus,
)


class ResultType(str, Enum):
    """结果类型"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    EMPTY = "empty"
    COMPLEX = "complex"


class OutputFormat(str, Enum):
    """输出格式"""
    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


@dataclass
class ProcessedResult:
    """处理后的结果"""
    success: bool
    summary: str
    details: str
    result_type: ResultType
    output_format: OutputFormat
    data: Optional[Dict[str, Any]] = None
    suggestions: List[str] = field(default_factory=list)
    follow_up_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiResultSummary:
    """多结果摘�?""
    total_count: int
    success_count: int
    failed_count: int
    total_time: float
    summary_text: str
    results: List[ProcessedResult] = field(default_factory=list)


class ResultParser:
    """结果解析�?""
    
    def __init__(self):
        self._category_templates = {
            SkillCategory.FILE: {
                "success": "文件操作成功完成",
                "error": "文件操作失败",
                "prefix": "📁",
            },
            SkillCategory.CODE: {
                "success": "代码处理完成",
                "error": "代码处理失败",
                "prefix": "💻",
            },
            SkillCategory.DATA: {
                "success": "数据处理完成",
                "error": "数据处理失败",
                "prefix": "📊",
            },
            SkillCategory.AI: {
                "success": "AI 处理完成",
                "error": "AI 处理失败",
                "prefix": "🤖",
            },
            SkillCategory.SYSTEM: {
                "success": "系统操作完成",
                "error": "系统操作失败",
                "prefix": "⚙️",
            },
            SkillCategory.COMMUNICATION: {
                "success": "通信完成",
                "error": "通信失败",
                "prefix": "💬",
            },
            SkillCategory.CUSTOM: {
                "success": "操作完成",
                "error": "操作失败",
                "prefix": "🔧",
            },
        }
    
    def parse(self, execution: SkillExecution) -> ProcessedResult:
        """解析单个执行结果"""
        result = execution.result
        
        if result is None:
            return ProcessedResult(
                success=False,
                summary="执行结果为空",
                details="技能执行未返回任何结果",
                result_type=ResultType.EMPTY,
                output_format=OutputFormat.TEXT,
            )
        
        result_type = self._determine_result_type(result)
        output_format = self._determine_output_format(result)
        
        summary = self._generate_summary(execution, result)
        details = self._generate_details(result)
        
        suggestions = self._generate_suggestions(execution, result)
        follow_up = self._generate_follow_up(execution, result)
        
        return ProcessedResult(
            success=result.success,
            summary=summary,
            details=details,
            result_type=result_type,
            output_format=output_format,
            data=result.data if isinstance(result.data, dict) else {"value": result.data},
            suggestions=suggestions,
            follow_up_actions=follow_up,
            metadata={
                "execution_id": execution.execution_id,
                "skill_name": execution.skill_name,
                "execution_time": result.execution_time,
                "tokens_used": result.tokens_used,
            },
        )
    
    def _determine_result_type(self, result: SkillResult) -> ResultType:
        """确定结果类型"""
        if not result.success:
            return ResultType.ERROR
        
        if result.data is None:
            return ResultType.EMPTY
        
        if isinstance(result.data, dict):
            if len(result.data) > 5:
                return ResultType.COMPLEX
            return ResultType.SUCCESS
        
        if isinstance(result.data, (list, tuple)):
            if len(result.data) > 3:
                return ResultType.COMPLEX
            return ResultType.SUCCESS
        
        return ResultType.SUCCESS
    
    def _determine_output_format(self, result: SkillResult) -> OutputFormat:
        """确定输出格式"""
        if result.metadata and "format" in result.metadata:
            format_str = result.metadata["format"]
            try:
                return OutputFormat(format_str)
            except ValueError:
                pass
        
        if result.data:
            if isinstance(result.data, str):
                if "```" in result.data or "#" in result.data:
                    return OutputFormat.MARKDOWN
                return OutputFormat.TEXT
            
            if isinstance(result.data, (dict, list)):
                return OutputFormat.JSON
        
        return OutputFormat.TEXT
    
    def _generate_summary(
        self,
        execution: SkillExecution,
        result: SkillResult,
    ) -> str:
        """生成摘要"""
        if result.message:
            return result.message
        
        category = self._get_category_from_skill_name(execution.skill_name)
        template = self._category_templates.get(category, self._category_templates[SkillCategory.CUSTOM])
        
        if result.success:
            base = template["success"]
        else:
            base = template["error"]
        
        if result.error:
            return f"{base}: {result.error}"
        
        return base
    
    def _generate_details(self, result: SkillResult) -> str:
        """生成详细信息"""
        details_parts = []
        
        if result.data is not None:
            if isinstance(result.data, str):
                details_parts.append(result.data)
            elif isinstance(result.data, dict):
                for key, value in result.data.items():
                    if isinstance(value, (str, int, float, bool)):
                        details_parts.append(f"- **{key}**: {value}")
                    else:
                        details_parts.append(f"- **{key}**: {json.dumps(value, ensure_ascii=False)}")
            elif isinstance(result.data, (list, tuple)):
                for i, item in enumerate(result.data[:10], 1):
                    details_parts.append(f"{i}. {item}")
                if len(result.data) > 10:
                    details_parts.append(f"... 还有 {len(result.data) - 10} �?)
        
        if result.metadata:
            if "details" in result.metadata:
                details_parts.append(result.metadata["details"])
        
        return "\n".join(details_parts) if details_parts else "无详细信�?
    
    def _generate_suggestions(
        self,
        execution: SkillExecution,
        result: SkillResult,
    ) -> List[str]:
        """生成建议"""
        suggestions = []
        
        if not result.success:
            if result.error_code == "INVALID_PARAMETERS":
                suggestions.append("请检查输入参数是否正�?)
            elif result.error_code == "TIMEOUT":
                suggestions.append("操作超时，请稍后重试或简化任�?)
            elif result.error_code == "SKILL_NOT_FOUND":
                suggestions.append("技能不存在，请检查技能名�?)
            else:
                suggestions.append("请检查输入或稍后重试")
        
        if result.metadata and "suggestions" in result.metadata:
            suggestions.extend(result.metadata["suggestions"])
        
        return suggestions
    
    def _generate_follow_up(
        self,
        execution: SkillExecution,
        result: SkillResult,
    ) -> List[str]:
        """生成后续操作建议"""
        follow_up = []
        
        if result.success:
            category = self._get_category_from_skill_name(execution.skill_name)
            
            if category == SkillCategory.FILE:
                follow_up.append("查看文件内容")
                follow_up.append("编辑文件")
            elif category == SkillCategory.DATA:
                follow_up.append("导出数据")
                follow_up.append("可视化展�?)
            elif category == SkillCategory.CODE:
                follow_up.append("运行代码")
                follow_up.append("优化代码")
        
        return follow_up
    
    def _get_category_from_skill_name(self, skill_name: str) -> SkillCategory:
        """从技能名称推断类�?""
        if "file" in skill_name.lower():
            return SkillCategory.FILE
        if "code" in skill_name.lower():
            return SkillCategory.CODE
        if "text" in skill_name.lower() or "word" in skill_name.lower():
            return SkillCategory.DATA
        if "ai" in skill_name.lower():
            return SkillCategory.AI
        if "system" in skill_name.lower():
            return SkillCategory.SYSTEM
        return SkillCategory.CUSTOM


class NaturalLanguageGenerator:
    """自然语言生成�?""
    
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self._templates = {
            "single_success": "�?{skill_name} 执行成功！{message}",
            "single_error": "�?{skill_name} 执行失败: {error}",
            "multi_success": "�?成功执行 {count} 个技�?,
            "multi_partial": "⚠️ 部分执行成功: {success}/{total}",
            "multi_error": "�?所有技能执行失�?,
        }
    
    def set_llm_client(self, client: Any):
        """设置 LLM 客户�?""
        self.llm_client = client
    
    def generate_response(
        self,
        processed: ProcessedResult,
        user_message: str = "",
    ) -> str:
        """生成自然语言响应"""
        if processed.success:
            template = self._templates["single_success"]
            return template.format(
                skill_name=processed.metadata.get("skill_name", "技�?),
                message=processed.summary,
            )
        else:
            template = self._templates["single_error"]
            return template.format(
                skill_name=processed.metadata.get("skill_name", "技�?),
                error=processed.summary,
            )
    
    def generate_multi_response(
        self,
        summary: MultiResultSummary,
    ) -> str:
        """生成多结果响�?""
        if summary.failed_count == 0:
            template = self._templates["multi_success"]
            return template.format(count=summary.success_count)
        elif summary.success_count == 0:
            return self._templates["multi_error"]
        else:
            template = self._templates["multi_partial"]
            return template.format(
                success=summary.success_count,
                total=summary.total_count,
            )
    
    async def generate_with_llm(
        self,
        processed: ProcessedResult,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """使用 LLM 生成响应"""
        if self.llm_client is None:
            return self.generate_response(processed, user_message)
        
        prompt = self._build_llm_prompt(processed, user_message, context)
        
        try:
            if hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model="default",
                )
            elif hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                return self.generate_response(processed, user_message)
            
            return response
        except Exception:
            return self.generate_response(processed, user_message)
    
    def _build_llm_prompt(
        self,
        processed: ProcessedResult,
        user_message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建 LLM 提示�?""
        status = "成功" if processed.success else "失败"
        
        prompt = f"""请根据以下信息生成一个友好的自然语言响应�?
用户原始消息: {user_message}
技能执行状�? {status}
执行摘要: {processed.summary}
详细信息: {processed.details}

请生成一个简洁、友好的响应，告诉用户执行结果。如果执行失败，请解释原因并给出建议�?
响应:"""
        
        return prompt


class ResultProcessor:
    """结果处理器（主入口）"""
    
    _instance: Optional["ResultProcessor"] = None
    _lock: threading.RLock = threading.RLock()
    
    def __new__(cls) -> "ResultProcessor":
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
        self.parser = ResultParser()
        self.nl_generator = NaturalLanguageGenerator()
        self._result_cache: Dict[str, ProcessedResult] = {}
        self._on_result_processed: Optional[Callable[[ProcessedResult], None]] = None
    
    @classmethod
    def get_instance(cls) -> "ResultProcessor":
        """获取单例实例"""
        return cls()
    
    def set_llm_client(self, client: Any):
        """设置 LLM 客户�?""
        self.nl_generator.set_llm_client(client)
    
    def process(self, execution: SkillExecution) -> ProcessedResult:
        """处理单个执行结果"""
        processed = self.parser.parse(execution)
        
        self._result_cache[execution.execution_id] = processed
        
        if self._on_result_processed:
            self._on_result_processed(processed)
        
        return processed
    
    def process_multiple(
        self,
        executions: List[SkillExecution],
    ) -> MultiResultSummary:
        """处理多个执行结果"""
        processed_results = []
        success_count = 0
        failed_count = 0
        total_time = 0.0
        
        for execution in executions:
            processed = self.process(execution)
            processed_results.append(processed)
            
            if processed.success:
                success_count += 1
            else:
                failed_count += 1
            
            total_time += processed.metadata.get("execution_time", 0.0)
        
        summary_text = self.nl_generator.generate_multi_response(
            MultiResultSummary(
                total_count=len(executions),
                success_count=success_count,
                failed_count=failed_count,
                total_time=total_time,
                summary_text="",
            )
        )
        
        return MultiResultSummary(
            total_count=len(executions),
            success_count=success_count,
            failed_count=failed_count,
            total_time=total_time,
            summary_text=summary_text,
            results=processed_results,
        )
    
    def generate_response(
        self,
        processed: ProcessedResult,
        user_message: str = "",
        use_llm: bool = False,
    ) -> str:
        """生成自然语言响应"""
        if use_llm:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.nl_generator.generate_with_llm(processed, user_message)
                )
            finally:
                loop.close()
        
        return self.nl_generator.generate_response(processed, user_message)
    
    async def generate_response_async(
        self,
        processed: ProcessedResult,
        user_message: str = "",
        use_llm: bool = True,
    ) -> str:
        """异步生成自然语言响应"""
        if use_llm:
            return await self.nl_generator.generate_with_llm(processed, user_message)
        
        return self.nl_generator.generate_response(processed, user_message)
    
    def format_result(
        self,
        processed: ProcessedResult,
        format_type: OutputFormat = OutputFormat.MARKDOWN,
    ) -> str:
        """格式化结�?""
        if format_type == OutputFormat.JSON:
            return json.dumps({
                "success": processed.success,
                "summary": processed.summary,
                "details": processed.details,
                "data": processed.data,
                "suggestions": processed.suggestions,
            }, ensure_ascii=False, indent=2)
        
        if format_type == OutputFormat.MARKDOWN:
            lines = []
            
            status_icon = "�? if processed.success else "�?
            lines.append(f"## {status_icon} 执行结果")
            lines.append("")
            lines.append(f"**摘要**: {processed.summary}")
            lines.append("")
            
            if processed.details and processed.details != "无详细信�?:
                lines.append("**详细信息**:")
                lines.append(processed.details)
                lines.append("")
            
            if processed.suggestions:
                lines.append("**建议**:")
                for suggestion in processed.suggestions:
                    lines.append(f"- {suggestion}")
                lines.append("")
            
            if processed.follow_up_actions:
                lines.append("**后续操作**:")
                for action in processed.follow_up_actions:
                    lines.append(f"- {action}")
            
            return "\n".join(lines)
        
        return processed.summary
    
    def combine_results(
        self,
        results: List[ProcessedResult],
        strategy: str = "concat",
    ) -> ProcessedResult:
        """合并多个结果"""
        if not results:
            return ProcessedResult(
                success=True,
                summary="无结�?,
                details="",
                result_type=ResultType.EMPTY,
                output_format=OutputFormat.TEXT,
            )
        
        if len(results) == 1:
            return results[0]
        
        all_success = all(r.success for r in results)
        summaries = [r.summary for r in results if r.summary]
        details = [r.details for r in results if r.details != "无详细信�?]
        
        combined_data = {}
        for i, r in enumerate(results):
            skill_name = r.metadata.get("skill_name", f"skill_{i}")
            if r.data:
                combined_data[skill_name] = r.data
        
        all_suggestions = []
        for r in results:
            all_suggestions.extend(r.suggestions)
        
        return ProcessedResult(
            success=all_success,
            summary="; ".join(summaries[:3]),
            details="\n\n---\n\n".join(details),
            result_type=ResultType.COMPLEX,
            output_format=OutputFormat.MARKDOWN,
            data=combined_data,
            suggestions=list(set(all_suggestions)),
            metadata={
                "combined_count": len(results),
            },
        )
    
    def get_cached_result(self, execution_id: str) -> Optional[ProcessedResult]:
        """获取缓存的结�?""
        return self._result_cache.get(execution_id)
    
    def clear_cache(self):
        """清空缓存"""
        self._result_cache.clear()
    
    def set_on_result_processed(self, callback: Callable[[ProcessedResult], None]):
        """设置结果处理回调"""
        self._on_result_processed = callback


def get_result_processor() -> ResultProcessor:
    """获取结果处理器实�?""
    return ResultProcessor.get_instance()
