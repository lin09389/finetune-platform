"""
记忆合并与更新模块
处理记忆去重、合并、更新策略
"""
import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class MergeStrategy(str, Enum):
    """合并策略"""
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"
    KEEP_HIGHEST_CONFIDENCE = "keep_highest_confidence"
    MERGE_ATTRIBUTES = "merge_attributes"
    CREATE_NEW = "create_new"


class ConflictResolution(str, Enum):
    """冲突解决策略"""
    SOURCE_PRIORITY = "source_priority"
    RECENCY_PRIORITY = "recency_priority"
    CONFIDENCE_PRIORITY = "confidence_priority"
    MANUAL = "manual"


@dataclass
class MemoryConflict:
    """记忆冲突"""
    memory_id_1: str
    memory_id_2: str
    field: str
    value_1: Any
    value_2: Any
    confidence_1: float
    confidence_2: float
    resolution: str | None = None
    resolved_value: Any | None = None


@dataclass
class MergeResult:
    """合并结果"""
    success: bool
    merged_count: int = 0
    skipped_count: int = 0
    conflicts: list[MemoryConflict] = field(default_factory=list)
    merged_memories: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


class MemoryDeduplicator:
    """记忆去重器"""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        content_weight: float = 0.6,
        metadata_weight: float = 0.4
    ):
        self.similarity_threshold = similarity_threshold
        self.content_weight = content_weight
        self.metadata_weight = metadata_weight

    def find_duplicates(
        self,
        memories: list[dict[str, Any]]
    ) -> list[tuple[int, int, float]]:
        """
        查找重复记忆

        Args:
            memories: 记忆列表

        Returns:
            重复对列表 [(index1, index2, similarity), ...]
        """
        duplicates = []
        n = len(memories)

        for i in range(n):
            for j in range(i + 1, n):
                similarity = self._calculate_similarity(memories[i], memories[j])
                if similarity >= self.similarity_threshold:
                    duplicates.append((i, j, similarity))

        return duplicates

    def deduplicate(
        self,
        memories: list[dict[str, Any]],
        strategy: MergeStrategy = MergeStrategy.KEEP_HIGHEST_CONFIDENCE
    ) -> tuple[list[dict[str, Any]], int]:
        """
        去重

        Args:
            memories: 记忆列表
            strategy: 合并策略

        Returns:
            (去重后的列表, 移除的数量)
        """
        if not memories:
            return [], 0

        duplicates = self.find_duplicates(memories)

        to_remove: set[int] = set()

        for i, j, similarity in duplicates:
            if i in to_remove or j in to_remove:
                continue

            merged = self._select_memory(memories[i], memories[j], strategy)

            if merged == memories[i]:
                to_remove.add(j)
            else:
                to_remove.add(i)

        result = [m for idx, m in enumerate(memories) if idx not in to_remove]

        return result, len(to_remove)

    def _calculate_similarity(
        self,
        memory1: dict[str, Any],
        memory2: dict[str, Any]
    ) -> float:
        """计算两个记忆的相似度"""
        content1 = memory1.get('content', '')
        content2 = memory2.get('content', '')

        content_similarity = difflib.SequenceMatcher(
            None,
            content1.lower(),
            content2.lower()
        ).ratio()

        type1 = memory1.get('type', '')
        type2 = memory2.get('type', '')
        type_similarity = 1.0 if type1 == type2 else 0.0

        source1 = memory1.get('source', '')
        source2 = memory2.get('source', '')
        source_similarity = 1.0 if source1 == source2 else 0.0

        metadata_similarity = (type_similarity + source_similarity) / 2

        total_similarity = (
            self.content_weight * content_similarity +
            self.metadata_weight * metadata_similarity
        )

        return total_similarity

    def _select_memory(
        self,
        memory1: dict[str, Any],
        memory2: dict[str, Any],
        strategy: MergeStrategy
    ) -> dict[str, Any]:
        """根据策略选择记忆"""
        if strategy == MergeStrategy.KEEP_FIRST:
            return memory1
        elif strategy == MergeStrategy.KEEP_LAST:
            return memory2
        elif strategy == MergeStrategy.KEEP_HIGHEST_CONFIDENCE:
            conf1 = memory1.get('confidence', 0.5)
            conf2 = memory2.get('confidence', 0.5)
            return memory1 if conf1 >= conf2 else memory2
        elif strategy == MergeStrategy.MERGE_ATTRIBUTES:
            return self._merge_attributes(memory1, memory2)
        else:
            return memory1

    def _merge_attributes(
        self,
        memory1: dict[str, Any],
        memory2: dict[str, Any]
    ) -> dict[str, Any]:
        """合并两个记忆的属性"""
        merged = memory1.copy()

        for key, value in memory2.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key].update(value)
            elif isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = list(set(merged[key] + value))
            elif merged[key] != value:
                conf1 = memory1.get('confidence', 0.5)
                conf2 = memory2.get('confidence', 0.5)
                if conf2 > conf1:
                    merged[key] = value

        merged['confidence'] = max(
            memory1.get('confidence', 0.5),
            memory2.get('confidence', 0.5)
        )

        return merged


