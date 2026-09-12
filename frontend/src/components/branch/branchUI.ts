/**
 * Atlas Branch UI tokens — shared design system for all *BranchView and
 * Cockpit components. Brand palette: solid purple (primary action + surfaces)
 * over warm-stone (light) / deep-slate (dark) neutrals.
 *
 * Status colors (emerald/green) are kept ONLY as semantic indicators for
 * "shift open", "positive variance", "no pending". They are NOT brand colors.
 *
 * Use these strings as Tailwind class fragments in JSX. Dark variants are
 * baked in so each token can be dropped into className= directly.
 */

export const ui = {
  // Page shell
  page: 'min-h-full bg-stone-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100',
  // Wide, dense container (uses more screen width than max-w-3xl)
  container: 'max-w-7xl mx-auto px-4 lg:px-6',
  // Surface panels — iOS-premium: rounded-3xl + soft shadow, no border
  card: 'rounded-3xl bg-white dark:bg-slate-900 shadow-lg shadow-slate-900/5 dark:shadow-black/30',
  cardHover: 'hover:border-purple-400 dark:hover:border-purple-500 transition-colors',
  // Hero panel — solid purple, no gradient
  hero: 'rounded-3xl bg-purple-600 dark:bg-purple-700 text-white shadow-2xl shadow-purple-900/20',
  heroAlt: 'rounded-3xl bg-purple-700 dark:bg-purple-800 text-white shadow-2xl shadow-purple-900/30',
  // Hero panel — state-aware variants for shift status (Mi Caja, Mi Día)
  // Solid colors to match the existing hero pattern (no gradients).
  heroEmerald: 'rounded-3xl bg-emerald-600 dark:bg-emerald-700 text-white shadow-2xl shadow-emerald-900/20',
  heroOrange: 'rounded-3xl bg-orange-600 dark:bg-orange-700 text-white shadow-2xl shadow-orange-900/20',
  // Hero con cielo — el fondo lo pinta `.hero-sky` (styles/motion.css) según
  // la hora; el estado del turno solo aporta banda lateral + píldora.
  heroSky: 'rounded-3xl hero-sky shadow-2xl shadow-black/20',
  // Frosted/sticky header
  glass: 'sticky top-0 z-10 backdrop-blur-xl bg-white/80 dark:bg-slate-950/80 border-b border-stone-200/60 dark:border-slate-800/60',
  // Typography
  pageTitle: 'text-3xl lg:text-4xl font-bold tracking-tight',
  sectionTitle: 'text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400',
  kpiLabel: 'text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400',
  kpiValue: 'text-3xl lg:text-4xl font-bold tabular-nums',
  kpiHero: 'text-5xl lg:text-6xl font-black tabular-nums tracking-tight',
  // Inputs — iOS-style: rounded-2xl, no border, ring-based focus
  input: 'w-full rounded-2xl bg-stone-100 dark:bg-slate-800 border-0 ring-1 ring-stone-200 dark:ring-slate-700 px-5 py-4 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500',
  // Buttons — bumped for cashier module tap targets (primary ~56px, secondary ~52px)
  btnPrimary: 'inline-flex items-center justify-center gap-2 rounded-2xl bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white text-base font-semibold px-6 py-4 shadow-lg shadow-purple-900/20 transition-colors',
  btnSecondary: 'inline-flex items-center justify-center gap-2 rounded-2xl bg-stone-100 hover:bg-stone-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-900 dark:text-slate-100 text-base font-medium px-5 py-3.5 transition-colors',
  btnGhost: 'inline-flex items-center justify-center gap-2 rounded-lg text-slate-600 dark:text-slate-400 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-stone-100 dark:hover:bg-slate-800 text-sm px-4 py-2.5 transition-colors',
  // Subtle/muted text
  muted: 'text-slate-500 dark:text-slate-400',
  // Divider
  divider: 'divide-y divide-stone-200 dark:divide-slate-800',
  // Severity dots — STATUS only, not brand
  dotGreen: 'w-2 h-2 rounded-full bg-emerald-500',   // status: open / positive / ok
  dotAmber: 'w-2 h-2 rounded-full bg-amber-500',
  dotRed:   'w-2 h-2 rounded-full bg-rose-500',
  dotPurple: 'w-2 h-2 rounded-full bg-purple-500',
  // Pills
  // pillStatusOk — semantic alias for "shift open / positive / no issues"
  pillStatusOk: 'inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-300 text-xs font-semibold px-2.5 py-1',
  /** @deprecated use pillStatusOk — kept for migration */
  pillEmerald: 'inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-300 text-xs font-semibold px-2.5 py-1',
  pillPurple:  'inline-flex items-center gap-1.5 rounded-full bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 text-xs font-semibold px-2.5 py-1',
  pillAmber:   'inline-flex items-center gap-1.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 text-xs font-semibold px-2.5 py-1',
  pillRose:    'inline-flex items-center gap-1.5 rounded-full bg-rose-100 dark:bg-rose-900/30 text-rose-800 dark:text-rose-300 text-xs font-semibold px-2.5 py-1',
  pillSlate:   'inline-flex items-center gap-1.5 rounded-full bg-stone-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-semibold px-2.5 py-1',
} as const

/**
 * Brand accent tokens.
 * status.* are SEMANTIC (not brand) — use for positive variance, shift open, no pending.
 * purple.* are BRAND primary.
 */
export const brand = {
  // Status — kept as emerald for semantic "positive / open / ok" meanings only
  /** @status positive variance / shift open / no issues */
  greenText:  'text-emerald-600 dark:text-emerald-400',
  /** @status use sparingly, only for filled status indicators */
  greenBg:    'bg-emerald-600',
  /** @status soft background for positive state badges */
  greenSoft:  'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-800 dark:text-emerald-300',
  // Purple — brand primary
  purpleText:   'text-purple-600 dark:text-purple-400',
  purpleBg:     'bg-purple-600',
  purpleSoft:   'bg-purple-50 dark:bg-purple-900/20 text-purple-800 dark:text-purple-300',
} as const

/** Money formatter — single instance reused */
const _money = new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' })
export function fmtMoney(v: string | number | null | undefined): string {
  return v == null || v === '' ? '—' : _money.format(typeof v === 'number' ? v : Number(v))
}

/** HH:MM formatter for short timestamps */
export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })
}

/** Long datetime in es-MX */
export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString('es-MX', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

/** Date-only es-MX */
export function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-MX', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}
