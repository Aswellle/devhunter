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


def source_identity(source_url: str, fallback: str = "") -> str:
    """来源 URL 的稳定 provider 身份（主机名，小写，去 www 前缀）。

    Thread 来源独立性必须以它计算而不是任务名：任务改名不得改变身份，
    同平台的多个任务（同一主机）不构成跨平台共识，不同平台主机不同
    才是独立来源证据。URL 缺失或畸形时回退 fallback。
    """
    if not source_url:
        return fallback
    try:
        host = urlparse(source_url.strip()).hostname or ""
    except ValueError:
        return fallback
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or fallback


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
