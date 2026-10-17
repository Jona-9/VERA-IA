import React, { useEffect, useState } from 'react'
import type { DashboardData } from '../types'
import { api } from '../api'
import { Tile } from '../components/Tile'
import { Tag } from '../components/Tag'

const PASTEL = ['#A8C5F0', '#F6C1B2', '#B9E3C6', '#F3DFA2', '#D3C0F0', '#F2B8D0']

interface ChartItem {
  label: string
  value: number
  color?: string
}

interface BarChartProps {
  title: string
  bars: ChartItem[]
}

const PieChart: React.FC<BarChartProps> = ({ title, bars }) => {
  const total = bars.reduce((a, b) => a + b.value, 0)
  let acc = 0
  const stops = bars.map((b, i) => {
    const start = (acc / Math.max(total, 1)) * 100
    acc += b.value
    return `${b.color ?? PASTEL[i % PASTEL.length]} ${start}% ${(acc / Math.max(total, 1)) * 100}%`
  })
  return (
    <div className="flex flex-col gap-3 border border-[var(--muted)] rounded-2xl p-4">
      <h3 className="text-sm font-semibold text-[var(--ink)]">{title}</h3>
      <div className="flex items-center gap-6 h-44">
        <div
          className="w-36 h-36 rounded-full shrink-0"
          style={{ background: total ? `conic-gradient(${stops.join(', ')})` : '#F0F0EC' }}
        />
        <ul className="flex flex-col gap-1.5 text-xs">
          {bars.map((b, i) => (
            <li key={b.label} className="flex items-center gap-2 text-[var(--ink)]">
              <span className="w-3 h-3 rounded-full" style={{ backgroundColor: b.color ?? PASTEL[i % PASTEL.length] }} />
              <span>{b.label}</span>
              <span className="font-bold">
                {b.value}
                {total ? ` (${Math.round((b.value / total) * 100)}%)` : ''}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

const BarChart: React.FC<BarChartProps> = ({ title, bars }) => {
  const max = Math.max(...bars.map((b) => b.value), 1)
  return (
    <div className="flex flex-col gap-3 border border-[var(--muted)] rounded-2xl p-4">
      <h3 className="text-sm font-semibold text-[var(--ink)]">{title}</h3>
      <div className="flex items-end gap-3 h-44 border-b border-[#ECECE8]">
        {bars.map((b, i) => (
          <div key={b.label} className="flex-1 h-full flex flex-col justify-end items-center gap-1">
            <span className="text-xs font-bold text-[var(--ink)]">{b.value}</span>
            <div
              className="w-full max-w-[56px] rounded-t-lg transition-all duration-500"
              style={{ height: `${(b.value / max) * 85}%`, minHeight: b.value ? 4 : 0, backgroundColor: b.color ?? PASTEL[i % PASTEL.length] }}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-3">
        {bars.map((b) => (
          <span key={b.label} className="flex-1 text-center text-[11px] text-[var(--muted)] leading-tight">
            {b.label}
          </span>
        ))}
      </div>
    </div>
  )
}

interface DashboardViewProps {
  onNavigateToReview: (caseId?: string) => void
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigateToReview }) => {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  const loadDashboard = async () => {
    try {
      setLoading(true)
      const res = await api.getDashboard()
      setData(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  if (loading) {
    return <div className="page py-12 text-center text-[var(--muted)]">Cargando Dashboard…</div>
  }

  if (!data) {
    return <div className="page py-12 text-center text-red-600">Error al cargar datos del Dashboard.</div>
  }

  const {
    resolved_by_ai,
    resolved_by_ai_pct,
    human_review_required,
    human_review_pct,
    cases_status,
    pending_cases,
    resolved_cases,
  } = data

  const countBy = (keyOf: (c: (typeof pending_cases)[number]) => string, order: string[]) =>
    order.map((label) => ({ label, value: pending_cases.filter((c) => keyOf(c) === label).length }))
  const dueBars = countBy(
    (c) => (c.days_to_due <= 0 ? 'Vencido / hoy' : c.days_to_due <= 2 ? '1–2 días' : c.days_to_due <= 4 ? '3–4 días' : '5+ días'),
    ['Vencido / hoy', '1–2 días', '3–4 días', '5+ días']
  ).map((b, i) => ({ ...b, color: ['#F6B7B0', '#F7D3A6', '#F3E7A4', '#B9E3C6'][i] }))
  const riskBars = countBy(
    (c) => ({ BAJA: 'Bajo', MODERADA: 'Moderado', ALTA: 'Alto' } as Record<string, string>)[c.risk_band ?? ''] ?? 'Sin evaluar',
    ['Bajo', 'Moderado', 'Alto', 'Sin evaluar']
  ).map((b, i) => ({ ...b, color: ['#B9E3C6', '#F3E7A4', '#F6B7B0', '#D9DCE3'][i] }))
  const portfolioPie: ChartItem[] = [
    { label: 'Resueltas por IA', value: resolved_by_ai, color: '#A8C5F0' },
    { label: 'En revisión', value: human_review_required, color: '#F6C1B2' },
  ]
  const queuePie: ChartItem[] = [
    { label: 'Pendientes de hoy', value: cases_status.pending_today, color: '#D3C0F0' },
    { label: 'Arrastrados', value: cases_status.pending_carryover, color: '#F2B8D0' },
  ]

  return (
    <main className="page gap-8">
      <section className="hero">
        <h1>Dashboard</h1>
        <p className="muted">
          Monitoreo integral: resoluciones autónomas por IA, gestión humana de excepciones y efectividad del agente.
        </p>
      </section>

      {/* KPI Cards: AI vs Human & Status */}
      <section className="stack">
        <h2 className="section-title">Resolución del agente vs. Revisión humana</h2>
        <div className="tiles">
          <Tile
            number={resolved_by_ai}
            title="Resueltas por IA"
            text={`${resolved_by_ai_pct}% de la cartera gestionada de forma 100% autónoma sin intervención humana.`}
          />
          <Tile
            number={human_review_required}
            title="Derivadas a revisión"
            text={`${human_review_pct}% de la cartera con excepciones o pagos en trámite que requieren tu visto bueno.`}
            onClick={() => onNavigateToReview()}
            muted={human_review_required === 0}
          />
          <Tile
            number={cases_status.pending_carryover}
            title="Arrastrados de días previos"
            text="Casos que no se revisaron a tiempo y pasaron en cola al día siguiente."
            muted={cases_status.pending_carryover === 0}
            onClick={cases_status.pending_carryover > 0 ? () => onNavigateToReview() : undefined}
          />
          <Tile
            number={cases_status.resolved_count}
            title="Casos resueltos por analista"
            text="Decisiones evaluadas, confirmadas y auditadas en la sesión."
          />
        </div>
      </section>

      {/* Casos pendientes no revisados: gráficos de barras */}
      <section className="card card-pad stack">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#ECECE8] pb-3">
          <div>
            <h2 className="section-title text-base font-semibold">
              Casos pendientes no revisados ({pending_cases.length})
            </h2>
            <p className="small muted">
              {cases_status.pending_today} pendientes de hoy · {cases_status.pending_carryover} arrastrados de días anteriores
            </p>
          </div>
          {pending_cases.length > 0 && (
            <button
              type="button"
              className="btn btn-primary text-xs !min-h-[38px] !px-4"
              onClick={() => onNavigateToReview()}
            >
              Abrir cola de revisión →
            </button>
          )}
        </div>

        {pending_cases.length === 0 ? (
          <p className="text-sm text-[var(--muted)] py-4">No hay casos pendientes de revisión.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-2">
            <BarChart title="Por vencimiento" bars={dueBars} />
            <BarChart title="Por nivel de riesgo" bars={riskBars} />
            <PieChart title="Cartera: IA vs. revisión humana" bars={portfolioPie} />
            <PieChart title="Cola: hoy vs. arrastrados" bars={queuePie} />
          </div>
        )}
      </section>

      {/* Historial de casos resueltos por analista si hay */}
      {resolved_cases.length > 0 && (
        <section className="card card-pad stack">
          <h2 className="section-title text-base font-semibold">
            Últimos casos resueltos y auditados ({resolved_cases.length})
          </h2>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Cliente</th>
                  <th>Cuenta</th>
                  <th>Motivo original</th>
                  <th>Estado</th>
                  <th>Resuelto por</th>
                  <th>Fecha y hora</th>
                </tr>
              </thead>
              <tbody>
                {resolved_cases.map((rc) => (
                  <tr key={rc.case_id}>
                    <td className="font-medium">{rc.customer_name}</td>
                    <td>{rc.account_id}</td>
                    <td className="text-xs">{rc.reason}</td>
                    <td>
                      <Tag text={rc.status} css="t-ok" />
                    </td>
                    <td className="text-xs text-[var(--muted)]">{rc.resolved_by}</td>
                    <td className="text-xs text-[var(--muted)] whitespace-nowrap">{rc.resolved_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  )
}
