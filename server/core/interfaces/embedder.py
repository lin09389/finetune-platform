"""
嵌入器接口 - 用于文本向量化
实现依赖倒置原则，使高层模块不依赖具体实现
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """向量化结果"""
    embeddings: list[list[float]]
    model_name: str
    dimension: int
    processing_time_ms: float = 0.0


class EmbedderInterface(ABC):
    """
    嵌入器接口

    定义文本向量化的标准接口，支持多种后端实现：
    - sentence-transformers
    - OpenAI embeddings
    - 自定义模型
    """

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转换为向量

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        pass

    @abstractmethod
    def embed_single(self, text: str) -> list[float]:
        """
        将单个文本转换为向量

        Args:
            text: 输入文本

        Returns:
            向量
        """
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        获取向量维度

        Returns:
            向量维度
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        获取模型名称

        Returns:
            模型名称
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查嵌入器是否可用

        Returns:
            是否可用
        """
        pass

    async def embed_async(self, texts: list[str]) -> EmbeddingResult:
        """
        异步向量化（可选实现）

        Args:
            texts: 文本列表

        Returns:
            向量化结果
        """
        import time
        start = time.time()
        embeddings = self.embed(texts)
        return EmbeddingResult(
            embeddings=embeddings,
            model_name=self.model_name,
            dimension=self.dimension,
            processing_time_ms=(time.time() - start) * 1000
        )

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32
    ) -> list[list[float]]:
        """
        批量向量化

        Args:
            texts: 文本列表
            batch_size: 批次大小

        Returns:
            向量列表
        """
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = self.embed(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings
