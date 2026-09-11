import { useCallback, useEffect, useRef, useState } from 'react'

import { organizationApi } from '../../api/organization'
import { productsApi } from '../../api/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { useAuthStore } from '../../store/authStore'
import type { Branch } from '../../types/auth'
import type { Product } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import {
  createDetector, isNativeDetectorAvailable, normalizeCode, normalizeTyped,
} from './barcodeReader'
import { currentStock, parseTierPrice } from './productStock'
import { buildDetailsUpdatePayload, buildPriceUpdatePayload, type TierEdits } from './scanPayload'
import { computeAdjustment } from './stockAdjust'

/**
 * Scanner de tienda.
 *
 * Para el admin/gerente/cajero parado en el pasillo: escanea un producto con
 * la cámara del teléfono, lo ve y corrige precio, escalones y existencias ahí
 * mismo. El scope por organización y sucursal lo aplica el backend — esta
 * pantalla no alcanza otra tienda.
 *
 * v1 a propósito: foto y ficha (nombre/departamento/marca) del producto
 * quedan fuera hasta saber si la herramienta sirve en piso. Sí se porta la
 * corrección de precio/escalones, el conteo de existencias y la ruta para
 * asignarle un código de barras a un producto que no tiene uno.
 *
 * La sucursal es explícita y no se deduce del token: un ADMINISTRADOR de HQ
 * tiene `branch_id = null`, y sin sucursal no se puede registrar un conteo de
 * inventario. Se recuerda por dispositivo.
 */

const BRANCH_KEY = 'atlas_scanner_branch_id'

