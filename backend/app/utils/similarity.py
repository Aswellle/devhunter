"""
app/utils/similarity.py
基于词集合 Jaccard 相似度的标题比较算法。

用于 Cross-Platform Thread：判断两条内容是否在讨论同一事件。
阈值 0.35 经过测试，适合处理新闻标题的表述差异（如 "GPT-5 发布" vs "OpenAI 推出 GPT-5"）。
"""
import re
import unicodedata
from typing import Callable


# Jaccard 相似度阈值：高于此值视为"讨论同一事件"
DEFAULT_THRESHOLD = 0.35

# 停用词：新闻标题中高频出现但不携带语义信息的词
STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
    "at", "by", "from", "as", "into", "through", "during", "before", "after",
    "and", "or", "but", "if", "not", "no", "so", "than", "too", "very",
    "just", "about", "up", "down", "out", "all", "any", "each", "every",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "he", "him", "his", "she", "her",
    "what", "which", "who", "whom", "when", "where", "why", "how",
    "new", "latest", "announces", "announced", "launches", "launched",
    "introduces", "introduced", "reveals", "revealed", "releases", "released",
})


def normalize_text(text: str) -> str:
    """
    将文本标准化为可比格式：
    1. Unicode NFC 规范化
    2. 转小写
    3. 移除标点符号
    4. 规范化空白
    """
    if not text:
        return ""
    # Unicode NFC：把组合字符拆开再重新组合（如 é → e + ̨）
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    # 移除所有非字母数字和空格
    text = re.sub(r"[^\w\s]", " ", text)
    # 规范化空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> set[str]:
    """
    将文本分词为词集合。
    过滤停用词和单字符词。
    """
    normalized = normalize_text(text)
    tokens = set(normalized.split())
    # 过滤停用词和太短的词
    tokens = {t for t in tokens if t not in STOP_WORDS and len(t) > 1}
    return tokens


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    计算两条文本的 Jaccard 相似度（基于词集合）。
    返回值范围 [0.0, 1.0]：
    1.0 = 完全相同，0.0 = 完全不同
    """
    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    return len(intersection) / len(union)


def is_similar(title_a: str, title_b: str, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """判断两条标题是否相似（高于阈值）"""
    return jaccard_similarity(title_a, title_b) >= threshold


def find_similar_titles(
    new_titles: list[str],
    existing_titles: list[tuple[str, str, float]],  # (title, item_id, fetched_at)
    threshold: float = DEFAULT_THRESHOLD,
    min_token_count: int = 2,
) -> dict[int, str]:
    """
    在新标题集合中找出与已有标题相似的项。

    Args:
        new_titles: 新标题列表，索引即 item index
        existing_titles: 已存在的 (title, item_id, fetched_at) 列表
        threshold: Jaccard 相似度阈值
        min_token_count: 最小有效词数（低于此值的新标题不参与匹配，避免短标题误匹配）

    Returns:
        dict[new_item_index] = existing_item_id
        即每个匹配到已有项的新标题索引，映射到已有项的 item_id
    """
    new_valid = []
    new_valid_indices = []
    for i, title in enumerate(new_titles):
        tokens = tokenize(title)
        if len(tokens) >= min_token_count:
            new_valid.append(tokens)
            new_valid_indices.append(i)

    if not new_valid:
        return {}

    # 用已有标题构建倒排索引，加速匹配
    # key: word -> set of (existing_index, title_str)
    inv_index: dict[str, set[tuple[int, str]]] = {}
    for j, (ex_title, _, _) in enumerate(existing_titles):
        for word in tokenize(ex_title):
            inv_index.setdefault(word, set()).add((j, ex_title))

    matches: dict[int, str] = {}
    for i, tokens in zip(new_valid_indices, new_valid):
        if not tokens:
            continue
        best_score = 0.0
        best_existing_id = None

        # 从倒排索引获取候选（至少有共同词的已有标题）
        candidates = set()
        for word in tokens:
            for key_inv in inv_index.get(word, []):
                candidates.add(key_inv)

        if not candidates:
            continue

        for (j, ex_title) in candidates:
            ex_item_id = existing_titles[j][1]
            score = jaccard_similarity(new_titles[i], ex_title)
            if score > best_score:
                best_score = score
                best_existing_id = ex_item_id

        if best_score >= threshold and best_existing_id is not None:
            matches[i] = best_existing_id

    return matches
