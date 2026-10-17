import { useCallback, useEffect, useState } from 'react'
import type { NavTab } from './components/Navbar'
import type { SimulationStatus } from './types'
import { api } from './api'
import { Navbar } from './components/Navbar'
import { SimulationBar } from './components/SimulationBar'
import { Footer } from './components/Footer'
import { TodayView } from './views/TodayView'
import { ReviewQueueView } from './views/ReviewQueueView'
import { NoticesView } from './views/NoticesView'
import { PortfolioView } from './views/PortfolioView'
import { DashboardView } from './views/DashboardView'

export function App() {
  const [currentTab, setCurrentTab] = useState<NavTab>('dashboard')
  const [status, setStatus] = useState<SimulationStatus | null>(null)

  // Navigation cross-linking states
  const [targetCaseId, setTargetCaseId] = useState<string | undefined>()
  const [targetAccountId, setTargetAccountId] = useState<string | undefined>()
  const [targetFilter, setTargetFilter] = useState<string | undefined>()

  const refreshStatus = useCallback(async () => {
    try {
      const res = await api.getStatus()
      setStatus(res)
    } catch (err) {
      console.error('Error fetching status:', err)
    }
  }, [])

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  const handleNavigate = (
    tab: NavTab,
    params?: { caseId?: string; accountId?: string; filter?: string }
  ) => {
    if (params?.caseId) setTargetCaseId(params.caseId)
    if (params?.accountId) setTargetAccountId(params.accountId)
    if (params?.filter) setTargetFilter(params.filter)
    setCurrentTab(tab)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSelectTab = (tab: NavTab) => {
    if (tab !== 'por-revisar') setTargetCaseId(undefined)
    if (tab !== 'clientes') {
      setTargetAccountId(undefined)
      setTargetFilter(undefined)
    }
    setCurrentTab(tab)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#FAFAF8]">
      <Navbar
        currentTab={currentTab}
        onSelectTab={handleSelectTab}
        status={status}
      />

      <div className="app-container flex-1 flex flex-col">
        <SimulationBar status={status} onUpdate={refreshStatus} />

        <div className="flex-1">
          {currentTab === 'hoy' && (
            <TodayView onNavigate={handleNavigate} />
          )}

          {currentTab === 'por-revisar' && (
            <ReviewQueueView
              initialCaseId={targetCaseId}
              onCaseResolved={refreshStatus}
            />
          )}

          {currentTab === 'notificaciones' && (
            <NoticesView
              onSelectClient={(accId) =>
                handleNavigate('clientes', { accountId: accId })
              }
            />
          )}

          {currentTab === 'clientes' && (
            <PortfolioView
              initialAccountId={targetAccountId}
              initialFilter={targetFilter}
            />
          )}

          {currentTab === 'dashboard' && (
            <DashboardView
              onNavigateToReview={(caseId) =>
                handleNavigate('por-revisar', { caseId })
              }
            />
          )}
        </div>

        <Footer />
      </div>
    </div>
  )
}

export default App
