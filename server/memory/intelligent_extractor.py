"""
智能记忆提取�?结合规则提取和LLM辅助提取
"""
from typing import List, Dict, Tuple, Optional, Any
import re
from dataclasses import dataclass, field
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """提取结果"""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    extraction_method: str = "unknown"
    
    def is_empty(self) -> bool:
        return not self.entities and not self.relations and not self.facts
    
    def to_dict(self) -> Dict:
        return {
            'entities': self.entities,
            'relations': self.relations,
            'facts': self.facts,
            'confidence': self.confidence,
            'extraction_method': self.extraction_method
        }
    
    def merge(self, other: 'ExtractionResult') -> 'ExtractionResult':
        """合并两个提取结果"""
        merged = ExtractionResult()
        
        entity_keys = set()
        for e in self.entities + other.entities:
            key = (e.get('name', ''), e.get('type', ''))
            if key not in entity_keys:
                entity_keys.add(key)
                merged.entities.append(e)
        
        relation_keys = set()
        for r in self.relations + other.relations:
            key = (r.get('source', ''), r.get('target', ''), r.get('relation', ''))
            if key not in relation_keys:
                relation_keys.add(key)
                merged.relations.append(r)
        
        fact_contents = set()
        for f in self.facts + other.facts:
            content = f.get('content', '')
            if content not in fact_contents:
                fact_contents.add(content)
                merged.facts.append(f)
        
        merged.confidence = max(self.confidence, other.confidence)
        merged.extraction_method = f"{self.extraction_method}+{other.extraction_method}"
        
        return merged