class MemoryUpdater:
    """记忆更新器"""

    SOURCE_PRIORITY = {
        'llm': 3,
        'rule': 2,
        'keyword': 1,
        'unknown': 0
    }

    def __init__(
        self,
        resolution_strategy: ConflictResolution = ConflictResolution.CONFIDENCE_PRIORITY
    ):
        self.resolution_strategy = resolution_strategy

    def update(
        self,
        existing: dict[str, Any],
        new_data: dict[str, Any]
    ) -> tuple[dict[str, Any], list[MemoryConflict]]:
        """
        更新记忆

        Args:
            existing: 现有记忆
            new_data: 新数据

        Returns:
            (更新后的记忆, 冲突列表)
        """
        conflicts = []
        updated = existing.copy()

        for key, new_value in new_data.items():
            if key not in existing:
                updated[key] = new_value
                continue

            old_value = existing[key]

            if old_value == new_value:
                continue

            conflict = MemoryConflict(
                memory_id_1=existing.get('id', ''),
                memory_id_2=new_data.get('id', ''),
                field=key,
                value_1=old_value,
                value_2=new_value,
                confidence_1=existing.get('confidence', 0.5),
                confidence_2=new_data.get('confidence', 0.5)
            )

            resolved_value = self._resolve_conflict(
                key,
                old_value,
                new_value,
                existing,
                new_data
            )

            conflict.resolution = self.resolution_strategy.value
            conflict.resolved_value = resolved_value
            conflicts.append(conflict)

            updated[key] = resolved_value

        if conflicts:
            updated['updated_at'] = datetime.now().isoformat()
            updated['update_count'] = existing.get('update_count', 0) + 1

        return updated, conflicts

    def batch_update(
        self,
        existing_memories: list[dict[str, Any]],
        new_memories: list[dict[str, Any]],
        match_field: str = 'content'
    ) -> MergeResult:
        """
        批量更新

        Args:
            existing_memories: 现有记忆列表
            new_memories: 新记忆列表
            match_field: 匹配字段

        Returns:
            合并结果
        """
        result = MergeResult(success=True)

        existing_index = {
            m.get(match_field, ''): m
            for m in existing_memories
            if match_field in m
        }

        updated_memories = list(existing_memories)

        for new_mem in new_memories:
            match_key = new_mem.get(match_field, '')

            if not match_key:
                updated_memories.append(new_mem)
                result.merged_count += 1
                continue

            if match_key in existing_index:
                existing = existing_index[match_key]
                updated, conflicts = self.update(existing, new_mem)

                for i, m in enumerate(updated_memories):
                    if m.get(match_field, '') == match_key:
                        updated_memories[i] = updated
                        break

                result.conflicts.extend(conflicts)
                result.merged_count += 1
            else:
                updated_memories.append(new_mem)
                result.merged_count += 1

        result.merged_memories = updated_memories
        result.message = f"合并完成: {result.merged_count} 条记忆, {len(result.conflicts)} 个冲突"

        return result

    def _resolve_conflict(
        self,
        field: str,
        old_value: Any,
        new_value: Any,
        old_memory: dict[str, Any],
        new_memory: dict[str, Any]
    ) -> Any:
        """解决冲突"""
        if self.resolution_strategy == ConflictResolution.CONFIDENCE_PRIORITY:
            old_conf = old_memory.get('confidence', 0.5)
            new_conf = new_memory.get('confidence', 0.5)
            return new_value if new_conf > old_conf else old_value

        elif self.resolution_strategy == ConflictResolution.SOURCE_PRIORITY:
            old_source = old_memory.get('source', 'unknown')
            new_source = new_memory.get('source', 'unknown')
            old_priority = self.SOURCE_PRIORITY.get(old_source, 0)
            new_priority = self.SOURCE_PRIORITY.get(new_source, 0)
            return new_value if new_priority > old_priority else old_value

        elif self.resolution_strategy == ConflictResolution.RECENCY_PRIORITY:
            old_time = old_memory.get('updated_at') or old_memory.get('created_at')
            new_time = new_memory.get('updated_at') or new_memory.get('created_at')

            if not old_time:
                return new_value
            if not new_time:
                return old_value

            try:
                old_dt = datetime.fromisoformat(old_time) if isinstance(old_time, str) else old_time
                new_dt = datetime.fromisoformat(new_time) if isinstance(new_time, str) else new_time
                return new_value if new_dt > old_dt else old_value
            except (ValueError, TypeError):
                return new_value

        else:
            return old_value


