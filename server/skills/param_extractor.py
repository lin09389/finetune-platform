# -*- coding: utf-8 -*-
"""
参数自动提取器

使用规则引擎和 LLM 辅助从对话上下文中提取技能参数。
"""
import asyncio
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import SkillBase
from .models import (
    SkillMetadata,
    SkillParameter,
    SkillParameterType,
    SkillValidationResult,
)
from .enhanced_registry import EnhancedSkillRegistry, get_enhanced_registry


@dataclass
class ExtractionResult:
    """参数提取结果"""
    parameters: Dict[str, Any]
    confidence: float
    source: str
    missing_required: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExtractionContext:
    """提取上下文"""
    user_message: str
    skill_name: str
    skill_metadata: SkillMetadata
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    available_context: Dict[str, Any] = field(default_factory=dict)
    previous_params: Dict[str, Any] = field(default_factory=dict)


class RuleBasedExtractor:
    """基于规则的参数提取器"""

    def __init__(self):
        self._type_patterns = {
            SkillParameterType.STRING: [
                r'"([^"]+)"',
                r"'([^']+)'",
                r'「([^」]+)」',
                r'【([^】]+)】',
            ],
            SkillParameterType.INTEGER: [
                r'(\d+)',
                r'(-?\d+)',
            ],
            SkillParameterType.FLOAT: [
                r'(\d+\.\d+)',
                r'(\d+)',
            ],
            SkillParameterType.BOOLEAN: [
                r'(是|否|true|false|yes|no|真|假|开|关|启用|禁用)',
            ],
            SkillParameterType.FILE: [
                r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)',
                r'"([^"]+\.[a-zA-Z0-9]+)"',
                r"'([^']+\.[a-zA-Z0-9]+)'",
            ],
        }

        self._param_hints: Dict[str, Dict[str, List[str]]] = {
            "text": {
                "patterns": [r'(?:文本|内容|字符串)[是为]\s*["\']?([^"\']+)["\']?'],
                "keywords": ["文本", "内容", "字符串"],
            },
            "file_path": {
                "patterns": [r'(?:文件|路径)[是为]\s*["\']?([^"\']+)["\']?'],
                "keywords": ["文件", "路径"],
            },
            "operation": {
                "patterns": [r'(?:操作|动作)[是为]\s*(\w+)'],
                "keywords": ["操作", "动作"],
            },
            "content": {
                "patterns": [r'(?:内容)[是为]\s*["\']?([^"\']+)["\']?'],
                "keywords": ["内容"],
            },
            "directory": {
                "patterns": [r'(?:目录|文件夹)[是为]\s*["\']?([^"\']+)["\']?'],
                "keywords": ["目录", "文件夹"],
            },
        }

    def extract(
        self,
        context: ExtractionContext,
    ) -> ExtractionResult:
        """提取参数"""
        params = {}
        confidence_scores = []
        missing_required = []
        warnings = []
        suggestions = {}

        for param_def in context.skill_metadata.parameters:
            name = param_def.name
            value = None
            param_confidence = 0.0

            if name in context.previous_params:
                value = context.previous_params[name]
                param_confidence = 0.9

            if value is None and name in context.available_context:
                value = context.available_context[name]
                param_confidence = 0.8

            if value is None:
                value, param_confidence = self._extract_by_type(
                    context.user_message,
                    param_def,
                )

            if value is None:
                value, param_confidence = self._extract_by_hints(
                    context.user_message,
                    param_def,
                )

            if value is None:
                value, param_confidence = self._extract_from_history(
                    context.conversation_history,
                    param_def,
                )

            if value is not None:
                params[name] = value
                confidence_scores.append(param_confidence)
            else:
                if param_def.required and param_def.default is None:
                    missing_required.append(name)
                    if param_def.description:
                        suggestions[name] = param_def.description
                elif param_def.default is not None:
                    params[name] = param_def.default
                    confidence_scores.append(0.5)

        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores else 0.0
        )

        return ExtractionResult(
            parameters=params,
            confidence=overall_confidence,
            source="rule_based",
            missing_required=missing_required,
            warnings=warnings,
            suggestions=suggestions,
        )

    def _extract_by_type(
        self,
        message: str,
        param_def: SkillParameter,
    ) -> Tuple[Optional[Any], float]:
        """按类型提取"""
        patterns = self._type_patterns.get(param_def.type, [])

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                value = match.group(1)

                try:
                    if param_def.type == SkillParameterType.INTEGER:
                        value = int(value)
                    elif param_def.type == SkillParameterType.FLOAT:
                        value = float(value)
                    elif param_def.type == SkillParameterType.BOOLEAN:
                        value = self._parse_boolean(value)

                    if param_def.enum and value not in param_def.enum:
                        continue

                    return value, 0.7
                except (ValueError, TypeError):
                    continue

        return None, 0.0

    def _extract_by_hints(
        self,
        message: str,
        param_def: SkillParameter,
    ) -> Tuple[Optional[Any], float]:
        """按提示词提取"""
        hints = self._param_hints.get(param_def.name, {})
        patterns = hints.get("patterns", [])

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value, 0.6

        keywords = hints.get("keywords", [])
        for keyword in keywords:
            if keyword in message:
                parts = message.split(keyword)
                if len(parts) > 1:
                    potential_value = parts[1].strip()[:100]
                    potential_value = re.sub(r'[是为]\s*', '', potential_value, count=1)
                    potential_value = potential_value.split()[0] if potential_value.split() else potential_value
                    if potential_value:
                        return potential_value, 0.5

        return None, 0.0

    def _extract_from_history(
        self,
        history: List[Dict[str, str]],
        param_def: SkillParameter,
    ) -> Tuple[Optional[Any], float]:
        """从历史对话中提取"""
        for msg in reversed(history[-5:]):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                value, confidence = self._extract_by_type(content, param_def)
                if value is not None:
                    return value, confidence * 0.8

                value, confidence = self._extract_by_hints(content, param_def)
                if value is not None:
                    return value, confidence * 0.8

        return None, 0.0

    def _parse_boolean(self, value: str) -> bool:
        """解析布尔值"""
        true_values = {"是", "true", "yes", "真", "开", "启用", "1"}
        false_values = {"否", "false", "no", "假", "关", "禁用", "0"}

        value_lower = value.lower().strip()
        if value_lower in true_values:
            return True
        if value_lower in false_values:
            return False

        raise ValueError(f"无法解析布尔值: {value}")


