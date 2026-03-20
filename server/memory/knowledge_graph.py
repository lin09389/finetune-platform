"""
知识图谱记忆系统
基于实体-关系网络的记忆管�?"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Any, Tuple
from datetime import datetime
from collections import defaultdict
import uuid
import json
import logging
import difflib

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """实体节点"""
    id: str
    name: str
    entity_type: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    source: str = "unknown"
    access_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'entity_type': self.entity_type,
            'attributes': self.attributes,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'confidence': self.confidence,
            'source': self.source,
            'access_count': self.access_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Entity':
        return cls(
            id=data['id'],
            name=data['name'],
            entity_type=data['entity_type'],
            attributes=data.get('attributes', {}),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            updated_at=datetime.fromisoformat(data['updated_at']) if isinstance(data.get('updated_at'), str) else data.get('updated_at', datetime.now()),
            confidence=data.get('confidence', 0.5),
            source=data.get('source', 'unknown'),
            access_count=data.get('access_count', 0)
        )


@dataclass
class Relation:
    """关系�?""
    id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    evidence: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.5
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type,
            'weight': self.weight,
            'evidence': self.evidence,
            'created_at': self.created_at.isoformat(),
            'confidence': self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Relation':
        return cls(
            id=data['id'],
            source_id=data['source_id'],
            target_id=data['target_id'],
            relation_type=data['relation_type'],
            weight=data.get('weight', 1.0),
            evidence=data.get('evidence', ''),
            created_at=datetime.fromisoformat(data['created_at']) if isinstance(data.get('created_at'), str) else data.get('created_at', datetime.now()),
            confidence=data.get('confidence', 0.5)
        )


