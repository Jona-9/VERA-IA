import React, { useEffect, useState } from 'react'
import type { CapturedEmail, NoticeItem } from '../types'
import { api } from '../api'
import { Tag } from '../components/Tag'
import { CaseRow } from '../components/CaseRow'

interface NoticesViewProps {
  onSelectClient: (accountId: string) => void
}

export const NoticesView: React.FC<NoticesViewProps> = ({ onSelectClient }) => {
  const [activeTab, setActiveTab] = useState<'avisos' | 'bandeja'>('avisos')
  const [notices, setNotices] = useState<NoticeItem[]>([])
  const [emails, setEmails] = useState<CapturedEmail[]>([])
  const [selectedStatus, setSelectedStatus] = useState<string>('TODOS')
  const [expandedEmailId, setExpandedEmailId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    try {
      const [noticesRes, emailsRes] = await Promise.all([
        api.getNotices(),
        api.getEmails(),
      ])
      setNotices(noticesRes)
      setEmails(emailsRes)
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
    return <div className="page py-12 text-center text-[var(--muted)]">Cargando notificaciones…</div>
  }

  const allStatuses = Array.from(new Set(notices.map((n) => n.status)))
  const filteredNotices =
    selectedStatus === 'TODOS'
      ? notices
      : notices.filter((n) => n.status === selectedStatus)

  return (
    <main className="page gap-4">
      <section className="hero">
        <h1>Notificaciones</h1>
        <p className="muted">
          Lo que el agente programó y lo que llegó a la bandeja local. Esta bandeja es el único
          destino: ningún correo sale de este equipo.
        </p>
      </section>

      {/* Tabs */}
      <div className="flex border-b border-[#ECECE8] gap-6 mt-4">
        <button
          type="button"
          onClick={() => setActiveTab('avisos')}
          className={`pb-3 font-semibold text-base transition-colors relative ${
            activeTab === 'avisos'
              ? 'text-[var(--ink)] border-b-2 border-[var(--accent)]'
              : 'text-[var(--muted)] hover:text-[var(--ink)]'
          }`}
        >
          Avisos ({notices.length})
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('bandeja')}
          className={`pb-3 font-semibold text-base transition-colors relative ${
            activeTab === 'bandeja'
              ? 'text-[var(--ink)] border-b-2 border-[var(--accent)]'
              : 'text-[var(--muted)] hover:text-[var(--ink)]'
          }`}
        >
          Bandeja de correos ({emails.length})
        </button>
      </div>

      {/* Tab: Avisos */}
      {activeTab === 'avisos' && (
        <div className="flex flex-col gap-4 mt-2">
          {allStatuses.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-[var(--muted)] uppercase mr-1">
                Estado:
              </span>
              <button
                type="button"
                onClick={() => setSelectedStatus('TODOS')}
                className={`tag cursor-pointer ${
                  selectedStatus === 'TODOS' ? 't-info font-bold' : 't-soon'
                }`}
              >
                Todos
              </button>
              {allStatuses.map((st) => (
                <button
                  key={st}
                  type="button"
                  onClick={() => setSelectedStatus(st)}
                  className={`tag cursor-pointer ${
                    selectedStatus === st ? 't-info font-bold' : 't-soon'
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>
          )}

          {filteredNotices.length === 0 ? (
            <div className="card card-pad">
              <p className="muted">Todavía no hay avisos.</p>
            </div>
          ) : (
            <section className="card overflow-hidden">
              {filteredNotices.map((n) => {
                const detail = n.rejection_reason
                  ? n.rejection_reason
                  : `${n.tone_label} · ${n.subject}`
                return (
                  <CaseRow
                    key={n.notice_id}
                    name={n.customer_name}
                    tag={<Tag text={n.status_label} css={n.status_css} />}
                    summary={`${n.date} · ${detail}`}
                    onClick={() => onSelectClient(n.account_id)}
                  />
                )
              })}
            </section>
          )}
        </div>
      )}

      {/* Tab: Bandeja de correos */}
      {activeTab === 'bandeja' && (
        <div className="flex flex-col gap-3 mt-2">
          {emails.length === 0 ? (
            <div className="card card-pad">
              <p className="muted">
                La bandeja está vacía. Los correos aparecen aquí al enviar a las 10:00.
              </p>
            </div>
          ) : (
            emails.map((email) => {
              const isExpanded = expandedEmailId === email.email_id
              return (
                <div key={email.email_id} className="card overflow-hidden">
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() =>
                      setExpandedEmailId(isExpanded ? null : email.email_id)
                    }
                    onKeyDown={(e) =>
                      e.key === 'Enter' &&
                      setExpandedEmailId(isExpanded ? null : email.email_id)
                    }
                    className="p-4 flex items-center justify-between cursor-pointer hover:bg-[#F7F7F4] transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
                      <span className="font-semibold text-[15px]">{email.subject}</span>
                      <span className="text-xs text-[var(--muted)]">→ {email.recipient}</span>
                    </div>
                    <span className="text-xs text-[var(--muted)] whitespace-nowrap ml-2">
                      {isExpanded ? '▲' : '▼'}
                    </span>
                  </div>

                  {isExpanded && (
                    <div className="p-4 pt-1 border-t border-[#ECECE8] bg-[#FAFAF8]">
                      <p className="small muted mb-3">
                        De {email.sender} · {email.captured_date_label}
                      </p>
                      <div className="mail-body bg-white p-4 rounded-xl border border-[#E8E8E3]">
                        {email.body}
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      )}
    </main>
  )
}
