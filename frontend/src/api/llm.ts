import client from './client'
import type {
  LLMConfigPayload,
  LLMConfigStatus,
  LLMModelsResult,
  LLMReceiptsOverview,
  LLMTestResult,
} from '../types'

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

  /** 用表单参数拉取服务商可用模型列表（空字段沿用当前生效值） */
  getModels: (payload: LLMConfigPayload) =>
    client.post<LLMModelsResult>('/llm/models', payload).then((r) => r.data),

  /** 当日调用汇总 + 回执分页（created_at 倒序） */
  getReceipts: (limit: number = 10, offset: number = 0) =>
    client.get<LLMReceiptsOverview>('/llm/receipts', { params: { limit, offset } }).then((r) => r.data),
}