class MemoryMerger:
    """记忆合并器"""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        merge_strategy: MergeStrategy = MergeStrategy.KEEP_HIGHEST_CONFIDENCE,
        conflict_resolution: ConflictResolution = ConflictResolution.CONFIDENCE_PRIORITY
    ):
        self.deduplicator = MemoryDeduplicator(similarity_threshold)
        self.updater = MemoryUpdater(conflict_resolution)
        self.merge_strategy = merge_strategy

    def merge(
        self,
        existing_memories: list[dict[str, Any]],
        new_memories: list[dict[str, Any]]
    ) -> MergeResult:
        """
        合并记忆

        Args:
            existing_memories: 现有记忆
            new_memories: 新记忆

        Returns:
            合并结果
        """
        if not existing_memories:
            return MergeResult(
                success=True,
                merged_count=len(new_memories),
                merged_memories=new_memories,
                message="无现有记忆，直接添加新记忆"
            )

        if not new_memories:
            return MergeResult(
                success=True,
                merged_count=0,
                merged_memories=existing_memories,
                message="无新记忆需要合并"
            )

        update_result = self.updater.batch_update(
            existing_memories,
            new_memories,
            match_field='content'
        )

        deduplicated, removed = self.deduplicator.deduplicate(
            update_result.merged_memories,
            self.merge_strategy
        )

        result = MergeResult(
            success=True,
            merged_count=update_result.merged_count,
            skipped_count=removed,
            conflicts=update_result.conflicts,
            merged_memories=deduplicated,
            message=f"合并完成: {update_result.merged_count} 条, 去重 {removed} 条, 冲突 {len(update_result.conflicts)} 个"
        )

        logger.info(result.message)

        return result

    def merge_by_type(
        self,
        existing_memories: list[dict[str, Any]],
        new_memories: list[dict[str, Any]]
    ) -> dict[str, MergeResult]:
        """按类型合并记忆"""
        existing_by_type: dict[str, list[dict]] = {}
        for m in existing_memories:
            mem_type = m.get('type', 'unknown')
            if mem_type not in existing_by_type:
                existing_by_type[mem_type] = []
            existing_by_type[mem_type].append(m)

        new_by_type: dict[str, list[dict]] = {}
        for m in new_memories:
            mem_type = m.get('type', 'unknown')
            if mem_type not in new_by_type:
                new_by_type[mem_type] = []
            new_by_type[mem_type].append(m)

        results = {}
        all_types = set(existing_by_type.keys()) | set(new_by_type.keys())

        for mem_type in all_types:
            existing = existing_by_type.get(mem_type, [])
            new = new_by_type.get(mem_type, [])
            results[mem_type] = self.merge(existing, new)

        return results

    def smart_merge(
        self,
        existing_memories: list[dict[str, Any]],
        new_memories: list[dict[str, Any]],
        context: dict[str, Any] = None
    ) -> MergeResult:
        """
        智能合并

        根据上下文自动选择最佳合并策略
        """
        if context and context.get('high_confidence_mode'):
            self.merge_strategy = MergeStrategy.KEEP_HIGHEST_CONFIDENCE
        elif context and context.get('merge_all'):
            self.merge_strategy = MergeStrategy.MERGE_ATTRIBUTES
        else:
            self.merge_strategy = MergeStrategy.KEEP_HIGHEST_CONFIDENCE

        return self.merge(existing_memories, new_memories)


_memory_merger: MemoryMerger | None = None
_memory_updater: MemoryUpdater | None = None


def get_memory_merger() -> MemoryMerger:
    """获取记忆合并器实例"""
    global _memory_merger
    if _memory_merger is None:
        _memory_merger = MemoryMerger()
    return _memory_merger


def get_memory_updater() -> MemoryUpdater:
    """获取记忆更新器实例"""
    global _memory_updater
    if _memory_updater is None:
        _memory_updater = MemoryUpdater()
    return _memory_updater
