"""
tests/test_sources/test_discovery_taxonomy.py
URL 发现的失败分类体系与解析成功率增强回归。

锁住三类契约：
1. URL 归一化：无 scheme 自动补 https、www 变体回退、http 降级
2. 解析成功率：HTML 内嵌 feed 自动发现、根路径 feed 探测、文章页兜底
3. 失败分类：技术上根本无法解析的情况各自落进独立编码 + 提示
   （DNS/连接/超时/TLS/404/登录墙/反爬挑战/限流/5xx/非网页/SPA/详情页）
"""
import httpx
import pytest
import socket
from contextlib import contextmanager

from app.sources.discovery import url_discoverer, FailureCode

PUBLIC_IP = "93.184.216.34"

LIST_HTML = """<html><head><title>列表页</title></head><body>
<article><h2><a href="/a/1">标题一</a></h2><p>摘要一</p></article>
<article><h2><a href="/a/2">标题二</a></h2><p>摘要二</p></article>
<article><h2><a href="/a/3">标题三</a></h2><p>摘要三</p></article>
</body></html>"""

FEED_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>博客 Feed</title>
<item><title>文章一</title><link>https://blog.example.com/1</link><description>摘要</description></item>
<item><title>文章二</title><link>https://blog.example.com/2</link><description>摘要</description></item>
</channel></rss>"""

ARTICLE_HTML = """<html><head><title>一篇长文</title>
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
</head><body>
<article><h1>非常长的文章标题</h1>""" + ("<p>" + "正文内容。" * 300 + "</p>") + "</article></body></html>"

ARTICLE_NO_FEED_HTML = """<html><head><title>一篇长文</title></head><body>
<article><h1>非常长的文章标题</h1>""" + ("<p>" + "正文内容。" * 300 + "</p>") + "</article></body></html>"

SPA_HTML = """<html><head><title>单页应用</title></head><body>
<div id="root"></div>
<script type="module" src="/assets/index-abc123.js"></script>
<script src="/static/vendor.js"></script>
</body></html>"""

NAV_SHELL_HTML = """<html><head><title>客户端渲染的标签页</title></head><body>
<div id="__nuxt">
<nav><a href="/">首页</a><a href="/c1">共创</a><a href="/c2">PRIME</a><a href="/c3">Matrix</a><a href="/c4">栏目</a></nav>
<div>页脚备案信息文字，凑一点文本量让导航壳更真实。</div>
</div>
<script src="/static/runtime.js"></script>
<script src="/static/app.js"></script>
</body></html>"""


@contextmanager
def _make_client(monkeypatch, routes, dns_fail_hosts=(), default_status=404):
    """
    MockTransport 客户端 + 可控 DNS 解析（SSRF 预检会真实调用 getaddrinfo）。

    routes: {url 或 host 前缀"*": httpx.Response}，精确匹配优先；
    未命中返回 default_status。dns_fail_hosts 中的主机解析报 gaierror。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in routes:
            return routes[url]
        for key, resp in routes.items():
            if key.endswith("*") and url.startswith(key[:-1]):
                return resp
        return httpx.Response(default_status, text="not found")

    fake = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("app.sources.discovery.get_http_client", lambda: fake)

    def _stub_dns(host, *args, **kwargs):
        h = str(host).lower().rstrip(".")
        if h in dns_fail_hosts:
            raise socket.gaierror(11001, "Host not found")
        # IP 字面量与 localhost 保持自身（私有地址拦截依赖真实解析值）
        try:
            import ipaddress
            ipaddress.ip_address(h)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (h, 0))]
        except ValueError:
            pass
        if h == "localhost":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _stub_dns)
    yield fake
    fake.close()


@pytest.fixture
def make_client(monkeypatch):
    def _factory(routes, **kwargs):
        return _make_client(monkeypatch, routes, **kwargs)
    return _factory


# ── URL 归一化与成功率增强 ────────────────────────────────────────────────────

def test_missing_scheme_defaults_to_https(make_client):
    """无 scheme 输入（如 blog.example.org）自动补全 https 并成功发现"""
    with make_client({"https://blog.example.org/": httpx.Response(200, text=LIST_HTML)}):
        d = url_discoverer.discover("blog.example.org")
    assert d.failure is None
    assert d.url == "https://blog.example.org/"
    assert d.source_type == "html"
    assert d.list_selector == "article"


def test_html_feed_link_autodiscovery(make_client):
    """HTML 页面声明了 RSS feed → 自动改用 feed 并返回 rss 结果"""
    with make_client({
        "https://blog.example.com/": httpx.Response(200, text=ARTICLE_HTML),
        "https://blog.example.com/feed.xml": httpx.Response(200, text=FEED_XML),
    }):
        d = url_discoverer.discover("https://blog.example.com/")
    assert d.failure is None
    assert d.source_type == "rss"
    assert d.feed_url == "https://blog.example.com/feed.xml"
    assert d.url == "https://blog.example.com/feed.xml", "任务地址应回写为实际可抓取的 feed"


