import React, { useEffect, useState } from 'react'
import type { DashboardData } from '../types'
import { api } from '../api'
import { Tile } from '../components/Tile'
import { Tag, BandTag } from '../components/Tag'

const AGENT_COLOR = '#1F3FBF'
const FIXED_COLOR = '#9AA0AA'

interface BarGroupProps {
  label: string
  agentVal: number
  fixedVal: number
  maxVal: number
}

const BarGroup: React.FC<BarGroupProps> = ({ label, agentVal, fixedVal, maxVal }) => {
  const safeMax = Math.max(maxVal, 1)
  const agentPct = (agentVal / safeMax) * 100
  const fixedPct = (fixedVal / safeMax) * 100

  return (
    <div className="flex flex-col gap-1.5 py-2">
      <div className="flex justify-between text-xs font-semibold text-[var(--ink)]">
        <span>{label}</span>
      </div>
      <div className="flex items-center gap-4">
        {/* Agente bar */}
        <div className="flex-1 flex flex-col gap-1">
          <div className="flex justify-between text-[11px] text-[var(--muted)]">
            <span className="font-medium text-[#1F3FBF]">Agente</span>
            <span className="font-bold text-[var(--ink)]">{agentVal}</span>
          </div>
          <div className="w-full bg-[#F0F0EC] h-5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${agentPct}%`, backgroundColor: AGENT_COLOR }}
            />
          </div>
        </div>

        {/* Campaña fija bar */}
        <div className="flex-1 flex flex-col gap-1">
          <div className="flex justify-between text-[11px] text-[var(--muted)]">
            <span className="font-medium text-[#7A808A]">Campaña fija</span>
            <span className="font-bold text-[var(--ink)]">{fixedVal}</span>
          </div>
          <div className="w-full bg-[#F0F0EC] h-5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${fixedPct}%`, backgroundColor: FIXED_COLOR }}
            />
          </div>
        </div>
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
  const [calculating, setCalculating] = useState(false)

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

  const handleRunBenchmark = async () => {
    try {
      setCalculating(true)
      await api.runBenchmark()
      await loadDashboard()
    } catch (err) {
      alert(`Error al calcular benchmark: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setCalculating(false)
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
    total_portfolio,
    resolved_by_ai,
    resolved_by_ai_pct,
    human_review_required,
    human_review_pct,
    cases_status,
    pending_cases,
    resolved_cases,
    benchmark,
  } = data

  const bData = benchmark?.data

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

      {/* Casos pendientes no revisados */}
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
          <div className="divide-y divide-[#EFEFEB]">
            {pending_cases.map((c) => (
              <div
                key={c.case_id}
                role="button"
                tabIndex={0}
                onClick={() => onNavigateToReview(c.case_id)}
                onKeyDown={(e) => e.key === 'Enter' && onNavigateToReview(c.case_id)}
                className="py-3.5 flex flex-col gap-1.5 hover:bg-[#F7F7F4] rounded-lg px-2 -mx-2 transition-colors cursor-pointer"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-[var(--ink)]">{c.customer_name}</span>
                    <span className="text-xs text-[var(--muted)]">({c.account_id})</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Tag
                      text={c.status_label || (c.is_carryover ? 'Arrastrado de ayer' : 'Pendiente hoy')}
                      css={c.status_css || (c.is_carryover ? 't-urgent' : 't-soon')}
                    />
                    <Tag text={c.when_text} css={c.is_urgent ? 't-urgent' : 't-soon'} />
                    <BandTag band={c.risk_band} />
                  </div>
                </div>

                {c.customer_context && (
                  <div className="text-xs text-[var(--muted)]">{c.customer_context}</div>
                )}

                {c.why_manual_approval && (
                  <div className="text-xs text-[#7A2E06] bg-[#FDF5E6] p-2 rounded-md border border-[#FBE6C6]">
                    <strong>Por qué debe ser aprobado manualmente:</strong> {c.why_manual_approval}
                  </div>
                )}
              </div>
            ))}
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

      {/* Sección Benchmark y Efectividad */}
      <section className="stack">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Efectividad del Agente vs. Campaña fija</h2>
          {bData && (
            <button
              type="button"
              className="link-s text-xs"
              disabled={calculating}
              onClick={handleRunBenchmark}
            >
              {calculating ? 'Recalculando…' : 'Recalcular benchmark'}
            </button>
          )}
        </div>

        {!bData ? (
          <div className="card card-pad stack">
            <p className="muted">
              Todavía no se calculó la comparación contra la campaña fija tradicional.
            </p>
            <div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={calculating}
                onClick={handleRunBenchmark}
              >
                {calculating ? 'Simulando 21 días con cada estrategia…' : 'Calcular comparación'}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <div className="tiles">
              <Tile
                number={`${Math.round(bData.low_moderate_reduction * 100)}%`}
                title="Menos avisos a riesgo bajo y moderado"
                text={`${bData.agent.notices_low_moderate} con el agente frente a ${bData.fixed.notices_low_moderate} con la campaña fija.`}
                muted={bData.low_moderate_reduction < 0.25}
              />
              <Tile
                number={`${bData.agent.avg_anticipation_days.toFixed(1)} días`}
                title="Anticipación promedio del pago"
                text={`Campaña fija: ${bData.fixed.avg_anticipation_days.toFixed(1)} días. Entre quienes pagaron a tiempo.`}
              />
              <Tile
                number={`${Math.round(bData.agent.on_time_rate * 100)}%`}
                title="Pago a tiempo"
                text={`Campaña fija: ${Math.round(bData.fixed.on_time_rate * 100)}%.`}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="card card-pad stack">
                <div className="flex items-center justify-between pb-2 border-b border-[#ECECE8]">
                  <h3 className="section-title text-base">Avisos enviados</h3>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="flex items-center gap-1 font-medium text-[#1F3FBF]">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#1F3FBF]"></span> Agente
                    </span>
                    <span className="flex items-center gap-1 font-medium text-[#7A808A]">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#9AA0AA]"></span> Fija
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-3">
                  <BarGroup
                    label="Total de avisos"
                    agentVal={bData.agent.total_notices}
                    fixedVal={bData.fixed.total_notices}
                    maxVal={Math.max(bData.agent.total_notices, bData.fixed.total_notices)}
                  />
                  <BarGroup
                    label="Riesgo bajo / moderado"
                    agentVal={bData.agent.notices_low_moderate}
                    fixedVal={bData.fixed.notices_low_moderate}
                    maxVal={Math.max(bData.agent.total_notices, bData.fixed.total_notices)}
                  />
                </div>
              </div>

              <div className="card card-pad stack">
                <div className="flex items-center justify-between pb-2 border-b border-[#ECECE8]">
                  <h3 className="section-title text-base">Pagos de clientes</h3>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="flex items-center gap-1 font-medium text-[#1F3FBF]">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#1F3FBF]"></span> Agente
                    </span>
                    <span className="flex items-center gap-1 font-medium text-[#7A808A]">
                      <span className="w-2.5 h-2.5 rounded-full bg-[#9AA0AA]"></span> Fija
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-3">
                  <BarGroup
                    label="Antes del vencimiento"
                    agentVal={bData.agent.paid_before_due}
                    fixedVal={bData.fixed.paid_before_due}
                    maxVal={bData.agent.accounts}
                  />
                  <BarGroup
                    label="A tiempo (≤ vencimiento)"
                    agentVal={bData.agent.paid_on_time}
                    fixedVal={bData.fixed.paid_on_time}
                    maxVal={bData.agent.accounts}
                  />
                </div>
              </div>
            </div>

            <div className="text-xs text-[var(--muted)] leading-relaxed">
              Semilla {bData.seed} · corte {bData.cutoff_date} · {bData.horizon_days} días ·{' '}
              {bData.agent.accounts} clientes en cartera ({total_portfolio} totales). Los avisos a clientes con pago en trámite fueron{' '}
              {bData.agent.notices_while_payment_in_process} con el agente y{' '}
              {bData.fixed.notices_while_payment_in_process} con la campaña fija.
            </div>
          </div>
        )}
      </section>
    </main>
  )
}
