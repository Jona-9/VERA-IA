import type {
  BenchmarkData,
  ClientDossier,
  NoticeItem,
  PortfolioClient,
  ReviewCase,
  SimulationStatus,
  TodayData,
} from './types'

const BASE_URL = '/api'

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })
  if (!res.ok) {
    let errorMsg = `Error ${res.status}: ${res.statusText}`
    try {
      const errorJson = await res.json()
      if (errorJson.detail) errorMsg = errorJson.detail
    } catch {
      // ignore
    }
    throw new Error(errorMsg)
  }
  return res.json()
}

export const api = {
  getStatus: () => request<SimulationStatus>('/status'),
  closeDay: () => request<SimulationStatus>('/simulation/close-day', { method: 'POST' }),
  advanceDay: () => request<SimulationStatus>('/simulation/advance-day', { method: 'POST' }),
  resetDemo: () => request<SimulationStatus>('/simulation/reset', { method: 'POST' }),

  getToday: () => request<TodayData>('/today'),

  getReviewQueue: () => request<ReviewCase[]>('/review-queue'),
  reevaluateCase: (
    caseId: string,
    data: {
      confirmed: boolean
      amount?: number
      payment_date?: string
      analyst?: string
      notes?: string
    }
  ) =>
    request<{ success: boolean; summary: string }>(`/review-queue/${caseId}/reevaluate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getNotices: () => request<NoticeItem[]>('/notices'),
  getEmails: () =>
    request<
      Array<{
        email_id: string
        sender: string
        recipient: string
        subject: string
        body: string
        captured_at: string
        captured_date_label: string
      }>
    >('/emails'),

  getPortfolio: (query?: string, filter?: string) => {
    const params = new URLSearchParams()
    if (query) params.append('query', query)
    if (filter) params.append('filter', filter)
    const qs = params.toString() ? `?${params.toString()}` : ''
    return request<{ total_portfolio: number; total_filtered: number; clients: PortfolioClient[] }>(
      `/portfolio${qs}`
    )
  },

  getClientDossier: (accountId: string) => request<ClientDossier>(`/portfolio/${accountId}`),

  probeTool: (accountId: string) =>
    request<{ success: boolean; rejection_code?: string; message: string }>(
      `/portfolio/${accountId}/probe`,
      { method: 'POST' }
    ),

  getBenchmark: () => request<BenchmarkData>('/benchmark'),
  runBenchmark: () => request<BenchmarkData>('/benchmark/run', { method: 'POST' }),
}
