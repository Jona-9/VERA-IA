export interface SimulationStatus {
  day_number: number
  current_date: string
  date_label: string
  phase: string
  in_review: boolean
  header_note: string
  review_count: number
  total_portfolio?: number
  resolved_by_ai?: number
  smtp_ok: boolean
}

export interface ThoughtStep {
  step: number
  title: string
  tool: string
  detail: string
  observation: string
  status: 'SUCCESS' | 'BLOCKED' | 'INFO' | 'WARNING' | string
  timestamp?: string
}

export interface AgentThoughtTrace {
  account_id: string
  customer_name: string
  cycle_date: string
  steps: ThoughtStep[]
  final_verdict: string
  constitutional_rule: string
  llm_analysis?: string | null
  used_llm?: boolean
}

export interface ReviewCase {
  case_id: string
  account_id: string
  customer_name: string
  days_to_due: number
  when_text: string
  is_urgent: boolean
  risk_band?: string
  reason: string
  agent_hypothesis?: string
  customer_context?: string
  why_manual_approval?: string
  status_code?: 'PENDIENTE_HOY' | 'ARRAS_TRADO' | 'RESUELTO' | string
  status_label?: string
  status_css?: string
  is_carryover?: boolean
  opened_date?: string
  facts?: Array<{ k: string; v: string }>
  message_preview?: { subject: string; body_text: string } | null
  default_amount?: number
  default_date?: string
  thought_trace?: AgentThoughtTrace | null
}

export interface TodayData {
  headline: string
  lead: string
  in_review: boolean
  total_portfolio: number
  review_count: number
  resolved_by_ai_count: number
  cases: ReviewCase[]
  counts: {
    programados: number
    enviados: number
    retenidos: number
  }
  early_signals: number
  reminders: number
  no_action: number
  agent_trace?: AgentThoughtTrace | null
}

export interface NoticeItem {
  notice_id: string
  account_id: string
  customer_name: string
  date: string
  tone: string
  tone_label: string
  status: string
  status_label: string
  status_css: string
  subject: string
  body_text: string
  validation_status: string
  rejection_reason?: string
}

export interface CapturedEmail {
  email_id: string
  sender: string
  recipient: string
  subject: string
  body: string
  captured_at: string
  captured_date_label: string
}

export interface PortfolioClient {
  account_id: string
  customer_name: string
  email: string
  due_date: string
  days_to_due: number
  when_text: string
  is_urgent: boolean
  balance: number
  balance_money: string
  credit_limit: number
  limit_money: string
  utilization: number
  utilization_pct: string
  status: string
  paid: boolean
  risk_band: string
  risk_label: string
  risk_css: string
  probability?: number
  probability_pct: string
  evidence: string
  evidence_label: string
  action: string
  action_label: string
  rule: string
  explanation: string
  in_review: boolean
  early_signal: boolean
  summary: string
}

export interface ClientDossier {
  account_id: string
  customer_name: string
  email: string
  due_date: string
  days_to_due: number
  when_text: string
  is_urgent: boolean
  balance: string
  credit_limit: string
  utilization: string
  probability_pct: string
  risk_band: string
  risk_label: string
  risk_css: string
  evidence: string
  evidence_label: string
  action: string
  action_label: string
  rule: string
  explanation: string
  signals: {
    credit_utilization_ratio: string
    consecutive_min_payments: number
    payment_to_billed_ratio: string
    payment_ratio_drop: string
    historical_delinquency_rate: string
    max_past_due_days: number
  }
  history: Array<{
    period_index: number
    billed_amount: string
    paid_amount: string
    due_date: string
    actual_payment_date: string
    days_past_due: number
    line_utilization: string
  }>
  notices: Array<{
    notice_id: string
    scheduled_date: string
    tone: string
    tone_label: string
    status: string
    status_label: string
    status_css: string
    subject: string
    rejection_reason?: string
  }>
  audit: Array<{
    timestamp: string
    event_type: string
    actor: string
    payload: string
  }>
  thought_trace?: AgentThoughtTrace | null
}

export interface BenchmarkData {
  calculated: boolean
  data?: {
    seed: number
    cutoff_date: string
    horizon_days: number
    low_moderate_reduction: number
    agent: {
      accounts: number
      total_notices: number
      notices_low_moderate: number
      paid_before_due: number
      paid_on_time: number
      on_time_rate: number
      avg_anticipation_days: number
      notices_while_payment_in_process: number
    }
    fixed: {
      accounts: number
      total_notices: number
      notices_low_moderate: number
      paid_before_due: number
      paid_on_time: number
      on_time_rate: number
      avg_anticipation_days: number
      notices_while_payment_in_process: number
    }
  }
}

export interface DashboardData {
  total_portfolio: number
  resolved_by_ai: number
  resolved_by_ai_pct: number
  human_review_required: number
  human_review_pct: number
  cases_status: {
    pending_total: number
    pending_today: number
    pending_carryover: number
    resolved_count: number
  }
  pending_cases: ReviewCase[]
  resolved_cases: Array<{
    case_id: string
    account_id: string
    customer_name: string
    reason: string
    status: string
    risk_band: string
    resolved_by: string
    resolved_at: string
  }>
  notices_counts: {
    programados: number
    enviados: number
    retenidos: number
  }
  benchmark: BenchmarkData
}
