"""
app/utils/hash.py
哈希工具函数
"""
import hashlib


def sha256_hex(text: str) -> str:
    """计算字符串的 SHA-256 十六进制摘要（64 字符）"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
