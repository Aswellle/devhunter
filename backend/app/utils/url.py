"""
app/utils/url.py
URL 规范化工具 - 用于去重 hash 计算
"""
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from app.utils.hash import sha256_hex


def normalize_url(raw_url: str) -> str:
    """
    规范化 URL，消除等价 URL 的差异：
    1. scheme 小写
    2. host 小写
    3. 去除 fragment（#...）
    4. path 去除尾部 /（根路径保留 /）
    5. query 参数按字母排序
    """
    parsed = urlparse(raw_url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    # 排序 query 参数
    query_dict = parse_qs(parsed.query, keep_blank_values=True)
    query = urlencode(sorted(query_dict.items()), doseq=True)

    normalized = f"{scheme}://{netloc}{path}"
    if query:
        normalized += f"?{query}"
    return normalized


def compute_url_hash(raw_url: str) -> str:
    """规范化 URL 后计算 sha256，用于去重索引"""
    return sha256_hex(normalize_url(raw_url))


def to_absolute_url(base_url: str, href: str) -> str:
    """将相对路径链接转换为绝对 URL"""
    return urljoin(base_url, href)


def is_valid_url(url: str) -> bool:
    """简单校验 URL 格式是否合法"""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False
