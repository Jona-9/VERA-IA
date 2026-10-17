import React, { useEffect, useState } from 'react'
import type { ReviewCase } from '../types'
import { api } from '../api'
import { Tag, BandTag } from '../components/Tag'
import { CaseRow } from '../components/CaseRow'

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

  // Form states
  const [confirmedPayment, setConfirmedPayment] = useState<boolean>(true)
  const [amount, setAmount] = useState<number>(0)
  const [paymentDate, setPaymentDate] = useState<string>('')
  const [analyst, setAnalyst] = useState<string>('analista@demo.veraia.local')
  const [notes, setNotes] = useState<string>('')

  const loadQueue = async (preserveSelectedId?: string) => {
    try {
      const res = await api.getReviewQueue()
      setCases(res)
      if (res.length > 0) {
        const nextSelected = preserveSelectedId && res.some((c) => c.case_id === preserveSelectedId)
          ? preserveSelectedId
          : res[0].case_id
        setSelectedCaseId(nextSelected)
        initFormForCase(res.find((c) => c.case_id === nextSelected))
      } else {
        setSelectedCaseId(null)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const initFormForCase = (c?: ReviewCase) => {
    if (!c) return
    setConfirmedPayment(true)
    setAmount(c.default_amount ?? 0)
    setPaymentDate(c.default_date ?? new Date().toISOString().split('T')[0])
    setNotes('')
  }

  useEffect(() => {
    loadQueue(initialCaseId)
  }, [initialCaseId])

  const selectedCase = cases.find((c) => c.case_id === selectedCaseId)

  const handleSelectCase = (c: ReviewCase) => {
    setSelectedCaseId(c.case_id)
    initFormForCase(c)
  }

  const handleReevaluate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedCase) return

    try {
      setSubmitting(true)
      const res = await api.reevaluateCase(selectedCase.case_id, {
        confirmed: confirmedPayment,
        amount: confirmedPayment ? Number(amount) : undefined,
        payment_date: confirmedPayment ? paymentDate : undefined,
        analyst,
        notes,
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
          Casos que el agente no resuelve solo. Corrige el dato y reevalúa al instante.
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
          <p className="muted">No hay casos pendientes.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start mt-4">
          {/* Left Column: Queue */}
          <div className="md:col-span-5">
            <section className="card overflow-hidden">
              {cases.map((c) => (
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
                  selected={c.case_id === selectedCaseId}
                  onClick={() => handleSelectCase(c)}
                />
              ))}
            </section>
          </div>

          {/* Right Column: Case details & Form */}
          {selectedCase && (
            <div className="md:col-span-7 flex flex-col gap-4">
              <div className="card card-pad stack">
                <h2 className="section-title text-xl">{selectedCase.customer_name}</h2>
                <div className="flex items-center gap-2">
                  <Tag
                    text={selectedCase.when_text}
                    css={selectedCase.is_urgent ? 't-urgent' : 't-soon'}
                  />
                  <BandTag band={selectedCase.risk_band} />
                </div>
                <p className="font-semibold text-[15px]">{selectedCase.reason}</p>
                {selectedCase.agent_hypothesis && (
                  <p className="small muted">
                    <strong>Lo que concluyó el agente:</strong> {selectedCase.agent_hypothesis}
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

              {/* Form */}
              <form onSubmit={handleReevaluate} className="card card-pad stack">
                <h3 className="section-title text-base font-semibold">Corregir y reevaluar</h3>

                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium">¿Se recibió el pago?</label>
                  <div className="flex flex-col sm:flex-row gap-3">
                    <label className="flex items-center gap-2 cursor-pointer text-sm">
                      <input
                        type="radio"
                        name="payment_confirmed"
                        checked={confirmedPayment === true}
                        onChange={() => setConfirmedPayment(true)}
                        className="accent-[#1F3FBF]"
                      />
                      <span>Sí, confirmar el pago</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer text-sm">
                      <input
                        type="radio"
                        name="payment_confirmed"
                        checked={confirmedPayment === false}
                        onChange={() => setConfirmedPayment(false)}
                        className="accent-[#1F3FBF]"
                      />
                      <span>No hay pago, seguir con la política</span>
                    </label>
                  </div>
                </div>

                {confirmedPayment && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-[var(--muted)] mb-1">
                        Monto pagado
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={amount}
                        onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                        className="form-input"
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[var(--muted)] mb-1">
                        Fecha del pago
                      </label>
                      <input
                        type="date"
                        value={paymentDate}
                        onChange={(e) => setPaymentDate(e.target.value)}
                        className="form-input"
                        required
                      />
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-[var(--muted)] mb-1">
                    Analista
                  </label>
                  <input
                    type="text"
                    value={analyst}
                    onChange={(e) => setAnalyst(e.target.value)}
                    className="form-input"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[var(--muted)] mb-1">
                    Notas
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Opcional. Queda en la auditoría."
                    className="form-textarea"
                  />
                </div>

                <div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={submitting}
                  >
                    {submitting ? 'Reevaluando…' : 'Reevaluar'}
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
