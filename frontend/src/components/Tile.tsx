import React from 'react'

interface TileProps {
  number: string | number
  title: string
  text: string
  onClick?: () => void
  muted?: boolean
}

export const Tile: React.FC<TileProps> = ({ number, title, text, onClick, muted = false }) => {
  const content = (
    <>
      <span className="num" style={muted ? { color: '#5F646D' } : undefined}>
        {number}
      </span>
      <span style={{ fontWeight: 600 }}>{title}</span>
      <span className="small muted">{text}</span>
      {onClick && <span className="link-s mt-1">Ver →</span>}
    </>
  )

  if (onClick) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => e.key === 'Enter' && onClick()}
        className="card tile cursor-pointer select-none"
      >
        {content}
      </div>
    )
  }

  return <div className="card tile">{content}</div>
}
