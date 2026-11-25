import { useState } from 'react'
import client from '../../api/client'
import { BRANCH_COPY } from '../../copy/branchCopy'
import { esRolCaja } from '../../utils/rolesCaja'
import { useAuthStore } from '../../store/authStore'
import { ui } from './branchUI'

type Step = 'find' | 'mark' | 'confirm' | 'done'

interface SaleLine {
  id: string
  variant_id?: string
  sku?: string
  description?: string
  quantity: number
  unit_price?: string
}

interface Sale {
  id: number | string
  folio?: number | string | null
  series?: string | null
  total_amount: string
  lines: SaleLine[]
}

const REASONS = ['Defecto de fábrica', 'Producto incorrecto', 'Cliente cambió de opinión', 'Otro']

// Step pill — shows current position in wizard
function StepPills({ current }: { current: Step }) {
  const steps: Step[] = ['find', 'mark', 'confirm']
  const labels = ['Buscar', 'Artículos', 'Confirmar']
  return (
    <div className="flex items-center gap-2 mb-6">
      {steps.map((s, i) => {
        const active = s === current
        const past   = steps.indexOf(current) > i
        return (
          <div key={s} className="flex items-center gap-2">
            <span className={`
              inline-flex items-center justify-center
              w-6 h-6 rounded-full text-xs font-bold
              transition-colors
              ${active ? 'bg-purple-600 text-white' : past ? 'bg-purple-200 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300' : 'bg-stone-200 dark:bg-slate-800 text-slate-400'}
            `}>
              {past ? <i className="fa-solid fa-check text-[9px]" /> : i + 1}
            </span>
            <span className={`text-xs font-medium ${active ? 'text-slate-900 dark:text-slate-100' : 'text-slate-400 dark:text-slate-500'}`}>
              {labels[i]}
            </span>
            {i < steps.length - 1 && (
              <span className="text-stone-300 dark:text-slate-700 mx-1">·</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function ReturnsBranchView() {
  const esCajera = esRolCaja(useAuthStore((s) => s.user?.role))
  const [step, setStep] = useState<Step>('find')
  const [query, setQuery] = useState('')
  const [sale, setSale] = useState<Sale | null>(null)
  const [picked, setPicked] = useState<Record<string, { qty: number; reason: string }>>({})
  const [refundMethod, setRefundMethod] = useState<'CASH' | 'CARD' | 'STORE_CREDIT'>('CASH')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function findSale() {
    setError(null)
    try {
      const raw = query.trim()
      if (!raw) throw new Error('Escribe un folio.')
      const m = raw.match(/^([A-Za-z]+)?-?(\d+)$/)
      if (!m) throw new Error('Folio inválido. Usa el formato A-1234 o 1234.')
      const series = (m[1] || 'A').toUpperCase()
      const folio  = m[2]
      const { data } = await client.get(`/sales/by-folio/${series}/${folio}`)
      setSale(data); setStep('mark')
    } catch (e: any) {
      if (e?.response?.status === 404) {
        // La cajera solo encuentra ventas de hoy: un folio viejo responde 404, no "inexistente".
        setError(esCajera
          ? 'Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.'
          : 'No encontré esa venta.')
      }
      else setError(e?.message ?? 'Error')
    }
  }

  async function submit() {
    if (!sale) return
    setSubmitting(true); setError(null)
    try {
      const items = Object.entries(picked)
        .filter(([, v]) => v.qty > 0)
        .map(([line_id, v]) => {
          const line = sale.lines.find((l) => String(l.id) === line_id)
          const unit = Number(line?.unit_price ?? 0)
          return {
            variant_id: line?.variant_id ?? '',
            quantity: v.qty,
            refund_amount: Number((unit * v.qty).toFixed(2)),
            is_inventory_reentry: true,
          }
        })
      const total_refunded = items.reduce((s, it) => s + it.refund_amount, 0)
      const reasonsList = Array.from(new Set(Object.values(picked).filter((v) => v.qty > 0).map((v) => v.reason)))
      const reason = reasonsList.join('; ') || 'Devolución'
      await client.post('/returns/', {
        sale_id: sale.id,
        reason,
        total_refunded,
        refund_method: refundMethod,
        items,
      })
      setStep('done')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'No pude registrar la devolución.')
    } finally { setSubmitting(false) }
  }

  return (
    <div className={`${ui.page} py-6`}>
      <div className="max-w-2xl mx-auto px-4">
        <h1 className={`${ui.pageTitle} mb-6`}>{BRANCH_COPY.pages.returns}</h1>

        {step !== 'done' && <StepPills current={step} />}

        {error && (
          <div className="mb-4 rounded-2xl bg-rose-50 dark:bg-rose-900/20 border border-rose-200/60 dark:border-rose-800/40 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
            {error}
          </div>
        )}

        {step === 'find' && (
          <section className={`${ui.card} p-6 space-y-4`}>
            <div>
              <label className={`block ${ui.kpiLabel} mb-2`}>Folio de la venta</label>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && findSale()}
                className={ui.input}
                placeholder="V-0001234"
              />
            </div>
            <button onClick={findSale} className={`${ui.btnPrimary} w-full`}>
              <i className="fa-solid fa-magnifying-glass text-sm" aria-hidden="true" />
              Buscar venta
            </button>
          </section>
        )}

        {step === 'mark' && sale && (
          <section className={`${ui.card} p-6 space-y-4`}>
            <p className={`text-sm ${ui.muted}`}>
              Folio {sale.series ?? ''}{sale.folio ?? sale.id} · Total {sale.total_amount}
            </p>
            {sale.lines.map((l) => {
              const id = String(l.id)
              return (
                <div key={id} className="rounded-2xl bg-stone-50 dark:bg-slate-800/60 p-4 space-y-3">
                  <div>
                    <p className="font-medium text-slate-900 dark:text-slate-100">{l.description ?? l.sku ?? id}</p>
                    <p className={`text-xs ${ui.muted}`}>{l.sku ?? ''} · {l.quantity} unidades</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className={`block ${ui.kpiLabel} mb-1.5`}>Cantidad a devolver</label>
                      <input
                        type="number"
                        min={0}
                        max={l.quantity}
                        value={picked[id]?.qty ?? 0}
                        onChange={(e) => setPicked((p) => ({
                          ...p, [id]: { qty: Number(e.target.value), reason: p[id]?.reason ?? REASONS[0] },
                        }))}
                        className={ui.input}
                      />
                    </div>
                    <div>
                      <label className={`block ${ui.kpiLabel} mb-1.5`}>Motivo</label>
                      <select
                        value={picked[id]?.reason ?? REASONS[0]}
                        onChange={(e) => setPicked((p) => ({
                          ...p, [id]: { qty: p[id]?.qty ?? 0, reason: e.target.value },
                        }))}
                        className={ui.input}
                      >
                        {REASONS.map((r) => <option key={r}>{r}</option>)}
                      </select>
                    </div>
                  </div>
                </div>
              )
            })}
            <button onClick={() => setStep('confirm')} className={`${ui.btnPrimary} w-full`}>
              Continuar
            </button>
          </section>
        )}

        {step === 'confirm' && (
          <section className={`${ui.card} p-6 space-y-4`}>
            <div>
              <label className={`block ${ui.kpiLabel} mb-2`}>Reembolso por</label>
              <select
                value={refundMethod}
                onChange={(e) => setRefundMethod(e.target.value as typeof refundMethod)}
                className={ui.input}
              >
                <option value="CASH">Efectivo</option>
                <option value="CARD">Tarjeta</option>
                <option value="STORE_CREDIT">Nota de crédito</option>
              </select>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setStep('mark')} className={`${ui.btnSecondary} flex-1`}>
                Atrás
              </button>
              <button
                onClick={submit}
                disabled={submitting}
                className={`${ui.btnPrimary} flex-1 disabled:opacity-40 disabled:cursor-not-allowed`}
              >
                {submitting ? BRANCH_COPY.states.loading : 'Confirmar devolución'}
              </button>
            </div>
          </section>
        )}

        {step === 'done' && (
          <section className={`${ui.card} p-8 text-center space-y-4`}>
            <div className="w-14 h-14 rounded-full bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center mx-auto">
              <i className="fa-solid fa-check text-2xl text-purple-600 dark:text-purple-400" />
            </div>
            <p className="font-semibold text-lg text-slate-900 dark:text-slate-100">Devolución registrada.</p>
            <button
              onClick={() => { setStep('find'); setSale(null); setPicked({}); setQuery('') }}
              className={ui.btnSecondary}
            >
              Otra devolución
            </button>
          </section>
        )}
      </div>
    </div>
  )
}
