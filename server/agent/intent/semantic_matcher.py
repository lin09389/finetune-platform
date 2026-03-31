"""
语义匹配模块
基于语义相似度的意图匹配
支持实例复用和懒加载
"""
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SemanticMatchResult:
    """语义匹配结果"""
    intent_name: str
    similarity: float
    matched_samples: list[str]
    confidence: float


class SemanticMatcher:
    """
    语义匹配器
    
    支持实例复用和懒加载初始化
    """

    _instance: Optional['SemanticMatcher'] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, use_embedding: bool = True):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._use_embedding = use_embedding
                    cls._instance._embedder = None
                    cls._instance._intent_vectors = defaultdict(list)
                    cls._instance._sample_texts = defaultdict(list)
                    cls._instance._local_initialized = False
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'SemanticMatcher':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False

    def initialize(self):
        """初始化嵌入模型（懒加载）"""
        if self._local_initialized:
            return

        with self._lock:
            if self._local_initialized:
                return

            if self._use_embedding:
                try:
                    from rag.embedder import get_embedder
                    self._embedder = get_embedder()
                    logger.info("语义匹配器已初始化嵌入模型")
                except Exception as e:
                    logger.warning(f"嵌入模型加载失败，使用关键词匹配: {e}")
                    self._use_embedding = False

            self._local_initialized = True
            SemanticMatcher._initialized = True

    def warmup(self, intent_samples: dict[str, list[str]] = None):
        """
        预热模型
        
        Args:
            intent_samples: 意图样本，用于预计算向量
        """
        self.initialize()

        if intent_samples and self._use_embedding and self._embedder:
            for intent_name, samples in intent_samples.items():
                self._sample_texts[intent_name] = samples
                for sample in samples:
                    try:
                        vector = self._embedder.embed(sample)
                        self._intent_vectors[intent_name].append(vector)
                    except Exception as e:
                        logger.debug(f"样本向量化失败: {sample[:30]}... - {e}")

            logger.info(f"语义匹配器预热完成，共 {sum(len(v) for v in self._intent_vectors.values())} 个向量")

    def load_intent_samples(self, intent_samples: dict[str, list[str]]):
        """加载意图样本"""
        self._sample_texts = defaultdict(list)
        for intent_name, samples in intent_samples.items():
            self._sample_texts[intent_name] = samples

        if self._use_embedding and self._embedder:
            self._intent_vectors = defaultdict(list)
            for intent_name, samples in intent_samples.items():
                for sample in samples:
                    try:
                        vector = self._embedder.embed(sample)
                        self._intent_vectors[intent_name].append(vector)
                    except Exception as e:
                        logger.debug(f"样本向量化失败: {e}")

    def match(self, query: str, top_k: int = 3, threshold: float = 0.5) -> list[SemanticMatchResult]:
        """
        匹配查询与意图
        
        Args:
            query: 查询文本
            top_k: 返回前k个结果
            threshold: 相似度阈值
            
        Returns:
            List[SemanticMatchResult]: 匹配结果列表
        """
        self.initialize()

        results = []

        if self._use_embedding and self._embedder and self._intent_vectors:
            try:
                query_vector = self._embedder.embed(query)

                for intent_name, vectors in self._intent_vectors.items():
                    max_similarity = 0.0
                    matched_samples = []

                    for i, vector in enumerate(vectors):
                        similarity = self._cosine_similarity(query_vector, vector)
                        if similarity > threshold:
                            matched_samples.append(self._sample_texts[intent_name][i])
                        max_similarity = max(max_similarity, similarity)

                    if max_similarity >= threshold:
                        results.append(SemanticMatchResult(
                            intent_name=intent_name,
                            similarity=max_similarity,
                            matched_samples=matched_samples[:5],
                            confidence=min(max_similarity * 1.2, 1.0)
                        ))
            except Exception as e:
                logger.warning(f"语义匹配失败，降级到关键词匹配: {e}")
                return self._keyword_match(query, top_k, threshold)
        else:
            return self._keyword_match(query, top_k, threshold)

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    def _keyword_match(self, query: str, top_k: int, threshold: float) -> list[SemanticMatchResult]:
        """关键词匹配（降级方案）"""
        results = []
        query_lower = query.lower()

        for intent_name, samples in self._sample_texts.items():
            max_similarity = 0.0
            matched_samples = []

            for sample in samples:
                similarity = self._keyword_similarity(query_lower, sample.lower())
                if similarity > threshold:
                    matched_samples.append(sample)
                max_similarity = max(max_similarity, similarity)

            if max_similarity >= threshold:
                results.append(SemanticMatchResult(
                    intent_name=intent_name,
                    similarity=max_similarity,
                    matched_samples=matched_samples[:5],
                    confidence=min(max_similarity * 1.1, 0.9)
                ))

        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:top_k]

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _keyword_similarity(self, query: str, sample: str) -> float:
        """计算关键词相似度"""
        query_words = set(query.split())
        sample_words = set(sample.split())

        if not query_words or not sample_words:
            return 0.0

        intersection = query_words & sample_words
        union = query_words | sample_words

        return len(intersection) / len(union) if union else 0.0


class FuzzyMatcher:
    """模糊匹配器"""

    _instance: Optional['FuzzyMatcher'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._intent_patterns = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'FuzzyMatcher':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_patterns(self, patterns: dict[str, list[str]]):
        """加载模式"""
        self._intent_patterns = patterns

    def fuzzy_match(self, query: str, threshold: float = 0.5) -> list[tuple[str, float]]:
        """模糊匹配"""
        results = []

        query_lower = query.lower()

        for intent_name, patterns in self._intent_patterns.items():
            for pattern in patterns:
                score = self._fuzzy_score(query_lower, pattern.lower())
                if score >= threshold:
                    results.append((intent_name, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _fuzzy_score(self, query: str, pattern: str) -> float:
        """模糊评分"""
        if pattern in query:
            return 1.0

        query_chars = list(query)
        pattern_chars = list(pattern)

        matches = 0
        for pc in pattern_chars:
            if pc in query_chars:
                matches += 1
                query_chars.remove(pc)

        return matches / len(pattern_chars) if pattern_chars else 0


_semantic_matcher: SemanticMatcher | None = None
_fuzzy_matcher: FuzzyMatcher | None = None


def get_semantic_matcher() -> SemanticMatcher:
    """获取语义匹配器单例"""
    global _semantic_matcher
    if _semantic_matcher is None:
        _semantic_matcher = SemanticMatcher.get_instance()
    return _semantic_matcher


def get_fuzzy_matcher() -> FuzzyMatcher:
    """获取模糊匹配器单例"""
    global _fuzzy_matcher
    if _fuzzy_matcher is None:
        _fuzzy_matcher = FuzzyMatcher.get_instance()
    return _fuzzy_matcher


def create_semantic_matcher(use_embedding: bool = True) -> SemanticMatcher:
    """创建语义匹配器（兼容旧API）"""
    return get_semantic_matcher()


def create_fuzzy_matcher() -> FuzzyMatcher:
    """创建模糊匹配器（兼容旧API）"""
    return get_fuzzy_matcher()
