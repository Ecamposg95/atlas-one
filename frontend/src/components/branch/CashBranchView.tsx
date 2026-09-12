import { useCallback, useEffect, useMemo, useState } from 'react'
import { BLIND_MASK, BLIND_LABEL, isValidCount, shouldRevealExpected, shouldShowExpectedKpi } from '../../utils/blindCash'
import client from '../../api/client'
import { cashApi, type CashSummary } from '../../api/cash'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import { toast } from '../../store/toastStore'
import { BRANCH_COPY, PAY_METHOD_LABELS } from '../../copy/branchCopy'
import type { CashWarning } from '../../types/cash'
import { ui, brand, fmtMoney, fmtDateTime } from './branchUI'
import { MovementModal } from './MovementModal'
import { OpenShiftModal } from './OpenShiftModal'
import { WeekSalesChart } from './WeekSalesChart'
import { Sky } from './Sky'
import { Confetti } from './Confetti'
import { useCountUp } from '../../hooks/useCountUp'
import { closeVerdict } from '../../theme/verdict'
import { heroState } from '../../theme/heroState'
import { skyPeriod } from '../../theme/sky'

// ─── Types ────────────────────────────────────────────────────────────────────

interface CashSession {
  id: number
  opened_at: string
  closed_at: string | null
  opening_balance: string
  closing_balance: string | null
  total_cash_sales: string
  difference: string
  notes: string | null
  status: string
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function elapsedMins(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
}

function formatElapsed(iso: string): string {
  const mins = elapsedMins(iso)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h === 0) return `${m}m`
  return `${h}h ${String(m).padStart(2, '0')}m`
}

function parseNum(v: string | null | undefined): number {
  if (v == null || v === '') return 0
  return Number(v)
}

// ─── Sub-components ───────────────────────────────────────────────────────────

interface KpiCardProps {
  icon: string
  label: string
  value: string
  valueClass?: string
  sub?: string
  iconBg?: string
  iconColor?: string
}

function KpiCard({ icon, label, value, valueClass, sub, iconBg, iconColor }: KpiCardProps) {
  return (
    <div className={`${ui.card} p-5 flex flex-col gap-1`}>
      <div className="flex items-center gap-2">
        <div
          className="flex items-center justify-center w-7 h-7 rounded-lg flex-shrink-0"
          style={{ background: iconBg ?? 'rgba(139,92,246,0.12)' }}
        >
          <i className={`fa-solid ${icon} text-sm`} style={{ color: iconColor ?? '#a78bfa' }} />
        </div>
        <span className={ui.kpiLabel}>{label}</span>
      </div>
      <span className={`${ui.kpiValue} text-2xl ${valueClass ?? ''}`}>{value}</span>
      {sub && <span className={`text-xs ${ui.muted}`}>{sub}</span>}
    </div>
  )
}

// ─── Session Row ──────────────────────────────────────────────────────────────

interface SessionRowProps {
  session: CashSession
  onReprint: (id: number) => void
  reprinting: boolean
}

function SessionRow({ session, onReprint, reprinting }: SessionRowProps) {
  const COPY = BRANCH_COPY.pages.cashHistory
  const diff = parseNum(session.difference)
  const isNeg = diff < 0
  // STATUS colors for variance — semantic, not brand
  const diffClass = isNeg
    ? 'text-rose-600 dark:text-rose-400'
    : diff === 0
    ? ui.muted
    : brand.greenText

  return (
    <li className="py-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      {/* dates */}
      <div className="flex flex-col min-w-[130px]">
        <span className="font-medium text-slate-800 dark:text-slate-200">
          {fmtDateTime(session.opened_at)}
        </span>
        {session.closed_at && (
          <span className={`text-xs ${ui.muted}`}>
            {COPY.closedAt} {fmtDateTime(session.closed_at)}
          </span>
        )}
      </div>

      {/* ventas */}
      <div className="flex flex-col items-end flex-1 min-w-[90px]">
        <span className={`text-xs ${ui.muted}`}>{COPY.sales}</span>
        <span className="font-semibold tabular-nums">
          {fmtMoney(session.total_cash_sales)}
        </span>
      </div>

      {/* diferencia */}
      <div className="flex flex-col items-end min-w-[90px]">
        <span className={`text-xs ${ui.muted}`}>{COPY.diff}</span>
        <span className={`font-bold tabular-nums ${diffClass}`}>
          {isNeg ? '' : diff > 0 ? '+' : ''}
          {fmtMoney(session.difference)}
        </span>
      </div>

      {/* reprint */}
      <button
        className={`${ui.btnGhost} text-xs ml-auto`}
        onClick={() => onReprint(session.id)}
        disabled={reprinting}
        title={COPY.reprint}
      >
        {reprinting ? (
          <i className="fa-solid fa-spinner fa-spin" />
        ) : (
          <i className="fa-solid fa-print" />
        )}
        <span className="hidden sm:inline">{COPY.reprint}</span>
      </button>
    </li>
  )
}