class KnowledgeGraph:
    """知识图谱管理�?""
    
    ENTITY_TYPES = {
        'person': '人物',
        'project': '项目',
        'skill': '技�?,
        'concept': '概念',
        'tool': '工具',
        'organization': '组织',
        'location': '地点',
        'event': '事件',
        'preference': '偏好',
        'habit': '习惯'
    }
    
    RELATION_TYPES = {
        'knows': '知道',
        'works_on': '从事',
        'uses': '使用',
        'prefers': '偏好',
        'has_skill': '拥有技�?,
        'related_to': '相关',
        'part_of': '属于',
        'located_at': '位于',
        'happened_at': '发生�?,
        'causes': '导致'
    }
    
    def __init__(self, storage_backend: str = "memory"):
        self.storage_backend = storage_backend
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.entity_name_index: Dict[str, Set[str]] = defaultdict(set)
        self.entity_type_index: Dict[str, Set[str]] = defaultdict(set)
        self.relation_source_index: Dict[str, Set[str]] = defaultdict(set)
        self.relation_target_index: Dict[str, Set[str]] = defaultdict(set)
        self.relation_type_index: Dict[str, Set[str]] = defaultdict(set)
        
        logger.info(f"知识图谱初始化完成，存储后端: {storage_backend}")
    
    def add_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Dict[str, Any] = None,
        confidence: float = 0.5,
        source: str = "unknown"
    ) -> Tuple[str, bool]:
        """
        添加实体
        
        Args:
            name: 实体名称
            entity_type: 实体类型
            attributes: 属性字�?            confidence: 置信�?            source: 来源
            
        Returns:
            (entity_id, is_new) - 实体ID和是否新�?        """
        similar_entity = self.find_similar_entity(name, entity_type)
        
        if similar_entity and similar_entity.confidence >= 0.8:
            self._merge_entity_attributes(similar_entity, attributes or {})
            similar_entity.updated_at = datetime.now()
            similar_entity.confidence = min(1.0, similar_entity.confidence + 0.05)
            logger.debug(f"合并实体: {name} -> {similar_entity.id}")
            return similar_entity.id, False
        
        entity_id = f"ent_{uuid.uuid4().hex[:8]}"
        entity = Entity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            attributes=attributes or {},
            confidence=confidence,
            source=source
        )
        
        self.entities[entity_id] = entity
        self._index_entity(entity)
        
        logger.info(f"添加实体: {name} ({entity_type})")
        return entity_id, True
    
    def add_relation(
        self,
        source_name: str,
        target_name: str,
        relation_type: str,
        evidence: str = "",
        weight: float = 1.0,
        confidence: float = 0.5
    ) -> Optional[str]:
        """
        添加关系
        
        Args:
            source_name: 源实体名�?            target_name: 目标实体名称
            relation_type: 关系类型
            evidence: 证据文本
            weight: 关系权重
            confidence: 置信�?            
        Returns:
            关系ID，如果失败返回None
        """
        source_entity = self.find_entity_by_name(source_name)
        target_entity = self.find_entity_by_name(target_name)
        
        if not source_entity or not target_entity:
            logger.warning(f"无法添加关系: 实体不存�?({source_name} -> {target_name})")
            return None
        
        existing = self._find_relation(
            source_entity.id,
            target_entity.id,
            relation_type
        )
        
        if existing:
            existing.weight = (existing.weight + weight) / 2
            existing.confidence = min(1.0, existing.confidence + 0.1)
            if evidence:
                existing.evidence = evidence
            logger.debug(f"更新关系权重: {source_name} -[{relation_type}]-> {target_name}")
            return existing.id
        
        relation_id = f"rel_{uuid.uuid4().hex[:8]}"
        relation = Relation(
            id=relation_id,
            source_id=source_entity.id,
            target_id=target_entity.id,
            relation_type=relation_type,
            weight=weight,
            evidence=evidence,
            confidence=confidence
        )
        
        self.relations[relation_id] = relation
        self._index_relation(relation)
        
        logger.info(f"添加关系: {source_name} -[{relation_type}]-> {target_name}")
        return relation_id
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        entity = self.entities.get(entity_id)
        if entity:
            entity.access_count += 1
            entity.updated_at = datetime.now()
        return entity
    
    def get_entity_context(self, entity_id: str, depth: int = 2) -> Dict[str, Any]:
        """
        获取实体上下文（多跳关系遍历�?        
        Args:
            entity_id: 实体ID
            depth: 遍历深度
            
        Returns:
            包含实体、关系和关联实体的上下文字典
        """
        entity = self.entities.get(entity_id)
        if not entity:
            return {"error": "Entity not found"}
        
        context = {
            "entity": entity.to_dict(),
            "relations": [],
            "related_entities": [],
            "paths": []
        }
        
        visited_entities = {entity_id}
        visited_relations = set()
        queue = [(entity_id, 0)]
        
        while queue:
            current_id, current_depth = queue.pop(0)
            
            if current_depth >= depth:
                continue
            
            for rel_id in self.relation_source_index.get(current_id, []):
                if rel_id in visited_relations:
                    continue
                visited_relations.add(rel_id)
                
                rel = self.relations.get(rel_id)
                if not rel:
                    continue
                
                context["relations"].append(rel.to_dict())
                
                other_id = rel.target_id
                if other_id not in visited_entities:
                    visited_entities.add(other_id)
                    other_entity = self.entities.get(other_id)
                    if other_entity:
                        context["related_entities"].append(other_entity.to_dict())
                        queue.append((other_id, current_depth + 1))
            
            for rel_id in self.relation_target_index.get(current_id, []):
                if rel_id in visited_relations:
                    continue
                visited_relations.add(rel_id)
                
                rel = self.relations.get(rel_id)
                if not rel:
                    continue
                
                context["relations"].append(rel.to_dict())
                
                other_id = rel.source_id
                if other_id not in visited_entities:
                    visited_entities.add(other_id)
                    other_entity = self.entities.get(other_id)
                    if other_entity:
                        context["related_entities"].append(other_entity.to_dict())
                        queue.append((other_id, current_depth + 1))
        
        return context
    
    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 4
    ) -> List[List[Dict]]:
        """
        查找两个实体之间的所有路�?        
        Args:
            source_id: 源实体ID
            target_id: 目标实体ID
            max_depth: 最大搜索深�?            
        Returns:
            路径列表，每条路径是关系字典的列�?        """
        if source_id not in self.entities or target_id not in self.entities:
            return []
        
        paths = []
        queue = [(source_id, [], {source_id})]
        
        while queue:
            current_id, path, visited = queue.pop(0)
            
            if len(path) > max_depth:
                continue
            
            if current_id == target_id and path:
                paths.append(path)
                continue
            
            for rel_id in self.relation_source_index.get(current_id, []):
                rel = self.relations.get(rel_id)
                if not rel:
                    continue
                
                next_id = rel.target_id
                if next_id not in visited:
                    new_visited = visited | {next_id}
                    new_path = path + [rel.to_dict()]
                    queue.append((next_id, new_path, new_visited))
            
            for rel_id in self.relation_target_index.get(current_id, []):
                rel = self.relations.get(rel_id)
                if not rel:
                    continue
                
                next_id = rel.source_id
                if next_id not in visited:
                    new_visited = visited | {next_id}
                    reversed_rel = rel.to_dict()
                    reversed_rel['direction'] = 'incoming'
                    new_path = path + [reversed_rel]
                    queue.append((next_id, new_path, new_visited))
        
        return paths[:10]
    
    def find_entity_by_name(self, name: str, entity_type: str = None) -> Optional[Entity]:
        """按名称查找实�?""
        entity_ids = self.entity_name_index.get(name.lower())
        if not entity_ids:
            return None
        
        for eid in entity_ids:
            entity = self.entities.get(eid)
            if entity:
                if entity_type is None or entity.entity_type == entity_type:
                    return entity
        
        return None
    
    def find_similar_entity(
        self,
        name: str,
        entity_type: str,
        threshold: float = 0.85
    ) -> Optional[Entity]:
        """查找相似实体"""
        exact_match = self.find_entity_by_name(name, entity_type)
        if exact_match:
            return exact_match
        
        entity_ids = self.entity_type_index.get(entity_type)
        if not entity_ids:
            return None
        
        best_match = None
        best_score = threshold
        
        for eid in entity_ids:
            entity = self.entities.get(eid)
            if not entity:
                continue
            
            score = difflib.SequenceMatcher(
                None,
                name.lower(),
                entity.name.lower()
            ).ratio()
            
            if score > best_score:
                best_score = score
                best_match = entity
        
        return best_match
    
    def get_entities_by_type(self, entity_type: str) -> List[Entity]:
        """按类型获取实�?""
        entity_ids = self.entity_type_index.get(entity_type, set())
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]
    
    def get_relations_by_type(self, relation_type: str) -> List[Relation]:
        """按类型获取关�?""
        relation_ids = self.relation_type_index.get(relation_type, set())
        return [self.relations[rid] for rid in relation_ids if rid in self.relations]
    
    def get_all_entities(self) -> List[Entity]:
        """获取所有实�?""
        return list(self.entities.values())
    
    def get_all_relations(self) -> List[Relation]:
        """获取所有关�?""
        return list(self.relations.values())
    
    def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """更新实体"""
        entity = self.entities.get(entity_id)
        if not entity:
            return False
        
        if 'name' in updates and updates['name'] != entity.name:
            old_name = entity.name.lower()
            self.entity_name_index[old_name].discard(entity_id)
            entity.name = updates['name']
            self.entity_name_index[entity.name.lower()].add(entity_id)
        
        if 'attributes' in updates:
            entity.attributes.update(updates['attributes'])
        
        if 'confidence' in updates:
            entity.confidence = min(1.0, updates['confidence'])
        
        entity.updated_at = datetime.now()
        return True
    
    def delete_entity(self, entity_id: str) -> bool:
        """删除实体及其关系"""
        if entity_id not in self.entities:
            return False
        
        entity = self.entities[entity_id]
        
        self.entity_name_index[entity.name.lower()].discard(entity_id)
        self.entity_type_index[entity.entity_type].discard(entity_id)
        
        for rel_id in list(self.relation_source_index.get(entity_id, set())):
            self._delete_relation(rel_id)
        
        for rel_id in list(self.relation_target_index.get(entity_id, set())):
            self._delete_relation(rel_id)
        
        del self.entities[entity_id]
        
        logger.info(f"删除实体: {entity.name}")
        return True
    
    def clear(self):
        """清空图谱"""
        self.entities.clear()
        self.relations.clear()
        self.entity_name_index.clear()
        self.entity_type_index.clear()
        self.relation_source_index.clear()
        self.relation_target_index.clear()
        self.relation_type_index.clear()
        logger.info("知识图谱已清�?)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        entity_types = defaultdict(int)
        for entity in self.entities.values():
            entity_types[entity.entity_type] += 1
        
        relation_types = defaultdict(int)
        for relation in self.relations.values():
            relation_types[relation.relation_type] += 1
        
        return {
            'total_entities': len(self.entities),
            'total_relations': len(self.relations),
            'entity_types': dict(entity_types),
            'relation_types': dict(relation_types)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字�?""
        return {
            'entities': [e.to_dict() for e in self.entities.values()],
            'relations': [r.to_dict() for r in self.relations.values()]
        }
    
    def from_dict(self, data: Dict[str, Any]):
        """从字典导�?""
        self.clear()
        
        for entity_data in data.get('entities', []):
            entity = Entity.from_dict(entity_data)
            self.entities[entity.id] = entity
            self._index_entity(entity)
        
        for relation_data in data.get('relations', []):
            relation = Relation.from_dict(relation_data)
            self.relations[relation.id] = relation
            self._index_relation(relation)
        
        logger.info(f"导入图谱: {len(self.entities)} 实体, {len(self.relations)} 关系")
    
    def _index_entity(self, entity: Entity):
        """索引实体"""
        self.entity_name_index[entity.name.lower()].add(entity.id)
        self.entity_type_index[entity.entity_type].add(entity.id)
    
    def _index_relation(self, relation: Relation):
        """索引关系"""
        self.relation_source_index[relation.source_id].add(relation.id)
        self.relation_target_index[relation.target_id].add(relation.id)
        self.relation_type_index[relation.relation_type].add(relation.id)
    
    def _find_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str
    ) -> Optional[Relation]:
        """查找特定关系"""
        for rel_id in self.relation_source_index.get(source_id, set()):
            rel = self.relations.get(rel_id)
            if rel and rel.target_id == target_id and rel.relation_type == relation_type:
                return rel
        return None
    
    def _delete_relation(self, relation_id: str):
        """删除关系"""
        if relation_id not in self.relations:
            return
        
        rel = self.relations[relation_id]
        self.relation_source_index[rel.source_id].discard(relation_id)
        self.relation_target_index[rel.target_id].discard(relation_id)
        self.relation_type_index[rel.relation_type].discard(relation_id)
        del self.relations[relation_id]
    
    def _merge_entity_attributes(self, entity: Entity, new_attrs: Dict[str, Any]):
        """合并实体属�?""
        for key, value in new_attrs.items():
            if key not in entity.attributes:
                entity.attributes[key] = value
            elif isinstance(entity.attributes[key], list):
                if isinstance(value, list):
                    entity.attributes[key].extend(v for v in value if v not in entity.attributes[key])
                elif value not in entity.attributes[key]:
                    entity.attributes[key].append(value)
            elif entity.attributes[key] != value:
                entity.attributes[key] = [entity.attributes[key], value]


_knowledge_graph: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> KnowledgeGraph:
    """获取知识图谱实例"""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph


def reset_knowledge_graph() -> KnowledgeGraph:
    """重置知识图谱"""
    global _knowledge_graph
    _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph
