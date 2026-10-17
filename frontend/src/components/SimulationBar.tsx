import React, { useState } from 'react'
import type { SimulationStatus } from '../types'
import { api } from '../api'

interface SimulationBarProps {
  status: SimulationStatus | null
  onUpdate: () => void
}

export const SimulationBar: React.FC<SimulationBarProps> = ({ status, onUpdate }) => {
  const [loading, setLoading] = useState(false)

  if (!status) return null

  const handleAction = async () => {
    try {
      setLoading(true)
      if (status.in_review) {
        await api.closeDay()
      } else {
        await api.advanceDay()
      }
      onUpdate()
    } catch (err) {
      alert(`Error: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    if (!confirm('¿Deseas reiniciar la simulación con la semilla inicial?')) return
    try {
      setLoading(true)
      await api.resetDemo()
      onUpdate()
    } catch (err) {
      alert(`Error al reiniciar: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full mt-4">
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-3 border-b border-[#ECECE8]">
        <div className="text-sm text-[var(--muted)]">
          Simulación · día {status.day_number} ·{' '}
          {status.in_review ? 'esperando el cierre de revisión' : 'día cerrado'}
        </div>

        <div className="flex items-center gap-3 w-full sm:w-auto">
          <button
            type="button"
            className="btn btn-primary flex-1 sm:flex-initial"
            disabled={loading}
            onClick={handleAction}
          >
            {loading
              ? 'Procesando…'
              : status.in_review
              ? 'Cerrar revisión y enviar a las 10:00'
              : 'Pasar al día siguiente'}
          </button>

          <button
            type="button"
            className="btn"
            disabled={loading}
            onClick={handleReset}
          >
            Reiniciar demo
          </button>
        </div>
      </div>

      {!status.smtp_ok && (
        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-sm">
          ⚠️ El puerto 1025 está ocupado: los correos no se capturarán en la bandeja local.
        </div>
      )}
    </div>
  )
}