class LLMParamExtractor:
    """LLM 辅助参数提取器"""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        model: str = "default",
    ):
        self.llm_client = llm_client
        self.model = model
        self._fallback_extractor = RuleBasedExtractor()

    def set_llm_client(self, client: Any):
        """设置 LLM 客户端"""
        self.llm_client = client

    async def extract(
        self,
        context: ExtractionContext,
    ) -> ExtractionResult:
        """使用 LLM 提取参数"""
        if self.llm_client is None:
            return self._fallback_extractor.extract(context)

        try:
            prompt = self._build_extraction_prompt(context)

            if hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.model,
                )
            elif hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(prompt)
            else:
                return self._fallback_extractor.extract(context)

            result = self._parse_llm_response(response, context)
            return result

        except Exception as e:
            fallback_result = self._fallback_extractor.extract(context)
            fallback_result.warnings.append(f"LLM 提取失败，使用规则提取: {str(e)}")
            return fallback_result

    def _build_extraction_prompt(self, context: ExtractionContext) -> str:
        """构建提取提示词"""
        param_descriptions = []
        for param in context.skill_metadata.parameters:
            desc = f"- {param.name} ({param.type.value})"
            if param.required:
                desc += " [必需]"
            if param.description:
                desc += f": {param.description}"
            if param.enum:
                desc += f" (可选值: {', '.join(map(str, param.enum))})"
            if param.default is not None:
                desc += f" (默认: {param.default})"
            param_descriptions.append(desc)

        history_text = ""
        if context.conversation_history:
            history_text = "\n对话历史:\n"
            for msg in context.conversation_history[-3:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_text += f"{role}: {content}\n"

        prompt = f"""请从用户消息中提取技能参数。

技能名称: {context.skill_name}
技能描述: {context.skill_metadata.description}

参数定义:
{chr(10).join(param_descriptions)}

用户消息: {context.user_message}
{history_text}

请以 JSON 格式返回提取的参数，格式如下:
{{
    "parameters": {{
        "参数名": "参数值"
    }},
    "confidence": 0.8,
    "missing_required": ["缺失的必需参数"],
    "suggestions": {{
        "参数名": "建议或说明"
    }}
}}

注意:
1. 只返回 JSON，不要添加其他内容
2. 如果无法确定参数值，不要猜测，放入 missing_required
3. confidence 表示整体提取置信度(0-1)
4. 对于枚举类型参数，确保值在允许范围内"""

        return prompt

    def _parse_llm_response(
        self,
        response: str,
        context: ExtractionContext,
    ) -> ExtractionResult:
        """解析 LLM 响应"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("未找到 JSON 响应")

            data = json.loads(json_match.group())

            params = data.get("parameters", {})
            confidence = data.get("confidence", 0.5)
            missing_required = data.get("missing_required", [])
            suggestions = data.get("suggestions", {})

            for param_def in context.skill_metadata.parameters:
                if param_def.name in params:
                    value = params[param_def.name]

                    if param_def.type == SkillParameterType.INTEGER:
                        value = int(value)
                    elif param_def.type == SkillParameterType.FLOAT:
                        value = float(value)
                    elif param_def.type == SkillParameterType.BOOLEAN:
                        if isinstance(value, str):
                            value = value.lower() in ("true", "yes", "是", "1")

                    if param_def.enum and value not in param_def.enum:
                        missing_required.append(param_def.name)
                        del params[param_def.name]
                    else:
                        params[param_def.name] = value

            return ExtractionResult(
                parameters=params,
                confidence=confidence,
                source="llm",
                missing_required=missing_required,
                suggestions=suggestions,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return self._fallback_extractor.extract(context)


class ParamExtractor:
    """参数提取器（主入口）"""

    _instance: Optional["ParamExtractor"] = None
    _lock: threading.RLock = threading.RLock()

    def __new__(cls) -> "ParamExtractor":
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
        self.registry = get_enhanced_registry()
        self.rule_extractor = RuleBasedExtractor()
        self.llm_extractor = LLMParamExtractor()
        self._extraction_cache: Dict[str, Tuple[ExtractionResult, float]] = {}
        self._cache_ttl = 300.0
        self._use_llm = True

    @classmethod
    def get_instance(cls) -> "ParamExtractor":
        """获取单例实例"""
        return cls()

    def set_llm_client(self, client: Any, model: str = "default"):
        """设置 LLM 客户端"""
        self.llm_extractor.set_llm_client(client)
        self.llm_extractor.model = model

    def enable_llm(self, enabled: bool = True):
        """启用/禁用 LLM 提取"""
        self._use_llm = enabled

    def extract(
        self,
        user_message: str,
        skill_name: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        available_context: Optional[Dict[str, Any]] = None,
        previous_params: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """同步提取参数"""
        metadata = self.registry.get_metadata(skill_name)
        if not metadata:
            return ExtractionResult(
                parameters={},
                confidence=0.0,
                source="error",
                missing_required=[],
                warnings=[f"技能不存在: {skill_name}"],
            )

        context = ExtractionContext(
            user_message=user_message,
            skill_name=skill_name,
            skill_metadata=metadata,
            conversation_history=conversation_history or [],
            available_context=available_context or {},
            previous_params=previous_params or {},
        )

        return self.rule_extractor.extract(context)

    async def extract_async(
        self,
        user_message: str,
        skill_name: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        available_context: Optional[Dict[str, Any]] = None,
        previous_params: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """异步提取参数（支持 LLM）"""
        metadata = self.registry.get_metadata(skill_name)
        if not metadata:
            return ExtractionResult(
                parameters={},
                confidence=0.0,
                source="error",
                missing_required=[],
                warnings=[f"技能不存在: {skill_name}"],
            )

        context = ExtractionContext(
            user_message=user_message,
            skill_name=skill_name,
            skill_metadata=metadata,
            conversation_history=conversation_history or [],
            available_context=available_context or {},
            previous_params=previous_params or {},
        )

        if self._use_llm and self.llm_extractor.llm_client:
            return await self.llm_extractor.extract(context)

        return self.rule_extractor.extract(context)

    def extract_for_multiple(
        self,
        user_message: str,
        skill_names: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        available_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ExtractionResult]:
        """为多个技能提取参数"""
        results = {}

        for skill_name in skill_names:
            results[skill_name] = self.extract(
                user_message=user_message,
                skill_name=skill_name,
                conversation_history=conversation_history,
                available_context=available_context,
            )

        return results

    def validate_and_normalize(
        self,
        skill_name: str,
        parameters: Dict[str, Any],
    ) -> SkillValidationResult:
        """验证并规范化参数"""
        skill = self.registry.get_skill(skill_name)
        if not skill:
            return SkillValidationResult(
                valid=False,
                errors=[f"技能不存在: {skill_name}"],
            )

        return skill.validate_parameters(parameters)

    def merge_params(
        self,
        base_params: Dict[str, Any],
        extracted_params: Dict[str, Any],
        override: bool = False,
    ) -> Dict[str, Any]:
        """合并参数"""
        if override:
            return {**base_params, **extracted_params}
        else:
            return {**extracted_params, **base_params}

    def get_param_suggestions(
        self,
        skill_name: str,
        missing_params: List[str],
    ) -> Dict[str, str]:
        """获取参数建议"""
        metadata = self.registry.get_metadata(skill_name)
        if not metadata:
            return {}

        suggestions = {}
        param_defs = {p.name: p for p in metadata.parameters}

        for param_name in missing_params:
            if param_name in param_defs:
                param_def = param_defs[param_name]
                suggestion = param_def.description or f"请提供 {param_name}"
                if param_def.example is not None:
                    suggestion += f" (示例: {param_def.example})"
                if param_def.enum:
                    suggestion += f" (可选值: {', '.join(map(str, param_def.enum))})"
                suggestions[param_name] = suggestion

        return suggestions

    def clear_cache(self):
        """清空缓存"""
        self._extraction_cache.clear()


def get_param_extractor() -> ParamExtractor:
    """获取参数提取器实例"""
    return ParamExtractor.get_instance()
