import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..types import IntentType, ParseResult
from .param_extractor import ParamExtractor


@dataclass
class OperationHistory:
    action: str
    params: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    result: str | None = None
    success: bool = True


@dataclass
class ConversationContext:
    last_intent: IntentType | None = None
    last_action: str | None = None
    last_params: dict[str, Any] = field(default_factory=dict)
    last_file: str | None = None
    last_app: str | None = None
    last_directory: str | None = None
    operation_history: list[OperationHistory] = field(default_factory=list)
    mentioned_files: list[str] = field(default_factory=list)
    mentioned_apps: list[str] = field(default_factory=list)


class ContextAwareParser:
    PRONOUN_PATTERNS = {
        'file': [
            (r'它\b', 0.85),
            (r'这个文件\b', 0.95),
            (r'那个文件\b', 0.90),
            (r'该文件\b', 0.95),
            (r'刚才的文件\b', 0.95),
            (r'刚才那个\b', 0.80),
            (r'这个\b', 0.70),
            (r'那个\b', 0.65),
        ],
        'app': [
            (r'它\b', 0.80),
            (r'这个程序\b', 0.95),
            (r'那个程序\b', 0.90),
            (r'这个应用\b', 0.95),
            (r'那个应用\b', 0.90),
        ],
        'directory': [
            (r'这个目录\b', 0.95),
            (r'那个目录\b', 0.90),
            (r'当前目录\b', 0.95),
            (r'这里\b', 0.70),
            (r'那里\b', 0.65),
        ],
        'content': [
            (r'刚才的内容\b', 0.95),
            (r'那个内容\b', 0.85),
            (r'这些内容\b', 0.90),
        ],
        'operation': [
            (r'刚才的操作\b', 0.95),
            (r'上次的操作\b', 0.95),
            (r'之前的操作\b', 0.90),
            (r'刚才做的\b', 0.85),
        ],
    }

    REFERENCE_PATTERNS = [
        (r'刚才(创建|新建|生成|建立)的', 'last_created'),
        (r'刚才(读取|查看|打开)的', 'last_read'),
        (r'刚才(修改|更新|写入)的', 'last_modified'),
        (r'刚才(删除|移除)的', 'last_deleted'),
        (r'上次(创建|新建|生成|建立)的', 'last_created'),
        (r'上次(读取|查看|打开)的', 'last_read'),
        (r'最近(创建|新建|生成|建立)的', 'recent_created'),
        (r'最近(修改|更新|写入)的', 'recent_modified'),
    ]

    def __init__(
        self,
        working_dir: Path | None = None,
        max_history: int = 20
    ):
        self.working_dir = working_dir or Path.cwd()
        self.max_history = max_history
        self.context = ConversationContext()
        self.param_extractor = ParamExtractor(working_dir)
        self._compiled_pronouns = self._compile_pronoun_patterns()
        self._compiled_references = [
            (re.compile(p), t) for p, t in self.REFERENCE_PATTERNS
        ]

    def _compile_pronoun_patterns(self) -> dict[str, list[tuple]]:
        compiled = {}
        for ref_type, patterns in self.PRONOUN_PATTERNS.items():
            compiled[ref_type] = [
                (re.compile(p), c) for p, c in patterns
            ]
        return compiled

    def parse_with_context(
        self,
        message: str,
        initial_result: ParseResult
    ) -> ParseResult:
        resolved_message = self._resolve_pronouns(message)

        resolved_params = self._resolve_params(initial_result.params, message)

        inferred_params = self._infer_missing_params(
            initial_result.action,
            resolved_params,
            message
        )

        resolved_params.update(inferred_params)

        return ParseResult(
            intent=initial_result.intent,
            action=initial_result.action,
            params=resolved_params,
            confidence=self._adjust_confidence(initial_result.confidence, resolved_params),
            raw_message=initial_result.raw_message,
            alternatives=initial_result.alternatives,
            metadata={
                **initial_result.metadata,
                "context_resolved": True,
                "pronouns_resolved": resolved_message != message
            }
        )

    def _resolve_pronouns(self, message: str) -> str:
        resolved = message

        for ref_type, patterns in self._compiled_pronouns.items():
            for pattern, confidence in patterns:
                if pattern.search(resolved):
                    replacement = self._get_context_replacement(ref_type)
                    if replacement:
                        resolved = pattern.sub(replacement, resolved, count=1)
                        break

        return resolved

    def _get_context_replacement(self, ref_type: str) -> str | None:
        if ref_type == 'file':
            return self.context.last_file
        elif ref_type == 'app':
            return self.context.last_app
        elif ref_type == 'directory':
            return self.context.last_directory or str(self.working_dir)
        elif ref_type == 'content':
            return self.context.last_params.get('content')
        elif ref_type == 'operation':
            return self.context.last_action
        return None

    def _resolve_params(
        self,
        params: dict[str, Any],
        message: str
    ) -> dict[str, Any]:
        resolved = dict(params)

        for pattern, ref_type in self._compiled_references:
            if pattern.search(message):
                context_value = self._get_reference_value(ref_type)
                if context_value:
                    if 'file_path' not in resolved and ref_type in ['last_created', 'last_read', 'last_modified']:
                        resolved['file_path'] = context_value
                    elif 'content' not in resolved and ref_type == 'last_modified':
                        resolved['content'] = context_value

        if 'file_path' not in resolved:
            file_ref = self._detect_file_reference(message)
            if file_ref:
                resolved['file_path'] = file_ref

        if 'app_name' not in resolved:
            app_ref = self._detect_app_reference(message)
            if app_ref:
                resolved['app_name'] = app_ref

        return resolved

    def _get_reference_value(self, ref_type: str) -> str | None:
        if ref_type == 'last_created':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_create', 'create']:
                    return op.params.get('file_path')
        elif ref_type == 'last_read':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_read', 'read']:
                    return op.params.get('file_path')
        elif ref_type == 'last_modified':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_write', 'write', 'modify']:
                    return op.params.get('file_path')
        elif ref_type == 'last_deleted':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_delete', 'delete']:
                    return op.params.get('file_path')
        elif ref_type == 'recent_created':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_create', 'create']:
                    return op.params.get('file_path')
        elif ref_type == 'recent_modified':
            for op in reversed(self.context.operation_history):
                if op.action in ['file_write', 'write', 'modify']:
                    return op.params.get('file_path')
        return None

    def _detect_file_reference(self, message: str) -> str | None:
        if self.context.last_file:
            file_patterns = [
                r'它\b',
                r'这个\b',
                r'那个\b',
                r'该文件\b',
            ]
            for pattern in file_patterns:
                if re.search(pattern, message):
                    return self.context.last_file

        return None

    def _detect_app_reference(self, message: str) -> str | None:
        if self.context.last_app:
            app_patterns = [
                r'它\b',
                r'这个程序\b',
                r'那个程序\b',
            ]
            for pattern in app_patterns:
                if re.search(pattern, message):
                    return self.context.last_app

        return None

    def _infer_missing_params(
        self,
        action: str,
        params: dict[str, Any],
        message: str
    ) -> dict[str, Any]:
        inferred = {}

        required_params = self._get_required_params(action)

        for param in required_params:
            if param not in params or not params[param]:
                inferred_value = self._infer_param(param, message)
                if inferred_value:
                    inferred[param] = inferred_value

        return inferred

    def _get_required_params(self, action: str) -> list[str]:
        requirements = {
            'file_create': ['file_path'],
            'file_read': ['file_path'],
            'file_write': ['file_path', 'content'],
            'file_delete': ['file_path'],
            'file_list': [],
            'file_copy': ['source', 'destination'],
            'file_move': ['source', 'destination'],
            'file_rename': ['file_path', 'new_name'],
            'app_open': ['app_name'],
            'app_close': ['app_name'],
        }
        return requirements.get(action, [])

    def _infer_param(self, param: str, message: str) -> Any | None:
        if param == 'file_path':
            if self.context.last_file:
                return self.context.last_file
            if self.context.mentioned_files:
                return self.context.mentioned_files[-1]

        elif param == 'content':
            if self.context.last_params.get('content'):
                return self.context.last_params['content']

        elif param == 'app_name':
            if self.context.last_app:
                return self.context.last_app
            if self.context.mentioned_apps:
                return self.context.mentioned_apps[-1]

        elif param == 'directory':
            if self.context.last_directory:
                return self.context.last_directory
            return str(self.working_dir)

        elif param == 'source':
            if self.context.last_file:
                return self.context.last_file

        return None

    def _adjust_confidence(
        self,
        base_confidence: float,
        resolved_params: dict[str, Any]
    ) -> float:
        adjustment = 0.0

        if resolved_params:
            filled_ratio = len([v for v in resolved_params.values() if v]) / max(len(resolved_params), 1)
            adjustment += filled_ratio * 0.1

        if base_confidence < 0.5 and resolved_params:
            adjustment += 0.15

        return min(1.0, base_confidence + adjustment)

    def update_context(
        self,
        action: str,
        params: dict[str, Any],
        result: str | None = None,
        success: bool = True
    ):
        self.context.last_action = action
        self.context.last_params = dict(params)

        if 'file_path' in params:
            self.context.last_file = params['file_path']
            if params['file_path'] not in self.context.mentioned_files:
                self.context.mentioned_files.append(params['file_path'])
                if len(self.context.mentioned_files) > self.max_history:
                    self.context.mentioned_files.pop(0)

        if 'app_name' in params:
            self.context.last_app = params['app_name']
            if params['app_name'] not in self.context.mentioned_apps:
                self.context.mentioned_apps.append(params['app_name'])
                if len(self.context.mentioned_apps) > self.max_history:
                    self.context.mentioned_apps.pop(0)

        if 'directory' in params:
            self.context.last_directory = params['directory']

        operation = OperationHistory(
            action=action,
            params=dict(params),
            result=result,
            success=success
        )
        self.context.operation_history.append(operation)

        if len(self.context.operation_history) > self.max_history:
            self.context.operation_history.pop(0)

    def set_working_directory(self, directory: Path):
        self.working_dir = directory
        self.context.last_directory = str(directory)
        self.param_extractor.working_dir = directory

    def get_context_summary(self) -> dict[str, Any]:
        return {
            'last_file': self.context.last_file,
            'last_app': self.context.last_app,
            'last_directory': self.context.last_directory,
            'last_action': self.context.last_action,
            'recent_files': self.context.mentioned_files[-5:],
            'recent_apps': self.context.mentioned_apps[-5:],
            'recent_operations': [
                {
                    'action': op.action,
                    'params': op.params,
                    'success': op.success
                }
                for op in self.context.operation_history[-5:]
            ]
        }

    def clear_context(self):
        self.context = ConversationContext()

    def resolve_relative_path(self, path: str) -> str:
        if Path(path).is_absolute():
            return path
        return str((self.working_dir / path).resolve())
