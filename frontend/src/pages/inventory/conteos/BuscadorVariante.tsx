import { useEffect, useState } from 'react'

import type { ProductoResumen } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import type { Product } from '../../../types/products'
import { resumenDesdeProducto } from './sesion'

/** Busca por nombre/SKU (`posSearch`, parcial) y deja elegir la talla. */
export function BuscadorVariante({ open, onClose, onElegir, titulo = 'Buscar pieza' }: {
  open: boolean
  onClose: () => void
  onElegir: (p: ProductoResumen) => void
  titulo?: string
}) {
  const [q, setQ] = useState('')
  const [resultados, setResultados] = useState<Product[]>([])
  const [buscando, setBuscando] = useState(false)

  useEffect(() => {
    if (!open) { setQ(''); setResultados([]); return }
  }, [open])

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
    <Modal open={open} onClose={onClose} title={titulo} size="md">
      <input autoFocus className="dax-input w-full" placeholder="Nombre, marca o SKU…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-3 space-y-2 max-h-[60vh] overflow-y-auto">
        {buscando && <Spinner />}
        {!buscando && q.trim().length >= 2 && resultados.length === 0 && <p className="text-sm text-slate-400">Sin resultados.</p>}
        {resultados.map((p) => (
          <div key={p.id} className="rounded-lg border border-slate-800 p-2">
            <div className="text-sm text-white font-semibold">{p.sale_name ?? p.name}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {(p.variants ?? []).map((v) => (
                <button key={v.id} type="button" className="dax-btn-secondary text-xs"
                  onClick={() => { onElegir(resumenDesdeProducto(p, v)); onClose() }}>
                  {[v.color, v.size].filter(Boolean).join(' / ') || v.sku}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  )
}
