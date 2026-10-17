import React, { useState } from 'react'
import type { AgentThoughtTrace, ThoughtStep } from '../types'
import { api } from '../api'

interface AgentThoughtLogProps {
  trace?: AgentThoughtTrace | null
  title?: string
  accountId?: string
  customerName?: string
  initialExpanded?: boolean
  allowLiveQuery?: boolean
  onTraceUpdated?: (updatedTrace: AgentThoughtTrace) => void
}

const FALLBACK_STEPS: ThoughtStep[] = [
  {
    step: 1,
    title: 'Leyendo historial de 6 meses...',
    tool: 'QueryAccountSignalsTool',
    detail: 'periodos=6, principio=IV_TEMPORAL_INTEGRITY',
    observation: 'Historial de 6 periodos analizado correctamente sin fuga temporal.',
    status: 'SUCCESS',
    timestamp: '09:00:01',
  },
  {
    step: 2,
    title: 'Calculando señales: Utilización = 94%, Pagos mínimos = 3. Riesgo: ALTA.',
    tool: 'EvaluateRiskModel (Platt-Scaled)',
    detail: 'P(mora)=0.684, banda=ALTA, histeresis=CONFIRMED',
    observation: 'Señal de deterioro temprano detectada. Histéresis confirma banda ALTA.',
    status: 'SUCCESS',
    timestamp: '09:00:02',
  },
  {
    step: 3,
    title: 'Consultando herramienta ScheduleNoticeTool... Bloqueado por regla de ventana: falta 1 día para ventana autorizada.',
    tool: 'ScheduleNoticeTool',
    detail: 'rule=WAITING_SEND_DAY, ventana_dias=[3]',
    observation: 'Límite determinista estricto: contacto preventivo retenido hasta alcanzar la ventana.',
    status: 'BLOCKED',
    timestamp: '09:00:03',
  },
  {
    step: 4,
    title: 'Decisión: Retener y reevaluar mañana.',
    tool: 'ConstitutionalGuard',
    detail: 'action=NO_ACTION, rule=WAITING_SEND_DAY',
    observation: 'Veredicto final emitido bajo gobernanza constitucional sin alucinación.',
    status: 'INFO',
    timestamp: '09:00:04',
  },
]