export function StoreScanner() {
  const user = useAuthStore((s) => s.user)

  const [code, setCode] = useState('')
  const [results, setResults] = useState<Product[] | null>(null)
  const [selected, setSelected] = useState<Product | null>(null)
  const [loading, setLoading] = useState(false)
  // Un fallo de red NO es lo mismo que un código inexistente: confundirlos
  // ofrecía pegar el código escaneado a otro producto por un problema de señal.
  const [lookupError, setLookupError] = useState(false)
  const [camOn, setCamOn] = useState(false)
  const [camError, setCamError] = useState<string | null>(null)

  const [branches, setBranches] = useState<Branch[]>([])
  const [branchId, setBranchId] = useState<number | null>(() => {
    const stored = localStorage.getItem(BRANCH_KEY)
    return stored ? Number(stored) : null
  })

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const loopRef = useRef<number | null>(null)
  // Evita re-disparar la búsqueda mientras el mismo código sigue frente a la
  // cámara: sin esto, un producto quieto dispara una petición por cuadro.
  const lastCodeRef = useRef<string>('')
  // Se marca al desmontar para abortar un arranque de cámara en vuelo.
  const cancelledRef = useRef(false)

  // El usuario con sucursal propia (cajero/gerente) no elige nada.
  const effectiveBranchId = user?.branch_id ?? branchId

  useEffect(() => {
    if (user?.branch_id) return
    void organizationApi.getBranches()
      .then((bs) => setBranches(bs.filter((b) => b.branch_type !== 'HQ')))
      .catch(() => setBranches([]))
  }, [user?.branch_id])

  // `raw` ya viene limpio por quien llama: la cámara con `normalizeCode` (quita
  // el ruido del lector) y el teclado con `normalizeTyped` (solo recorta). Si
  // se limpiaran igual, un SKU como `m-1151` se volvería `m1151` y la búsqueda
  // exacta dejaría de empatar.
  const lookup = useCallback(async (raw: string) => {
    const clean = raw.trim()
    if (!clean) return
    setLoading(true)
    setSelected(null)
    setLookupError(false)
    try {
      const found = await productsApi.scanExact(clean, effectiveBranchId)
      setResults(found)
      // Un solo resultado se abre directo. Con más de uno hay que preguntar:
      // un mismo código puede repetirse dentro de la misma organización.
      if (found.length === 1) setSelected(found[0])
    } catch {
      // Sin resultados NI oferta de asignar el código: no sabemos si existe.
      setResults(null)
      setLookupError(true)
    } finally {
      setLoading(false)
    }
  }, [effectiveBranchId])

  const stopCam = useCallback(() => {
    if (loopRef.current) { window.clearInterval(loopRef.current); loopRef.current = null }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    // Sin esto, volver a escanear el MISMO producto no hacía nada nunca más:
    // el guard anti-repetición por cuadro se quedaba pegado para siempre.
    // Pasa al verificar que un precio quedó bien, o tras un intento fallido.
    lastCodeRef.current = ''
    // El track detenido no basta: sin soltar srcObject el <video> conserva la
    // referencia y algunos navegadores dejan el indicador de cámara prendido.
    if (videoRef.current) videoRef.current.srcObject = null
    setCamOn(false)
  }, [])

  const startCam = useCallback(async () => {
    setCamError(null)
    lastCodeRef.current = ''
    // `startCam` espera a getUserMedia, a play() y —en iPhone— a la descarga de
    // la librería de decodificación. Si el admin navega durante esas esperas, la
    // limpieza del desmontaje ya corrió y el stream quedaba vivo con la cámara
    // encendida. Este flag deja abortar en cada punto de espera.
    cancelledRef.current = false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
      })
      if (cancelledRef.current) { stream.getTracks().forEach((tr) => tr.stop()); return }
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCamOn(true)

      // A diferencia de `getUserMedia`, esto puede fallar con la cámara YA
      // encendida (p. ej. Safari sin `BarcodeDetector` nativo) — el catch de
      // afuera diría "no se pudo abrir la cámara", que sería falso: sí se
      // abrió, solo no puede decodificar. Se apaga y se avisa aparte.
      let detector
      try {
        detector = await createDetector()
      } catch (err) {
        stopCam()
        setCamError(err instanceof Error ? err.message : 'Este navegador no puede leer códigos de barras con la cámara.')
        return
      }
      if (cancelledRef.current) { stopCam(); return }
      loopRef.current = window.setInterval(async () => {
        const video = videoRef.current
        const canvas = canvasRef.current
        if (!video || !canvas || video.readyState < 2) return
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d')?.drawImage(video, 0, 0)
        try {
          const hits = await detector.detect(canvas)
          const clean = normalizeCode(hits?.[0]?.rawValue)
          if (clean && clean !== lastCodeRef.current) {
            lastCodeRef.current = clean
            setCode(clean)
            void lookup(clean)
          }
        } catch {
          // Cuadro sin código legible: es el caso normal entre lecturas.
        }
      }, 400)
    } catch {
      setCamError(
        'No se pudo abrir la cámara. Revisa el permiso del navegador para este sitio, o teclea el código a mano.',
      )
      setCamOn(false)
    }
  }, [lookup, stopCam])

  useEffect(() => () => { cancelledRef.current = true; stopCam() }, [stopCam])

  const pickBranch = (id: number | null) => {
    setBranchId(id)
    if (id) localStorage.setItem(BRANCH_KEY, String(id))
    else localStorage.removeItem(BRANCH_KEY)
  }

  return (
    <div className="space-y-4 max-w-lg mx-auto pb-24">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-barcode text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Scanner de tienda</h1>
      </div>

      {!user?.branch_id && (
        <DaxCard>
          <label className="block">
            <span className="text-xs text-slate-400">¿En qué sucursal estás?</span>
            <select
              value={effectiveBranchId ?? ''}
              onChange={(e) => pickBranch(e.target.value ? Number(e.target.value) : null)}
              className="dax-input mt-1"
            >
              <option value="">— Elige la sucursal —</option>
              {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <p className="text-[11px] text-slate-500 mt-1">
            Se usa para registrar los conteos de inventario. Se recuerda en este dispositivo.
          </p>
        </DaxCard>
      )}

      <DaxCard>
        <div className="space-y-3">
          <div className="relative rounded-lg overflow-hidden bg-black/40" style={{ aspectRatio: '4/3' }}>
            <video ref={videoRef} playsInline muted className="w-full h-full object-cover" />
            <canvas ref={canvasRef} className="hidden" />
            {!camOn && (
              <div className="absolute inset-0 flex items-center justify-center">
                <button onClick={startCam} className="dax-btn-primary">
                  <i className="fa-solid fa-camera" />Encender cámara
                </button>
              </div>
            )}
          </div>

          {camOn && (
            <button onClick={stopCam} className="text-xs text-slate-400 underline">
              Apagar cámara
            </button>
          )}

          {camError && <p className="text-sm text-amber-400">{camError}</p>}
          {!isNativeDetectorAvailable() && (
            <p className="text-[11px] text-slate-500">
              Este navegador decodifica por software; en Android con Chrome el escaneo es más rápido.
            </p>
          )}

          {/* Siempre disponible: hay variantes sin código de barras, y cuando
              la etiqueta está rota escanear no es opción. */}
          <form
            onSubmit={(e) => { e.preventDefault(); void lookup(normalizeTyped(code)) }}
            className="flex gap-2"
          >
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="text"
              placeholder="O teclea el código / SKU"
              className="dax-input flex-1"
            />
            <button type="submit" className="dax-btn-secondary">Buscar</button>
          </form>
        </div>
      </DaxCard>

      {loading && <div className="flex justify-center py-6"><Spinner /></div>}

      {!loading && lookupError && (
        <DaxCard>
          <p className="text-amber-400 text-sm">
            No se pudo consultar el catálogo. Revisa la señal y vuelve a intentar
            — no sabemos si ese código existe o no.
          </p>
        </DaxCard>
      )}

      {!loading && !lookupError && results?.length === 0 && (
        <AttachCodePanel
          code={normalizeTyped(code)}
          onAttached={(p) => { setResults([p]); setSelected(p) }}
        />
      )}

      {!loading && results && results.length > 1 && !selected && (
        <DaxCard>
          <p className="text-amber-400 text-sm font-bold mb-2">
            Ese código está en {results.length} productos. ¿Cuál es?
          </p>
          <div className="space-y-2">
            {results.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelected(p)}
                className="w-full text-left px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700"
              >
                <span className="text-white font-semibold">{p.name}</span>
                <span className="text-slate-400 text-xs ml-2">{p.sku}</span>
                <span className="text-emerald-400 float-right">{formatCurrency(p.price)}</span>
              </button>
            ))}
          </div>
        </DaxCard>
      )}

      {selected && (
        <ProductEditPanel
          product={selected}
          branchId={effectiveBranchId ?? null}
          onChanged={setSelected}
        />
      )}
    </div>
  )
}

