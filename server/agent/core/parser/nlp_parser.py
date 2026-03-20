import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..interfaces.base_parser import BaseParser
from ..types import ParseResult, IntentType
from .param_extractor import ParamExtractor, ParamType
from .multi_intent import MultiIntentParser, MultiIntentResult
from .context_aware import ContextAwareParser


class NLPParser(BaseParser):
    FILE_ACTIONS = {
        'create': ['创建', '新建', '生成', '建立', '弄', '搞', '写', '做', '建', '建个', '新建个'],
        'read': ['读取', '查看', '打开', '显示', '看看', '读一下', '看一下', '瞧瞧', '瞅瞅'],
        'write': ['写入', '修改', '更新', '编辑', '更改', '改', '保存', '存'],
        'delete': ['删除', '移除', '清除', '去掉', '删掉', '卸载', '清理'],
        'list': ['列出', '显示', '查看', 'ls', 'dir', '有哪些', '文件列表'],
        'copy': ['复制', '拷贝', 'copy'],
        'move': ['移动', '搬移', '转移', 'move'],
        'rename': ['重命名', '改名', '改名为', '改叫', 'rename'],
    }
    
    SYSTEM_ACTIONS = {
        'process_list': ['列出进程', '显示进程', '查看进程', '进程列表', 'ps'],
        'process_kill': ['结束进程', '杀死进程', '关闭进程', 'kill', '终止进程'],
        'service_start': ['启动服务', '开启服务', 'start service'],
        'service_stop': ['停止服务', '关闭服务', 'stop service'],
        'service_list': ['列出服务', '显示服务', '查看服务'],
    }
    
    APP_ACTIONS = {
        'open': ['打开', '启动', '运行', '开启', '执行'],
        'close': ['关闭', '退出', '结束', '终止'],
    }
    
    INTENT_PATTERNS = [
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_create',
            'patterns': [
                r'(?:创建|新建|生成|建立|弄|搞|写|做|建)\s*(?:一个)?(?:新)?(?:文件|文档|脚本)?',
                r'帮我(?:创建|新建|生成|建立)',
                r'要一个(?:新)?文件',
            ],
            'required_params': ['file_path'],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_read',
            'patterns': [
                r'(?:读取|查看|打开|显示|看看|读一下|看一下|瞧瞧|瞅瞅)\s*(?:一下)?(?:这个)?(?:文件|文档)?',
            ],
            'required_params': ['file_path'],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_write',
            'patterns': [
                r'(?:写入|修改|更新|编辑|更改|改|保存|存)\s*(?:一下)?',
                r'(?:把|将).*(?:写入|保存|改成|修改)',
                r'保存\s*(?:到|在)?\s*(?:桌面)?',
            ],
            'required_params': ['file_path'],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_delete',
            'patterns': [
                r'(?:删除|移除|清除|去掉|删掉|卸载|清理)\s*(?:这个)?(?:文件|文档)?',
            ],
            'required_params': ['file_path'],
            'priority': 1,
            'dangerous': True,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_list',
            'patterns': [
                r'(?:列出|显示|查看|ls|dir)\s*(?:一下)?(?:当前)?(?:目录|文件夹)?',
                r'有哪些文件',
                r'文件列表',
            ],
            'required_params': [],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_copy',
            'patterns': [
                r'(?:复制|拷贝|copy)\s*(?:这个)?(?:文件)?',
            ],
            'required_params': ['source', 'destination'],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_move',
            'patterns': [
                r'(?:移动|搬移|转移|move)\s*(?:这个)?(?:文件)?',
            ],
            'required_params': ['source', 'destination'],
            'priority': 1,
        },
        {
            'intent': IntentType.FILE_OPERATION,
            'action': 'file_rename',
            'patterns': [
                r'(?:重命名|改名|改名为|改叫|rename)\s*(?:这个)?(?:文件)?',
            ],
            'required_params': ['file_path', 'new_name'],
            'priority': 1,
        },
        {
            'intent': IntentType.APPLICATION,
            'action': 'app_open',
            'patterns': [
                r'(?:打开|启动|运行|开启)\s*\S+',
            ],
            'required_params': ['app_name'],
            'priority': 2,
        },
        {
            'intent': IntentType.APPLICATION,
            'action': 'app_close',
            'patterns': [
                r'(?:关闭|退出|结束|终止)\s*\S+(?:应用|程序|软件)?',
            ],
            'required_params': ['app_name'],
            'priority': 2,
        },
        {
            'intent': IntentType.SYSTEM_CONTROL,
            'action': 'process_list',
            'patterns': [
                r'(?:列出|显示|查看)?(?:当前)?(?:运行)?(?:的)?进程(?:列表)?',
                r'(?:ps|process\s*list)',
            ],
            'required_params': [],
            'priority': 3,
        },
        {
            'intent': IntentType.SYSTEM_CONTROL,
            'action': 'process_kill',
            'patterns': [
                r'(?:结束|杀死|关闭|终止)\s*(?:进程)?\s*\S+',
            ],
            'required_params': ['process_name'],
            'priority': 3,
            'dangerous': True,
        },
    ]
    
    def __init__(
        self,
        working_dir: Optional[Path] = None,
        confidence_threshold: float = 0.5
    ):
        self.working_dir = working_dir or Path.cwd()
        self.confidence_threshold = confidence_threshold
        self.param_extractor = ParamExtractor(working_dir)
        self.multi_intent_parser = MultiIntentParser()
        self.context_parser = ContextAwareParser(working_dir)
        self._compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> List[Dict]:
        compiled = []
        for pattern_def in self.INTENT_PATTERNS:
            compiled_patterns = [
                re.compile(p, re.IGNORECASE) for p in pattern_def['patterns']
            ]
            compiled.append({
                'intent': pattern_def['intent'],
                'action': pattern_def['action'],
                'patterns': compiled_patterns,
                'required_params': pattern_def.get('required_params', []),
                'priority': pattern_def.get('priority', 3),
                'dangerous': pattern_def.get('dangerous', False),
            })
        
        compiled.sort(key=lambda x: x['priority'])
        return compiled
    
    async def parse(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ParseResult:
        if not message or not message.strip():
            return ParseResult(
                intent=IntentType.UNKNOWN,
                action="",
                raw_message=message or "",
                confidence=0.0
            )
        
        message = message.strip()
        
        multi_result = self.multi_intent_parser.detect_multi_intent(message)
        if multi_result.has_multiple:
            return await self._parse_multi_intent(message, multi_result, context)
        
        result = self._parse_single(message)
        
        if context:
            result = self.context_parser.parse_with_context(message, result)
        
        return result
    
    async def _parse_multi_intent(
        self,
        message: str,
        multi_result: MultiIntentResult,
        context: Optional[Dict[str, Any]]
    ) -> ParseResult:
        intents = []
        for segment in multi_result.segments:
            segment_result = self._parse_single(segment)
            if context:
                segment_result = self.context_parser.parse_with_context(segment, segment_result)
            intents.append(segment_result)
        
        if len(intents) == 1:
            return intents[0]
        
        best_intent = max(intents, key=lambda x: x.confidence)
        
        all_params = {}
        for intent in intents:
            all_params.update(intent.params)
        
        return ParseResult(
            intent=best_intent.intent,
            action="multi_action",
            params=all_params,
            confidence=sum(i.confidence for i in intents) / len(intents),
            raw_message=message,
            alternatives=intents,
            metadata={
                "multi_intent": True,
                "intent_count": len(intents),
                "segments": multi_result.segments
            }
        )
    
    def _parse_single(self, message: str) -> ParseResult:
        candidates = []
        
        for pattern_def in self._compiled_patterns:
            for pattern in pattern_def['patterns']:
                match = pattern.search(message)
                if match:
                    confidence = self._calculate_confidence(message, match, pattern_def)
                    params = self._extract_params(message, match, pattern_def)
                    
                    candidates.append(ParseResult(
                        intent=pattern_def['intent'],
                        action=pattern_def['action'],
                        params=params,
                        confidence=confidence,
                        raw_message=message,
                        metadata={
                            'dangerous': pattern_def.get('dangerous', False),
                            'match_text': match.group(0)
                        }
                    ))
                    break
        
        if not candidates:
            return self._create_unknown_result(message)
        
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        best = candidates[0]
        
        if len(candidates) > 1:
            best.alternatives = candidates[1:3]
        
        return best
    
    def _calculate_confidence(
        self,
        message: str,
        match: re.Match,
        pattern_def: Dict
    ) -> float:
        base_confidence = 0.6
        
        match_coverage = len(match.group(0)) / len(message)
        base_confidence += match_coverage * 0.2
        
        required_params = pattern_def.get('required_params', [])
        if required_params:
            extracted_count = sum(
                1 for p in required_params
                if self._has_param_in_message(message, p)
            )
            param_score = extracted_count / len(required_params)
            base_confidence += param_score * 0.15
        
        if pattern_def.get('dangerous'):
            base_confidence *= 0.95
        
        return min(1.0, base_confidence)
    
    def _has_param_in_message(self, message: str, param_name: str) -> bool:
        param_patterns = {
            'file_path': [r'[\w\-./]+\.[a-zA-Z]{1,10}', r'[a-zA-Z]:\\'],
            'app_name': [r'(?:打开|启动|运行)\s*\S+'],
            'content': [r'[：:]\s*\S', r'内容'],
            'source': [r'(?:从|源)\s*\S+'],
            'destination': [r'(?:到|目标)\s*\S+'],
            'new_name': [r'(?:改名为|改叫)\s*\S+'],
            'process_name': [r'(?:进程)?\s*\S+'],
        }
        
        patterns = param_patterns.get(param_name, [])
        for pattern in patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def _extract_params(
        self,
        message: str,
        match: re.Match,
        pattern_def: Dict
    ) -> Dict[str, Any]:
        params = {}
        
        if match.groups():
            group_values = [g for g in match.groups() if g]
            if group_values:
                param_name = self._infer_param_name(pattern_def['action'], 0)
                params[param_name] = group_values[0]
        
        extracted = self.param_extractor.extract_all(message)
        
        param_mapping = {
            'path': 'file_path',
            'url': 'url',
            'number': 'count',
            'time': 'time',
            'app_name': 'app_name',
            'content': 'content',
            'command': 'command',
        }
        
        for extracted_type, param in extracted.items():
            mapped_name = param_mapping.get(extracted_type, extracted_type)
            if mapped_name not in params:
                params[mapped_name] = param.value
        
        if pattern_def['action'] in ['file_copy', 'file_move']:
            params = self._extract_source_destination(message, params)
        elif pattern_def['action'] == 'file_rename':
            params = self._extract_rename_params(message, params)
        
        return params
    
    def _infer_param_name(self, action: str, index: int) -> str:
        mapping = {
            'file_create': ['file_path', 'content'],
            'file_read': ['file_path'],
            'file_write': ['file_path', 'content'],
            'file_delete': ['file_path'],
            'file_list': ['directory'],
            'file_copy': ['source', 'destination'],
            'file_move': ['source', 'destination'],
            'file_rename': ['file_path', 'new_name'],
            'app_open': ['app_name'],
            'app_close': ['app_name'],
            'process_kill': ['process_name'],
        }
        
        names = mapping.get(action, [])
        return names[index] if index < len(names) else f'param_{index}'
    
    def _extract_source_destination(self, message: str, params: Dict[str, Any]) -> Dict[str, Any]:
        source_pattern = r'(?:从|源(?:文件)?)\s*["\']?([\w\-./\\]+)["\']?'
        dest_pattern = r'(?:到|目标(?:文件)?|目的地)\s*["\']?([\w\-./\\]+)["\']?'
        
        source_match = re.search(source_pattern, message, re.IGNORECASE)
        if source_match:
            params['source'] = source_match.group(1)
        
        dest_match = re.search(dest_pattern, message, re.IGNORECASE)
        if dest_match:
            params['destination'] = dest_match.group(1)
        
        return params
    
    def _extract_rename_params(self, message: str, params: Dict[str, Any]) -> Dict[str, Any]:
        rename_pattern = r'(?:改名为|改叫|重命名为)\s*["\']?([\w\-./]+)["\']?'
        
        rename_match = re.search(rename_pattern, message, re.IGNORECASE)
        if rename_match:
            params['new_name'] = rename_match.group(1)
        
        return params
    
    def _create_unknown_result(self, message: str) -> ParseResult:
        return ParseResult(
            intent=IntentType.UNKNOWN,
            action="",
            params={},
            confidence=0.0,
            raw_message=message,
            metadata={'error': 'No matching intent found'}
        )
    
    async def extract_params(self, message: str) -> Dict[str, Any]:
        extracted = self.param_extractor.extract_all(message)
        return {k: v.value for k, v in extracted.items()}
    
    async def detect_multi_intent(self, message: str) -> List[ParseResult]:
        multi_result = self.multi_intent_parser.detect_multi_intent(message)
        
        if not multi_result.has_multiple:
            result = await self.parse(message)
            return [result]
        
        results = []
        for segment in multi_result.segments:
            result = await self.parse(segment)
            results.append(result)
        
        return results
    
    def get_supported_intents(self) -> List[str]:
        return list(set(p['action'] for p in self.INTENT_PATTERNS))
    
    def get_confidence_threshold(self) -> float:
        return self.confidence_threshold
    
    def set_confidence_threshold(self, threshold: float):
        self.confidence_threshold = max(0.0, min(1.0, threshold))
    
    def update_context(
        self,
        action: str,
        params: Dict[str, Any],
        result: Optional[str] = None,
        success: bool = True
    ):
        self.context_parser.update_context(action, params, result, success)
    
    def set_working_directory(self, directory: Path):
        self.working_dir = directory
        self.param_extractor.working_dir = directory
        self.context_parser.set_working_directory(directory)
    
    def get_context_summary(self) -> Dict[str, Any]:
        return self.context_parser.get_context_summary()
    
    def clear_context(self):
        self.context_parser.clear_context()