// ─── Close-shift simple modal — single-screen confirmation ───────────────────

interface CloseShiftModalProps {
  onClosed: () => void
  onCancel: () => void
}

// Resultado del arqueo ya cerrado — se muestra en pantalla en vez de
// depender del ticket impreso. Antes, si no había impresora configurada
// (frecuente en campo), el cajero cerraba turno y nunca veía su faltante.
interface CloseResult {
  expected: number
  counted: number
  diff: number
  warnings: CashWarning[]
}

function CloseShiftModal({ onClosed, onCancel }: CloseShiftModalProps) {
  const [summary, setSummary] = useState<CashSummary | null>(null)
  const [counted, setCounted] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [result, setResult] = useState<CloseResult | null>(null)

  useEffect(() => {
    // Conteo ciego: NO pre-llenar "contado" con el esperado. El cajero captura
    // su propio conteo físico; el esperado se revela después (shouldRevealExpected).
    cashApi.getSummary()
      .then((s) => setSummary(s))
      .catch(() => setLoadError(true))
  }, [])

  const expected = summary?.expected_cash ?? 0
  const countedNum = parseFloat(counted)
  const diff = !isNaN(countedNum) ? countedNum - expected : 0

  async function submit() {
    if (!isValidCount(counted)) return
    setSubmitting(true)
    try {
      const closed = await cashApi.close(countedNum)
      toast.success('Turno cerrado')

      // Auto-print del corte vía agente local si hay impresora configurada.
      // El cierre se considera exitoso aunque la impresión falle — no bloqueamos
      // el flujo del cajero por un error de impresora.
      const printerName = usePOSStore.getState().printerName
      if (printerName && closed?.id) {
        try {
          await printerApi.printCashCut(closed.id, printerName)
        } catch (e: unknown) {
          const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          toast.error(`Turno cerrado pero falló impresión: ${detail ?? 'Verifica el agente local'}`)
        }
      } else if (!printerName) {
        toast.error('Turno cerrado. Configura una impresora para imprimir el corte.')
      }

      // Mostrar el arqueo en pantalla: es la única garantía de que el cajero
      // vea su esperado/contado/diferencia cuando no hay impresora (arriba).
      const expectedFinal = closed?.difference != null
        ? countedNum - Number(closed.difference)
        : expected
      setResult({
        expected: expectedFinal,
        counted: countedNum,
        diff: closed?.difference != null ? Number(closed.difference) : diff,
        warnings: closed?.warnings ?? [],
      })
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Error al cerrar turno')
    } finally {
      setSubmitting(false)
    }
  }

  // Tras cerrar, el modal muta a pantalla de resultado (no se cierra solo):
  // es el único lugar donde el cajero ve esperado/contado/diferencia si no
  // hay impresora configurada (ver toast.error de arriba en ese caso).
  const dismiss = result ? onClosed : onCancel

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) dismiss() }}
    >
      <div className={`${ui.card} w-full max-w-md p-6`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {result ? 'Turno cerrado' : 'Finalizar turno'}
          </h3>
          <button onClick={dismiss} className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 p-1" aria-label="Cerrar">
            <i className="fa-solid fa-xmark text-lg" />
          </button>
        </div>

        {result ? (
          <CloseResultPanel result={result} onDone={onClosed} />
        ) : loadError ? (
          <p className={`text-sm ${ui.muted}`}>No se pudo cargar el resumen del turno.</p>
        ) : !summary ? (
          <p className={`text-sm italic ${ui.muted}`}>Cargando resumen…</p>
        ) : (
          <>
            <div className="space-y-2 text-sm mb-5">
              <Row label="Fondo inicial"  value={fmtMoney(String(summary.opening_amount))} />
              <Row label="Ventas efectivo" value={fmtMoney(String(summary.total_cash))} />
              <Row label="Entradas"        value={`+${fmtMoney(String(summary.total_inflows))}`}  valueClass={brand.greenText} />
              <Row label="Salidas"         value={`-${fmtMoney(String(summary.total_outflows))}`} valueClass="text-rose-600 dark:text-rose-400" />
              {summary.cash_refunds > 0 && (
                <Row
                  label={`Reembolsos efectivo${summary.returns_count > 0 ? ` (${summary.returns_count})` : ''}`}
                  value={`-${fmtMoney(String(summary.cash_refunds))}`}
                  valueClass="text-rose-600 dark:text-rose-400"
                />
              )}
              <div className="border-t border-stone-200 dark:border-slate-700 pt-2 flex justify-between font-bold text-slate-900 dark:text-slate-100">
                <span>Esperado en caja</span>
                {shouldRevealExpected(counted) ? (
                  <span className="tabular-nums">{fmtMoney(String(expected))}</span>
                ) : (
                  <span
                    className="tabular-nums text-slate-400 dark:text-slate-500"
                    title={`${BLIND_LABEL} — cuenta el efectivo y captúralo abajo`}
                  >
                    {BLIND_MASK}
                  </span>
                )}
              </div>
              {!shouldRevealExpected(counted) && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                  {BLIND_LABEL} · se revela al capturar tu conteo
                </p>
              )}
            </div>

            <label className={`block ${ui.kpiLabel} mb-1`}>Efectivo contado</label>
            <input
              type="number"
              value={counted}
              onChange={(e) => setCounted(e.target.value)}
              step="0.01"
              autoFocus
              className={ui.input}
            />
            {!isNaN(countedNum) && diff !== 0 && (
              <p className={`text-xs mt-2 font-semibold ${diff > 0 ? brand.greenText : 'text-rose-600 dark:text-rose-400'}`}>
                Diferencia: {diff > 0 ? '+' : ''}{fmtMoney(String(diff))}
              </p>
            )}

            <div className="flex gap-2 mt-5">
              <button onClick={onCancel} className={`${ui.btnSecondary} flex-1`} disabled={submitting}>
                Cancelar
              </button>
              <button
                onClick={submit}
                disabled={submitting || isNaN(countedNum)}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-600 hover:bg-rose-700 active:bg-rose-800 text-white text-base font-semibold px-6 py-4 shadow-lg shadow-rose-900/20 transition-colors disabled:opacity-50"
              >
                {submitting
                  ? <i className="fa-solid fa-spinner fa-spin" />
                  : <><i className="fa-solid fa-lock" /> Cerrar turno</>}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// Colores por severidad de alerta (SALES_WITHOUT_SESSION = 'high' es la que
// motivó esta pantalla: efectivo cobrado que no pertenece a ningún corte).
const SEVERITY_STYLE: Record<string, string> = {
  critical: 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
  high: 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
  warning: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
}

function CloseResultPanel({ result, onDone }: { result: CloseResult; onDone: () => void }) {
  const { expected, counted, diff, warnings } = result
  // Veredicto: el mismo `difference` que ya devolvió el backend, solo vestido.
  const verdict = closeVerdict(diff)
  const verdictAmount = useCountUp(Math.abs(diff), 1200)
  const diffClass = diff === 0 ? '' : diff > 0 ? brand.greenText : 'text-rose-600 dark:text-rose-400'
  return (
    <div>
      <div className={`anim-pop ${verdict.className} p-5 text-center mb-4`} role="status">
        <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">Cierre de turno</p>
        <p className="text-4xl font-black tabular-nums mt-1">{fmtMoney(verdictAmount)}</p>
        <p className="text-base font-bold mt-0.5">{verdict.label}</p>
      </div>

      <div className="space-y-2 text-sm mb-4">
        <Row label="Esperado en caja" value={fmtMoney(String(expected))} />
        <Row label="Contado" value={fmtMoney(String(counted))} />
        <div className="border-t border-stone-200 dark:border-slate-700 pt-2 flex justify-between font-bold text-slate-900 dark:text-slate-100">
          <span>Diferencia</span>
          <span className={`tabular-nums ${diffClass}`}>
            {diff > 0 ? '+' : ''}{fmtMoney(String(diff))}
          </span>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="space-y-2 mb-4">
          {warnings.map((w, i) => (
            <div
              key={`${w.code}-${i}`}
              className={`rounded-lg border px-3 py-2 text-xs ${SEVERITY_STYLE[w.severity] ?? SEVERITY_STYLE.warning}`}
            >
              <p className="font-semibold mb-0.5">
                <i className="fa-solid fa-triangle-exclamation mr-1" />
                {w.code}
              </p>
              <p>{w.message}</p>
            </div>
          ))}
        </div>
      )}

      <button
        onClick={onDone}
        className="w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-rose-600 hover:bg-rose-700 active:bg-rose-800 text-white text-base font-semibold px-6 py-4 shadow-lg shadow-rose-900/20 transition-colors"
      >
        Listo
      </button>
    </div>
  )
}

