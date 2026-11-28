import client from './client'
import type {
  Opportunity, OpportunityStatus, OpportunityType, OpportunityPriority,
} from '../types'

export interface OpportunityCreatePayload {
  origin_type: 'item' | 'thread'
  origin_id: string
  title?: string
  opportunity_type?: OpportunityType
  status?: OpportunityStatus
  priority?: OpportunityPriority
  value_score?: number | null
  notes?: string
  tags?: string[]
  remind_at?: string | null
}

export interface OpportunityUpdatePayload {
  title?: string
  opportunity_type?: OpportunityType
  status?: OpportunityStatus
  priority?: OpportunityPriority
  value_score?: number | null
  notes?: string
  tags?: string[]
  remind_at?: string | null
}

export const opportunitiesApi = {
  list: (status?: string) =>
    client.get<Opportunity[]>('/opportunities', { params: status ? { status } : {} })
      .then((r) => r.data),

  get: (id: string) =>
    client.get<Opportunity>(`/opportunities/${id}`).then((r) => r.data),

  create: (payload: OpportunityCreatePayload) =>
    client.post<Opportunity>('/opportunities', payload).then((r) => r.data),

  update: (id: string, payload: OpportunityUpdatePayload) =>
    client.patch<Opportunity>(`/opportunities/${id}`, payload).then((r) => r.data),

  delete: (id: string) =>
    client.delete(`/opportunities/${id}`).then((r) => r.data),
}
