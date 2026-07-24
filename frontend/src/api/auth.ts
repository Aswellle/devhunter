import client from './client'
import type { TokenResponse } from '../types'

export const authApi = {
  login: (password: string) =>
    client.post<TokenResponse>('/auth/login', { password }).then((r) => r.data),

  logout: () =>
    client.post('/auth/logout').then((r) => r.data),
}
