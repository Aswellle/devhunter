/**
 * utils/text.ts
 * 文本清洗工具（展示层）。
 */

/** 来源站点摘要末尾常见的"查看全文"类跳转提示 */
const READ_MORE_SUFFIX_RE = /(?:\s*(?:\.{2,}|…|。{2,}))?\s*(?:查看全文|阅读全文|查看原文|阅读原文|查看全部)\s*$/;

/**
 * 去掉摘要末尾的"查看全文 / 阅读全文"等提示词。
 *
 * 这些词是来源页面自身的跳转提示，被爬取进摘要后以纯文本渲染，
 * 与正文连成一体、看起来像可点击链接却点不动。展示层剥掉它，
 * 由卡片提供真正的「查看全文」链接（见 ClampText 的 readMoreHref）。
 */
export function stripReadMoreSuffix(text: string | null | undefined): string {
  if (!text) return ''
  return text.replace(READ_MORE_SUFFIX_RE, '').trimEnd()
}
