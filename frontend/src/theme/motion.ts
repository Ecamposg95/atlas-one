/**
 * Escape hatch de movimiento: cualquier terminal puede apagar las animaciones
 * sin deploy con `localStorage.atlas_ui_motion = '0'`. Solo la parte de
 * movimiento — Atlas ONE conserva su identidad visual, así que aquí no existe
 * la bandera de diseño anterior.
 */
export const MOTION_KEY = 'atlas_ui_motion'

/** true cuando el usuario apagó el movimiento (bandera local o preferencia del sistema). */
export function motionDisabled(): boolean {
  let flagOff = false
  try { flagOff = localStorage.getItem(MOTION_KEY) === '0' } catch { /* modo privado o bloqueado */ }
  if (flagOff) return true
  if (typeof window === 'undefined') return true
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/** Enciende o apaga la bandera local. */
export function setMotion(on: boolean): void {
  try { localStorage.setItem(MOTION_KEY, on ? '1' : '0') } catch { /* modo privado o bloqueado */ }
}

/**
 * Marca `<html>` con `ui-no-motion` cuando la bandera local está apagada.
 * `prefers-reduced-motion` lo cubre el CSS por su cuenta, así que aquí solo
 * miramos la bandera: apagarla no debe depender de la preferencia del sistema.
 */
export function applyMotionFlag(root: { classList: DOMTokenList }): void {
  let flagOff = false
  try { flagOff = localStorage.getItem(MOTION_KEY) === '0' } catch { /* modo privado o bloqueado */ }
  if (flagOff) root.classList.add('ui-no-motion')
  else root.classList.remove('ui-no-motion')
}
