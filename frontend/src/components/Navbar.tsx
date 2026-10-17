import React from 'react'
import type { SimulationStatus } from '../types'

export type NavTab = 'hoy' | 'por-revisar' | 'notificaciones' | 'clientes' | 'efectividad'

interface NavbarProps {
  currentTab: NavTab
  onSelectTab: (tab: NavTab) => void
  status: SimulationStatus | null
}

export const Navbar: React.FC<NavbarProps> = ({ currentTab, onSelectTab, status }) => {
  const tabs: Array<{ id: NavTab; label: string; badge?: number }> = [
    { id: 'hoy', label: 'Hoy' },
    { id: 'por-revisar', label: 'Por revisar', badge: status?.review_count || 0 },
    { id: 'notificaciones', label: 'Notificaciones' },
    { id: 'clientes', label: 'Clientes' },
    { id: 'efectividad', label: 'Efectividad' },
  ]

  return (
    <header className="vh-header">
      <div className="nav">
        <a
          href="#hoy"
          onClick={(e) => {
            e.preventDefault()
            onSelectTab('hoy')
          }}
          className="brand"
        >
          <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
            <rect width="28" height="28" rx="8" fill="#111318"></rect>
            <path
              d="M7 18l5-5 3 3 6-7"
              fill="none"
              stroke="#FFFFFF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            ></path>
          </svg>
          Cobranza temprana
        </a>

        <nav className="links" aria-label="Principal">
          {tabs.map((tab) => {
            const isActive = currentTab === tab.id
            return (
              <button
                key={tab.id}
                type="button"
                className={`lnk ${isActive ? 'lnk-on' : ''}`}
                onClick={() => onSelectTab(tab.id)}
              >
                {tab.label}
                {Boolean(tab.badge && tab.badge > 0) && (
                  <span className="badge">{tab.badge}</span>
                )}
              </button>
            )
          })}
        </nav>

        <span className="small muted">
          {status?.header_note || 'Cargando estado…'}
        </span>
      </div>
    </header>
  )
}
