"""
app/features/entities.py
Entity Extraction：从文本中抽取结构化实体。

识别的实体类型：
- company: 公司（OpenAI, Google, Microsoft, etc.）
- product: 产品（GPT-5, Claude, React, etc.）
- person: 人物（通过 @ 或已知模式）
- github_repo: GitHub 仓库（owner/repo 格式）
- language: 编程语言（Python, Rust, JavaScript, etc.）
- ai_model: AI 模型（GPT-5, Claude 3, Gemini, etc.）
- version: 版本号（v1.2.3, 19, etc.）
- date: 日期（2026-09-15, Sep 15, etc.）
- number: 数字指标（100%, 1M, etc.）
"""
import re
from typing import Any


# 已知实体词典（可扩展）
KNOWN_COMPANIES = {
    "openai", "google", "microsoft", "apple", "amazon", "meta", "anthropic",
    "nvidia", "intel", "amd", "tesla", "spacex", "twitter", "x", "bytedance",
    "tencent", "alibaba", "baidu", "meituan", "jd", "pinduoduo",
}

KNOWN_PRODUCTS = {
    "gpt-5", "gpt-4", "claude", "gemini", "llama", "mistral", "qwen",
    "react", "vue", "angular", "svelte", "next.js", "nuxt",
    "rust", "python", "javascript", "typescript", "go", "java", "c++", "c#",
    "docker", "kubernetes", "terraform", "ansible",
    "iphone", "ipad", "macbook", "airpods",
    "tesla", "model 3", "model y", "cybertruck",
}

KNOWN_AI_MODELS = {
    "gpt-5", "gpt-4", "gpt-4o", "claude", "claude 3", "claude 3.5",
    "gemini", "gemini 2", "llama", "llama 3", "mistral", "qwen",
    "deepseek", "kimi", "doubao", "chatgpt", "sora", "dall-e",
}

KNOWN_LANGUAGES = {
    "python", "rust", "javascript", "typescript", "go", "java", "c++", "c#",
    "ruby", "php", "swift", "kotlin", "scala", "haskell", "erlang",
    "elixir", "clojure", "lua", "perl", "r", "matlab", "dart", "flutter",
}


class EntityExtractor:
    """实体抽取器"""

    def extract(self, title: str, summary: str) -> dict[str, list[str]]:
        """从标题和摘要中抽取实体"""
        text = f"{title} {summary}"
        normalized = text.lower()

        entities: dict[str, list[str]] = {
            "company": [],
            "product": [],
            "person": [],
            "github_repo": [],
            "language": [],
            "ai_model": [],
            "version": [],
            "date": [],
            "number": [],
        }

        # 1. 公司
        for company in KNOWN_COMPANIES:
            if company in normalized:
                entities["company"].append(company)

        # 2. 产品
        for product in KNOWN_PRODUCTS:
            if product in normalized:
                entities["product"].append(product)

        # 3. GitHub 仓库 (owner/repo 格式)
        github_pattern = r'\b([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)\b'
        for match in re.finditer(github_pattern, text):
            repo = match.group(1)
            # 过滤掉 URL 中的路径
            if "/" in repo and not repo.startswith("http"):
                entities["github_repo"].append(repo)

        # 4. 编程语言
        for lang in KNOWN_LANGUAGES:
            if lang in normalized:
                entities["language"].append(lang)

        # 5. AI 模型
        for model in KNOWN_AI_MODELS:
            if model in normalized:
                entities["ai_model"].append(model)

        # 6. 版本号
        version_pattern = r'\bv?(\d+\.\d+(?:\.\d+)?)\b'
        for match in re.finditer(version_pattern, text):
            entities["version"].append(match.group(0))

        # 7. 日期
        date_patterns = [
            r'\b(\d{4}-\d{2}-\d{2})\b',  # 2026-09-15
            r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',  # 9/15/2026
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',  # Sep 15, 2026
        ]
        for pattern in date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities["date"].append(match.group(0))

        # 8. 数字指标
        number_pattern = r'\b(\d+(?:\.\d+)?[MBKmbk]?)\b'
        for match in re.finditer(number_pattern, text):
            num = match.group(1)
            # 过滤掉太小的数字（可能是版本号的一部分）
            if len(num) > 1 and not num.startswith("0"):
                entities["number"].append(num)

        # 去重
        for key in entities:
            entities[key] = list(dict.fromkeys(entities[key]))

        return entities


# 全局单例
entity_extractor = EntityExtractor()
