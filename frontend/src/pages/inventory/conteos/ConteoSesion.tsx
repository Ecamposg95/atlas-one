import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { conteosApi, type ConteoDetalle, type Linea, type ProductoResumen, type ScanResult } from '../../../api/conteos'
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
import { vibrar } from './sesion'
import { useLectorCodigos } from './useLectorCodigos'

/**
 * Sesión de conteo: escanear, ver la pieza, seguir. La lista siempre se
 * vuelve a leer del servidor, así que recargar o cambiar de teléfono no
 * pierde nada. Diseño: spec 2026-10-22 §6.
 */
export function ConteoSesion() {
  const { id } = useParams()
  const conteoId = Number(id)
  const navigate = useNavigate()

  const [conteo, setConteo] = useState<ConteoDetalle | null>(null)
  const [ultimo, setUltimo] = useState<ScanResult | null>(null)
  const [pausado, setPausado] = useState(false)
  const [tecleado, setTecleado] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [buscar, setBuscar] = useState(false)
  const [ligarCodigo, setLigarCodigo] = useState<string | null>(null)   // código desconocido que se va a ligar
  const [candidatos, setCandidatos] = useState<ProductoResumen[] | null>(null)

  const recargar = useCallback(async () => {
    try { setConteo(await conteosApi.ver(conteoId)) } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir el conteo')) }
  }, [conteoId])
  useEffect(() => { void recargar() }, [recargar])

  const procesar = useCallback(async (code: string) => {
    if (ocupado) return
    setOcupado(true)
    setPausado(true)
    try {
      const r = await conteosApi.escanear(conteoId, code)
      setUltimo(r)
      if (r.resultado === 'contado') vibrar('ok'); else vibrar('aviso')
      if (r.resultado === 'ambiguo') setCandidatos(r.candidatos)
      await recargar()
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se registró el escaneo; vuelve a intentarlo'))
      setPausado(false)
    } finally {
      setOcupado(false)
    }
  }, [conteoId, ocupado, recargar])

  const lector = useLectorCodigos({ onCodigo: procesar, pausado })

  const siguiente = () => { setUltimo(null); setCandidatos(null); setPausado(false) }

  const masUno = async () => {
    const vid = ultimo?.producto?.variant_id
    if (!vid) return
    try { await conteosApi.agregarLinea(conteoId, vid, 1); vibrar('ok'); await recargar()
      setUltimo((u) => u && u.linea ? { ...u, linea: { ...u.linea, qty_contada: String(num(u.linea.qty_contada) + 1) } } : u)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo sumar')) }
  }

  const elegido = async (p: ProductoResumen) => {
    try {
      if (ligarCodigo) {
        // Reemplaza el código interno por el de la pieza (igual que el Escáner) y
        // quita la línea de desconocido: la próxima lectura ya empata.
        await productsApi.updateVariant(p.variant_id, { barcode: ligarCodigo })
        const desconocida = conteo?.lineas.find((l) => l.variant_id === null && l.codigo === ligarCodigo)
        if (desconocida) await conteosApi.borrarLinea(conteoId, desconocida.id)
        setLigarCodigo(null)
      }
      await conteosApi.agregarLinea(conteoId, p.variant_id, 1)
      vibrar('ok')
      setUltimo({ resultado: 'contado', linea: null, producto: p, qty_sistema: null, fuera_de_alcance: false, candidatos: [] })
      setCandidatos(null)
      await recargar()
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo registrar la pieza')) }
  }

  const fijar = async (l: Linea, qty: number) => {
    try { await conteosApi.fijarLinea(conteoId, l.id, qty); await recargar() } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo corregir')) }
  }

  const cerrar = async () => {
    if (!conteo) return
    const faltan = conteo.avance.esperadas_variantes - conteo.avance.contadas_variantes
    const ok = await confirm({
      title: 'Cerrar el conteo',
      message: faltan > 0 ? `Hay ${faltan} tallas con existencia que no se escanearon; quedarán como faltantes en el reporte.` : 'Se congela el reporte con lo contado.',
      confirmText: 'Cerrar y ver reporte', variant: 'warning',
    })
    if (!ok) return
    try { lector.stop(); await conteosApi.cerrar(conteoId); navigate(`/inventory/conteos/${conteoId}/reporte`) } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cerrar')) }
  }

  if (!conteo) return <Spinner />
  if (conteo.status === 'CERRADO') { navigate(`/inventory/conteos/${conteoId}/reporte`, { replace: true }); return null }

  const pct = porcentajeAvance(conteo.avance.contadas_variantes, conteo.avance.esperadas_variantes)
  const ultimaLinea = ultimo?.linea ?? conteo.lineas.find((l) => l.variant_id === ultimo?.producto?.variant_id) ?? null

  return (
    <div className="space-y-4 max-w-lg mx-auto pb-24">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-black text-white">{conteo.department_name ?? 'Toda la tienda'}</h1>
          <p className="text-xs text-slate-400">{conteo.branch_name}{conteo.notes ? ` · ${conteo.notes}` : ''}</p>
        </div>
        <button onClick={cerrar} className="dax-btn-secondary text-xs">Cerrar conteo</button>
      </div>

      <DaxCard>
        <div className="flex justify-between text-xs text-slate-400">
          <span>{conteo.avance.contadas_variantes} de {conteo.avance.esperadas_variantes} tallas · {num(conteo.avance.contadas_piezas)} de {num(conteo.avance.esperadas_piezas)} piezas</span>
          <span>{pct}%</span>
        </div>
        <div className="mt-1 h-2 rounded bg-slate-800"><div className="h-2 rounded bg-indigo-500" style={{ width: `${pct}%` }} /></div>
      </DaxCard>

      <DaxCard>
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
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); const c = normalizeTyped(tecleado); if (c) { setTecleado(''); void procesar(c) } }}>
          <input className="dax-input flex-1" placeholder="O teclea / pega el código" value={tecleado} onChange={(e) => setTecleado(e.target.value)} />
          <button type="submit" className="dax-btn-secondary">Buscar</button>
        </form>
        <button type="button" onClick={() => { setLigarCodigo(null); setBuscar(true) }} className="dax-btn-ghost mt-2 text-xs"><i className="fa-solid fa-magnifying-glass" /> Sin código: buscar por nombre</button>
      </DaxCard>

      {ultimo && (
        <DaxCard className={ultimo.resultado === 'contado' ? 'border border-emerald-700' : 'border border-amber-700'}>
          {ultimo.resultado === 'contado' && ultimo.producto && (
            <div className="flex gap-3">
              {ultimo.producto.foto && <img src={ultimo.producto.foto} alt="" className="h-20 w-20 rounded object-cover" />}
              <div className="flex-1">
                <div className="text-white font-bold">{ultimo.producto.nombre}</div>
                <div className="text-xs text-slate-400">{ultimo.producto.sku}{ultimo.producto.departamento ? ` · ${ultimo.producto.departamento}` : ''}</div>
                <div className="mt-1 text-sm text-emerald-300">
                  Contadas <b>{num(ultimaLinea?.qty_contada)}</b>{ultimo.qty_sistema != null && <> · sistema <b>{num(ultimo.qty_sistema)}</b></>}
                </div>
                {ultimo.fuera_de_alcance && <div className="text-xs text-amber-400">Esta pieza no es de este departamento; se cuenta y el reporte la separa.</div>}
              </div>
            </div>
          )}
          {ultimo.resultado === 'desconocido' && ultimo.linea && (
            <div>
              <div className="text-white font-bold">Código desconocido: {ultimo.linea.codigo}</div>
              <p className="text-xs text-slate-400 mt-1">No existe en el sistema. Puedes buscar la pieza y ligarle este código, o dejarla como desconocida en el reporte.</p>
              <button onClick={() => { setLigarCodigo(ultimo.linea?.codigo ?? null); setBuscar(true) }} className="dax-btn-secondary mt-2 text-xs"><i className="fa-solid fa-link" /> Buscar y ligar código</button>
            </div>
          )}
          {ultimo.resultado === 'ambiguo' && <div className="text-white font-bold">Varias tallas comparten ese código: elige una.</div>}
          <div className="mt-3 flex gap-2">
            <button onClick={siguiente} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-forward" /> Siguiente</button>
            {ultimo.resultado === 'contado' && <button onClick={masUno} className="dax-btn-secondary flex-1 justify-center">+1 igual</button>}
          </div>
        </DaxCard>
      )}

      <DaxCard>
        <h2 className="text-sm font-bold text-white mb-2">Contado en esta sesión ({conteo.lineas.length})</h2>
        {conteo.lineas.length === 0 && <p className="text-xs text-slate-500">Todavía nada. Escanea la primera pieza.</p>}
        <ul className="divide-y divide-slate-800">
          {conteo.lineas.map((l) => (
            <li key={l.id} className="py-2 flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white truncate">{l.producto?.nombre ?? `Desconocido · ${l.codigo}`}</div>
                <div className="text-xs text-slate-500">{l.producto?.sku}</div>
              </div>
              <input type="number" min={0} inputMode="numeric" className="dax-input w-16 text-center"
                defaultValue={num(l.qty_contada)} key={`${l.id}-${l.qty_contada}`}
                onBlur={(e) => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= 0 && n !== num(l.qty_contada)) void fijar(l, n) }} />
              <button aria-label="Quitar" onClick={() => void fijar(l, 0)} className="dax-btn-icon dax-btn-ghost"><i className="fa-solid fa-trash" /></button>
            </li>
          ))}
        </ul>
      </DaxCard>

      <BuscadorVariante open={buscar} onClose={() => setBuscar(false)} onElegir={elegido}
        titulo={ligarCodigo ? `Ligar el código ${ligarCodigo} a…` : 'Buscar pieza'} />

      <Modal open={candidatos !== null} onClose={() => setCandidatos(null)} title="¿Cuál es?" size="sm">
        <div className="space-y-2">
          {(candidatos ?? []).map((p) => (
            <button key={p.variant_id} className="dax-btn-secondary w-full justify-start text-left" onClick={() => void elegido(p)}>
              {p.nombre} <span className="text-xs text-slate-400">· {p.sku}</span>
            </button>
          ))}
        </div>
      </Modal>
    </div>
  )
}
