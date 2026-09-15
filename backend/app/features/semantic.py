"""
app/features/semantic.py
Semantic Similarity：语义相似度可插拔架构。

支持多种实现：
1. CharacterNgramSimilarity - 字符级 n-gram 相似度（fallback，无需外部依赖）
2. EmbeddingSimilarity - 基于嵌入模型的相似度（预留接口，可接入 sentence-transformers 等）

通过环境变量 SEMANTIC_BACKEND 切换实现。
"""
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

# Optional numpy dependency for embedding similarity
try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False
    np = None  # type: ignore

logger = logging.getLogger(__name__)


class SemanticSimilarity(ABC):
    """语义相似度抽象基类"""

    @abstractmethod
    def compute(self, text_a: str, text_b: str) -> float:
        """
        计算两个文本的语义相似度。

        Args:
            text_a: 第一个文本
            text_b: 第二个文本

        Returns:
            相似度分数 [0.0, 1.0]
        """
        pass

    @abstractmethod
    def batch_compute(self, query: str, candidates: list[str]) -> list[float]:
        """
        批量计算相似度。

        Args:
            query: 查询文本
            candidates: 候选文本列表

        Returns:
            相似度分数列表
        """
        pass


class CharacterNgramSimilarity(SemanticSimilarity):
    """
    字符级 n-gram 相似度。

    使用字符级 n-gram 的 Jaccard 相似度作为语义相似度的近似。
    对于中英文混合文本效果较好，无需外部依赖。
    """

    def __init__(self, n: int = 2):
        """
        Args:
            n: n-gram 大小，默认 2（bigram）
        """
        self.n = n

    def _tokenize(self, text: str) -> set[str]:
        """将文本分解为字符级 n-gram"""
        if not text:
            return set()
        # 清理文本：保留中英文数字
        text = re.sub(r'[^\w\u4e00-\u9fff]', '', text.lower())
        if len(text) < self.n:
            return {text}
        return {text[i:i + self.n] for i in range(len(text) - self.n + 1)}

    def compute(self, text_a: str, text_b: str) -> float:
        """计算两个文本的 n-gram Jaccard 相似度"""
        if not text_a or not text_b:
            return 0.0

        tokens_a = self._tokenize(text_a)
        tokens_b = self._tokenize(text_b)

        if not tokens_a or not tokens_b:
            return 0.0

        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b

        return len(intersection) / len(union)

    def batch_compute(self, query: str, candidates: list[str]) -> list[float]:
        """批量计算相似度"""
        return [self.compute(query, c) for c in candidates]


class EmbeddingSimilarity(SemanticSimilarity):
    """
    基于嵌入模型的语义相似度。

    预留接口，可接入 sentence-transformers、OpenAI Embeddings 等。
    需要安装额外的依赖包。
    """

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Args:
            model_name: 嵌入模型名称
        """
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None:
            if not _NUMPY_AVAILABLE:
                logger.warning(
                    "numpy not installed. "
                    "Falling back to CharacterNgramSimilarity."
                )
                return False
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info("Loaded embedding model: %s", self.model_name)
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed. "
                    "Falling back to CharacterNgramSimilarity."
                )
                return False
        return True

    def compute(self, text_a: str, text_b: str) -> float:
        """计算两个文本的嵌入相似度"""
        if not self._load_model():
            # Fallback to n-gram
            fallback = CharacterNgramSimilarity()
            return fallback.compute(text_a, text_b)

        if not text_a or not text_b:
            return 0.0

        embeddings = self._model.encode([text_a, text_b])
        # Cosine similarity using module-level numpy
        sim = np.dot(embeddings[0], embeddings[1]) / (
            np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
        )
        return float(max(0.0, min(1.0, sim)))

    def batch_compute(self, query: str, candidates: list[str]) -> list[float]:
        """批量计算相似度"""
        if not self._load_model():
            fallback = CharacterNgramSimilarity()
            return fallback.batch_compute(query, candidates)

        if not candidates:
            return []

        texts = [query] + candidates
        embeddings = self._model.encode(texts)

        query_emb = embeddings[0]
        candidate_embs = embeddings[1:]

        # Cosine similarity using module-level numpy
        similarities = []
        for emb in candidate_embs:
            sim = np.dot(query_emb, emb) / (
                np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8
            )
            similarities.append(float(max(0.0, min(1.0, sim))))

        return similarities


def get_semantic_similarity(backend: str | None = None) -> SemanticSimilarity:
    """
    获取语义相似度实现。

    Args:
        backend: 后端类型 ('ngram' | 'embedding')，None 则根据环境变量选择

    Returns:
        SemanticSimilarity 实例
    """
    import os
    backend = backend or os.environ.get("SEMANTIC_BACKEND", "ngram")

    if backend == "embedding":
        try:
            return EmbeddingSimilarity()
        except Exception as e:
            logger.warning("Failed to load embedding backend: %s. Falling back to ngram.", e)
            return CharacterNgramSimilarity()
    else:
        return CharacterNgramSimilarity()


# 全局单例
semantic_similarity = get_semantic_similarity()
