import React, { useEffect, useState } from 'react'
import type { ClientDossier, PortfolioClient } from '../types'
import { api } from '../api'
import { Tag, BandTag } from '../components/Tag'
import { CaseRow } from '../components/CaseRow'

interface PortfolioViewProps {
  initialAccountId?: string
  initialFilter?: string
}

export const PortfolioView: React.FC<PortfolioViewProps> = ({
  initialAccountId,
  initialFilter,
}) => {
  const [clients, setClients] = useState<PortfolioClient[]>([])
  const [totalPortfolio, setTotalPortfolio] = useState<number>(0)
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    initialAccountId || null
  )
  const [dossier, setDossier] = useState<ClientDossier | null>(null)

  // Filters
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<string>(initialFilter || 'Todos')
  const [loading, setLoading] = useState(true)
  const [loadingDossier, setLoadingDossier] = useState(false)

  // Probe tool state
  const [probing, setProbing] = useState(false)
  const [probeResult, setProbeResult] = useState<{
    success: boolean
    rejection_code?: string
    message: string
  } | null>(null)
  const [showAudit, setShowAudit] = useState(false)

  const loadPortfolio = async () => {
    try {
      setLoading(true)
      const res = await api.getPortfolio(query, filter)
      setClients(res.clients)
      setTotalPortfolio(res.total_portfolio)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const loadDossier = async (accountId: string) => {
    try {
      setLoadingDossier(true)
      setProbeResult(null)
      setShowAudit(false)
      const res = await api.getClientDossier(accountId)
      setDossier(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingDossier(false)
    }
  }

  useEffect(() => {
    loadPortfolio()
  }, [query, filter])

  useEffect(() => {
    if (selectedAccountId) {
      loadDossier(selectedAccountId)
    } else {
      setDossier(null)
    }
  }, [selectedAccountId])

  const handleProbe = async () => {
    if (!selectedAccountId) return
    try {
      setProbing(true)
      const res = await api.probeTool(selectedAccountId)
      setProbeResult(res)
      // Reload dossier notices & audit
      await loadDossier(selectedAccountId)
    } catch (err) {
      alert(`Error al probar herramienta: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setProbing(false)
    }
  }

  // --- DOSSIER VIEW ---
  if (selectedAccountId && dossier) {
    return (
      <main className="page gap-4">
        <div>
          <button
            type="button"
            className="link-s font-medium"
            onClick={() => setSelectedAccountId(null)}
          >
            ← Todos los clientes
          </button>
        </div>

        {loadingDossier ? (
          <div className="py-12 text-center text-[var(--muted)]">Cargando expediente…</div>
        ) : (
          <div className="flex flex-col gap-6">
            {/* Header Card */}
            <div className="card card-pad stack">
              <h2 className="section-title text-2xl">{dossier.customer_name}</h2>
              <p className="small muted">
                {dossier.account_id} · {dossier.email}
              </p>

              <div className="flex flex-wrap items-center gap-2">
                <BandTag band={dossier.risk_band} />
                {dossier.evidence !== '—' && (
                  <Tag text={`Evidencia ${dossier.evidence_label}`} css="t-soon" />
                )}
                <Tag
                  text={dossier.when_text}
                  css={dossier.is_urgent ? 't-urgent' : 't-soon'}
                />
              </div>

              {/* KV Grid */}
              <div className="kv pt-2 border-t border-[#ECECE8]">
                <div>
                  <div className="k">Saldo</div>
                  <div className="v">{dossier.balance}</div>
                </div>
                <div>
                  <div className="k">Límite</div>
                  <div className="v">{dossier.credit_limit}</div>
                </div>
                <div>
                  <div className="k">Uso de línea</div>
                  <div className="v">{dossier.utilization}</div>
                </div>
                <div>
                  <div className="k">Vencimiento</div>
                  <div className="v">{dossier.when_text}</div>
                </div>
                <div>
                  <div className="k">Prob. de atraso</div>
                  <div className="v">{dossier.probability_pct}</div>
                </div>
              </div>

              <p className="small muted pt-2 border-t border-[#ECECE8]">
                <strong>Decisión del agente:</strong> {dossier.action_label} ({dossier.rule}).{' '}
                {dossier.explanation}
              </p>
            </div>

            {/* Señales Table */}
            <div className="card card-pad stack overflow-x-auto">
              <h3 className="section-title text-base">Señales a la fecha de corte</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Uso de línea</th>
                    <th>Pagos mín. seguidos</th>
                    <th>Pagado / facturado</th>
                    <th>Caída del ratio</th>
                    <th>Períodos con atraso</th>
                    <th>Máx. días atraso</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{dossier.signals.credit_utilization_ratio}</td>
                    <td>{dossier.signals.consecutive_min_payments}</td>
                    <td>{dossier.signals.payment_to_billed_ratio}</td>
                    <td>{dossier.signals.payment_ratio_drop}</td>
                    <td>{dossier.signals.historical_delinquency_rate}</td>
                    <td>{dossier.signals.max_past_due_days}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Historial Table */}
            <div className="card card-pad stack overflow-x-auto">
              <h3 className="section-title text-base">Historial de períodos</h3>
              {dossier.history.length === 0 ? (
                <p className="small muted">Sin historial registrado.</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Período</th>
                      <th>Facturado</th>
                      <th>Pagado</th>
                      <th>Vencía</th>
                      <th>Pagó el</th>
                      <th>Días atraso</th>
                      <th>Uso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dossier.history.map((h) => (
                      <tr key={h.period_index}>
                        <td>{h.period_index}</td>
                        <td>{h.billed_amount}</td>
                        <td>{h.paid_amount}</td>
                        <td>{h.due_date}</td>
                        <td>{h.actual_payment_date}</td>
                        <td>{h.days_past_due}</td>
                        <td>{h.line_utilization}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Avisos */}
            <div className="card card-pad stack">
              <h3 className="section-title text-base">Avisos</h3>
              {dossier.notices.length === 0 ? (
                <p className="small muted">Sin avisos todavía.</p>
              ) : (
                <div className="rounded-xl border border-[#ECECE8] overflow-hidden">
                  {dossier.notices.map((n) => (
                    <CaseRow
                      key={n.notice_id}
                      name={`${n.scheduled_date} · ${n.tone_label}`}
                      tag={<Tag text={n.status_label} css={n.status_css} />}
                      summary={n.rejection_reason || n.subject}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Probar límites de la herramienta */}
            <div className="card card-pad stack">
              <h3 className="section-title text-base">Probar los límites de la herramienta</h3>
              <p className="small muted">
                Pide al agente un aviso adicional hoy. La herramienta decide: si rompe la política,
                lo rechaza con un código.
              </p>

              <div>
                <button
                  type="button"
                  className="btn"
                  disabled={probing}
                  onClick={handleProbe}
                >
                  {probing ? 'Verificando con la herramienta…' : 'Intentar programar un aviso hoy'}
                </button>
              </div>

              {probeResult && (
                <div
                  className={`p-4 rounded-xl text-sm ${
                    probeResult.success
                      ? 'bg-blue-50 text-blue-800 border border-blue-200'
                      : 'bg-rose-50 text-rose-800 border border-rose-200'
                  }`}
                >
                  {probeResult.success ? (
                    <span>
                      ✓ La política lo permite: aviso aprobado para las 10:00. {probeResult.message}
                    </span>
                  ) : (
                    <span>
                      ✕ Rechazado por la herramienta ({probeResult.rejection_code}).{' '}
                      {probeResult.message}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Auditoría Expandable */}
            <div className="card overflow-hidden">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setShowAudit(!showAudit)}
                onKeyDown={(e) => e.key === 'Enter' && setShowAudit(!showAudit)}
                className="p-4 flex items-center justify-between cursor-pointer hover:bg-[#F7F7F4] font-semibold text-sm"
              >
                <span>Auditoría ({dossier.audit.length} eventos)</span>
                <span>{showAudit ? '▲' : '▼'}</span>
              </div>

              {showAudit && (
                <div className="p-4 pt-0 border-t border-[#ECECE8] overflow-x-auto">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Cuándo</th>
                        <th>Evento</th>
                        <th>Actor</th>
                        <th>Detalle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dossier.audit.map((l, idx) => (
                        <tr key={idx}>
                          <td className="whitespace-nowrap">{l.timestamp}</td>
                          <td>{l.event_type}</td>
                          <td>{l.actor}</td>
                          <td className="text-xs break-all">{l.payload}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    )
  }

  // --- LIST VIEW ---
  return (
    <main className="page gap-4">
      <section className="hero">
        <h1>Clientes</h1>
        <p className="muted">
          La cartera a la fecha simulada, con la decisión más reciente del agente.
        </p>
      </section>

      {/* Search and Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 mt-4">
        <div className="sm:col-span-7">
          <input
            type="text"
            placeholder="Buscar por nombre o número de cuenta…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="form-input"
          />
        </div>

        <div className="sm:col-span-5">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="form-select"
          >
            <option value="Todos">Todos</option>
            <option value="senales">Señales tempranas</option>
            <option value="revision">En revisión</option>
            <option value="alto_critico">Riesgo alto o crítico</option>
            <option value="con_saldo">Con saldo pendiente</option>
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-[var(--muted)] px-1">
        <span>
          {clients.length} de {totalPortfolio} clientes
        </span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-[var(--muted)]">Cargando cartera…</div>
      ) : clients.length === 0 ? (
        <div className="card card-pad">
          <p className="muted">Ningún cliente coincide con la búsqueda.</p>
        </div>
      ) : (
        <section className="card overflow-hidden">
          {clients.map((c) => {
            let tags = <BandTag band={c.risk_band} />
            if (c.early_signal) {
              tags = (
                <div className="flex items-center gap-1">
                  {tags}
                  <Tag text="Señal temprana" css="t-info" />
                </div>
              )
            }
            if (c.paid) {
              tags = <Tag text="Pagó" css="t-ok" />
            }
            return (
              <CaseRow
                key={c.account_id}
                name={c.customer_name}
                tag={tags}
                summary={c.summary}
                onClick={() => setSelectedAccountId(c.account_id)}
              />
            )
          })}
        </section>
      )}
    </main>
  )
}
