import { useEffect, useState } from 'react'
import { motionDisabled } from '../../theme/motion'

// Papelitos de colores: son ILUSTRACIÓN, igual que el cielo. No siguen el tema
// ni el acento del vertical — un confeti monocromo no celebra nada.
const COLORS = ['#fde047', '#ffffff', '#c4b5fd', '#34d399', '#fdba74']

/**
 * 12 piezas, 2 s, se desmonta solo. El padre debe ser `relative overflow-hidden`.
 * Con el movimiento apagado no se pinta y `onDone` se avisa de inmediato, para
 * que quien lo use no se quede esperando una celebración que nunca llega.
 */
export function Confetti({ pieces = 12, onDone }: { pieces?: number; onDone?: () => void }) {
  const [alive, setAlive] = useState(true)
  const skip = motionDisabled()

  useEffect(() => {
    if (skip) { onDone?.(); return }
    const t = setTimeout(() => { setAlive(false); onDone?.() }, 2200)
    return () => clearTimeout(t)
  }, [skip, onDone])

  if (skip || !alive) return null
  return (
    <div className="confetti" aria-hidden="true">
      {Array.from({ length: pieces }, (_, i) => (
        <span key={i} style={{
          left: `${(i * 83) % 100}%`,
          background: COLORS[i % COLORS.length],
          animationDelay: `${(i % 4) * 0.12}s`,
        }} />
      ))}
    </div>
  )
}
