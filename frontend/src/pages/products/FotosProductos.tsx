import { useCallback, useEffect, useRef, useState } from 'react'
import { productsApi } from '../../api/products'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { Spinner } from '../../components/ui/Spinner'
import { GaleriaProducto } from '../../components/products/GaleriaProducto'
import { useCanalTienda } from '../../hooks/useCanalTienda'
import { toast } from '../../store/toastStore'
import type { Product } from '../../types/products'

const POR_PAGINA = 30

/**
 * Fotos de productos — pensada para el teléfono: buscar el producto, tomarle
 * foto con la cámara y subirla. La foto se reduce en el teléfono (≤1600 px,
 * JPEG) y el servidor la guarda en Cloudinary; la primera queda como principal
 * y, si el producto está publicado, la tienda en línea la recoge sola en la
 * siguiente sincronización (la foto sube `updated_at`).
 */
export function FotosProductos() {
  const [busqueda, setBusqueda] = useState('')
  const [soloSinFoto, setSoloSinFoto] = useState(true)
  const [productos, setProductos] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [cargando, setCargando] = useState(false)
  const [elegido, setElegido] = useState<Product | null>(null)

  const cargar = useCallback(async (q: string, sinFoto: boolean, desde: number) => {
    setCargando(true)
    try {
      const r = await productsApi.list({
        search: q.trim() || undefined, sin_foto: sinFoto || undefined,
        active_only: true, skip: desde, limit: POR_PAGINA,
      })
      setProductos((prev) => (desde === 0 ? r.items : [...prev, ...r.items]))
      setTotal(r.total ?? r.items.length)
    } catch {
      toast.error('No se pudo cargar la lista de productos.')
    } finally { setCargando(false) }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => cargar(busqueda, soloSinFoto, 0), 300)
    return () => clearTimeout(t)
  }, [busqueda, soloSinFoto, cargar])

  if (elegido) {
    return (
      <FichaFotos
        producto={elegido}
        onVolver={() => { setElegido(null); cargar(busqueda, soloSinFoto, 0) }}
      />
    )
  }

  return (
    <div className="space-y-4 max-w-3xl mx-auto">
      <CabeceraPagina
        titulo="Fotos de productos"
        descripcion="Busca el producto, tómale foto con el teléfono y queda en línea."
      />
      <div className="space-y-2">
        <input
          type="search"
          className="dax-input w-full text-base"
          placeholder="Nombre, SKU o código de barras"
          aria-label="Buscar producto"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          autoFocus
        />
        <label className="flex items-center gap-2 text-sm text-dax-muted">
          <input type="checkbox" checked={soloSinFoto} onChange={(e) => setSoloSinFoto(e.target.checked)} />
          Solo productos sin foto
        </label>
      </div>

      {cargando && productos.length === 0 ? (
        <div className="flex justify-center py-10"><Spinner /></div>
      ) : productos.length === 0 ? (
        <p className="text-center text-sm text-dax-muted py-10">
          {soloSinFoto ? 'No hay productos sin foto con esa búsqueda.' : 'Sin resultados.'}
        </p>
      ) : (
        <ul className="space-y-2" aria-label="Productos">
          {productos.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => setElegido(p)}
                className="w-full flex items-center gap-3 rounded-xl border border-dax-border bg-dax-surface p-2 text-left min-h-[64px]"
              >
                {p.image_url ? (
                  <img src={p.image_url} alt="" className="w-14 h-14 rounded-lg object-cover shrink-0" loading="lazy" />
                ) : (
                  <span className="w-14 h-14 rounded-lg border border-dashed border-dax-border flex items-center justify-center shrink-0 text-dax-muted">
                    <i className="fa-solid fa-camera" />
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-dax-text truncate">{p.sale_name ?? p.name}</span>
                  <span className="block text-xs text-dax-muted truncate">
                    {[p.sku, p.brand_name].filter(Boolean).join(' · ')}
                  </span>
                </span>
                {p.web_published && <span className="dax-badge dax-badge-green text-[10px] shrink-0">En línea</span>}
                <i className="fa-solid fa-chevron-right text-dax-muted shrink-0" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {productos.length < total && (
        <button
          type="button"
          className="dax-btn-secondary w-full"
          disabled={cargando}
          onClick={() => cargar(busqueda, soloSinFoto, productos.length)}
        >
          {cargando ? 'Cargando…' : `Ver más (${total - productos.length})`}
        </button>
      )}
    </div>
  )
}

function FichaFotos({ producto, onVolver }: { producto: Product; onVolver: () => void }) {
  const { activo: canalActivo, puedePublicarUno: puedePublicar } = useCanalTienda()
  const [publicado, setPublicado] = useState(!!producto.web_published)
  const [subiendo, setSubiendo] = useState<{ hecho: number; total: number } | null>(null)
  const [publicando, setPublicando] = useState(false)
  const [version, setVersion] = useState(0) // remonta la galería tras subir
  const camaraRef = useRef<HTMLInputElement>(null)
  const archivoRef = useRef<HTMLInputElement>(null)

  const subir = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivos = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (archivos.length === 0) return
    let ok = 0
    for (let i = 0; i < archivos.length; i++) {
      setSubiendo({ hecho: i, total: archivos.length })
      try { await productsApi.addImage(producto.id, archivos[i]); ok++ }
      catch (err: any) {
        toast.error(err?.response?.data?.detail ?? `No se pudo subir la foto ${i + 1}.`)
      }
    }
    setSubiendo(null)
    setVersion((v) => v + 1)
    if (ok > 0) toast.success(ok === 1 ? 'Foto subida.' : `${ok} fotos subidas.`)
  }

  const alternarPublicacion = async () => {
    setPublicando(true)
    try {
      await productsApi.webPublish({ ids: [producto.id], published: !publicado })
      setPublicado(!publicado)
      toast.success(!publicado ? 'Publicado en la tienda en línea.' : 'Quitado de la tienda en línea.')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'No se pudo actualizar la tienda en línea.')
    } finally { setPublicando(false) }
  }

  const ocupado = subiendo !== null

  return (
    <div className="space-y-4 max-w-3xl mx-auto">
      <button type="button" className="dax-btn-ghost text-sm" onClick={onVolver}>
        <i className="fa-solid fa-arrow-left" /> Volver a la lista
      </button>
      <div>
        <h1 className="text-lg font-semibold text-dax-text">{producto.sale_name ?? producto.name}</h1>
        <p className="text-xs text-dax-muted">{[producto.sku, producto.brand_name].filter(Boolean).join(' · ')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <button type="button" className="dax-btn-primary w-full min-h-[52px] text-base" disabled={ocupado} onClick={() => camaraRef.current?.click()}>
          <i className="fa-solid fa-camera" /> Tomar foto
        </button>
        <button type="button" className="dax-btn-secondary w-full min-h-[52px] text-base" disabled={ocupado} onClick={() => archivoRef.current?.click()}>
          <i className="fa-solid fa-images" /> Elegir del teléfono
        </button>
      </div>
      {/* capture="environment" abre directo la cámara trasera en el teléfono. */}
      <input ref={camaraRef} type="file" accept="image/*" capture="environment" className="hidden" aria-label="Tomar foto con la cámara" onChange={subir} />
      <input ref={archivoRef} type="file" accept="image/*" multiple className="hidden" aria-label="Elegir fotos del teléfono" onChange={subir} />

      {subiendo && (
        <p className="flex items-center gap-2 text-sm text-dax-muted" role="status">
          <Spinner /> Subiendo foto {subiendo.hecho + 1} de {subiendo.total}…
        </p>
      )}

      {canalActivo && (
        <div className="rounded-xl border border-dax-border p-3 flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-dax-text">
            {publicado ? <><i className="fa-solid fa-globe text-dax-success" /> Publicado en la tienda en línea</> : 'No está en la tienda en línea'}
          </span>
          {puedePublicar && (
            <button type="button" className={publicado ? 'dax-btn-secondary text-sm' : 'dax-btn-primary text-sm'} disabled={publicando} onClick={alternarPublicacion}>
              {publicado ? 'Quitar de la tienda' : 'Publicar'}
            </button>
          )}
        </div>
      )}

      <GaleriaProducto key={version} productId={producto.id} imagenHeredada={producto.image_url} />
    </div>
  )
}
