"""
记忆合并与更新器
处理记忆冲突、合并和更新
"""
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import difflib
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ConflictResolution(Enum):
    """冲突解决策略"""
    KEEP_RECENT = "keep_recent"
    KEEP_CONFIDENT = "keep_confident"
    KEEP_BOTH = "keep_both"
    ASK_USER = "ask_user"
    MERGE = "merge"


@dataclass
class ConflictInfo:
    """冲突信息"""
    conflict_type: str
    field: str
    existing_value: Any
    new_value: Any
    resolution: ConflictResolution
    message: str = ""


class MemoryMerger:
    """记忆合并�?""
    
    def __init__(
        self,
        similarity_threshold: float = 0.85,
        auto_resolve: bool = True
    ):
        self.similarity_threshold = similarity_threshold
        self.auto_resolve = auto_resolve
        self.pending_conflicts: List[Dict] = []
    
    def merge_memories(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Optional[ConflictInfo]]:
        """
        合并两条记忆
        
        Args:
            existing: 现有记忆
            new: 新记�?            
        Returns:
            (合并后的记忆, 冲突信息)
        """
        conflict = self.detect_contradiction(existing, new)
        
        if conflict:
            if self.auto_resolve:
                resolved = self._resolve_conflict(existing, new, conflict)
                return resolved, conflict
            else:
                self.pending_conflicts.append({
                    'existing': existing,
                    'new': new,
                    'conflict': conflict,
                    'timestamp': datetime.now().isoformat()
                })
                return existing, conflict
        
        if not self._should_merge(existing, new):
            return new, None
        
        merged = existing.copy()
        
        if 'attributes' in new:
            if 'attributes' not in merged:
                merged['attributes'] = {}
            merged['attributes'].update(new['attributes'])
        
        merged['updated_at'] = datetime.now().isoformat()
        
        if 'confidence' in existing and 'confidence' in new:
            merged['confidence'] = min(1.0, (existing['confidence'] + new['confidence']) / 2 + 0.05)
        elif 'confidence' in new:
            merged['confidence'] = new['confidence']
        
        if 'evidence' in new:
            if 'evidence' not in merged:
                merged['evidence'] = []
            if isinstance(merged['evidence'], str):
                merged['evidence'] = [merged['evidence']]
            if isinstance(new['evidence'], str):
                if new['evidence'] not in merged['evidence']:
                    merged['evidence'].append(new['evidence'])
            elif isinstance(new['evidence'], list):
                for e in new['evidence']:
                    if e not in merged['evidence']:
                        merged['evidence'].append(e)
        
        if 'source' in new:
            if 'source' not in merged:
                merged['source'] = new['source']
            elif merged['source'] != new['source']:
                if isinstance(merged['source'], list):
                    if new['source'] not in merged['source']:
                        merged['source'].append(new['source'])
                else:
                    merged['source'] = [merged['source'], new['source']]
        
        merged['access_count'] = existing.get('access_count', 0) + 1
        
        return merged, None
    
    def detect_contradiction(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any]
    ) -> Optional[ConflictInfo]:
        """检测矛�?""
        if existing.get('type') != new.get('type'):
            return ConflictInfo(
                conflict_type='type_conflict',
                field='type',
                existing_value=existing.get('type'),
                new_value=new.get('type'),
                resolution=ConflictResolution.ASK_USER,
                message=f"类型冲突: {existing.get('type')} vs {new.get('type')}"
            )
        
        for key in ['name', 'value', 'content']:
            if key in existing and key in new:
                if existing[key] != new[key]:
                    if self._is_similar(existing[key], new[key]):
                        continue
                    
                    return ConflictInfo(
                        conflict_type='value_conflict',
                        field=key,
                        existing_value=existing[key],
                        new_value=new[key],
                        resolution=ConflictResolution.KEEP_RECENT,
                        message=f"值冲�?({key}): {existing[key]} vs {new[key]}"
                    )
        
        if 'attributes' in existing and 'attributes' in new:
            for key in existing['attributes']:
                if key in new['attributes']:
                    if existing['attributes'][key] != new['attributes'][key]:
                        if not self._is_similar(existing['attributes'][key], new['attributes'][key]):
                            return ConflictInfo(
                                conflict_type='attribute_conflict',
                                field=f'attributes.{key}',
                                existing_value=existing['attributes'][key],
                                new_value=new['attributes'][key],
                                resolution=ConflictResolution.MERGE,
                                message=f"属性冲�?({key}): {existing['attributes'][key]} vs {new['attributes'][key]}"
                            )
        
        return None
    
    def batch_merge(
        self,
        memories: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[ConflictInfo]]:
        """
        批量合并记忆
        
        Args:
            memories: 记忆列表
            
        Returns:
            (合并后的记忆列表, 冲突列表)
        """
        if not memories:
            return [], []
        
        merged = [memories[0]]
        conflicts = []
        
        for new_mem in memories[1:]:
            merged_with_existing = False
            
            for i, existing in enumerate(merged):
                if self._should_merge(existing, new_mem):
                    result, conflict = self.merge_memories(existing, new_mem)
                    merged[i] = result
                    if conflict:
                        conflicts.append(conflict)
                    merged_with_existing = True
                    break
            
            if not merged_with_existing:
                merged.append(new_mem)
        
        return merged, conflicts
    
    def get_pending_conflicts(self) -> List[Dict]:
        """获取待解决的冲突"""
        return self.pending_conflicts.copy()
    
    def resolve_pending_conflict(
        self,
        conflict_id: int,
        resolution: ConflictResolution
    ) -> Optional[Dict]:
        """解决待处理的冲突"""
        if conflict_id >= len(self.pending_conflicts):
            return None
        
        conflict_data = self.pending_conflicts.pop(conflict_id)
        existing = conflict_data['existing']
        new = conflict_data['new']
        conflict = conflict_data['conflict']
        
        conflict.resolution = resolution
        resolved = self._resolve_conflict(existing, new, conflict)
        
        return resolved
    
    def clear_pending_conflicts(self):
        """清空待处理的冲突"""
        self.pending_conflicts.clear()
    
    def _should_merge(self, existing: Dict, new: Dict) -> bool:
        """判断是否应该合并"""
        if existing.get('id') == new.get('id'):
            return True
        
        if 'name' in existing and 'name' in new:
            if existing['name'] == new['name']:
                return True
            
            similarity = difflib.SequenceMatcher(
                None,
                str(existing['name']).lower(),
                str(new['name']).lower()
            ).ratio()
            
            if similarity > self.similarity_threshold:
                return True
        
        if 'content' in existing and 'content' in new:
            similarity = difflib.SequenceMatcher(
                None,
                str(existing['content']).lower(),
                str(new['content']).lower()
            ).ratio()
            
            if similarity > 0.95:
                return True
        
        return False
    
    def _is_similar(self, value1: Any, value2: Any) -> bool:
        """判断两个值是否相�?""
        if value1 == value2:
            return True
        
        str1 = str(value1).lower()
        str2 = str(value2).lower()
        
        if str1 == str2:
            return True
        
        similarity = difflib.SequenceMatcher(None, str1, str2).ratio()
        return similarity > 0.9
    
    def _resolve_conflict(
        self,
        existing: Dict,
        new: Dict,
        conflict: ConflictInfo
    ) -> Dict:
        """解决冲突"""
        resolution = conflict.resolution
        
        if resolution == ConflictResolution.KEEP_RECENT:
            existing_time = existing.get('updated_at') or existing.get('created_at')
            new_time = new.get('updated_at') or new.get('created_at')
            
            if new_time and existing_time:
                if new_time > existing_time:
                    return new
                return existing
            return new
        
        elif resolution == ConflictResolution.KEEP_CONFIDENT:
            if new.get('confidence', 0) > existing.get('confidence', 0):
                return new
            return existing
        
        elif resolution == ConflictResolution.KEEP_BOTH:
            merged = existing.copy()
            if 'alternatives' not in merged:
                merged['alternatives'] = []
            merged['alternatives'].append({
                'value': new.get(conflict.field),
                'source': new.get('source'),
                'confidence': new.get('confidence')
            })
            return merged
        
        elif resolution == ConflictResolution.MERGE:
            merged = existing.copy()
            if conflict.field.startswith('attributes.'):
                attr_key = conflict.field.split('.')[1]
                if 'attributes' not in merged:
                    merged['attributes'] = {}
                merged['attributes'][attr_key] = [
                    existing.get('attributes', {}).get(attr_key),
                    new.get('attributes', {}).get(attr_key)
                ]
            else:
                merged[conflict.field] = [existing.get(conflict.field), new.get(conflict.field)]
            return merged
        
        return existing


class MemoryUpdater:
    """记忆更新�?""
    
    def __init__(self, knowledge_graph=None, merger: MemoryMerger = None):
        self.kg = knowledge_graph
        self.merger = merger or MemoryMerger()
        self.update_history: List[Dict] = []
    
    def update_entity(
        self,
        entity_id: str,
        updates: Dict[str, Any]
    ) -> Tuple[Optional[Dict], Optional[ConflictInfo]]:
        """
        更新实体
        
        Args:
            entity_id: 实体ID
            updates: 更新内容
            
        Returns:
            (更新后的实体, 冲突信息)
        """
        if not self.kg:
            logger.warning("知识图谱未初始化")
            return None, None
        
        existing = self.kg.get_entity(entity_id)
        if not existing:
            logger.warning(f"实体不存�? {entity_id}")
            return None, None
        
        existing_dict = existing.to_dict() if hasattr(existing, 'to_dict') else existing
        
        merged, conflict = self.merger.merge_memories(existing_dict, updates)
        
        if conflict and conflict.resolution == ConflictResolution.ASK_USER:
            return existing_dict, conflict
        
        self.kg.update_entity(entity_id, merged)
        
        self._record_update('entity', entity_id, existing_dict, merged)
        
        return merged, conflict
    
    def update_relation(
        self,
        relation_id: str,
        updates: Dict[str, Any]
    ) -> Tuple[Optional[Dict], Optional[ConflictInfo]]:
        """更新关系"""
        if not self.kg:
            return None, None
        
        existing = self.kg.relations.get(relation_id)
        if not existing:
            return None, None
        
        existing_dict = existing.to_dict() if hasattr(existing, 'to_dict') else existing
        
        merged, conflict = self.merger.merge_memories(existing_dict, updates)
        
        if 'weight' in updates:
            merged['weight'] = min(1.0, max(0.0, updates['weight']))
        
        self._record_update('relation', relation_id, existing_dict, merged)
        
        return merged, conflict
    
    def increment_access_count(self, entity_id: str) -> int:
        """增加访问计数"""
        if not self.kg:
            return 0
        
        entity = self.kg.get_entity(entity_id)
        if entity:
            entity.access_count += 1
            entity.updated_at = datetime.now()
            return entity.access_count
        
        return 0
    
    def decay_importance(
        self,
        entity_id: str,
        decay_factor: float = 0.95
    ) -> float:
        """衰减重要�?""
        if not self.kg:
            return 0
        
        entity = self.kg.get_entity(entity_id)
        if entity:
            entity.confidence *= decay_factor
            entity.updated_at = datetime.now()
            return entity.confidence
        
        return 0
    
    def get_update_history(
        self,
        entity_id: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """获取更新历史"""
        if entity_id:
            return [
                h for h in self.update_history
                if h.get('entity_id') == entity_id
            ][-limit:]
        
        return self.update_history[-limit:]
    
    def _record_update(
        self,
        update_type: str,
        entity_id: str,
        before: Dict,
        after: Dict
    ):
        """记录更新"""
        self.update_history.append({
            'type': update_type,
            'entity_id': entity_id,
            'before': before,
            'after': after,
            'timestamp': datetime.now().isoformat()
        })
        
        if len(self.update_history) > 1000:
            self.update_history = self.update_history[-500:]


class MemoryDeduplicator:
    """记忆去重�?""
    
    def __init__(self, similarity_threshold: float = 0.9):
        self.similarity_threshold = similarity_threshold
    
    def deduplicate(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        去重记忆列表
        
        Args:
            memories: 记忆列表
            
        Returns:
            去重后的记忆列表
        """
        if not memories:
            return []
        
        unique = []
        seen_hashes = set()
        
        for mem in memories:
            mem_hash = self._compute_hash(mem)
            
            if mem_hash in seen_hashes:
                continue
            
            is_duplicate = False
            for existing in unique:
                if self._is_duplicate(mem, existing):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(mem)
                seen_hashes.add(mem_hash)
        
        return unique
    
    def find_duplicates(
        self,
        memories: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """查找重复的记忆组"""
        groups = []
        processed = set()
        
        for i, mem1 in enumerate(memories):
            if i in processed:
                continue
            
            duplicates = [mem1]
            
            for j, mem2 in enumerate(memories[i+1:], i+1):
                if j in processed:
                    continue
                
                if self._is_duplicate(mem1, mem2):
                    duplicates.append(mem2)
                    processed.add(j)
            
            if len(duplicates) > 1:
                groups.append(duplicates)
                processed.add(i)
        
        return groups
    
    def _compute_hash(self, memory: Dict) -> str:
        """计算记忆哈希"""
        key_fields = ['name', 'content', 'type']
        values = [str(memory.get(f, '')) for f in key_fields]
        return '|'.join(values)
    
    def _is_duplicate(self, mem1: Dict, mem2: Dict) -> bool:
        """判断两条记忆是否重复"""
        if mem1.get('id') and mem2.get('id') and mem1['id'] == mem2['id']:
            return True
        
        if mem1.get('name') and mem2.get('name'):
            if mem1['name'] == mem2['name'] and mem1.get('type') == mem2.get('type'):
                return True
        
        if mem1.get('content') and mem2.get('content'):
            similarity = difflib.SequenceMatcher(
                None,
                str(mem1['content']).lower(),
                str(mem2['content']).lower()
            ).ratio()
            
            if similarity > self.similarity_threshold:
                return True
        
        return False


_memory_merger: Optional[MemoryMerger] = None
_memory_updater: Optional[MemoryUpdater] = None


def get_memory_merger() -> MemoryMerger:
    """获取记忆合并器实�?""
    global _memory_merger
    if _memory_merger is None:
        _memory_merger = MemoryMerger()
    return _memory_merger


def get_memory_updater(knowledge_graph=None) -> MemoryUpdater:
    """获取记忆更新器实�?""
    global _memory_updater
    if _memory_updater is None:
        _memory_updater = MemoryUpdater(knowledge_graph)
    return _memory_updater