def test_root_404_probes_common_feed_paths(make_client):
    """站点根 404 → 自动探测 /feed 等常见 feed 路径"""
    with make_client({
        "https://blog.example.com/": httpx.Response(404, text="nope"),
        "https://blog.example.com/feed": httpx.Response(200, text=FEED_XML),
    }):
        d = url_discoverer.discover("https://blog.example.com/")
    assert d.failure is None
    assert d.source_type == "rss"
    assert d.url == "https://blog.example.com/feed"
    assert "https://blog.example.com/feed" in d.tried_urls


def test_dns_failure_falls_back_to_www_variant(make_client):
    """裸域 DNS 解析失败 → 尝试 www 变体"""
    with make_client({
        "https://www.site.example/": httpx.Response(200, text=LIST_HTML),
    }, dns_fail_hosts=("site.example",)):
        d = url_discoverer.discover("https://site.example/")
    assert d.failure is None
    assert d.url == "https://www.site.example/"
    assert "https://www.site.example/" in d.tried_urls


def test_https_failure_falls_back_to_http(make_client):
    """https 连接失败 → http 降级尝试"""
    routes = {
        "https://legacy.example.com/": None,  # 用异常占位
        "http://legacy.example.com/": httpx.Response(200, text=LIST_HTML),
    }

    class _FailRoutes(httpx.MockTransport):
        def __init__(self):
            super().__init__(self._handler)

        def _handler(self, request):
            if request.url.scheme == "https":
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200, text=LIST_HTML)

    fake = httpx.Client(transport=_FailRoutes())
    import app.sources.discovery as disc_mod
    from contextlib import ExitStack
    # 手工注入（不走 make_client 的固定路由）
    real_get = disc_mod.get_http_client
    disc_mod.get_http_client = lambda: fake
    try:
        import socket as _s
        real_getaddrinfo = _s.getaddrinfo
        _s.getaddrinfo = lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
        try:
            d = url_discoverer.discover("https://legacy.example.com/")
        finally:
            _s.getaddrinfo = real_getaddrinfo
    finally:
        disc_mod.get_http_client = real_get
        fake.close()
    assert d.failure is None
    assert d.url == "http://legacy.example.com/"
    assert d.source_type == "html"


# ── 失败分类：技术上根本无法解析的情况 ────────────────────────────────────────

def test_unsupported_scheme_classified(make_client):
    with make_client({}):
        d = url_discoverer.discover("ftp://files.example.com/pub")
    assert d.failure.code == FailureCode.UNSUPPORTED_SCHEME
    assert d.failure.hint


def test_dns_not_found_classified(make_client):
    with make_client({}, dns_fail_hosts=("gone.example",)):
        d = url_discoverer.discover("https://gone.example/")
    assert d.failure.code == FailureCode.DNS_NOT_FOUND
    # www 变体同样解析失败时，最终仍是 DNS 分类
    assert "https://www.gone.example/" in d.tried_urls


def test_connection_refused_classified(make_client):
    class _Refused(httpx.MockTransport):
        def __init__(self):
            super().__init__(self._handler)

        def _handler(self, request):
            raise httpx.ConnectError("connection refused")

    fake = httpx.Client(transport=_Refused())
    import app.sources.discovery as disc_mod
    real = disc_mod.get_http_client
    disc_mod.get_http_client = lambda: fake
    try:
        import socket as _s
        real_getaddrinfo = _s.getaddrinfo
        _s.getaddrinfo = lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
        try:
            d = url_discoverer.discover("http://down.example.com/")
        finally:
            _s.getaddrinfo = real_getaddrinfo
    finally:
        disc_mod.get_http_client = real
        fake.close()
    assert d.failure.code == FailureCode.CONNECTION_FAILED


def test_timeout_classified(make_client):
    class _Timeout(httpx.MockTransport):
        def __init__(self):
            super().__init__(self._handler)

        def _handler(self, request):
            raise httpx.ConnectTimeout("timed out")

    fake = httpx.Client(transport=_Timeout())
    import app.sources.discovery as disc_mod
    real = disc_mod.get_http_client
    disc_mod.get_http_client = lambda: fake
    try:
        import socket as _s
        real_getaddrinfo = _s.getaddrinfo
        _s.getaddrinfo = lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
        try:
            d = url_discoverer.discover("http://slow.example.com/")
        finally:
            _s.getaddrinfo = real_getaddrinfo
    finally:
        disc_mod.get_http_client = real
        fake.close()
    assert d.failure.code == FailureCode.TIMEOUT


