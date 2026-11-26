// frontend/src/pages/sales/FiltroProducto.tsx
import { useEffect, useState } from 'react'
import { productsApi } from '../../api/products'
import { Modal } from '../../components/ui/Modal'
import { Spinner } from '../../components/ui/Spinner'
import type { Product, ProductVariant } from '../../types/products'

/** Producto (o una talla/color) por el que se filtran las ventas. */
export interface ProductoFiltrado {
  productId: string
  variantId?: string
  nombre: string
}

const nombreVariante = (v: ProductVariant) => [v.color, v.size].filter(Boolean).join(' / ') || v.variant_name || v.sku

/**
 * Botón «Producto» de la barra de filtros de Ventas. Sin elegir, abre un
 * buscador (nombre, marca o SKU); con un producto elegido muestra su nombre y
 * una ✕ para quitarlo. Se puede elegir el producto completo (todas sus tallas)
 * o una sola variante.
 */
export function FiltroProducto({ valor, onCambio }: {
  valor: ProductoFiltrado | null
  onCambio: (p: ProductoFiltrado | null) => void
}) {
  const [abierto, setAbierto] = useState(false)

  if (valor) {
    return (
      <span className="inline-flex items-center gap-1 rounded-lg border border-dax-accent bg-dax-surface px-2 py-1 text-xs text-dax-text max-w-[260px]" data-testid="filtro-producto">
        <i className="fa-solid fa-box text-dax-accent-text" aria-hidden="true" />
        <span className="truncate" title={valor.nombre}>{valor.nombre}</span>
        <button type="button" onClick={() => onCambio(null)} className="dax-btn-ghost dax-btn-icon !p-0 w-6 h-6 justify-center" aria-label="Quitar filtro de producto">
          <i className="fa-solid fa-xmark" aria-hidden="true" />
        </button>
      </span>
    )
  }

  return (
    <>
      <button type="button" onClick={() => setAbierto(true)} className="dax-btn-secondary text-xs max-sm:min-h-[44px]">
        <i className="fa-solid fa-box" aria-hidden="true" /> Producto
      </button>
      <BuscadorProducto
        open={abierto}
        onClose={() => setAbierto(false)}
        onElegir={(p) => { onCambio(p); setAbierto(false) }}
      />
    </>
  )
}

function BuscadorProducto({ open, onClose, onElegir }: {
  open: boolean
  onClose: () => void
  onElegir: (p: ProductoFiltrado) => void
}) {
  const [q, setQ] = useState('')
  const [resultados, setResultados] = useState<Product[]>([])
  const [buscando, setBuscando] = useState(false)

  useEffect(() => { if (!open) { setQ(''); setResultados([]) } }, [open])

  useEffect(() => {
    const texto = q.trim()
    if (texto.length < 2) { setResultados([]); return }
    const t = window.setTimeout(async () => {
      setBuscando(true)
      try { setResultados(await productsApi.posSearch(texto, 'name_asc')) } catch { setResultados([]) } finally { setBuscando(false) }
    }, 300)
    return () => window.clearTimeout(t)
  }, [q])

  return (
    <Modal open={open} onClose={onClose} title="Filtrar por producto vendido" size="md">
      <input
        autoFocus
        type="search"
        aria-label="Buscar producto"
        className="dax-input w-full"
        placeholder="Nombre, marca o SKU…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="mt-3 space-y-2 max-h-[60vh] overflow-y-auto">
        {buscando && <Spinner />}
        {!buscando && q.trim().length >= 2 && resultados.length === 0 && (
          <p className="text-sm text-dax-muted">Sin resultados.</p>
        )}
        {resultados.map((p) => {
          const nombre = p.sale_name ?? p.name
          const variantes = p.variants ?? []
          return (
            <div key={p.id} className="rounded-lg border border-dax-border-dim p-2">
              <button
                type="button"
                className="w-full text-left text-sm font-semibold text-dax-text hover:text-dax-accent-text"
                onClick={() => onElegir({ productId: p.id, nombre })}
              >
                {nombre}
                <span className="ml-2 font-mono text-[11px] font-normal text-dax-muted">{p.sku}</span>
              </button>
              {variantes.length > 1 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  <button type="button" className="dax-btn-primary text-xs" onClick={() => onElegir({ productId: p.id, nombre })}>
                    Todas
                  </button>
                  {variantes.map((v) => (
                    <button
                      key={v.id}
                      type="button"
                      className="dax-btn-secondary text-xs"
                      onClick={() => onElegir({ productId: p.id, variantId: v.id, nombre: `${nombre} · ${nombreVariante(v)}` })}
                    >
                      {nombreVariante(v)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Modal>
  )
}
