import { useEffect, useState, useCallback, useRef } from 'react'
import client from '../../api/client'
import { organizationApi } from '../../api/organization'
import { productsApi } from '../../api/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Modal } from '../../components/ui/Modal'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { toast } from '../../store/toastStore'
import type { Branch } from '../../types/auth'
import type { Product } from '../../types/products'

// ── Types ────────────────────────────────────────────────────────────────────

type TransferStatus = 'DRAFT' | 'REQUESTED' | 'PARTIALLY_FULFILLED' | 'COMPLETED' | 'CANCELLED'

interface TransferOrder {
  id: number
  requesting_branch_id: number
  status: TransferStatus
  notes: string | null
  created_at: string
  updated_at: string | null
}

interface TransferLine { product_id: string; sku: string; name: string; qty: number }

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<TransferStatus, string> = {
  DRAFT: 'Borrador',
  REQUESTED: 'Solicitado',
  PARTIALLY_FULFILLED: 'Parcial',
  COMPLETED: 'Completado',
  CANCELLED: 'Cancelado',
}

const STATUS_CLASS: Record<TransferStatus, string> = {
  DRAFT: 'bg-slate-700/50 text-slate-400',
  REQUESTED: 'bg-amber-500/20 text-amber-400',
  PARTIALLY_FULFILLED: 'bg-blue-500/20 text-blue-400',
  COMPLETED: 'bg-emerald-500/20 text-emerald-400',
  CANCELLED: 'bg-red-500/20 text-red-400',
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
}

