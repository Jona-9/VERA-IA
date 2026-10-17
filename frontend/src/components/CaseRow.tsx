import React from 'react'

interface CaseRowProps {
  name: string
  tag: React.ReactNode
  summary: string
  selected?: boolean
  onClick?: () => void
}

export const CaseRow: React.FC<CaseRowProps> = ({ name, tag, summary, selected = false, onClick }) => {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
      className={`case ${selected ? 'case-on' : ''}`}
    >
      <span style={{ fontWeight: 600 }}>{name}</span>
      <div>{tag}</div>
      <span className="small muted" style={{ gridColumn: '1 / -1' }}>
        {summary}
      </span>
    </div>
  )
}
