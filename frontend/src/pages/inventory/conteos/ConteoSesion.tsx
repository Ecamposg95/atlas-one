// frontend/src/pages/inventory/conteos/ConteoSesion.tsx
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { conteosApi, type ConteoDetalle, type FilaLista, type Lista, type ProductoResumen, type ScanResult } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { DaxCard } from '../../../components/ui/DaxCard'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'
import { isNativeDetectorAvailable, normalizeTyped } from '../../scanner/barcodeReader'
import { num, porcentajeAvance } from './avance'
import { BuscadorVariante } from './BuscadorVariante'
import { FichaProducto } from './FichaProducto'
import { ListaDepartamento } from './ListaDepartamento'
import { crearCola, debeRedirigirTecla, vibrar } from './sesion'
import { useLectorCodigos } from './useLectorCodigos'

/**
 * Sesión de conteo, lista primero: el departamento completo aparece con su
 * paloma y la pistola USB (o la cámara) va palomeando pieza por pieza. Cada
 * lectura resalta la fila, muestra la tarjeta de la pieza para verificar la
 * descripción y deja corregir la ficha ahí mismo. La lista siempre se vuelve
 * a leer del servidor: recargar o cambiar de teléfono no pierde nada.
 *
 * La pistola teclea el código y manda Enter al campo que siempre está
 * enfocado, así que no necesita "Siguiente"; la pausa tras cada lectura solo
 * detiene la CÁMARA (una pieza quieta frente a ella se contaría por cuadro).
 * Diseño: spec 2026-10-22 §6 y ajuste "lista primero" del plan.
 */