const chipEstado = (s: TransferStatus) => (
  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_CLASS[s]}`}>{STATUS_LABEL[s]}</span>
)

// ── Component ─────────────────────────────────────────────────────────────────

export function Logistics() {
  const [orders, setOrders] = useState<TransferOrder[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [saving, setSaving] = useState(false)
  const esTelefono = useEsTelefono()

  // Form state
  const [toBranchId, setToBranchId] = useState<number | ''>('')
  const [lines, setLines] = useState<TransferLine[]>([])
  const [notes, setNotes] = useState('')

  // Product search
  const [productSearch, setProductSearch] = useState('')
  const [searchResults, setSearchResults] = useState<Product[]>([])
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [{ data: tOrders }, bArr] = await Promise.all([
        client.get<TransferOrder[]>('/transfers/'),
        organizationApi.getBranches(),
      ])
      setOrders(tOrders)
      setBranches(bArr)
    } catch { setOrders([]) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const openModal = () => {
    setLines([]); setNotes(''); setToBranchId(''); setProductSearch(''); setSearchResults([])
    setShowModal(true)
  }

  const addLine = (p: Product) => {
    setLines((prev) => {
      const existing = prev.find((l) => l.product_id === p.id)
      if (existing) return prev.map((l) => l.product_id === p.id ? { ...l, qty: l.qty + 1 } : l)
      return [...prev, { product_id: p.id, sku: p.sku, name: p.name, qty: 1 }]
    })
    setProductSearch(''); setSearchResults([])
  }

  const updateQty = (product_id: string, qty: number) => {
    if (qty <= 0) { setLines((p) => p.filter((l) => l.product_id !== product_id)); return }
    setLines((p) => p.map((l) => l.product_id === product_id ? { ...l, qty } : l))
  }

  const handleSave = async () => {
    if (!toBranchId || lines.length === 0) return
    setSaving(true)
    try {
      await client.post('/transfers/', {
        requesting_branch_id: toBranchId,
        notes: notes || null,
        lines: lines.map((l) => ({ variant_sku: l.sku, qty_requested: l.qty })),
      })
      setShowModal(false)
      load()
    } catch { toast.error('Error al crear la solicitud de transferencia') } finally { setSaving(false) }
  }

  const branchName = (id: number) => branches.find((b) => b.id === id)?.name ?? `Sucursal ${id}`

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-truck-loading text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Logística</h1>
        </div>}
        accionPrincipal={<button onClick={openModal} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nueva Solicitud
        </button>}
      />

      {/* Lista */}
      <DaxCard padding={false}>
        {esTelefono ? (
          <ListaTarjetas cargando={loading} vacio={orders.length === 0} textoVacio="Sin solicitudes de transferencia" className="p-3">
            {orders.map((o) => (
              <TarjetaFila key={o.id}
                titulo={`TR-${o.id}`}
                subtitulo={branchName(o.requesting_branch_id)}
                estado={chipEstado(o.status)}
                datos={[{ etiqueta: 'Fecha', valor: fmtDate(o.created_at) }, { etiqueta: 'Notas', valor: o.notes ?? '—' }]}
              />
            ))}
          </ListaTarjetas>
        ) : loading ? <Spinner text="Cargando transferencias..." /> : orders.length === 0 ? (
          <div className="p-12 text-center text-slate-600">
            <i className="fa-solid fa-truck text-4xl mb-3 block" />
            Sin solicitudes de transferencia
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Sucursal destino</th>
                  <th>Estado</th>
                  <th>Fecha</th>
                  <th>Notas</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="font-mono text-slate-400 text-xs">TR-{o.id}</td>
                    <td className="font-medium text-white">{branchName(o.requesting_branch_id)}</td>
                    <td>{chipEstado(o.status)}</td>
                    <td className="text-slate-400 text-xs">{fmtDate(o.created_at)}</td>
                    <td className="text-slate-500 text-xs max-w-[200px] truncate">{o.notes ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DaxCard>

      {/* Modal nueva solicitud: las líneas capturadas no se pierden por un clic en el fondo */}
      <Modal open={showModal} onClose={() => setShowModal(false)} title="Nueva Solicitud de Transferencia" size="lg" closeOnBackdrop={false}
        footer={<>
          <button onClick={() => setShowModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={handleSave}
            disabled={saving || !toBranchId || lines.length === 0}
            className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {saving
              ? <i className="fa-solid fa-spinner fa-spin" />
              : <><i className="fa-solid fa-paper-plane" /> Enviar Solicitud</>}
          </button>
        </>}>
        <div className="space-y-4">
          {/* Sucursal destino */}
          <div>
            <label className="dax-label">Sucursal que solicita</label>
            <select value={toBranchId} onChange={(e) => setToBranchId(Number(e.target.value))}
              className="dax-input w-full">
              <option value="">Seleccionar sucursal...</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </div>

          {/* Buscar producto */}
          <div>
            <label className="dax-label">Agregar producto</label>
            <div className="relative">
              <input type="text" placeholder="Nombre o SKU..."
                value={productSearch}
                onChange={(e) => {
                  setProductSearch(e.target.value)
                  if (searchTimer.current) clearTimeout(searchTimer.current)
                  searchTimer.current = setTimeout(async () => {
                    if (!e.target.value.trim()) { setSearchResults([]); return }
                    try {
                      const r = await productsApi.search(e.target.value, 0, 8)
                      setSearchResults(r.items)
                    } catch { setSearchResults([]) }
                  }, 300)
                }}
                className="dax-input w-full text-sm" />
              {searchResults.length > 0 && (
                <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl overflow-hidden">
                  {searchResults.map((p) => (
                    <button key={p.id} onClick={() => addLine(p)}
                      className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-700/60 text-left text-sm border-b border-slate-700/40 last:border-0 max-md:min-h-[44px]">
                      <span className="text-white font-medium">{p.name}</span>
                      <span className="text-slate-500 text-xs font-mono">{p.sku}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Líneas */}
          {lines.length > 0 && (
            <div className="border border-slate-700/50 rounded-lg overflow-hidden">
              {lines.map((l) => (
                <div key={l.product_id} className="flex items-center justify-between px-3 py-2 border-b border-slate-700/40 last:border-0">
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{l.name}</p>
                    <p className="text-slate-500 text-xs font-mono">{l.sku}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-3">
                    <button onClick={() => updateQty(l.product_id, l.qty - 1)} aria-label="Una menos"
                      className="w-6 h-6 max-md:w-11 max-md:h-11 bg-slate-700 rounded text-xs hover:bg-slate-600">−</button>
                    <span className="w-8 text-center font-bold text-white text-sm">{l.qty}</span>
                    <button onClick={() => updateQty(l.product_id, l.qty + 1)} aria-label="Una más"
                      className="w-6 h-6 max-md:w-11 max-md:h-11 bg-slate-700 rounded text-xs hover:bg-slate-600">+</button>
                    <button onClick={() => setLines((p) => p.filter((i) => i.product_id !== l.product_id))} aria-label="Quitar"
                      className="dax-btn-icon text-slate-600 hover:text-red-400 ml-1">
                      <i className="fa-solid fa-xmark text-xs" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Notas */}
          <div>
            <label className="dax-label">Notas (opcional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
              rows={2} className="dax-input w-full text-sm resize-none"
              placeholder="Motivo, urgencia, observaciones..." />
          </div>
        </div>
      </Modal>
    </div>
  )
}
