/**
 * 外链协议白名单：只放行 http(s)。
 *
 * 条目 URL 来自爬取的 HTML/RSS/JSON——urljoin 会原样放行
 * javascript:、data: 等伪协议。凡是以 href 渲染爬取来源 URL 的
 * 组件都应先用本函数判断，不安全时降级为纯文本展示。
 */
const SAFE_URL_PATTERN = /^https?:\/\//i

export function isSafeExternalUrl(url: string | null | undefined): boolean {
  return !!url && SAFE_URL_PATTERN.test(url.trim())
}
