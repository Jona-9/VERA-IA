import React, { useEffect, useState } from 'react'
import type { NavTab } from '../components/Navbar'
import type { TodayData } from '../types'
import { api } from '../api'
import { Tag } from '../components/Tag'
import { Tile } from '../components/Tile'
import { CaseRow } from '../components/CaseRow'

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
        <section className="card overflow-hidden">
          {cases.slice(0, MAX_CASES).map((c) => (
            <CaseRow
              key={c.case_id}
              name={c.customer_name}
              tag={
                <Tag
                  text={c.when_text}
                  css={c.is_urgent ? 't-urgent' : 't-soon'}
                />
              }
              summary={c.reason}
              onClick={() => onNavigate('por-revisar', { caseId: c.case_id })}
            />
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
        <h2 className="section-title">Lo hace el agente</h2>
        <div className="tiles">
          <Tile
            number={reminders}
            title={in_review ? 'Recordatorios a las 10:00' : 'Recordatorios enviados a las 10:00'}
            text={in_review ? 'Salen a las 10:00.' : 'Ya están en la bandeja de captura.'}
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
