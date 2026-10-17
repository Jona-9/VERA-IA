import React from 'react'

interface TagProps {
  text: string
  css?: 't-urgent' | 't-soon' | 't-ok' | 't-info' | string
}

export const Tag: React.FC<TagProps> = ({ text, css = 't-soon' }) => {
  return <span className={`tag ${css}`}>{text}</span>
}

export const BandTag: React.FC<{ band?: string }> = ({ band }) => {
  if (!band || band === '—') {
    return <Tag text="Sin evaluar" css="t-soon" />
  }
  const labels: Record<string, string> = {
    BAJA: 'Riesgo bajo',
    MODERADA: 'Riesgo moderado',
    ALTA: 'Riesgo alto',
    CRITICA: 'Riesgo crítico',
  }
  const classes: Record<string, string> = {
    BAJA: 't-ok',
    MODERADA: 't-soon',
    ALTA: 't-urgent',
    CRITICA: 't-urgent',
  }
  return <Tag text={labels[band] || band} css={classes[band] || 't-soon'} />
}