export function ConteoSesion() {
  const { id } = useParams()
  const conteoId = Number(id)
  const navigate = useNavigate()

  const [conteo, setConteo] = useState<ConteoDetalle | null>(null)
  const [lista, setLista] = useState<Lista | null>(null)
  const [ultimo, setUltimo] = useState<ScanResult | null>(null)
  const [resaltada, setResaltada] = useState<string | null>(null)
  const [pausado, setPausado] = useState(false)
  const [verCamara, setVerCamara] = useState(false)
  const [tecleado, setTecleado] = useState('')
  const [buscar, setBuscar] = useState(false)
  const [ligarCodigo, setLigarCodigo] = useState<string | null>(null)
  const [candidatos, setCandidatos] = useState<ProductoResumen[] | null>(null)
  const [ficha, setFicha] = useState<ProductoResumen | null>(null)
  const entradaRef = useRef<HTMLInputElement | null>(null)

  const enfocarEntrada = () => entradaRef.current?.focus()
  const sinModal = ficha === null && !buscar && candidatos === null

  // El Modal del kit devuelve el foco al botón que lo abrió DESPUÉS de onClose; refocar tras
  // el commit evita que el siguiente Enter de la pistola reabra la ficha o el buscador.
  useEffect(() => {
    if (!sinModal) return
    const t = setTimeout(enfocarEntrada, 0)
    return () => clearTimeout(t)
  }, [sinModal])

  // Red de seguridad: si el foco quedó en un botón (chip, papelera…) y la pistola dispara,
  // sus caracteres deben caer en el campo de escaneo. Solo actúa con caracteres imprimibles
  // (nunca Enter, Espacio, Tab, Escape ni flechas: el teclado sigue siendo accesible), fuera de
  // campos y sin ningún diálogo abierto (modales del kit o confirm). No hace preventDefault:
  // al enfocar el campo durante keydown, el navegador inserta el carácter ahí mismo.
  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      const enCampo = !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
      const hayDialogo = !!document.querySelector('[role="dialog"], [data-modal-kit]') || !!t?.closest?.('[role="dialog"], [data-modal-kit]')
      if (debeRedirigirTecla({ key: e.key, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, enCampo, hayDialogo })) entradaRef.current?.focus()
    }
    document.addEventListener('keydown', alTeclear, true)
    return () => document.removeEventListener('keydown', alTeclear, true)
  }, [])

  const recargar = useCallback(async () => {
    try {
      const [c, l] = await Promise.all([conteosApi.ver(conteoId), conteosApi.lista(conteoId)])
      setConteo(c)
      setLista(l)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir el conteo')) }
  }, [conteoId])
  useEffect(() => { void recargar() }, [recargar])

  const escanearUno = useCallback(async (code: string) => {
    setPausado(true)   // solo detiene la cámara; la pistola no depende de esto
    try {
      const r = await conteosApi.escanear(conteoId, code)
      setUltimo(r)
      if (r.resultado === 'contado') { vibrar('ok'); setResaltada(r.producto?.variant_id ?? null) } else vibrar('aviso')
      if (r.resultado === 'ambiguo') setCandidatos(r.candidatos)
      await recargar()
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se registró el escaneo; vuelve a intentarlo'))
      setPausado(false)
    }
  }, [conteoId, recargar])

  // Cola FIFO: una lectura que llega mientras se guarda la anterior se encola, no se pierde.
  const escanearRef = useRef(escanearUno)
  escanearRef.current = escanearUno
  const colaRef = useRef<ReturnType<typeof crearCola> | null>(null)
  if (colaRef.current === null) colaRef.current = crearCola((c) => escanearRef.current(c), () => entradaRef.current?.focus())
  const procesar = useCallback((code: string) => { void colaRef.current?.push(code) }, [])

  const lector = useLectorCodigos({ onCodigo: procesar, pausado })

  const siguiente = () => { setUltimo(null); setCandidatos(null); setLigarCodigo(null); setPausado(false); enfocarEntrada() }

  const alternarCamara = () => {
    if (verCamara) { lector.stop(); setVerCamara(false) } else { setPausado(false); setVerCamara(true) }
    enfocarEntrada()
  }

  const masUno = async () => {
    const vid = ultimo?.producto?.variant_id
    if (!vid) return
    try {
      await conteosApi.agregarLinea(conteoId, vid, 1)
      vibrar('ok')
      await recargar()
      setUltimo((u) => u && u.linea ? { ...u, linea: { ...u.linea, qty_contada: String(num(u.linea.qty_contada) + 1) } } : u)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo sumar')) }
    finally { enfocarEntrada() }
  }

  // `codigoALigar` llega explícito desde el buscador; el modal de candidatos pasa null.
  // Así un código viejo en el estado nunca se escribe en una variante ajena.
  const elegido = async (p: ProductoResumen, codigoALigar: string | null) => {
    try {
      if (codigoALigar) {
        // Reemplaza el código interno por el de la pieza (igual que el Escáner). La línea de
        // desconocido conserva sus piezas: pasan a la variante y solo entonces se borra.
        await productsApi.updateVariant(p.variant_id, { barcode: codigoALigar })
        const desconocida = conteo?.lineas.find((l) => l.variant_id === null && l.codigo === codigoALigar)
        const qty = desconocida ? Math.max(1, num(desconocida.qty_contada)) : 1
        await conteosApi.agregarLinea(conteoId, p.variant_id, qty)
        if (desconocida) await conteosApi.borrarLinea(conteoId, desconocida.id)
      } else {
        await conteosApi.agregarLinea(conteoId, p.variant_id, 1)
      }
      vibrar('ok')
      setResaltada(p.variant_id)
      setUltimo({ resultado: 'contado', linea: null, producto: p, qty_sistema: null, fuera_de_alcance: false, candidatos: [] })
      setCandidatos(null)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo registrar la pieza')) }
    finally { setLigarCodigo(null); await recargar(); enfocarEntrada() }
  }

  const fijarPorId = async (lineId: number, qty: number) => {
    try { await conteosApi.patchLinea(conteoId, lineId, { qty_contada: qty }); await recargar() }
    catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo corregir')) }
  }

  /** Tras guardar la ficha: marca la línea (si la pieza ya se escaneó) y recarga. */
  const fichaCorregida = async (p: ProductoResumen) => {
    const lineId = conteo?.lineas.find((l) => l.variant_id === p.variant_id)?.id ?? null
    if (lineId !== null) await conteosApi.patchLinea(conteoId, lineId, { corregida: true })
    await recargar()
  }

  const cerrar = async () => {
    if (!conteo) return
    const pendientes = lista?.totales.pendientes ?? 0
    const ok = await confirm({
      title: 'Cerrar el conteo',
      message: pendientes > 0 ? `Quedan ${pendientes} tallas sin revisar; las que tienen existencia quedarán como faltantes en el reporte.` : 'Se congela el reporte con lo contado.',
      confirmText: 'Cerrar y ver reporte', variant: 'warning',
    })
    if (!ok) return
    try { lector.stop(); await conteosApi.cerrar(conteoId); navigate(`/inventory/conteos/${conteoId}/reporte`) }
    catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cerrar')) }
  }

  if (!conteo || !lista) return <Spinner />
  if (conteo.status === 'CERRADO') { navigate(`/inventory/conteos/${conteoId}/reporte`, { replace: true }); return null }

  const fresco = (p: ProductoResumen | null) => (p ? lista.filas.find((f) => f.producto.variant_id === p.variant_id)?.producto ?? p : p)
  const ultimoVista = ultimo && ultimo.producto ? { ...ultimo, producto: fresco(ultimo.producto) } : ultimo
  const fichaVista = fresco(ficha)
  const pct = porcentajeAvance(lista.totales.revisados + lista.totales.con_diferencia, lista.totales.total)
  const ultimaLinea = ultimo?.linea ?? conteo.lineas.find((l) => l.variant_id === ultimo?.producto?.variant_id) ?? null
  const desconocidos = conteo.lineas.filter((l) => l.variant_id === null)
  const enLista = new Set(lista.filas.map((f) => f.producto.variant_id))
  const otras = conteo.lineas.filter((l) => l.variant_id !== null && !enLista.has(l.variant_id))

  return (
    <div className="space-y-4 max-w-3xl mx-auto pb-24">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-black text-white">{conteo.department_name ?? 'Toda la tienda'}</h1>
          <p className="text-xs text-slate-400">{conteo.branch_name}{conteo.notes ? ` · ${conteo.notes}` : ''}</p>
        </div>
        <button onClick={cerrar} className="dax-btn-secondary text-xs">Cerrar conteo</button>
      </div>

      <DaxCard>
        <div className="flex justify-between text-xs text-slate-400">
          <span>{lista.totales.total - lista.totales.pendientes} de {lista.totales.total} tallas revisadas · {num(conteo.avance.contadas_piezas)} piezas contadas</span>
          <span>{pct}%</span>
        </div>
        <div className="mt-1 h-2 rounded bg-slate-800"><div className="h-2 rounded bg-indigo-500" style={{ width: `${pct}%` }} /></div>
      </DaxCard>

      <DaxCard>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const c = normalizeTyped(tecleado); if (c) { setTecleado(''); void procesar(c) } }}>
          <input ref={entradaRef} autoFocus className="dax-input flex-1" placeholder="Escanea con la pistola o teclea el código" value={tecleado} onChange={(e) => setTecleado(e.target.value)} />
          <button type="submit" className="dax-btn-primary">Palomear</button>
        </form>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" onClick={alternarCamara} className="dax-btn-ghost text-xs"><i className="fa-solid fa-camera" /> {verCamara ? 'Ocultar cámara' : 'Usar cámara'}</button>
          <button type="button" onClick={() => { setLigarCodigo(null); setBuscar(true) }} className="dax-btn-ghost text-xs"><i className="fa-solid fa-magnifying-glass" /> Sin código: buscar por nombre</button>
        </div>
        {verCamara && (
          <div className="mt-3">
            <div className="relative rounded-lg overflow-hidden bg-black aspect-[4/3]">
              <video ref={lector.videoRef} className="w-full h-full object-cover" muted playsInline />
              <canvas ref={lector.canvasRef} className="hidden" />
              {!lector.camOn && (
                <button onClick={() => void lector.start()} className="dax-btn-primary absolute inset-0 m-auto h-12 w-48">
                  <i className="fa-solid fa-camera" /> Encender cámara
                </button>
              )}
              {lector.camOn && pausado && <div className="absolute inset-0 bg-black/60 flex items-center justify-center text-white text-sm">Pausado · toca Siguiente</div>}
            </div>
            {lector.camError && <p className="mt-2 text-xs text-amber-400">{lector.camError}</p>}
            {!isNativeDetectorAvailable() && !lector.camOn && <p className="mt-2 text-xs text-slate-500">En este navegador se carga un lector adicional al encender la cámara.</p>}
          </div>
        )}
      </DaxCard>

      {ultimoVista && (
        <DaxCard className={ultimoVista.resultado === 'contado' ? 'border border-emerald-700' : 'border border-amber-700'}>
          {ultimoVista.resultado === 'contado' && ultimoVista.producto && (
            <div className="flex gap-3">
              {ultimoVista.producto.foto && <img src={ultimoVista.producto.foto} alt="" className="h-20 w-20 rounded object-cover" />}
              <div className="flex-1">
                <div className="text-white font-bold"><i className="fa-solid fa-circle-check text-emerald-400" /> {ultimoVista.producto.nombre}</div>
                <div className="text-xs text-slate-400">{ultimoVista.producto.sku}{ultimoVista.producto.departamento ? ` · ${ultimoVista.producto.departamento}` : ''}</div>
                {ultimoVista.producto.descripcion && <div className="text-xs text-slate-300 mt-1 line-clamp-2">{ultimoVista.producto.descripcion}</div>}
                <div className="mt-1 text-sm text-emerald-300">
                  Contadas <b>{num(ultimaLinea?.qty_contada)}</b>{ultimoVista.qty_sistema != null && <> · sistema <b>{num(ultimoVista.qty_sistema)}</b></>}
                </div>
                {ultimoVista.fuera_de_alcance && <div className="text-xs text-amber-400">Esta pieza no es de este departamento; se cuenta y el reporte la separa.</div>}
              </div>
            </div>
          )}
          {ultimoVista.resultado === 'desconocido' && ultimoVista.linea && (
            <div>
              <div className="text-white font-bold">Código desconocido: {ultimoVista.linea.codigo}</div>
              <p className="text-xs text-slate-400 mt-1">No existe en el sistema. Puedes buscar la pieza y ligarle este código, o dejarla como desconocida en el reporte.</p>
              <button onClick={() => { setLigarCodigo(ultimoVista.linea?.codigo ?? null); setBuscar(true) }} className="dax-btn-secondary mt-2 text-xs"><i className="fa-solid fa-link" /> Buscar y ligar código</button>
            </div>
          )}
          {ultimoVista.resultado === 'ambiguo' && <div className="text-white font-bold">Varias tallas comparten ese código: elige una.</div>}
          <div className="mt-3 flex flex-wrap gap-2">
            {verCamara && <button onClick={siguiente} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-forward" /> Siguiente</button>}
            {ultimoVista.resultado === 'contado' && <button onClick={masUno} className="dax-btn-secondary flex-1 justify-center">+1 igual</button>}
            {ultimoVista.resultado === 'contado' && ultimoVista.producto && <button onClick={() => setFicha(ultimoVista.producto)} className="dax-btn-secondary flex-1 justify-center"><i className="fa-solid fa-id-card" /> Ver ficha</button>}
          </div>
        </DaxCard>
      )}

      <DaxCard>
        <h2 className="text-sm font-bold text-white mb-2">Lista del departamento</h2>
        <ListaDepartamento filas={lista.filas} resaltada={resaltada}
          onCantidad={(f: FilaLista, qty: number) => { if (f.line_id !== null) void fijarPorId(f.line_id, qty) }}
          onFicha={(f: FilaLista) => setFicha(f.producto)} />
      </DaxCard>

      {(desconocidos.length > 0 || otras.length > 0) && (
        <DaxCard>
          <h2 className="text-sm font-bold text-white mb-2">Otras piezas escaneadas</h2>
          <ul className="divide-y divide-slate-800">
            {[...otras, ...desconocidos].map((l) => (
              <li key={l.id} className="py-2 flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{l.producto?.nombre ?? `Desconocido · ${l.codigo}`}</div>
                  <div className="text-xs text-slate-500">{l.producto ? `${l.producto.sku ?? ''} · ${l.producto.departamento ?? 'otro departamento'}` : 'no existe en el sistema'}</div>
                </div>
                <span className="text-sm text-slate-300">{num(l.qty_contada)}</span>
                <button aria-label="Quitar" onClick={() => void fijarPorId(l.id, 0)} className="dax-btn-icon dax-btn-ghost"><i className="fa-solid fa-trash" /></button>
              </li>
            ))}
          </ul>
        </DaxCard>
      )}

      <BuscadorVariante open={buscar} onClose={() => { setBuscar(false); setLigarCodigo(null); enfocarEntrada() }} onElegir={(p) => elegido(p, ligarCodigo)}
        titulo={ligarCodigo ? `Ligar el código ${ligarCodigo} a…` : 'Buscar pieza'} />

      <FichaProducto producto={fichaVista} open={ficha !== null} onClose={() => { setFicha(null); enfocarEntrada() }} onCorregida={fichaCorregida} />

      <Modal open={candidatos !== null} onClose={() => setCandidatos(null)} title="¿Cuál es?" size="sm">
        <div className="space-y-2">
          {(candidatos ?? []).map((p) => (
            <button key={p.variant_id} className="dax-btn-secondary w-full justify-start text-left" onClick={() => void elegido(p, null)}>
              {p.nombre} <span className="text-xs text-slate-400">· {p.sku}</span>
            </button>
          ))}
        </div>
      </Modal>
    </div>
  )
}