function Row({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex justify-between">
      <span className={ui.muted}>{label}</span>
      <span className={`tabular-nums ${valueClass ?? ''}`}>{value}</span>
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface MethodTotals {
  CASH: number
  CARD: number
  TRANSFER: number
  STORE_CREDIT?: number
  [key: string]: number | undefined
}

export function CashBranchView() {
  const [current, setCurrent] = useState<CashSession | null>(null)
  const [past, setPast] = useState<CashSession[]>([])
  const [loading, setLoading] = useState(true)
  const [reprintingId, setReprintingId] = useState<number | null>(null)
  const [showCloseWizard, setShowCloseWizard] = useState(false)
  const [movementModal, setMovementModal] = useState<'IN' | 'OUT' | null>(null)
  const [openShiftModalVisible, setOpenShiftModalVisible] = useState(false)
  const [summary, setSummary] = useState<CashSummary | null>(null)
  const [methodTotals, setMethodTotals] = useState<MethodTotals | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  // Celebración de apertura: la enciende OpenShiftModal al volver de POST /cash/open.
  const [justOpened, setJustOpened] = useState(false)

  const printerName = usePOSStore((s) => s.printerName)

  useEffect(() => {
    if (!justOpened) return
    const t = setTimeout(() => setJustOpened(false), 2400)
    return () => clearTimeout(t)
  }, [justOpened])

  // Solo presentación: el fondo mostrado sale del mismo dato de la sesión.
  const openingAnimated = useCountUp(current ? parseNum(current.opening_balance) : 0)

  const COPY = BRANCH_COPY.pages

  const loadAll = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setSummaryError(false)
    try {
      const [cur, list] = await Promise.all([
        client.get('/cash/status').then((r) => r.data).catch(() => null),
        client.get('/cash/history', { params: { limit: 7 } }).then((r) => r.data).catch(() => []),
      ])
      setCurrent(cur ?? null)
      const sessions: CashSession[] = Array.isArray(list) ? list : list?.items ?? []
      setPast(sessions)

      // Resolver "turno de hoy": OPEN actual, o el más reciente cerrado HOY.
      const today = new Date()
      today.setHours(0, 0, 0, 0)
      const todayClosed = sessions.find((s) => {
        if (!s.closed_at) return false
        const d = new Date(s.closed_at)
        d.setHours(0, 0, 0, 0)
        return d.getTime() === today.getTime()
      })
      const todaySessionId = cur?.id ?? todayClosed?.id ?? null

      if (todaySessionId != null) {
        try {
          const sum = await cashApi.getSummary(cur ? undefined : todaySessionId)
          setSummary(sum)
          setMethodTotals({
            CASH: Number(sum.total_cash) || 0,
            CARD: Number(sum.total_card) || 0,
            TRANSFER: Number(sum.total_transfer) || 0,
          })
        } catch {
          setSummaryError(true)
        }
      } else {
        setSummary(null)
        setMethodTotals(null)
        setSummaryError(true)
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  // Carga inicial
  useEffect(() => {
    loadAll(false)
  }, [loadAll])

  // Live refresh — sólo cuando hay turno abierto:
  //   1) cuando la pestaña recupera foco / visibilidad
  //   2) cada 30s mientras la pestaña esté visible
  // Silent (sin spinner) para no parpadear los KPIs durante el día.
  useEffect(() => {
    if (!current) return
    const onWake = () => {
      if (document.visibilityState === 'visible') loadAll(true)
    }
    document.addEventListener('visibilitychange', onWake)
    window.addEventListener('focus', onWake)
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') loadAll(true)
    }, 30_000)
    return () => {
      document.removeEventListener('visibilitychange', onWake)
      window.removeEventListener('focus', onWake)
      window.clearInterval(interval)
    }
  }, [current, loadAll])

  function handleShiftClosed() {
    setShowCloseWizard(false)
    loadAll()
  }

  async function handleMovement(amount: number, concept: string) {
    if (!movementModal) return
    try {
      if (movementModal === 'IN') await cashApi.inflow(amount, concept)
      else await cashApi.outflow(amount, concept)
      toast.success(movementModal === 'IN' ? 'Entrada registrada' : 'Salida registrada')
      setMovementModal(null)
      try {
        const sum = await cashApi.getSummary()
        setSummary(sum)
        setMethodTotals({
          CASH: Number(sum.total_cash) || 0,
          CARD: Number(sum.total_card) || 0,
          TRANSFER: Number(sum.total_transfer) || 0,
        })
      } catch { /* swallow — toast already showed success */ }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'No se pudo registrar el movimiento')
    }
  }

  // ── Derived KPIs ────────────────────────────────────────────────────────────

  const closedSessions = useMemo(
    () => past.filter((s) => s.closed_at != null),
    [past],
  )

  // Turno cerrado más reciente de HOY (para anclar KPIs cuando ya no hay OPEN).
  const todayClosedSession = useMemo(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return (
      closedSessions.find((s) => {
        if (!s.closed_at) return false
        const d = new Date(s.closed_at)
        d.setHours(0, 0, 0, 0)
        return d.getTime() === today.getTime()
      }) ?? null
    )
  }, [closedSessions])

  // Sesión activa para mostrar en KPIs: OPEN actual o, si no hay, la cerrada de hoy.
  const todaySession = current ?? todayClosedSession

  // KPIs ahora leen de `summary` directo (cashApi.getSummary devuelve total_sales
  // y expected_cash live, calculados por backend). Los useMemos viejos
  // (todaySales / expectedCash basados en CashSession.total_cash_sales) se
  // eliminaron — ese campo solo se actualiza al cerrar el turno, por eso los
  // KPIs aparecían en $0 durante el día.

  // ── Reprint ─────────────────────────────────────────────────────────────────

  async function reprintCut(sessionId: number) {
    if (!printerName) {
      toast.error(COPY.cashReprint.noPrinter)
      return
    }
    setReprintingId(sessionId)
    try {
      const b64 = await printerApi.getCashCutBase64(sessionId)
      if (!b64) throw new Error('Sin contenido')
      await printerApi.printViaAgent(printerName, b64)
      toast.success(COPY.cashReprint.success)
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? COPY.cashReprint.error)
    } finally {
      setReprintingId(null)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className={`${ui.page} flex items-center justify-center min-h-screen`}>
        <i className="fa-solid fa-spinner fa-spin text-3xl text-purple-600" />
      </div>
    )
  }

  return (
    <div className={`${ui.page} py-6`}>
      <div className={`${ui.container} space-y-5`}>

        {/* ── Hero — el cielo es el fondo; el turno es banda + píldora ── */}
        {(() => {
          const state = heroState(!!current, !!todayClosedSession)
          return (
            <div
              className={`${ui.heroSky} px-8 py-7 pl-10 flex flex-wrap items-center justify-between gap-4 ${justOpened ? 'anim-just-opened' : ''}`}
              data-period={skyPeriod(new Date())}
            >
              <Sky />
              <div className="hero-band" style={{ background: state.band }} />
              {justOpened && <><div className="ripple" /><Confetti /></>}

              <div className="relative z-10">
                <p className="text-white/70 text-xs font-semibold uppercase tracking-widest mb-0.5">
                  {COPY.cash}
                </p>
                <h1 className="text-2xl lg:text-3xl font-bold text-white">Mi caja</h1>
              </div>

              <div className="relative z-10 flex items-center gap-3 flex-wrap">
                <i className="fa-solid fa-vault text-white/50 text-2xl" />

                {current ? (
                  <div className="text-right flex flex-col items-end gap-2">
                    <span className={state.pill}>
                      <i className="fa-solid fa-circle text-[8px]" />
                      {state.label}
                    </span>
                    <p className="text-white/80 text-sm">
                      <i className="fa-solid fa-clock mr-1 text-white/50" />
                      {formatElapsed(current.opened_at)}
                    </p>
                    <p className="text-white/90 text-sm font-semibold tabular-nums">
                      Fondo {fmtMoney(openingAnimated)}
                    </p>
                  </div>
                ) : todayClosedSession ? (
                  <div className="text-right flex flex-col items-end gap-2">
                    <span className={state.pill}>
                      <i className="fa-solid fa-circle-check text-[10px]" />
                      {state.label}
                    </span>
                    <p className="text-white/70 text-xs">
                      <i className="fa-solid fa-clock mr-1 text-white/50" />
                      {fmtDateTime(todayClosedSession.closed_at!)}
                    </p>
                  </div>
                ) : (
                  <span className={state.pill}>
                    <i className="fa-solid fa-circle text-[8px]" />
                    {state.label}
                  </span>
                )}
              </div>
            </div>
          )
        })()}

        {/* ── Action band — botones grandes touch-friendly ─────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {!current && !todayClosedSession && (
            <button
              onClick={() => setOpenShiftModalVisible(true)}
              className={`${ui.card} p-5 flex flex-col items-center gap-2 hover:bg-emerald-50 dark:hover:bg-emerald-900/10 transition-colors col-span-2 lg:col-span-4`}
            >
              <i className="fa-solid fa-play text-3xl text-emerald-600 dark:text-emerald-400" />
              <span className="text-base font-bold text-slate-900 dark:text-slate-100">Abrir turno</span>
            </button>
          )}

          {current && (
            <>
              <button
                onClick={() => setMovementModal('IN')}
                className={`${ui.card} p-5 flex flex-col items-center gap-2 hover:bg-emerald-50 dark:hover:bg-emerald-900/10 transition-colors`}
              >
                <i className="fa-solid fa-arrow-down text-3xl text-emerald-600 dark:text-emerald-400" />
                <span className="text-base font-bold text-slate-900 dark:text-slate-100">Entrada</span>
              </button>
              <button
                onClick={() => setMovementModal('OUT')}
                className={`${ui.card} p-5 flex flex-col items-center gap-2 hover:bg-rose-50 dark:hover:bg-rose-900/10 transition-colors`}
              >
                <i className="fa-solid fa-arrow-up text-3xl text-rose-600 dark:text-rose-400" />
                <span className="text-base font-bold text-slate-900 dark:text-slate-100">Salida</span>
              </button>
              <button
                onClick={() => setShowCloseWizard(true)}
                className={`${ui.card} p-5 flex flex-col items-center gap-2 hover:bg-amber-50 dark:hover:bg-amber-900/10 transition-colors col-span-2`}
              >
                <i className="fa-solid fa-moon text-3xl text-amber-600 dark:text-amber-400" />
                <span className="text-base font-bold text-slate-900 dark:text-slate-100">Cerrar turno</span>
              </button>
            </>
          )}
        </div>

        {/* ── KPI cards row — Efectivo / Esperado / Entradas / Salidas ─ */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard
            icon="fa-coins"
            label={COPY.cashKpis.totalSales}
            value={summary ? fmtMoney(String(summary.total_sales)) : '—'}
            iconBg="rgba(16,185,129,0.12)"
            iconColor="#10b981"
            valueClass="text-emerald-600 dark:text-emerald-400"
          />
          <KpiCard
            icon="fa-scale-balanced"
            label={current ? COPY.cashKpis.expected : 'Cierre reportado'}
            value={
              // Con turno abierto: el esperado, enmascarado por conteo ciego.
              // Con turno cerrado la etiqueta dice "Cierre reportado", asi que
              // debe mostrar lo que el cajero CONTO, no lo que el sistema esperaba.
              current
                ? (shouldShowExpectedKpi(true) ? fmtMoney(String(summary?.expected_cash ?? 0)) : BLIND_MASK)
                : (todayClosedSession?.closing_balance != null
                    ? fmtMoney(String(todayClosedSession.closing_balance))
                    : '—')
            }
            sub={
              current
                ? `Inicial: ${fmtMoney(current.opening_balance)}`
                : todayClosedSession
                  ? `Inicial: ${fmtMoney(todayClosedSession.opening_balance)}`
                  : undefined
            }
            iconBg="rgba(139,92,246,0.12)"
            iconColor="#a78bfa"
          />
          <KpiCard
            icon="fa-arrow-down"
            label={COPY.cashKpis.inflows}
            value={summary ? `+${fmtMoney(String(summary.total_inflows))}` : '—'}
            iconBg="rgba(16,185,129,0.12)"
            iconColor="#10b981"
            valueClass="text-emerald-600 dark:text-emerald-400"
          />
          <KpiCard
            icon="fa-arrow-up"
            label={COPY.cashKpis.outflows}
            value={summary ? `-${fmtMoney(String(summary.total_outflows))}` : '—'}
            iconBg="rgba(244,63,94,0.12)"
            iconColor="#f43f5e"
            valueClass="text-rose-600 dark:text-rose-400"
          />
        </div>

        {/* ── Cobrado por método de pago ────────────────────────────── */}
        <div className={`${ui.card} p-5`}>
          <div className="flex items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <i className="fa-solid fa-credit-card text-purple-400 dark:text-purple-500 text-sm" aria-hidden="true" />
              <p className={ui.sectionTitle}>{current ? 'Esperado por método de pago' : 'Cobrado hoy por método'}</p>
            </div>
            {!current && todayClosedSession && (
              <span className={`text-[10px] font-semibold uppercase tracking-wider ${ui.muted}`}>
                Turno cerrado
              </span>
            )}
          </div>
          {summaryError && !todaySession ? (
            <p className={`text-sm italic ${ui.muted}`}>Sin turno hoy</p>
          ) : methodTotals == null ? (
            <p className={`text-sm italic ${ui.muted}`}>Cargando…</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {(
                [
                  { key: 'CASH',     icon: 'fa-money-bill-wave',  iconBg: 'rgba(16,185,129,0.1)',  iconColor: '#10b981' },
                  { key: 'CARD',     icon: 'fa-credit-card',      iconBg: 'rgba(139,92,246,0.1)', iconColor: '#a78bfa' },
                  { key: 'TRANSFER', icon: 'fa-building-columns', iconBg: 'rgba(59,130,246,0.1)', iconColor: '#60a5fa' },
                ] as const
              ).map(({ key, icon, iconBg, iconColor }) => {
                const amount = (methodTotals as Record<string, number | undefined>)[key] ?? 0
                return (
                  <div
                    key={key}
                    className="flex items-center gap-3 rounded-xl px-4 py-3"
                    style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
                  >
                    <div
                      className="flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0"
                      style={{ background: iconBg }}
                    >
                      <i className={`fa-solid ${icon} text-sm`} style={{ color: iconColor }} />
                    </div>
                    <div className="min-w-0">
                      <p className={`text-[10px] font-semibold uppercase tracking-wider ${ui.muted}`}>
                        {PAY_METHOD_LABELS[key] ?? key}
                      </p>
                      <p className="text-sm font-bold tabular-nums text-slate-800 dark:text-slate-100 mt-0.5">
                        {fmtMoney(String(amount))}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Movimientos del turno — full width ─────────────────────── */}
        {summary && summary.movements.length > 0 && (
          <div className={`${ui.card} p-5`}>
            <p className={`${ui.sectionTitle} mb-3`}>{BRANCH_COPY.pages.cashMovements.title}</p>
            <ul className={ui.divider}>
              {summary.movements.map((m) => (
                <li key={m.id} className="py-3 flex items-center gap-3 text-sm">
                  <span
                    className={`inline-flex items-center justify-center w-8 h-8 rounded-lg flex-shrink-0 ${
                      m.type === 'IN'
                        ? 'bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400'
                        : 'bg-rose-100 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400'
                    }`}
                  >
                    <i className={`fa-solid ${m.type === 'IN' ? 'fa-arrow-down' : 'fa-arrow-up'} text-xs`} />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-800 dark:text-slate-200 truncate">{m.concept || '—'}</p>
                    <p className={`text-xs ${ui.muted}`}>
                      {new Date(m.created_at).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                  <span
                    className={`font-bold tabular-nums flex-shrink-0 ${
                      m.type === 'IN'
                        ? 'text-emerald-600 dark:text-emerald-400'
                        : 'text-rose-600 dark:text-rose-400'
                    }`}
                  >
                    {m.type === 'IN' ? '+' : '-'}{fmtMoney(String(m.amount))}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {summary && summary.movements.length === 0 && (current || todayClosedSession) && (
          <div className={`${ui.card} p-5`}>
            <p className={`${ui.sectionTitle} mb-3`}>{BRANCH_COPY.pages.cashMovements.title}</p>
            <p className={`text-sm italic ${ui.muted}`}>
              {BRANCH_COPY.pages.cashMovements.empty}
            </p>
          </div>
        )}

        {/* ── Bottom row: chart + list ────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">

          {/* chart — 5 cols */}
          <div className="lg:col-span-5">
            <WeekSalesChart
              sessions={past}
              todayCashSales={current ? Number(current.total_cash_sales) || 0 : 0}
            />
          </div>

          {/* past sessions — 7 cols */}
          <div className="lg:col-span-7">
            <div className={`${ui.card} p-5 h-full`}>
              <p className={`${ui.sectionTitle} mb-1`}>{COPY.cashHistory.title}</p>

              {closedSessions.length === 0 ? (
                <p className={`text-sm ${ui.muted} mt-4`}>{BRANCH_COPY.states.empty}</p>
              ) : (
                <ul className={ui.divider}>
                  {closedSessions.map((s) => (
                    <SessionRow
                      key={s.id}
                      session={s}
                      onReprint={reprintCut}
                      reprinting={reprintingId === s.id}
                    />
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

      </div>

      {/* ── Close-shift modal overlay ──────────────────────────────────── */}
      {showCloseWizard && current && (
        <CloseShiftModal
          onClosed={handleShiftClosed}
          onCancel={() => setShowCloseWizard(false)}
        />
      )}

      {/* ── Movement modal (IN/OUT) ───────────────────────────────────── */}
      {movementModal && (
        <MovementModal
          type={movementModal}
          onClose={() => setMovementModal(null)}
          onConfirm={handleMovement}
        />
      )}

      {/* ── Open-shift modal ──────────────────────────────────────────── */}
      {openShiftModalVisible && (
        <OpenShiftModal
          onOpened={() => {
            setOpenShiftModalVisible(false)
            setJustOpened(true)
            loadAll()
          }}
          onCancel={() => setOpenShiftModalVisible(false)}
        />
      )}
    </div>
  )
}
