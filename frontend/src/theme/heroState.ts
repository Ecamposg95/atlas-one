/** Estado del hero: el cielo es el fondo, el turno solo aporta banda + píldora. */
export type HeroStateKey = 'open' | 'closedToday' | 'none'
export interface HeroState { key: HeroStateKey; band: string; pill: string; label: string }

/**
 * `band` va directo a `style={{ background }}` y `pill` a `className`; ambos
 * consumen los tokens de Atlas ONE (`.hero-pill-*` vive en styles/motion.css),
 * nunca hexadecimales ni paleta fija de Tailwind.
 */
export const HERO_STATES: Record<HeroStateKey, HeroState> = {
  open:        { key: 'open',        band: 'var(--dax-success)', pill: 'hero-pill hero-pill-open',   label: 'Turno abierto' },
  closedToday: { key: 'closedToday', band: 'var(--dax-warning)', pill: 'hero-pill hero-pill-closed', label: 'Turno cerrado hoy' },
  none:        { key: 'none',        band: 'var(--dax-accent)',  pill: 'hero-pill hero-pill-none',   label: 'Sin caja abierta' },
}

export function heroState(isOpen: boolean, closedToday: boolean): HeroState {
  if (isOpen) return HERO_STATES.open
  if (closedToday) return HERO_STATES.closedToday
  return HERO_STATES.none
}