def test_ssrf_blocked_classified(make_client):
    with make_client({}):
        d = url_discoverer.discover("http://127.0.0.1:9000/admin")
    assert d.failure.code == FailureCode.SSRF_BLOCKED


def test_404_deep_path_classified(make_client):
    with make_client({}):
        d = url_discoverer.discover("https://site.example/deep/missing")
    assert d.failure.code == FailureCode.HTTP_NOT_FOUND
    assert d.failure.hint


def test_auth_required_classified(make_client):
    with make_client({
        "https://members.example.com/": httpx.Response(401, text="login required"),
    }):
        d = url_discoverer.discover("https://members.example.com/")
    assert d.failure.code == FailureCode.AUTH_REQUIRED


def test_cloudflare_challenge_classified_as_waf(make_client):
    cf = httpx.Response(
        403,
        text="<html><title>Just a moment...</title></html>",
        headers={"server": "cloudflare", "cf-mitigated": "challenge"},
    )
    with make_client({"https://shielded.example.com/": cf}):
        d = url_discoverer.discover("https://shielded.example.com/")
    assert d.failure.code == FailureCode.BLOCKED_BY_WAF


def test_rate_limited_classified(make_client):
    with make_client({
        "https://throttled.example.com/": httpx.Response(429, text="slow down"),
    }):
        d = url_discoverer.discover("https://throttled.example.com/")
    assert d.failure.code == FailureCode.RATE_LIMITED


def test_server_error_classified(make_client):
    with make_client({
        "https://broken.example.com/": httpx.Response(503, text="oops"),
    }):
        d = url_discoverer.discover("https://broken.example.com/")
    assert d.failure.code == FailureCode.SERVER_ERROR


def test_binary_content_classified(make_client):
    png = httpx.Response(200, content=b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                         headers={"content-type": "image/png"})
    with make_client({"https://cdn.example.com/pic.png": png}):
        d = url_discoverer.discover("https://cdn.example.com/pic.png")
    assert d.failure.code == FailureCode.NOT_A_WEBPAGE


def test_pdf_by_magic_bytes_classified(make_client):
    pdf = httpx.Response(200, content=b"%PDF-1.4 fake body",
                         headers={"content-type": "application/octet-stream"})
    with make_client({"https://files.example.com/doc": pdf}):
        d = url_discoverer.discover("https://files.example.com/doc")
    assert d.failure.code == FailureCode.NOT_A_WEBPAGE


def test_spa_page_classified(make_client):
    with make_client({
        "https://spa.example.com/": httpx.Response(200, text=SPA_HTML),
    }):
        d = url_discoverer.discover("https://spa.example.com/")
    assert d.failure.code == FailureCode.JS_RENDERED_PAGE
    assert "JavaScript" in d.failure.message


def test_nav_shell_page_classified_as_js(make_client):
    """回归：客户端渲染的标签/栏目页——服务端只有导航壳，正文文本量
    可能不低（页脚/导航），不能用文本长度做 SPA 判定的硬性短路。"""
    with make_client({
        "https://site.example/tag/weekly": httpx.Response(200, text=NAV_SHELL_HTML),
    }):
        d = url_discoverer.discover("https://site.example/tag/weekly")
    assert d.failure.code == FailureCode.JS_RENDERED_PAGE


def test_article_page_classified_with_no_list(make_client):
    """单篇文章详情页（无 feed 声明）→ NO_LIST_STRUCTURE + 详情页提示"""
    with make_client({
        "https://blog.example.com/posts/long-story": httpx.Response(200, text=ARTICLE_NO_FEED_HTML),
    }):
        d = url_discoverer.discover("https://blog.example.com/posts/long-story")
    assert d.failure.code == FailureCode.NO_LIST_STRUCTURE
    assert "文章详情页" in d.failure.hint


def test_redirect_loop_classified(make_client):
    loop = httpx.Response(301, headers={"location": "https://loopy.example.com/"})
    with make_client({"https://loopy.example.com/": loop}):
        d = url_discoverer.discover("https://loopy.example.com/")
    assert d.failure.code == FailureCode.REDIRECT_LIMIT


def test_invalid_input_classified(make_client):
    for bad in ("", "   ", "http://", "not a url !!"):
        d = url_discoverer.discover(bad)
        assert d.failure.code == FailureCode.INVALID_URL, bad
        assert d.errors, "错误清单必须同步人读文案"


def test_tried_urls_transparent_on_failure(make_client):
    """失败结果必须透明列出实际尝试过的地址（含探测回退）"""
    with make_client({}, dns_fail_hosts=("site.example",)):
        d = url_discoverer.discover("https://site.example/")
    assert d.failure.code == FailureCode.DNS_NOT_FOUND
    assert d.tried_urls[0] == "https://site.example/"
    assert "https://www.site.example/" in d.tried_urls
