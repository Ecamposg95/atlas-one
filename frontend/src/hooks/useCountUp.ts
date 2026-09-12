import { useEffect, useState } from 'react'
import { easeOutCubic } from '../theme/sky'
import { motionDisabled } from '../theme/motion'

/**
 * Devuelve un número que va de 0 a `target` en `durationMs` con easeOutCubic.
 * Con movimiento apagado (bandera o prefers-reduced-motion) devuelve `target`
 * de inmediato. Solo para mostrar: nunca usarlo para calcular ni enviar dinero.
 */
export function useCountUp(target: number, durationMs = 900): number {
  const reduced =
    typeof window === 'undefined' ||
    typeof requestAnimationFrame === 'undefined' ||
    motionDisabled()
  const [value, setValue] = useState(reduced ? target : 0)

  useEffect(() => {
    if (reduced || !Number.isFinite(target)) { setValue(target); return }
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const p = easeOutCubic((now - t0) / durationMs)
      setValue(target * p)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, durationMs, reduced])

  return value
}
