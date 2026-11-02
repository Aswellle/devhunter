"""
app/core/ssrf.py
SSRF 防护核心：URL 预检 + 连接层 IP pinning 网络后端。

两层防线，职责明确互补：

1. URL 预检（resolve_and_validate_url）——请求发出前的快速失败层：
   解析 DNS、逐条记录校验 IP、主机名策略（metadata.* 黑名单、协议白名单）、
   fail-closed。给调用方明确、即时的拒绝信息，避免无谓的网络 I/O。

2. 连接层 enforcement（SSRFPinnedNetworkBackend）——httpcore 真正建立
   TCP 连接时回调 connect_tcp，在这里再次解析 DNS 并逐地址校验，只拨号到
   通过黑名单的 IP。解析与拨号发生在同一次调用内，不存在「先校验、后
   请求」的时间窗，DNS rebinding（TOCTOU）被彻底关闭。即使某个新代码
   路径遗漏了 URL 预检，传输层仍然兜底。

TLS 不受 pinning 影响：httpcore 在 TLS 握手时使用 URL 原始主机名作为
SNI 与证书校验目标（server_hostname 取自 origin.host，而非 connect_tcp
实际拨号的地址，见 httpcore/_sync/connection.py；httpx==0.28.1 /
httpcore==1.0.9 已验证）。因此「按已验证 IP 建立连接 + 按原主机名校验
证书」是自洽的，https 站点不受影响。

两层判定保持一致：主机名的任一解析记录命中黑名单即整体拒绝（与
resolve_and_validate_url 的既有语义相同），不允许「跳过私有的记录、
拨号公网记录」的不一致行为。

URL 策略（metadata.* 主机名、协议白名单）只在预检层实现；连接层只做
IP 级地址校验，不重复主机名策略——单一策略归属，避免两处规则漂移。

已知取舍（有意为之）：
- 不做 DNS 结果缓存：每次新建连接都重新解析，宁可多付一次解析开销，
  也不引入「缓存里的 IP 未重新校验」的新风险；连接池复用会摊薄成本。
- 若部署方通过环境变量配置了 HTTP(S) 代理（httpx trust_env），pinning
  只保护「到代理的连接」，目标主机解析发生在代理侧——使用代理属于
  运营者的显式信任决策，本模块不做二次判断。
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpcore
import httpx

logger = logging.getLogger(__name__)


# ─── IP 黑名单 ────────────────────────────────────────────────────────────────

# Reserved/private IP ranges that should be blocked
_PRIVATE_IP_BLOCKS = [
    ipaddress.ip_network("10.0.0.0/8"),       # Class A private
    ipaddress.ip_network("172.16.0.0/12"),     # Class B private
    ipaddress.ip_network("192.168.0.0/16"),    # Class C private
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local (including 169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),    # IETF Protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),    # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),     # Multicast
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    ipaddress.ip_network("::1/128"),          # Loopback (IPv6)
    ipaddress.ip_network("::/128"),           # Unspecified address (IPv6) — connect() targets localhost
    ipaddress.ip_network("64:ff9b::/96"),     # NAT64 well-known prefix (embeds IPv4)
    ipaddress.ip_network("fc00::/7"),         # Unique local (IPv6)
    ipaddress.ip_network("fe80::/10"),        # Link-local (IPv6)
]


def _blocklist_ip(ip_str: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """
    把地址字符串转为黑名单比对用 IP。

    IPv4-mapped IPv6（::ffff:a.b.c.d）与 IPv4 黑名单段版本不同，直接做
    in 判断恒为 False；OS 实际连接时会把它映射回 IPv4——必须先归一化，
    否则 mapped 形式的内网/元数据地址会绕过校验。
    """
    ip = ipaddress.ip_address(ip_str)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def _first_blocked_ip(ip_str: str) -> str | None:
    """命中黑名单返回原地址字符串，否则 None。"""
    ip = _blocklist_ip(ip_str)
    for block in _PRIVATE_IP_BLOCKS:
        if ip in block:
            return ip_str
    return None


# ─── URL 预检（快速失败层） ──────────────────────────────────────────────────

def _is_metadata_host(hostname: str) -> bool:
    """云元数据端点的主机名策略，预检层专用。"""
    h = hostname.lower()
    if h in ("metadata.google.internal", "169.254.169.254"):
        return True
    return h.startswith("metadata.")


def resolve_and_validate_url(url: str) -> tuple[bool, str, str | None]:
    """
    请求前的 SSRF 预检：解析主机名、逐记录校验 IP 黑名单、fail-closed。

    返回 (is_safe, error_message, validated_ip_or_none)。第三项是首个通过
    校验的 IP（信息性用途，如日志），执法已下沉到传输层
    （SSRFPinnedNetworkBackend）——连接时会在同一次调用内重新解析并校验，
    预检不再依赖调用方「用返回的 IP 建立连接」来完成 pinning。
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"不支持的协议: {parsed.scheme}", None
        hostname = parsed.hostname
        if not hostname:
            return False, "无法解析的主机名", None
        hostname_lower = hostname.lower()
        if _is_metadata_host(hostname_lower):
            return False, f"禁止访问云元数据端点 ({hostname_lower})", None

        addr_info = socket.getaddrinfo(hostname_lower, None)
        if not addr_info:
            return False, "无法解析主机名对应的 IP 地址", None

        validated_ip = None
        for family, _, _, _, sockaddr in addr_info:
            if family not in (socket.AF_INET, socket.AF_INET6):
                continue
            ip_str = sockaddr[0]
            blocked = _first_blocked_ip(ip_str)
            if blocked is not None:
                return False, f"禁止访问私有/保留 IP 地址: {blocked}", None
            if validated_ip is None:
                validated_ip = ip_str

        return True, "", validated_ip
    except Exception as e:
        # fail closed — malformed URL or DNS resolution error must block
        logger.debug("resolve_and_validate_url error: %s", e)
        return False, f"URL 安全校验失败: {e}", None


