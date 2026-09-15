"""
app/features/extractor.py
Item Feature Extraction：从 Item 中提取结构化特征。

输出 ItemFeatures，包含：
- title_tokens: 标题词集合
- entities: 抽取的实体
- language: 语言检测
- content_type: 内容类型
- fingerprint: 内容指纹
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.utils.similarity import normalize_text, tokenize


@dataclass
class ItemFeatures:
    """Item 结构化特征"""
    title_tokens: set[str] = field(default_factory=set)
    entities: dict[str, list[str]] = field(default_factory=dict)
    language: str = "unknown"
    content_type: str = "unknown"
    fingerprint: str = ""
    title: str = ""
    summary: str = ""
    source_id: str = ""
    source_name: str = ""
    published_at: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_tokens": list(self.title_tokens),
            "entities": self.entities,
            "language": self.language,
            "content_type": self.content_type,
            "fingerprint": self.fingerprint,
            "title": self.title,
            "summary": self.summary,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "url": self.url,
        }


class ItemFeatureExtractor:
    """Item 特征提取器"""

    def extract(self, item: dict[str, Any]) -> ItemFeatures:
        """从 Item dict 中提取特征"""
        title = item.get("title", "")
        summary = item.get("summary", "")

        features = ItemFeatures(
            title=title,
            summary=summary,
            source_id=item.get("source_id", ""),
            source_name=item.get("source_name", ""),
            published_at=item.get("published_at", ""),
            url=item.get("url", ""),
        )

        # 1. 标题词集合
        features.title_tokens = tokenize(title)

        # 2. 实体抽取
        features.entities = self._extract_entities(title, summary)

        # 3. 语言检测
        features.language = self._detect_language(title + " " + summary)

        # 4. 内容类型
        features.content_type = self._detect_content_type(title, summary)

        # 5. 内容指纹
        features.fingerprint = self._compute_fingerprint(title, summary)

        return features

    def _extract_entities(self, title: str, summary: str) -> dict[str, list[str]]:
        """从标题和摘要中抽取实体"""
        from app.features.entities import entity_extractor
        return entity_extractor.extract(title, summary)

    def _detect_language(self, text: str) -> str:
        """简单语言检测"""
        if not text:
            return "unknown"
        # 检测中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.strip())
        if total_chars == 0:
            return "unknown"
        if chinese_chars / total_chars > 0.3:
            return "zh"
        return "en"

    def _detect_content_type(self, title: str, summary: str) -> str:
        """检测内容类型"""
        text = (title + " " + summary).lower()
        if any(kw in text for kw in ["release", "launch", "announce", "发布", "推出"]):
            return "release"
        if any(kw in text for kw in ["tutorial", "guide", "how to", "教程", "指南"]):
            return "tutorial"
        if any(kw in text for kw in ["discussion", "discuss", "讨论", "热议"]):
            return "discussion"
        if any(kw in text for kw in ["news", "breaking", "新闻", "快讯"]):
            return "news"
        return "article"

    def _compute_fingerprint(self, title: str, summary: str) -> str:
        """计算内容指纹（用于语义去重）"""
        # 使用规范化标题的 hash
        normalized = normalize_text(title)
        if not normalized:
            return ""
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# 全局单例
feature_extractor = ItemFeatureExtractor()
