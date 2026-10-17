import React, { useEffect, useState } from 'react'
import type { ReviewCase } from '../types'
import { api } from '../api'
import { Tag, BandTag } from '../components/Tag'

interface ReviewQueueViewProps {
  initialCaseId?: string
  onCaseResolved: () => void
}

export const ReviewQueueView: React.FC<ReviewQueueViewProps> = ({
  initialCaseId,
  onCaseResolved,
}) => {
  const [cases, setCases] = useState<ReviewCase[]>([])
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(initialCaseId || null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [notification, setNotification] = useState<string | null>(null)

  const analyst = 'analista@demo.veraia.local'

  const loadQueue = async (preserveSelectedId?: string) => {
    try {
      const res = await api.getReviewQueue()
      setCases(res)
      if (res.length > 0) {
        const nextSelected = preserveSelectedId && res.some((c) => c.case_id === preserveSelectedId)
          ? preserveSelectedId
          : res[0].case_id
        setSelectedCaseId(nextSelected)
      } else {
        setSelectedCaseId(null)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadQueue(initialCaseId)
  }, [initialCaseId])

  const selectedCase = cases.find((c) => c.case_id === selectedCaseId)

  const handleSelectCase = (c: ReviewCase) => {
    setSelectedCaseId(c.case_id)
  }

  const handleReevaluate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCase) return

    try {
      setSubmitting(true)
      const res = await api.reevaluateCase(selectedCase.case_id, {
        confirmed: false,
        analyst,
      })
      setNotification(`Caso resuelto. ${res.summary}`)
      onCaseResolved()
      await loadQueue()
    } catch (err) {
      alert(`Error al reevaluar: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <div className="page py-12 text-center text-[var(--muted)]">Cargando casos por revisar…</div>
  }

  return (
    <main className="page gap-4">
      <section className="hero">
        <h1>Por revisar</h1>
        <p className="muted">
          Casos que el agente no resuelve solo. Revisa el mensaje que se enviará y apruébalo.
        </p>
      </section>

      {notification && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-emerald-800 text-sm flex items-center justify-between">
          <span>{notification}</span>
          <button
            type="button"
            className="text-emerald-700 hover:text-emerald-900 font-bold ml-4"
            onClick={() => setNotification(null)}
          >
            ✕
          </button>
        </div>
      )}

      {cases.length === 0 ? (
        <div className="card card-pad mt-4">
          <p className="muted">No hay casos pendientes en la cola.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start mt-4">
          {/* Left Column: Queue */}
          <div className="md:col-span-5">
            <section className="card overflow-hidden divide-y divide-[#EFEFEB]">
              {cases.map((c) => (
                <div
                  key={c.case_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelectCase(c)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSelectCase(c)}
                  className={`p-4 flex flex-col gap-1.5 cursor-pointer transition-colors ${
                    c.case_id === selectedCaseId ? 'bg-[#F3F5FD]' : 'hover:bg-[#F7F7F4]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-sm text-[var(--ink)]">{c.customer_name}</span>
                    <Tag
                      text={c.status_label || (c.is_carryover ? 'Arrastrado de ayer' : 'Pendiente hoy')}
                      css={c.status_css || (c.is_carryover ? 't-urgent' : 't-soon')}
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <Tag
                      text={c.when_text}
                      css={c.is_urgent ? 't-urgent' : 't-soon'}
                    />
                    <BandTag band={c.risk_band} />
                  </div>

                  <span className="text-xs text-[var(--muted)] line-clamp-1">
                    {c.reason}
                  </span>
                </div>
              ))}
            </section>
          </div>

          {/* Right Column: Case details & Form */}
          {selectedCase && (
            <div className="md:col-span-7 flex flex-col gap-4">
              <div className="card card-pad stack">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="section-title text-xl">{selectedCase.customer_name}</h2>
                  <div className="flex items-center gap-2">
                    <Tag
                      text={selectedCase.status_label || (selectedCase.is_carryover ? 'Arrastrado de ayer' : 'Pendiente hoy')}
                      css={selectedCase.status_css || (selectedCase.is_carryover ? 't-urgent' : 't-soon')}
                    />
                    <Tag
                      text={selectedCase.when_text}
                      css={selectedCase.is_urgent ? 't-urgent' : 't-soon'}
                    />
                    <BandTag band={selectedCase.risk_band} />
                  </div>
                </div>

                {selectedCase.customer_context && (
                  <p className="text-xs text-[var(--muted)] border-b border-[#ECECE8] pb-2">
                    {selectedCase.customer_context}
                  </p>
                )}

                {/* Por qué requiere aprobación manual */}
                {selectedCase.why_manual_approval && (
                  <div className="p-3 bg-[#FDF5E6] border border-[#FBE6C6] rounded-xl text-xs text-[#7A2E06] leading-relaxed">
                    <strong>Por qué debe ser aprobado manualmente:</strong> {selectedCase.why_manual_approval}
                  </div>
                )}

                {selectedCase.agent_hypothesis && (
                  <p className="text-xs text-[var(--muted)]">
                    <strong>Conclusión preliminar del agente:</strong> {selectedCase.agent_hypothesis}
                  </p>
                )}

                {/* Facts Grid */}
                {selectedCase.facts && (
                  <div className="kv pt-2 border-t border-[#ECECE8]">
                    {selectedCase.facts.map((fact) => (
                      <div key={fact.k}>
                        <div className="k">{fact.k}</div>
                        <div className="v text-[15px]">{fact.v}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Mensaje que se enviará */}
              <form onSubmit={handleReevaluate} className="card card-pad stack">
                <h3 className="section-title text-base font-semibold">Mensaje que se enviará</h3>

                {selectedCase.message_preview ? (
                  <div className="p-4 bg-[#FAFAF8] border border-[#ECECE8] rounded-xl flex flex-col gap-2">
                    <div className="text-sm font-semibold text-[var(--ink)]">
                      Asunto: {selectedCase.message_preview.subject}
                    </div>
                    <p className="text-sm text-[var(--ink)] whitespace-pre-line leading-relaxed">
                      {selectedCase.message_preview.body_text}
                    </p>
                  </div>
                ) : (
                  <p className="muted">No hay plantilla disponible para este caso.</p>
                )}

                <div>
                  <button type="submit" className="btn btn-primary" disabled={submitting}>
                    {submitting ? 'Enviando…' : 'Aprobar y enviar'}
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}
    </main>
  )
}
