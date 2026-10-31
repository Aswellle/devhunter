"""
app/threads/relations.py
"同一故事线"关联的共享约定。

thread_relations 表以 (thread_a, thread_b) 字典序规范存储，
CHECK (thread_a < thread_b) 与 SQLite BINARY 排序一致；
所有写入方都必须经过 canonical_pair，保证规则只活在一处。
"""
from __future__ import annotations


def canonical_pair(thread_a: str, thread_b: str) -> tuple[str, str]:
    """按字典序返回规范序二元组（与 CHECK (thread_a < thread_b) 一致）"""
    return (thread_a, thread_b) if thread_a <= thread_b else (thread_b, thread_a)
