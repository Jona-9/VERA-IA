import React, { useEffect, useState } from 'react'
import type { BenchmarkData } from '../types'
import { api } from '../api'
import { Tile } from '../components/Tile'

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

export const BenchmarkView: React.FC = () => {
  const [data, setData] = useState<BenchmarkData | null>(null)
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)

  const loadBenchmark = async () => {
    try {
      setLoading(true)
      const res = await api.getBenchmark()
      setData(res)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRun = async () => {
    try {
      setCalculating(true)
      const res = await api.runBenchmark()
      setData(res)
    } catch (err) {
      alert(`Error al calcular: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setCalculating(false)
    }
  }

  useEffect(() => {
    loadBenchmark()
  }, [])

  if (loading) {
    return <div className="page py-12 text-center text-[var(--muted)]">Cargando efectividad…</div>
  }

  const bData = data?.data

  return (
    <main className="page gap-4">
      <section className="hero">
        <h1>Efectividad</h1>
        <p className="muted">
          El mismo grupo de clientes simulados, tratado de dos maneras: con el agente o con una
          campaña fija por segmento.
        </p>
      </section>

      {!data?.calculated || !bData ? (
        <div className="card card-pad stack mt-4">
          <p className="muted">
            Todavía no se calculó la comparación. Recorre 21 días simulados con cada estrategia
            (unos 10 segundos).
          </p>
          <div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={calculating}
              onClick={handleRun}
            >
              {calculating ? 'Simulando 21 días con cada estrategia…' : 'Calcular comparación'}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-6 mt-4">
          {/* Tiles */}
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

          {/* Comparison Cards */}
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

          {/* Footnote */}
          <div className="text-xs text-[var(--muted)] leading-relaxed">
            Semilla {bData.seed} · corte {bData.cutoff_date} · {bData.horizon_days} días ·{' '}
            {bData.agent.accounts} clientes. Los avisos a clientes con pago en trámite fueron{' '}
            {bData.agent.notices_while_payment_in_process} con el agente y{' '}
            {bData.fixed.notices_while_payment_in_process} con la campaña fija. La respuesta de los
            clientes es un supuesto del simulador, no evidencia real: las diferencias muestran el
            efecto de la política, no una promesa de resultados.
          </div>

          <div>
            <button
              type="button"
              className="btn"
              disabled={calculating}
              onClick={handleRun}
            >
              {calculating ? 'Recalculando…' : 'Recalcular'}
            </button>
          </div>
        </div>
      )}
    </main>
  )
}
