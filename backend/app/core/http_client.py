"""
app/core/http_client.py
httpx.Client 单例工厂 - 同步客户端，强化浏览器指纹防反爬
"""
import threading

import httpx

from app.core.config import settings


def _build_client() -> httpx.Client:
    """构建配置好的 httpx 同步客户端，加载完整的浏览器指纹头部"""
    return httpx.Client(
        headers={
            # 模拟真实 Chrome 浏览器完整头部
            "User-Agent":      settings.crawler_user_agent,
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,"
                               "image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection":      "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":  "document",
            "Sec-Fetch-Mode":  "navigate",
            "Sec-Fetch-Site":  "none",
            "Sec-Fetch-User":  "?1",
            "Sec-CH-UA":       '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Cache-Control":   "max-age=0",
        },
        timeout=httpx.Timeout(
            connect=10.0,
            read=settings.crawler_timeout,
            write=10.0,
            pool=5.0,
        ),
        # C1: redirects must NOT be auto-followed. Each hop's Location URL is
        # re-validated against the SSRF blocklist by the crawler engine
        # (see engine.py::_fetch_page_with_retry) before being followed
        # manually — auto-following here would let a 301/302 to a private
        # IP bypass the SSRF check entirely.
        follow_redirects=False,
        limits=httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
        ),
        # 显式启用 SSL 证书验证，防止中间人攻击
        verify=True,
    )


_http_client: httpx.Client | None = None
_client_lock = threading.Lock()


def get_http_client() -> httpx.Client:
    """
    获取全局 httpx.Client 单例。

    C4: 加锁保护单例构建。APScheduler 用 ThreadPoolExecutor 并发执行多个
    Job，若不加锁，两个 Worker 线程可能同时看到 _http_client is None，
    各自构建一个 httpx.Client —— 其中一个会被后写入的赋值覆盖引用，
    连接池永远不会被 close_http_client() 关闭，造成连接泄漏。
    """
    global _http_client
    if _http_client is None or _http_client.is_closed:
        with _client_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = _build_client()
    return _http_client


def close_http_client() -> None:
    """关闭 HTTP 客户端（在 lifespan shutdown 时调用）"""
    global _http_client
    if _http_client and not _http_client.is_closed:
        _http_client.close()
    _http_client = None
