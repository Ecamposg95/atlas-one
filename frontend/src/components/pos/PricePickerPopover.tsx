import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { formatCurrency } from '../../utils/currency'
import { posicionaPopover, ANCHO_POPOVER, type PosicionPopover } from './popoverPos'

interface Tier {
  id: string
  price_name: string
  unit_price: number
  min_quantity: number
}

interface Props {
  open: boolean
  triggerRef: React.RefObject<HTMLElement | null>
  basePrice: number
  currentPrice: number
  tiers: Tier[]
  isForced: boolean
  priceInput: string
  onPriceInputChange: (v: string) => void
  onSelectTier: (unit_price: number, tier_name: string) => void
  onSelectFree: (unit_price: number) => void
  onResetToAuto: () => void
  onClose: () => void
}

export function PricePickerPopover({
  open,
  triggerRef,
  basePrice,
  currentPrice,
  tiers,
  isForced,
  priceInput,
  onPriceInputChange,
  onSelectTier,
  onSelectFree,
  onResetToAuto,
  onClose,
}: Props) {
  const popRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<PosicionPopover | null>(null)

  const reposition = () => {
    const trigger = triggerRef.current
    const pop = popRef.current
    if (!trigger) return
    const r = trigger.getBoundingClientRect()
    const popH = pop?.offsetHeight ?? 280
    setPos(posicionaPopover(r, popH, window.innerWidth, window.innerHeight))
  }

  useLayoutEffect(() => {
    if (!open) { setPos(null); return }
    reposition()
    // Re-measure once the portal renders so we know the real popover height.
    requestAnimationFrame(reposition)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const onScrollOrResize = () => reposition()
    window.addEventListener('resize', onScrollOrResize)
    window.addEventListener('scroll', onScrollOrResize, true)
    // Also attach to every scrollable ancestor of the trigger so that scrolling
    // an inner container (e.g. CartPanel's overflow-y-auto region) repositions
    // the popover. window 'scroll' with capture does not fire for nested
    // scroll containers, so this is required for correct positioning.
    const ancestors: Element[] = []
    const trigger = triggerRef.current
    if (trigger) {
      let cur: Element | null = trigger.parentElement
      while (cur && cur !== document.body) {
        const s = window.getComputedStyle(cur).overflowY
        if (s === 'auto' || s === 'scroll' || s === 'overlay') ancestors.push(cur)
        cur = cur.parentElement
      }
      for (const el of ancestors) {
        el.addEventListener('scroll', onScrollOrResize, { passive: true })
      }
    }
    return () => {
      window.removeEventListener('resize', onScrollOrResize)
      window.removeEventListener('scroll', onScrollOrResize, true)
      for (const el of ancestors) {
        el.removeEventListener('scroll', onScrollOrResize)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (popRef.current?.contains(target)) return
      if (triggerRef.current?.contains(target)) return
      onClose()
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose, triggerRef])

  if (!open) return null

  const sortedTiers = [...tiers].sort((a, b) => a.min_quantity - b.min_quantity)
  const isActive = (price: number) => Math.abs(currentPrice - price) < 0.01

  const submitFree = () => {
    const p = Math.max(0, parseFloat(priceInput) || 0)
    if (p > 0) onSelectFree(p)
    else onClose()
  }

  return createPortal(
    <div
      ref={popRef}
      role="dialog"
      aria-label="Elegir precio"
      style={{
        position: 'fixed',
        top: pos?.top ?? -9999,
        left: pos?.left ?? -9999,
        width: pos?.width ?? ANCHO_POPOVER,
        zIndex: 9999,
        // Solid background — `--dax-elevated` is only ~4% opacity and lets
        // cart text bleed through the popover.
        background: 'var(--dax-card-solid)',
        border: '1px solid rgba(139,92,246,0.45)',
        borderRadius: 12,
        boxShadow: '0 24px 64px rgba(0,0,0,0.7), 0 0 0 1px rgba(0,0,0,0.4)',
        opacity: pos ? 1 : 0,
        transition: 'opacity 120ms ease-out',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2"
           style={{ borderBottom: '1px solid rgba(139,92,246,0.15)' }}>
        <p className="text-xs font-bold uppercase tracking-widest"
           style={{ color: 'var(--dax-text-muted)' }}>Elegir precio</p>
        <button onClick={onClose}
                className="text-dax-muted hover:text-dax-text text-sm w-7 h-7 flex items-center justify-center rounded hover:bg-dax-elevated">
          <i className="fa-solid fa-xmark" />
        </button>
      </div>

      {/* Tier list */}
      <div className="p-2 space-y-1">
        <TierButton
          label="Menudeo"
          price={basePrice}
          active={isActive(basePrice) && !isForced}
          onClick={() => onSelectTier(basePrice, 'Menudeo')}
        />
        {sortedTiers.map((t) => (
          <TierButton
            key={t.id}
            label={t.price_name}
            sub={`≥${t.min_quantity}pz`}
            price={t.unit_price}
            active={isActive(t.unit_price) && !isForced}
            onClick={() => onSelectTier(t.unit_price, t.price_name)}
          />
        ))}
      </div>

      {/* Divider */}
      <div style={{ borderTop: '1px dashed rgba(139,92,246,0.18)' }} />

      {/* Libre */}
      <div className="p-2 flex items-center gap-2">
        <span className="text-xs font-semibold flex-shrink-0"
              style={{ color: 'var(--dax-text-faint)' }}>Libre $</span>
        <input
          type="number"
          autoFocus={tiers.length === 0}
          value={priceInput}
          onChange={(e) => onPriceInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitFree()
          }}
          placeholder="0.00"
          className="flex-1 text-center text-base rounded px-2 outline-none tabular-nums"
          style={{
            background: 'var(--dax-card)',
            border: '1px solid rgba(139,92,246,0.5)',
            color: 'var(--dax-text)',
            height: 44,
          }}
          min="0" step="0.01"
        />
        <button
          onClick={submitFree}
          className="text-sm font-bold rounded px-3 transition-colors"
          style={{
            height: 44,
            background: 'var(--dax-accent-soft)',
            color: 'var(--dax-accent-text)',
            border: '1px solid var(--dax-accent)',
          }}
        >
          Aplicar
        </button>
      </div>

      {/* Reset */}
      {isForced && (
        <div style={{ borderTop: '1px solid rgba(139,92,246,0.15)' }}>
          <button
            onClick={onResetToAuto}
            className="w-full flex items-center justify-center gap-2 min-h-[44px] text-sm font-semibold transition-colors hover:bg-dax-elevated"
            style={{ color: 'var(--dax-warning)' }}
          >
            <i className="fa-solid fa-rotate-left text-[11px]" />
            Volver a precio automático
          </button>
        </div>
      )}
    </div>,
    document.body,
  )
}

function TierButton({
  label, sub, price, active, onClick,
}: {
  label: string
  sub?: string
  price: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center justify-between rounded-lg px-3 transition-colors text-left"
      style={{
        height: 48,
        background: active ? 'var(--dax-accent-soft)' : 'transparent',
        border: active ? '1px solid var(--dax-accent)' : '1px solid rgba(148,163,184,0.12)',
        color: 'var(--dax-text)',
      }}
    >
      <span className="text-sm font-bold">
        {label}
        {sub && <span className="ml-2 text-xs font-normal opacity-50">({sub})</span>}
      </span>
      <span className="text-base tabular-nums font-bold" style={{ color: '#86efac' }}>
        {formatCurrency(price)}
      </span>
    </button>
  )
}