/**
 * Código escaneado que no existe en el catálogo.
 *
 * Es el caso más valioso del scanner: hay variantes sin código de barras, así
 * que escanear el producto físico no las encuentra. En vez de un callejón sin
 * salida, se busca el producto por nombre y se le pega el código — desde ese
 * momento ya es escaneable.
 */
function AttachCodePanel({
  code,
  onAttached,
}: {
  code: string
  onAttached: (p: Product) => void
}) {
  const [term, setTerm] = useState('')
  const [hits, setHits] = useState<Product[]>([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const search = async () => {
    if (!term.trim()) return
    setBusy(true)
    try {
      const res = await productsApi.search(term, 0, 15)
      setHits(res.items ?? [])
    } catch {
      setHits([])
    } finally {
      setBusy(false)
    }
  }

  const attach = async (p: Product) => {
    setBusy(true)
    setMsg(null)
    try {
      const updated = await productsApi.update(
        p.id,
        buildDetailsUpdatePayload(p, { barcode: code }),
      )
      onAttached(updated)
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo asignar el código. ¿Ya lo tiene otro producto?'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <DaxCard>
      <p className="text-slate-300 text-sm">
        No hay ningún producto con el código <b className="font-mono">{code}</b> en esta sucursal.
      </p>

      {code && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-slate-400">¿Se lo asignamos a un producto?</p>
          <form onSubmit={(e) => { e.preventDefault(); void search() }} className="flex gap-2">
            <input
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="Busca por nombre"
              className="dax-input flex-1"
            />
            <button type="submit" className="dax-btn-secondary">Buscar</button>
          </form>

          {busy && <div className="flex justify-center py-3"><Spinner /></div>}

          <div className="space-y-2">
            {hits.map((p) => (
              <button
                key={p.id}
                onClick={() => attach(p)}
                disabled={busy}
                className="w-full text-left px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50"
              >
                <span className="text-white font-semibold">{p.name}</span>
                <span className="text-slate-400 text-xs ml-2 font-mono">{p.sku}</span>
                {p.barcode && (
                  <span className="block text-[11px] text-amber-400">
                    Ya tiene el código {p.barcode} — se reemplazará
                  </span>
                )}
              </button>
            ))}
          </div>

          {msg && <p className="text-sm text-rose-400">{msg}</p>}
        </div>
      )}
    </DaxCard>
  )
}

function Msg({ text }: { text: string | null }) {
  if (!text) return null
  return <p className="text-sm text-center text-slate-300 mt-2">{text}</p>
}

/**
 * Panel del producto escaneado: precios/escalones y conteo de existencias.
 *
 * Cada bloque guarda por su cuenta y con su propio endpoint — en el pasillo se
 * corrige una cosa a la vez, y un error de red en el conteo no debe tumbar el
 * cambio de precio.
 */
function ProductEditPanel({
  product,
  branchId,
  onChanged,
}: {
  product: Product
  branchId: number | null
  onChanged: (p: Product) => void
}) {
  return (
    <div className="space-y-3">
      <DaxCard>
        <h2 className="text-lg font-black text-white leading-tight">{product.name}</h2>
        <p className="text-xs text-slate-400 font-mono">
          {product.sku}
          {product.barcode ? ` · ${product.barcode}` : ' · sin código'}
        </p>
      </DaxCard>

      <PricesSection product={product} onChanged={onChanged} />
      <StockSection product={product} branchId={branchId} onChanged={onChanged} />
    </div>
  )
}

// ─── Precios ─────────────────────────────────────────────────────────────────

function PricesSection({
  product,
  onChanged,
}: {
  product: Product
  onChanged: (p: Product) => void
}) {
  const [base, setBase] = useState(String(product.price ?? 0))
  // Se guarda el TEXTO, no Number(): `Number('')` es 0 y ese 0 llegaba a la
  // base dejando el escalón en $0.00.
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    setBase(String(product.price ?? 0))
    setEdits({})
    setMsg(null)
  }, [product.id, product.price])

  const save = async () => {
    const parsed = Number(base)
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setMsg('El precio tiene que ser un número mayor que cero.')
      return
    }
    // Cada escalón tocado debe ser un precio de verdad. Un campo vacío a medio
    // escribir se guardaba como $0.00 y el POS vendía a ese precio.
    const limpios: TierEdits = {}
    for (const [id, raw] of Object.entries(edits)) {
      const v = parseTierPrice(raw)
      if (v === null) {
        const nombre = (product.prices ?? []).find((p) => p.id === id)?.price_name ?? 'el escalón'
        setMsg(`El precio de "${nombre}" tiene que ser mayor que cero.`)
        return
      }
      limpios[id] = v
    }
    setBusy(true)
    setMsg(null)
    try {
      onChanged(
        await productsApi.update(product.id, buildPriceUpdatePayload(product, parsed, limpios)),
      )
      setMsg('Precios guardados.')
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar. Revisa la conexión.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <DaxCard>
      <div className="space-y-3">
        <label className="block">
          <span className="text-xs text-slate-400">Precio menudeo</span>
          <input
            value={base}
            onChange={(e) => setBase(e.target.value)}
            inputMode="decimal"
            className="dax-input mt-1 font-bold text-lg"
          />
        </label>

        {(product.prices ?? []).length > 0 && (
          <div className="space-y-2">
            <span className="text-xs text-slate-400">Escalones</span>
            {(product.prices ?? []).map((t) => (
              <div key={t.id} className="flex items-center gap-2">
                <span className="flex-1 text-sm text-slate-200">
                  {t.price_name}
                  <span className="text-slate-500 text-xs ml-1">desde {t.min_quantity}</span>
                </span>
                <input
                  value={edits[t.id] ?? String(t.unit_price)}
                  onChange={(e) => setEdits((prev) => ({ ...prev, [t.id]: e.target.value }))}
                  inputMode="decimal"
                  className={`dax-input w-24 text-right ${
                    edits[t.id] !== undefined && parseTierPrice(edits[t.id]) === null
                      ? 'border-rose-500'
                      : ''
                  }`}
                />
              </div>
            ))}
          </div>
        )}

        <button onClick={save} disabled={busy} className="dax-btn-primary w-full justify-center">
          {busy ? 'Guardando…' : 'Guardar precios'}
        </button>
        <Msg text={msg} />
      </div>
    </DaxCard>
  )
}