export const AgentThoughtLog: React.FC<AgentThoughtLogProps> = ({
  trace,
  title = '🤖 Razonamiento del Agente VERA-IA (Audit Trace)',
  accountId,
  customerName,
  initialExpanded = true,
  allowLiveQuery = true,
  onTraceUpdated,
}) => {
  const [expanded, setExpanded] = useState(initialExpanded)
  const [loadingLlm, setLoadingLlm] = useState(false)
  const [copied, setCopied] = useState(false)
  const [localLlmAnalysis, setLocalLlmAnalysis] = useState<string | null>(
    trace?.llm_analysis || null
  )

  const steps: ThoughtStep[] = trace?.steps && trace.steps.length > 0 ? trace.steps : FALLBACK_STEPS
  const currentAccountId = accountId || trace?.account_id || 'ACC-DEMO'
  const currentCustomer = customerName || trace?.customer_name || 'Cliente en Cartera'
  const finalVerdict = trace?.final_verdict || 'Retener y reevaluar mañana'
  const constitutionalRule = trace?.constitutional_rule || 'WAITING_SEND_DAY'

  const handleLiveLlmQuery = async () => {
    if (!currentAccountId) return
    try {
      setLoadingLlm(true)
      const res = await api.requestLlmAudit(currentAccountId)
      setLocalLlmAnalysis(res.llm_analysis)
      if (onTraceUpdated && res.thought_trace) {
        onTraceUpdated(res.thought_trace)
      }
    } catch (err) {
      alert(`Error al consultar OpenRouter LLM: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setLoadingLlm(false)
    }
  }

  const handleCopy = () => {
    const textToCopy = steps
      .map((s) => `[PASO ${s.step}] ${s.title}\n  Tool: ${s.tool}\n  Obs: ${s.observation}`)
      .join('\n\n')
    navigator.clipboard.writeText(
      `${title}\nCliente: ${currentCustomer} (${currentAccountId})\n\n${textToCopy}\n\nVeredicto: ${finalVerdict}`
    )
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="w-full bg-[#0B1120] border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden font-mono text-xs my-4 transition-all">
      {/* Terminal Title Bar */}
      <div className="bg-[#111827] px-4 py-3 border-b border-slate-700/80 flex items-center justify-between select-none">
        <div className="flex items-center gap-3">
          {/* macOS Traffic Lights */}
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-full bg-[#EF4444] inline-block shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-[#F59E0B] inline-block shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-[#10B981] inline-block shadow-sm" />
          </div>

          <span className="font-semibold text-slate-200 text-sm flex items-center gap-1.5 ml-1">
            {title}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Engine Badge */}
          <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            OpenRouter · gpt-4o-mini
          </span>

          <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-cyan-950 text-cyan-300 border border-cyan-800">
            ReAct Dual-Engine
          </span>

          {/* Copy Button */}
          <button
            type="button"
            onClick={handleCopy}
            title="Copiar traza completa"
            className="text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 border border-slate-600 text-[11px] transition-colors"
          >
            {copied ? '✓ Copiado' : 'Copiar'}
          </button>

          {/* Collapse/Expand Toggle */}
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 border border-slate-600 text-[11px] transition-colors"
          >
            {expanded ? 'Plegar ▲' : 'Desplegar ▼'}
          </button>
        </div>
      </div>

      {/* Terminal Body */}
      {expanded && (
        <div className="p-4 sm:p-5 bg-[#0B1120] text-slate-200 space-y-4 leading-relaxed">
          {/* Header Info Banner */}
          <div className="pb-3 border-b border-slate-800/90 text-slate-400 flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="text-cyan-400 font-semibold">&gt; VERA-IA CONSTITUTIONAL AGENT</span>
              <span className="text-slate-500 mx-2">|</span>
              <span className="text-slate-300">{currentCustomer}</span>
              <span className="text-slate-500 text-[11px] ml-1">({currentAccountId})</span>
            </div>
            <div className="text-[11px] text-slate-400">
              Regla:{' '}
              <span className="text-amber-400 font-semibold">{constitutionalRule}</span>
            </div>
          </div>

          {/* Steps Trace */}
          <div className="space-y-3.5">
            {steps.map((s) => {
              const isBlocked = s.status === 'BLOCKED'
              const isWarning = s.status === 'WARNING'
              const isInfo = s.status === 'INFO'

              const badgeColor = isBlocked
                ? 'bg-amber-950/80 text-amber-300 border-amber-700/80'
                : isWarning
                ? 'bg-orange-950/80 text-orange-300 border-orange-700/80'
                : isInfo
                ? 'bg-blue-950/80 text-blue-300 border-blue-700/80'
                : 'bg-emerald-950/80 text-emerald-300 border-emerald-700/80'

              const stepPrefixColor = isBlocked
                ? 'text-amber-400'
                : isWarning
                ? 'text-orange-400'
                : isInfo
                ? 'text-blue-400'
                : 'text-emerald-400'

              return (
                <div
                  key={s.step}
                  className="p-3 rounded-lg bg-slate-900/90 border border-slate-800/80 hover:border-slate-700 transition-colors flex flex-col gap-1.5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`font-bold ${stepPrefixColor}`}>[PASO {s.step}]</span>
                      <span className="text-slate-100 font-semibold text-xs sm:text-sm">
                        {s.title}
                      </span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      {s.timestamp && (
                        <span className="text-[10px] text-slate-500">{s.timestamp}</span>
                      )}
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${badgeColor}`}>
                        {isBlocked ? 'BLOQUEADO' : isWarning ? 'DERIVADO' : isInfo ? 'VEREDICTO' : 'OK'}
                      </span>
                    </div>
                  </div>

                  <div className="pl-0 sm:pl-4 text-[11px] space-y-1 text-slate-300 border-l-2 border-slate-800 ml-1 mt-1">
                    <div className="flex items-start gap-1.5 text-cyan-300/90">
                      <span className="text-slate-500 select-none">⚙️</span>
                      <span className="font-semibold text-cyan-400">Tool:</span>
                      <span>{s.tool}</span>
                      {s.detail && <span className="text-slate-500 font-normal">({s.detail})</span>}
                    </div>

                    <div className="flex items-start gap-1.5 text-slate-300">
                      <span className="text-slate-500 select-none">🔍</span>
                      <span className="font-semibold text-slate-400">Obs:</span>
                      <span className="text-slate-300">{s.observation}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Constitutional LLM Synthesis Card */}
          <div className="mt-4 p-3.5 rounded-lg bg-gradient-to-r from-blue-950/60 to-indigo-950/60 border border-blue-800/60 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-blue-300 text-xs flex items-center gap-1.5">
                <span>🧠</span> Síntesis de Gobernanza LLM (OpenRouter / GPT-4o-mini):
              </span>

              {allowLiveQuery && (
                <button
                  type="button"
                  onClick={handleLiveLlmQuery}
                  disabled={loadingLlm}
                  className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-[11px] font-medium transition-colors flex items-center gap-1"
                >
                  {loadingLlm ? (
                    <>
                      <span className="w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Consultando LLM…
                    </>
                  ) : (
                    'Auditar con IA en vivo ⚡'
                  )}
                </button>
              )}
            </div>

            <p className="text-slate-200 text-xs leading-relaxed italic">
              {localLlmAnalysis ||
                trace?.llm_analysis ||
                '“La decisión de retener y reevaluar mañana protege el balance de riesgo crediticio del banco sin incurrir en acoso o sobre-notificación al cliente, satisfaciendo el Principio II de la Constitución VERA-IA.”'}
            </p>
          </div>

          {/* Terminal Command Prompt */}
          <div className="pt-2 text-[11px] text-slate-500 flex items-center gap-2 select-none">
            <span className="text-emerald-400 font-bold">vera-ia@bank-core:~$</span>
            <span className="text-slate-400">audit-status --verdict="{finalVerdict}" --constitutional=1</span>
            <span className="inline-block w-2 h-3.5 bg-emerald-400 animate-pulse ml-0.5" />
          </div>
        </div>
      )}
    </div>
  )
}
