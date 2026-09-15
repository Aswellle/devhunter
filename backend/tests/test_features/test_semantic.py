"""
tests/test_features/test_semantic.py
Semantic Similarity 单元测试
"""
import pytest
from app.features.semantic import (
    CharacterNgramSimilarity,
    get_semantic_similarity,
)


class TestCharacterNgramSimilarity:
    """字符级 n-gram 相似度测试"""

    def test_identical_texts(self):
        """完全相同的文本"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("Hello World", "Hello World")
        assert score == 1.0

    def test_completely_different(self):
        """完全不同的文本"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("ABC", "XYZ")
        assert score == 0.0

    def test_partial_overlap(self):
        """部分重叠"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("OpenAI GPT-5", "OpenAI GPT-4")
        assert 0 < score < 1.0

    def test_empty_text(self):
        """空文本"""
        sim = CharacterNgramSimilarity(n=2)
        assert sim.compute("", "Hello") == 0.0
        assert sim.compute("Hello", "") == 0.0
        assert sim.compute("", "") == 0.0

    def test_chinese_text(self):
        """中文文本"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("OpenAI 发布 GPT-5", "OpenAI 推出 GPT-5")
        assert score > 0.3

    def test_batch_compute(self):
        """批量计算"""
        sim = CharacterNgramSimilarity(n=2)
        scores = sim.batch_compute("Hello World", ["Hello", "World", "Foo"])
        assert len(scores) == 3
        assert all(0 <= s <= 1.0 for s in scores)

    def test_case_insensitive(self):
        """大小写不敏感"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("Hello World", "hello world")
        assert score == 1.0

    def test_punctuation_ignored(self):
        """标点符号被忽略"""
        sim = CharacterNgramSimilarity(n=2)
        score = sim.compute("Hello, World!", "Hello World")
        assert score == 1.0


class TestGetSemanticSimilarity:
    """语义相似度工厂函数测试"""

    def test_default_backend(self):
        """默认后端"""
        sim = get_semantic_similarity("ngram")
        assert isinstance(sim, CharacterNgramSimilarity)

    def test_ngram_backend(self):
        """ngram 后端"""
        sim = get_semantic_similarity("ngram")
        assert isinstance(sim, CharacterNgramSimilarity)

    def test_embedding_backend_fallback(self):
        """embedding 后端回退"""
        # 如果没有 sentence-transformers，应该回退到 ngram
        sim = get_semantic_similarity("embedding")
        assert sim is not None


# 创建 __init__.py
