import type {
  AttentionCounts,
  AttentionKey,
  AttentionLists,
  BranchOverviewRow,
  OverviewMix,
} from '../../../types/platformOverview'

export function fmtDelta(pct: number | null): { text: string; tone: 'up' | 'down' | 'flat' } {
  if (pct === null || pct === undefined) return { text: '—', tone: 'flat' }
  if (pct === 0) return { text: '=', tone: 'flat' }
  const abs = Math.abs(pct).toFixed(1)
  return pct > 0 ? { text: `▲ ${abs}%`, tone: 'up' } : { text: `▼ ${abs}%`, tone: 'down' }
}

/** "efectivo / no-efectivo" en porcentajes enteros; "—" si no hubo cobros. */
export function fmtMix(mix: OverviewMix): string {
  if (mix.cash_pct === null) return '—'
  const cash = Math.round(mix.cash_pct)
  return `${cash} / ${100 - cash}`
}

export function staleLabel(lastUpdatedAt: number | null, now: number): string | null {
  if (lastUpdatedAt === null) return null
  const minutes = Math.floor((now - lastUpdatedAt) / 60_000)
  return minutes >= 1 ? `datos de hace ${minutes} min` : null
}

const CHIP_DEFS: {
  key: AttentionKey
  singular: string
  plural: string
  tone: 'warning' | 'danger'
}[] = [
  { key: 'no_cut', singular: 'sin corte >14 h', plural: 'sin corte >14 h', tone: 'warning' },
  {
    key: 'cut_difference',
    singular: 'corte con diferencia',
    plural: 'cortes con diferencia',
    tone: 'danger',
  },
  {
    key: 'oldest_returns',
    singular: 'con devoluciones pendientes',
    plural: 'con devoluciones pendientes',
    tone: 'danger',
  },
  {
    key: 'cancelled_today',
    singular: 'con cancelaciones hoy',
    plural: 'con cancelaciones hoy',
    tone: 'warning',
  },
]

/** `counts` (el total real, antes del recorte) hace que un chip diga
 *  "10 de 23 cortes con diferencia" en vez de fingir que solo hay 10. */
export function attentionChips(a: AttentionLists, counts?: AttentionCounts): {
  key: AttentionKey
  label: string
  tone: 'warning' | 'danger'
}[] {
  return CHIP_DEFS.map((d) => ({ d, n: a[d.key].length, total: counts?.[d.key] ?? a[d.key].length }))
    .filter(({ total }) => total > 0)
    .map(({ d, n, total }) => ({
      key: d.key,
      label: `${total > n ? `${n} de ${total}` : total} ${total === 1 ? d.singular : d.plural}`,
      tone: d.tone,
    }))
}

/** Cuántas organizaciones distintas piden atención hoy — la tira cruza a todas,
 *  así que el conteo honesto es de clientes, no de dinero. */
export function orgsQueNecesitanAtencion(a: AttentionLists): number {
  const ids = new Set<number>()
  for (const d of CHIP_DEFS) for (const item of a[d.key]) ids.add(item.org_id)
  return ids.size
}

export function sortRowsBySales(rows: BranchOverviewRow[]): BranchOverviewRow[] {
  return [...rows].sort((a, b) => b.sales_today - a.sales_today)
}

const MONTHS_ES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

/** "hoy 21:14" | "ayer 21:14" | "5 sep 21:14" en hora local del navegador; "—" si no hay fecha. */
export function fmtCloseAt(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const time = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.toDateString() === now.toDateString()) return `hoy ${time}`
  if (d.toDateString() === yesterday.toDateString()) return `ayer ${time}`
  return `${d.getDate()} ${MONTHS_ES[d.getMonth()]} ${time}`
}
