import type { CSSProperties } from 'react'
import { skyPeriod, type SkyPeriod } from '../../theme/sky'
import { motionDisabled } from '../../theme/motion'

interface Props { period?: SkyPeriod }

const STARS = [[8, 20], [18, 70], [30, 35], [45, 15], [55, 75], [62, 45], [75, 20], [90, 60], [83, 85]] as const

/**
 * Capa decorativa del saludo (A1). El padre debe ser `relative overflow-hidden`.
 * Solo Mi día y Mi caja. No captura eventos ni lectores de pantalla.
 * Con el movimiento apagado no se pinta: el hero se queda con su degradado.
 */
export function Sky({ period = skyPeriod(new Date()) }: Props) {
  if (motionDisabled()) return null
  return (
    <div className="sky" aria-hidden="true" data-period={period}>
      {period === 'day' && (
        <>
          <div className="sky-sun">
            <div className="sky-ray" style={{ '--ray-offset': '0deg' } as CSSProperties} /><div className="sky-ray" style={{ '--ray-offset': '45deg' } as CSSProperties} />
            <div className="sky-ray" style={{ '--ray-offset': '90deg' } as CSSProperties} /><div className="sky-ray" style={{ '--ray-offset': '135deg' } as CSSProperties} />
          </div>
          <div className="sky-cloud" style={{ width: 70, top: 28, left: 20 }} />
          <div className="sky-cloud" style={{ width: 50, top: 92, left: -40, animationDelay: '-9s', opacity: .6 }} />
        </>
      )}
      {period === 'sunset' && (
        <>
          <div className="sky-sunset" />
          <div className="sky-cloud" style={{ width: 80, top: 40, left: 60, background: 'rgba(255,255,255,.35)' }} />
        </>
      )}
      {period === 'night' && (
        <>
          <div className="sky-moon" />
          <div className="sky-shoot" />
          {STARS.map(([l, t], i) => (
            <div key={i} className="sky-star" style={{ left: `${l}%`, top: `${t}%`, animationDelay: `${(i * 0.37) % 2}s` }} />
          ))}
        </>
      )}
    </div>
  )
}
