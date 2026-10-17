import React, { useEffect, useState } from 'react'
import type { NavTab } from '../components/Navbar'
import type { TodayData } from '../types'
import { api } from '../api'
import { Tag, BandTag } from '../components/Tag'
import { Tile } from '../components/Tile'

interface TodayViewProps {
  onNavigate: (tab: NavTab, params?: { caseId?: string; filter?: string }) => void
}

const MAX_CASES = 5

export const TodayView: React.FC<TodayViewProps> = ({ onNavigate }) => {
  const [data, setData] = useState<TodayData | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const res = await api.getToday()
      setData(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  if (loading) {
    return <div className="page py-12 text-center text-[var(--muted)]">Cargando jornada de hoy…</div>
  }

  if (!data) {
    return <div className="page py-12 text-center text-red-600">Error al cargar datos.</div>
  }

  const { headline, lead, cases, reminders, early_signals, no_action, in_review } = data
  const n = cases.length

  return (
    <main className="page">
      <section className="hero">
        <h1>{headline}</h1>
        <p className="muted">{lead}</p>
        {n > 0 && in_review && (
          <div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onNavigate('por-revisar')}
            >
              Empezar revisión →
            </button>
          </div>
        )}
      </section>

      {n > 0 && (
        <section className="card overflow-hidden divide-y divide-[#EFEFEB]">
          {cases.slice(0, MAX_CASES).map((c) => (
            <div
              key={c.case_id}
              role="button"
              tabIndex={0}
              onClick={() => onNavigate('por-revisar', { caseId: c.case_id })}
              onKeyDown={(e) => e.key === 'Enter' && onNavigate('por-revisar', { caseId: c.case_id })}
              className="p-5 flex flex-col gap-2 hover:bg-[#F7F7F4] transition-colors cursor-pointer"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-base text-[var(--ink)]">{c.customer_name}</span>
                <div className="flex items-center gap-2">
                  <Tag
                    text={c.status_label || (c.is_carryover ? 'Arrastrado de ayer' : 'Pendiente hoy')}
                    css={c.status_css || (c.is_carryover ? 't-urgent' : 't-soon')}
                  />
                  <Tag
                    text={c.when_text}
                    css={c.is_urgent ? 't-urgent' : 't-soon'}
                  />
                  <BandTag band={c.risk_band} />
                </div>
              </div>

              {c.customer_context && (
                <div className="text-xs text-[var(--muted)]">
                  {c.customer_context}
                </div>
              )}

              {c.why_manual_approval && (
                <div className="text-xs text-[#7A2E06] bg-[#FDF5E6] border border-[#FBE6C6] p-2.5 rounded-lg leading-relaxed mt-1">
                  <strong>Por qué requiere aprobación manual:</strong> {c.why_manual_approval}
                </div>
              )}
            </div>
          ))}

          {n > MAX_CASES && (
            <div
              role="button"
              tabIndex={0}
              onClick={() => onNavigate('por-revisar')}
              onKeyDown={(e) => e.key === 'Enter' && onNavigate('por-revisar')}
              className="case cursor-pointer"
              style={{ background: '#FAFAF8' }}
            >
              <span className="small muted">
                {n - MAX_CASES} {n - MAX_CASES === 1 ? 'caso' : 'casos'} más en la cola
              </span>
              <span className="small text-[var(--accent)] font-medium">Ver todos →</span>
            </div>
          )}
        </section>
      )}

      <section className="stack">
        <h2 className="section-title">Lo hace el agente autónomamente</h2>
        <div className="tiles">
          <Tile
            number={reminders}
            title={in_review ? 'Recordatorios para envío' : 'Recordatorios enviados'}
            text={in_review ? 'Listos para ser enviados tras la revisión.' : 'Ya están en la bandeja de captura.'}
            onClick={() => onNavigate('notificaciones')}
          />
          <Tile
            number={early_signals}
            title="Señales tempranas"
            text="Buenos pagadores con señales de deterioro. Se avisan antes."
            onClick={() => onNavigate('clientes', { filter: 'senales' })}
          />
          <Tile
            number={no_action}
            title="Sin acción"
            text="No necesitan aviso."
            muted
          />
        </div>
      </section>
    </main>
  )
}