class RuleBasedExtractor:
    """规则提取器（增强版）"""
    
    ENTITY_PATTERNS = {
        'person': [
            (r'我叫(\S+)', 'name'),
            (r'我是(\S+?)(?:，|。|！|,|\s|$)', 'identity'),
            (r'我的名字[是为](\S+)', 'name'),
            (r'我在?\s*(.+?)工作', 'workplace'),
            (r'我住[在是](\S+?)(?:，|。|�?', 'location'),
            (r'我的(\S+?)�?\S+)', 'attribute'),
            (r'�?\d+)�?, 'age'),
            (r'我是(\S+?)学生', 'student'),
            (r'我学(\S+)', 'major'),
        ],
        'project': [
            (r'我在�?\S+?)项目', 'name'),
            (r'我的项目[叫是为](\S+)', 'name'),
            (r'我在开�?\S+)', 'name'),
            (r'我在研究(\S+)', 'name'),
            (r'我在�?\S+?)代码', 'name'),
            (r'项目(\S+)', 'attribute'),
        ],
        'skill': [
            (r'我会(\S+)', 'name'),
            (r'我精�?\S+)', 'name'),
            (r'我熟�?\S+)', 'name'),
            (r'我掌�?\S+)', 'name'),
            (r'我正在学(\S+)', 'name'),
            (r'我学�?\S+)', 'name'),
        ],
        'tool': [
            (r'我用(\S+)', 'name'),
            (r'我使�?\S+)', 'name'),
            (r'我的(\S+?)工具', 'name'),
        ],
        'preference': [
            (r'我喜�?\S+)', 'value'),
            (r'我讨�?\S+)', 'value'),
            (r'我偏�?\S+)', 'value'),
            (r'我更(?:喜欢|倾向)(\S+)', 'value'),
            (r'我常�?\S+)', 'value'),
            (r'我不�?\S+)', 'value'),
        ],
        'habit': [
            (r'我习�?\S+)', 'description'),
            (r'我一�?\S+)', 'description'),
            (r'我通常(\S+)', 'description'),
            (r'我总是(\S+)', 'description'),
        ],
    }
    
    RELATION_PATTERNS = {
        'works_on': [
            (r'(\S+)在做(\S+)项目', ('subject', 'object')),
            (r'(\S+)开�?\S+)', ('subject', 'object')),
            (r'(\S+)研究(\S+)', ('subject', 'object')),
        ],
        'knows': [
            (r'(\S+)熟悉(\S+)', ('subject', 'object')),
            (r'(\S+)�?\S+)', ('subject', 'object')),
            (r'(\S+)精�?\S+)', ('subject', 'object')),
        ],
        'prefers': [
            (r'(\S+)喜欢(\S+)', ('subject', 'object')),
            (r'(\S+)偏好(\S+)', ('subject', 'object')),
            (r'(\S+)更倾向(\S+)', ('subject', 'object')),
        ],
        'uses': [
            (r'(\S+)�?\S+)', ('subject', 'object')),
            (r'(\S+)使用(\S+)', ('subject', 'object')),
        ],
        'has_skill': [
            (r'(\S+)�?\S+)', ('subject', 'object')),
            (r'(\S+)掌握(\S+)', ('subject', 'object')),
        ],
    }
    
    FACT_PATTERNS = {
        'preference': [
            r'我喜�?\S+)',
            r'我讨�?\S+)',
            r'我偏�?\S+)',
        ],
        'habit': [
            r'我习�?\S+)',
            r'我通常(\S+)',
            r'我总是(\S+)',
        ],
        'knowledge': [
            r'记住(.+)',
            r'别忘�?.+)',
            r'记得(.+)',
        ],
    }
    
    IMPORTANT_KEYWORDS = [
        '记住', '别忘�?, '记得', 'important',
        '我的', '我家', '我公�?, '我学�?, '我团�?,
        '注意', '提醒�?, '关键', '必须'
    ]
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """预编译正则表达式"""
        self.compiled_entity_patterns = {}
        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            self.compiled_entity_patterns[entity_type] = [
                (re.compile(p, re.IGNORECASE), attr_name)
                for p, attr_name in patterns
            ]
        
        self.compiled_relation_patterns = {}
        for relation_type, patterns in self.RELATION_PATTERNS.items():
            self.compiled_relation_patterns[relation_type] = [
                (re.compile(p, re.IGNORECASE), roles)
                for p, roles in patterns
            ]
        
        self.compiled_fact_patterns = {}
        for fact_type, patterns in self.FACT_PATTERNS.items():
            self.compiled_fact_patterns[fact_type] = [
                re.compile(p, re.IGNORECASE)
                for p in patterns
            ]
    
    def extract(self, message: str, role: str = 'user') -> ExtractionResult:
        """执行规则提取"""
        if role != 'user':
            return ExtractionResult(extraction_method='rule_skipped')
        
        entities = self._extract_entities(message)
        relations = self._extract_relations(message)
        facts = self._extract_facts(message)
        
        confidence = 0.0
        if entities:
            confidence += 0.4
        if relations:
            confidence += 0.3
        if facts:
            confidence += 0.3
        
        return ExtractionResult(
            entities=entities,
            relations=relations,
            facts=facts,
            confidence=min(1.0, confidence),
            extraction_method='rule'
        )
    
    def _extract_entities(self, message: str) -> List[Dict]:
        """提取实体"""
        entities = []
        seen = set()
        
        for entity_type, patterns in self.compiled_entity_patterns.items():
            for pattern, attr_name in patterns:
                try:
                    matches = pattern.finditer(message)
                    for match in matches:
                        name = match.group(1).strip()
                        
                        if len(name) < 2 or len(name) > 50:
                            continue
                        
                        key = (name, entity_type)
                        if key in seen:
                            continue
                        seen.add(key)
                        
                        entity = {
                            'name': name,
                            'type': entity_type,
                            'attributes': {},
                            'confidence': 0.9,
                            'source': 'rule',
                            'evidence': match.group(0)
                        }
                        
                        if len(match.groups()) > 1 and match.group(2):
                            entity['attributes'][attr_name] = match.group(2).strip()
                        else:
                            entity['attributes'][attr_name] = name
                        
                        entities.append(entity)
                        
                except Exception as e:
                    logger.warning(f"实体提取失败: {pattern.pattern}, {e}")
        
        return entities
    
    def _extract_relations(self, message: str) -> List[Dict]:
        """提取关系"""
        relations = []
        seen = set()
        
        for relation_type, patterns in self.compiled_relation_patterns.items():
            for pattern, roles in patterns:
                try:
                    matches = pattern.finditer(message)
                    for match in matches:
                        groups = match.groups()
                        if len(groups) < 2:
                            continue
                        
                        source = groups[0].strip() if roles[0] == 'subject' else groups[1].strip()
                        target = groups[1].strip() if roles[1] == 'object' else groups[0].strip()
                        
                        if len(source) < 2 or len(target) < 2:
                            continue
                        
                        key = (source, target, relation_type)
                        if key in seen:
                            continue
                        seen.add(key)
                        
                        relations.append({
                            'source': source,
                            'target': target,
                            'relation': relation_type,
                            'evidence': match.group(0),
                            'confidence': 0.85,
                            'source_method': 'rule'
                        })
                        
                except Exception as e:
                    logger.warning(f"关系提取失败: {pattern.pattern}, {e}")
        
        return relations
    
    def _extract_facts(self, message: str) -> List[Dict]:
        """提取事实"""
        facts = []
        seen = set()
        
        for fact_type, patterns in self.compiled_fact_patterns.items():
            for pattern in patterns:
                try:
                    matches = pattern.finditer(message)
                    for match in matches:
                        content = match.group(0).strip()
                        
                        if len(content) < 5 or len(content) > 200:
                            continue
                        
                        if content in seen:
                            continue
                        seen.add(content)
                        
                        facts.append({
                            'content': content,
                            'type': fact_type,
                            'confidence': 0.8,
                            'source': 'rule'
                        })
                        
                except Exception as e:
                    logger.warning(f"事实提取失败: {pattern.pattern}, {e}")
        
        if any(kw in message for kw in self.IMPORTANT_KEYWORDS):
            sentences = re.split(r'[。！�?!?]', message)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence or len(sentence) < 10 or len(sentence) > 100:
                    continue
                
                if any(kw in sentence for kw in self.IMPORTANT_KEYWORDS):
                    if sentence not in seen:
                        seen.add(sentence)
                        facts.append({
                            'content': sentence,
                            'type': 'important',
                            'confidence': 0.9,
                            'source': 'keyword'
                        })
        
        return facts


class LLMExtractor:
    """LLM辅助提取�?""
    
    EXTRACTION_PROMPT = """分析以下文本，提取实体、关系和事实�?
文本: {message}

请以严格的JSON格式返回，不要包含任何其他内�?
{{
  "entities": [
    {{"name": "实体�?, "type": "person/project/skill/tool/concept/preference/habit", "attributes": {{"key": "value"}}, "confidence": 0.9}}
  ],
  "relations": [
    {{"source": "实体A", "target": "实体B", "relation": "knows/works_on/uses/prefers/has_skill", "evidence": "原文依据", "confidence": 0.8}}
  ],
  "facts": [
    {{"content": "事实内容", "type": "preference/habit/knowledge/important", "confidence": 0.9}}
  ]
}}

注意�?1. 只提取明确提到的信息，不要推�?2. 实体类型必须是预定义类型之一
3. 关系类型必须是预定义类型之一
4. confidence 范围 0-1"""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
    
    def extract(self, message: str, context: Dict = None) -> ExtractionResult:
        """执行LLM提取"""
        if not self.llm_client:
            return ExtractionResult(extraction_method='llm_unavailable')
        
        try:
            prompt = self.EXTRACTION_PROMPT.format(message=message)
            
            response = self.llm_client.generate(prompt)
            
            result = self._parse_response(response)
            result.extraction_method = 'llm'
            
            return result
            
        except Exception as e:
            logger.error(f"LLM提取失败: {e}")
            return ExtractionResult(extraction_method='llm_failed')
    
    def _parse_response(self, response: str) -> ExtractionResult:
        """解析LLM响应"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return ExtractionResult(extraction_method='llm_parse_failed')
            
            data = json.loads(json_match.group())
            
            entities = []
            for e in data.get('entities', []):
                entities.append({
                    'name': e.get('name', ''),
                    'type': e.get('type', 'concept'),
                    'attributes': e.get('attributes', {}),
                    'confidence': e.get('confidence', 0.7),
                    'source': 'llm'
                })
            
            relations = []
            for r in data.get('relations', []):
                relations.append({
                    'source': r.get('source', ''),
                    'target': r.get('target', ''),
                    'relation': r.get('relation', 'related_to'),
                    'evidence': r.get('evidence', ''),
                    'confidence': r.get('confidence', 0.7),
                    'source_method': 'llm'
                })
            
            facts = []
            for f in data.get('facts', []):
                facts.append({
                    'content': f.get('content', ''),
                    'type': f.get('type', 'knowledge'),
                    'confidence': f.get('confidence', 0.7),
                    'source': 'llm'
                })
            
            return ExtractionResult(
                entities=entities,
                relations=relations,
                facts=facts,
                confidence=0.8,
                extraction_method='llm'
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")
            return ExtractionResult(extraction_method='llm_json_error')


class IntelligentMemoryExtractor:
    """智能记忆提取器（规则+LLM混合�?""
    
    COMPLEX_PATTERNS = ['因为', '所�?, '虽然', '但是', '如果', '那么', '不仅', '而且', '首先', '其次']
    
    def __init__(self, llm_client=None, use_llm: bool = True):
        self.rule_extractor = RuleBasedExtractor()
        self.llm_extractor = LLMExtractor(llm_client) if use_llm else None
        self.use_llm = use_llm and llm_client is not None
    
    def extract(
        self,
        message: str,
        role: str = 'user',
        context: Dict = None
    ) -> ExtractionResult:
        """
        执行智能提取
        
        Args:
            message: 消息内容
            role: 角色
            context: 上下文信�?            
        Returns:
            提取结果
        """
        rule_result = self.rule_extractor.extract(message, role)
        
        if not self.use_llm:
            return rule_result
        
        if self._should_use_llm(message, rule_result):
            llm_result = self.llm_extractor.extract(message, context)
            
            if not llm_result.is_empty():
                merged = rule_result.merge(llm_result)
                merged.extraction_method = 'rule+llm'
                return merged
        
        return rule_result
    
    def extract_from_conversation(
        self,
        messages: List[Dict[str, str]]
    ) -> ExtractionResult:
        """从对话历史中提取"""
        all_results = ExtractionResult()
        
        for msg in messages:
            if msg.get('role') == 'user':
                result = self.extract(
                    msg.get('content', ''),
                    'user'
                )
                all_results = all_results.merge(result)
        
        return all_results
    
    def _should_use_llm(self, message: str, rule_result: ExtractionResult) -> bool:
        """判断是否需要LLM提取"""
        if rule_result.confidence >= 0.8:
            return False
        
        if len(rule_result.entities) < 2 and len(rule_result.facts) < 1:
            return True
        
        if any(p in message for p in self.COMPLEX_PATTERNS):
            return True
        
        if len(message) > 200:
            return True
        
        return False


_memory_extractor: Optional[IntelligentMemoryExtractor] = None


def get_memory_extractor(llm_client=None) -> IntelligentMemoryExtractor:
    """获取记忆提取器实�?""
    global _memory_extractor
    if _memory_extractor is None:
        _memory_extractor = IntelligentMemoryExtractor(llm_client)
    return _memory_extractor


def extract_memories(
    message: str,
    role: str = 'user',
    llm_client=None
) -> ExtractionResult:
    """便捷函数：提取记�?""
    extractor = get_memory_extractor(llm_client)
    return extractor.extract(message, role)