// ─── Existencias ─────────────────────────────────────────────────────────────

function StockSection({
  product,
  branchId,
  onChanged,
}: {
  product: Product
  branchId: number | null
  onChanged: (p: Product) => void
}) {
  const [counted, setCounted] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  // `product.stock` no es lo que manda la API (manda `stock_total`, y como
  // cadena). `currentStock` resuelve ambas cosas y prefiere la existencia de
  // la sucursal elegida.
  const current = currentStock(product, branchId)
  const variantId = product.variants?.[0]?.id ?? null
  const adj = counted.trim() === '' ? null : computeAdjustment(current, Number(counted))

  useEffect(() => { setCounted(''); setNotes(''); setMsg(null) }, [product.id])

  const apply = async () => {
    if (!adj || adj.delta === 0 || !variantId || !branchId) return
    setBusy(true)
    setMsg(null)
    try {
      // Pasa por /inventory/adjust y NO por un UPDATE directo del stock: así
      // el movimiento queda en el kardex con quién y cuándo.
      await productsApi.adjustStock({
        variant_id: variantId,
        branch_id: branchId,
        quantity: adj.delta,
        reason: 'Inventario',
        notes: notes.trim() || undefined,
      })
      const fresh = await productsApi.getById(product.id)
      onChanged(fresh)
      setCounted('')
      setMsg(`Registrado: ${adj.kind} de ${adj.abs}.`)
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo registrar el movimiento.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <DaxCard>
      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-slate-400">Existencias</span>
          <span className="text-white font-black text-lg">{current} pz</span>
        </div>

        {!branchId && (
          <p className="text-sm text-amber-400">
            Elige la sucursal en la que estás para poder ajustar existencias.
          </p>
        )}
        {!variantId && (
          <p className="text-sm text-amber-400">
            Este producto no expone variante; no se puede ajustar desde aquí.
          </p>
        )}

        <label className="block">
          <span className="text-xs text-slate-400">¿Cuántas contaste?</span>
          <input
            value={counted}
            onChange={(e) => setCounted(e.target.value)}
            inputMode="decimal"
            placeholder="Lo que hay en el anaquel"
            className="dax-input mt-1 font-bold text-lg"
          />
        </label>

        {/* El movimiento se muestra ANTES de aplicarlo: queda firmado en el kardex. */}
        {adj && adj.delta !== 0 && (
          <p className="text-sm text-slate-200">
            Tienes <b>{current}</b>, contaste <b>{counted}</b> → se registra una{' '}
            <b className={adj.kind === 'salida' ? 'text-rose-400' : 'text-emerald-400'}>
              {adj.kind} de {adj.abs}
            </b>
            .
          </p>
        )}
        {adj && adj.delta === 0 && (
          <p className="text-sm text-slate-400">Coincide con el sistema: no hay movimiento.</p>
        )}
        {counted.trim() !== '' && !adj && (
          <p className="text-sm text-rose-400">Escribe una cantidad válida (0 o más).</p>
        )}

        <input
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Nota (opcional)"
          className="dax-input"
        />

        <button
          onClick={apply}
          disabled={busy || !adj || adj.delta === 0 || !variantId || !branchId}
          className="dax-btn-primary w-full justify-center"
        >
          {busy ? 'Registrando…' : 'Registrar conteo'}
        </button>
        <Msg text={msg} />
      </div>
    </DaxCard>
  )
}
