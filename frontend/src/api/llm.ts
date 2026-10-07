import client from './client'
import type { LLMConfigPayload, LLMConfigStatus, LLMReceiptsOverview, LLMTestResult } from '../types'

export const llmApi = {
  /** 当前生效的 LLM 配置（密钥脱敏）与用量/熔断状态 */
  getConfig: () =>
    client.get<LLMConfigStatus>('/llm/config').then((r) => r.data),

  /** 保存界面配置：缺失/null 不改动，空字符串清除覆盖，保存后立即生效 */
  saveConfig: (payload: LLMConfigPayload) =>
    client.put<LLMConfigStatus>('/llm/config', payload).then((r) => r.data),

  /** 清除全部界面配置，回落环境变量 */
  clearConfig: () =>
    client.delete<LLMConfigStatus>('/llm/config').then((r) => r.data),

  /** 连通性测试：空字段沿用当前生效值，支持先测试再保存 */
  testConfig: (payload: LLMConfigPayload) =>
    client.post<LLMTestResult>('/llm/test', payload).then((r) => r.data),

  /** 当日调用汇总 + 最近付费回执（含失败原因） */
  getReceipts: (limit: number = 30) =>
    client.get<LLMReceiptsOverview>('/llm/receipts', { params: { limit } }).then((r) => r.data),
}