# ─── 连接层执法（IP pinning 后端） ───────────────────────────────────────────

def _safe_dial_targets(host: str, port: int) -> tuple[list[str], str | None]:
    """
    解析 host 并返回通过黑名单校验的 IP 地址列表，fail-closed。

    返回 (addresses, None) 或 ([], error_message)。任一解析记录命中黑名单
    即整体拒绝——与 resolve_and_validate_url 的语义一致，两层判定不漂移。
    """
    # IP 字面量：直接校验，不做 DNS
    try:
        literal = ipaddress.ip_address(host)
        if _first_blocked_ip(str(literal)) is not None:
            return [], f"SSRF blocked: {host} is a private/reserved address"
        return [str(literal)], None
    except ValueError:
        pass  # 非字面量，走主机名解析

    try:
        addr_info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except Exception as e:
        return [], f"SSRF fail-closed: DNS resolution failed for {host}: {e}"
    if not addr_info:
        return [], f"SSRF fail-closed: no address resolved for {host}"

    targets: list[str] = []
    for family, _, _, _, sockaddr in addr_info:
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        ip_str = sockaddr[0]
        blocked = _first_blocked_ip(ip_str)
        if blocked is not None:
            return [], f"SSRF blocked: {host} resolves to private/reserved address {blocked}"
        if ip_str not in targets:
            targets.append(ip_str)
    return targets, None


class SSRFPinnedNetworkBackend(httpcore.NetworkBackend):
    """
    只拨号到通过 SSRF 校验地址的 httpcore 网络后端（关闭 DNS rebinding TOCTOU）。

    connect_tcp 收到的 host 是 URL 原始主机名（httpcore origin）。这里解析
    并校验后，把 TCP 连接指向校验通过的 IP；TLS 层的 SNI 与证书校验仍使用
    原始主机名（server_hostname 由 httpcore 取自 origin.host），https 不受影响。

    dial 注入真实拨号后端：生产环境由 SSRFPinnedTransport 把连接池中被
    替换下来的默认后端（httpcore.SyncBackend）传入；测试注入
    httpcore.MockBackend 或自定义桩。
    """

    def __init__(self, dial: httpcore.NetworkBackend):
        self._dial = dial

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        targets, err = _safe_dial_targets(host, port)
        if not targets:
            # 拦截/解析失败对上层表现为连接错误（httpx.ConnectError），
            # 走引擎既有的网络错误处理路径，错误信息保持可读
            raise httpcore.ConnectError(err)

        last_exc: Exception | None = None
        for ip in targets:
            try:
                return self._dial.connect_tcp(
                    ip, port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                # 该 IP 连接失败（对端拒绝/超时）不是安全问题：按解析顺序
                # 尝试下一个通过校验的地址，与 socket.create_connection
                # 遍历解析结果的默认行为对齐
                last_exc = e
        assert last_exc is not None
        # 保留原始异常类型（ConnectTimeout/ConnectError），不重新包装，
        # 让引擎的超时/网络错误分类保持准确
        raise last_exc

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ):
        # Unix domain socket 不经过 IP 层，无 SSRF 面；本项目的爬取客户端
        # 也不使用 UDS，委托保持行为一致
        return self._dial.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options,
        )


class SSRFPinnedTransport(httpx.HTTPTransport):
    """
    httpx.HTTPTransport，连接池使用 SSRFPinnedNetworkBackend。

    httpcore.ConnectionPool 的 network_backend 是公开参数，但 httpx 0.28 的
    HTTPTransport 构造时未透传，这里在构造后替换连接池默认后端。依赖两个
    内部属性（HTTPTransport._pool 与 ConnectionPool._network_backend，
    httpx==0.28.1 / httpcore==1.0.9 已验证）：属性缺失时立即抛错启动失败——
    绝不允许静默退化为无 pinning 的传输。
    """

    def __init__(self, dial_backend: httpcore.NetworkBackend | None = None, **kwargs):
        super().__init__(**kwargs)
        stock = getattr(self._pool, "_network_backend", None)
        if stock is None:
            raise RuntimeError(
                "httpx/httpcore internals changed: ConnectionPool._network_backend "
                "not found; the SSRF pinning transport cannot be wired. "
                "Check pinned versions (httpx==0.28.1, httpcore==1.0.9) or "
                "update app/core/ssrf.py."
            )
        self._pool._network_backend = SSRFPinnedNetworkBackend(
            dial=dial_backend or stock,
        )
