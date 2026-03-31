"""
RAG 知识库 - 向量化服务
使用 Sentence Transformers 进行文本嵌入
"""
import logging
import os

logger = logging.getLogger(__name__)


def _setup_hf_mirror():
    """配置 HuggingFace 镜像源（解决国内访问问题）"""
    from core.config import get_settings

    settings = get_settings()
    hf_mirror = settings.hf_mirror

    mirrors = {
        "hf-mirror": "https://hf-mirror.com",
        "aliyun": "https://mirrors.aliyun.com/huggingface",
        "modelscope": "https://modelscope.cn/models",
    }

    if hf_mirror in mirrors:
        endpoint = mirrors[hf_mirror]
        os.environ["HF_ENDPOINT"] = endpoint
        logger.info(f"已配置 HuggingFace 镜像：{endpoint}")


class Embedder:
    """文本向量化器"""

    def __init__(self, model_name: str = "shibing624/text2vec-base-chinese"):
        """
        初始化向量化器
        
        Args:
            model_name: 嵌入模型名称
                - 中文：shibing624/text2vec-base-chinese (768 维)
                - 英文：sentence-transformers/all-MiniLM-L6-v2 (384 维)
        """
        self.model_name = model_name
        self.model = None
        self._dimension = None

    def _load_model(self):
        """懒加载模型"""
        if self.model is None:
            _setup_hf_mirror()
            logger.info(f"加载嵌入模型：{self.model_name}")
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            test_embedding = self.model.encode(["test"])
            self._dimension = len(test_embedding[0])
            logger.info(f"模型加载完成，维度：{self._dimension}")

    @property
    def dimension(self) -> int:
        """获取嵌入维度"""
        if self._dimension is None:
            self._load_model()
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        self._load_model()

        if not texts:
            return []

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
                convert_to_numpy=True
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"向量化失败：{e}")
            raise

    def embed_single(self, text: str) -> list[float]:
        """
        将单个文本转换为向量
        
        Args:
            text: 输入文本
            
        Returns:
            向量
        """
        result = self.embed([text])
        return result[0] if result else []

    def embed_chunks(self, chunks: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        批量向量化文本块
        
        Args:
            chunks: 文本块列表
            batch_size: 批次大小
            
        Returns:
            向量列表
        """
        self._load_model()

        if not chunks:
            return []

        all_embeddings = []

        try:
            from tqdm import tqdm

            for i in tqdm(range(0, len(chunks), batch_size), desc="向量化"):
                batch = chunks[i:i + batch_size]
                embeddings = self.model.encode(
                    batch,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True
                )
                all_embeddings.extend(embeddings.tolist())
        except ImportError:
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                embeddings = self.model.encode(
                    batch,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                    convert_to_numpy=True
                )
                all_embeddings.extend(embeddings.tolist())

        return all_embeddings


_embedder_instance: Embedder | None = None


def get_embedder(model_name: str | None = None) -> Embedder:
    """获取向量化器实例"""
    global _embedder_instance
    if _embedder_instance is None:
        model = model_name or "shibing624/text2vec-base-chinese"
        _embedder_instance = Embedder(model)
    return _embedder_instance


def reset_embedder(model_name: str) -> Embedder:
    """重置向量化器（切换模型时使用）"""
    global _embedder_instance
    _embedder_instance = Embedder(model_name)
    return _embedder_instance
