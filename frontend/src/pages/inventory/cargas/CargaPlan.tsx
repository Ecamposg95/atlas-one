import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  cargasApi, type CargaDetalle, type Cambio, type Etiqueta, type ResumenAplicacion,
} from '../../../api/cargas'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ErrorState } from '../../../components/ui/ErrorState'
import { KpiCard } from '../../../components/ui/KpiCard'
import { Spinner } from '../../../components/ui/Spinner'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'
import { formatCurrency } from '../../../utils/currency'
import { esRolHq } from '../../../utils/rolesHq'
import { CambiosAntesDespues } from './componentes/CambiosAntesDespues'
import { ResumenEtiquetas } from './componentes/ResumenEtiquetas'
import { TablaPlan } from './componentes/TablaPlan'
import { TarjetaDuda } from './componentes/TarjetaDuda'
import { CLASES, cantidad, fechaCorta } from './formato'

/**
 * Plan de una carga: contadores, dudas numeradas, respuesta en texto libre,
 * antes/después con deshacer, autorización y, ya aplicada, las etiquetas.
 * Mientras la carga lee o aplica consulta el detalle cada 3 s.
 */
const CADA_MS = 3000

const plural = (n: number, uno: string, varios: string) => `${cantidad(n)} ${n === 1 ? uno : varios}`
const msg = (e: any, por: string) => errorDetailText(e?.response?.data?.detail, por)

export default function CargaPlan() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const rol = useAuthStore((s) => s.user?.role)

  const [det, setDet] = useState<CargaDetalle | null>(null)
  const [falloCarga, setFalloCarga] = useState(false)
  const [ocupado, setOcupado] = useState(false)
  const [texto, setTexto] = useState('')
  const [cambio, setCambio] = useState<Cambio | null>(null)
  const [rechazos, setRechazos] = useState<string[]>([])
  const [resumen, setResumen] = useState<ResumenAplicacion | null>(null)
  const [etiquetas, setEtiquetas] = useState<Etiqueta[] | null>(null)
  const enVuelo = useRef(false)

  const cargar = useCallback(async () => {
    try {
      setDet(await cargasApi.obtener(id))
      setFalloCarga(false)
    } catch {
      setFalloCarga(true)
      return false
    }
    return true
  }, [id])

  useEffect(() => { void cargar() }, [cargar])

  const estado = det?.carga.estado
  useEffect(() => {
    if (estado !== 'leyendo' && estado !== 'aplicando') return
    const t = setInterval(() => { void cargar() }, CADA_MS)
    return () => clearInterval(t)
  }, [estado, cargar])

  // Reabrir una carga ya aplicada: las etiquetas se piden aparte.
  useEffect(() => {
    if (estado !== 'aplicada' || etiquetas) return
    if (resumen) { setEtiquetas(resumen.etiquetas); return }
    let vigente = true
    cargasApi.etiquetas(id).then((e) => { if (vigente) setEtiquetas(e) }).catch(() => { if (vigente) setEtiquetas([]) })
    return () => { vigente = false }
  }, [estado, etiquetas, resumen, id])

  /** Una mutación a la vez: un doble toque no envía dos veces. */
  const correr = async (fn: () => Promise<void>, fallo: string) => {
    if (enVuelo.current) return
    enVuelo.current = true
    setOcupado(true)
    try { await fn() } catch (e) { toast.error(msg(e, fallo)) } finally {
      enVuelo.current = false
      setOcupado(false)
    }
  }

  const tomarRespuesta = async (r: { cambio: Cambio | null; rechazos: string[] }) => {
    setCambio(r.cambio)
    setRechazos(r.rechazos)
    if (!(await cargar())) toast.error('Se guardó, pero no se pudo actualizar el plan. Recarga la página.')
  }

  const elegir = (numero: number, opcion: string, valor?: string) =>
    correr(async () => tomarRespuesta(await cargasApi.resolverDuda(id, numero, opcion, valor)), 'No se pudo guardar la respuesta')

  const enviar = () => {
    const t = texto.trim()
    if (!t) return
    void correr(async () => {
      const r = await cargasApi.responder(id, t)
      setTexto('')
      await tomarRespuesta(r)
    }, 'No se pudo enviar la respuesta')
  }

  const deshacer = (cambioId: string) =>
    correr(async () => {
      setDet(await cargasApi.deshacer(id, cambioId))
      setCambio(null)
      setRechazos([])
    }, 'No se pudo deshacer')

  /** Tras un fallo (409 con preguntas nuevas, 422, carga ya aplicada…) el
   * detalle cambió en el servidor: se vuelve a pedir para que se vea. */
  const recargarTrasFallo = async () => {
    if (!(await cargar())) toast.error('La carga cambió, pero no se pudo actualizar el plan. Recarga la página.')
  }

  /** Corre `fn`; si falla, recarga el detalle y deja que `correr` avise del error. */
  const conRecarga = (fn: () => Promise<void>) => async () => {
    try { await fn() } catch (e) { await recargarTrasFallo(); throw e }
  }

  const reintentar = () =>
    correr(conRecarga(async () => { await cargasApi.reintentar(id); await cargar() }), 'No se pudo reintentar')

  const autorizar = async () => {
    if (!det || enVuelo.current) return
    const filas = det.grupos.flatMap((g) => g.renglones.map((r) => ({ g, r })))
      .filter(({ r }) => r.clase !== 'YA_CARGADO' && r.clase !== 'IGNORADO')
    const nuevos = new Set(filas.filter(({ g, r }) => r.clase === 'NUEVO' && !g.product_id).map(({ g }) => g.grupo)).size
    const piezas = filas.reduce((s, { r }) => s + Number(r.cantidad || 0), 0)
    const valor = filas.reduce((s, { r }) => s + Number(r.cantidad || 0) * Number(r.costo || 0), 0)
    enVuelo.current = true
    setOcupado(true)
    let ok = false
    try { ok = await confirm({
      title: 'Autorizar la carga',
      message: `Entran ${plural(nuevos, 'producto nuevo', 'productos nuevos')}, ${plural(piezas, 'pieza', 'piezas')}, ${formatCurrency(valor)} a costo. Esto escribe en el catálogo y en las existencias.`,
      confirmText: 'Autorizar', variant: 'warning',
    }) } finally { enVuelo.current = false; setOcupado(false) }
    if (!ok) return
    await correr(conRecarga(async () => { setResumen(await cargasApi.autorizar(id)); await cargar() }), 'No se pudo autorizar')
  }

  const descartar = async () => {
    if (enVuelo.current) return
    enVuelo.current = true
    setOcupado(true)
    let ok = false
    try { ok = await confirm({
      title: 'Descartar la carga',
      message: 'Se descarta el plan y no entra nada al catálogo.',
      confirmText: 'Descartar', variant: 'danger',
    }) } finally { enVuelo.current = false; setOcupado(false) }
    if (!ok) return
    await correr(async () => { await cargasApi.descartar(id); navigate('/inventory/cargas') }, 'No se pudo descartar')
  }

  const titulo = (
    <div className="flex items-center gap-3">
      <i className="fa-solid fa-file-import text-dax-accent-text text-xl" />
      <h1 className="text-2xl font-black text-dax-text">{det ? `Carga #${det.carga.folio}` : 'Carga'}</h1>
    </div>
  )

  if (!det) {
    return falloCarga
      ? <ErrorState message="No se pudo cargar la carga." onRetry={() => void cargar()} />
      : <Spinner text="Cargando…" />
  }

  const { carga } = det
  const volver = (
    <Link to="/inventory/cargas" className="text-sm text-dax-accent-text">← Volver a las cargas</Link>
  )

  if (estado === 'leyendo' || estado === 'aplicando') {
    return (
      <div className="space-y-4">
        <CabeceraPagina titulo={titulo} descripcion={carga.archivo_nombre} />
        <Spinner text={estado === 'leyendo' ? 'Leyendo el documento…' : 'Aplicando la carga…'} />
      </div>
    )
  }

  if (estado === 'error') {
    return (
      <div className="space-y-4">
        <CabeceraPagina titulo={titulo} descripcion={carga.archivo_nombre} />
        <ErrorState message={carga.error ?? 'No se pudo leer el documento.'} />
        <div className="flex flex-wrap justify-center gap-2">
          <button type="button" disabled={ocupado} onClick={() => void reintentar()}
            className="dax-btn-primary max-md:min-h-[44px] disabled:opacity-40">
            <i className="fa-solid fa-rotate-right" /> Volver a intentar
          </button>
          <button type="button" disabled={ocupado} onClick={() => void descartar()}
            className="dax-btn-danger max-md:min-h-[44px] disabled:opacity-40">Descartar</button>
        </div>
        {volver}
      </div>
    )
  }

  if (estado === 'descartada') {
    return (
      <div className="space-y-4">
        <CabeceraPagina titulo={titulo} descripcion={carga.archivo_nombre} />
        <DaxCard><p className="text-sm text-dax-text">Esta carga se descartó; no entró nada al catálogo.</p></DaxCard>
        {volver}
      </div>
    )
  }

  if (estado === 'aplicada') {
    return (
      <div className="space-y-4">
        <CabeceraPagina titulo={titulo} descripcion={carga.archivo_nombre} />
        {etiquetas === null
          ? <Spinner text="Cargando etiquetas…" />
          : <ResumenEtiquetas cargaId={id} folio={carga.folio} etiquetas={etiquetas} resumen={resumen} />}
        {volver}
      </div>
    )
  }

  // estado === 'plan'
  const abiertas = det.dudas.filter((d) => d.estado === 'abierta')
  const puedeAutorizar = det.puede_autorizar && esRolHq(rol) && abiertas.length === 0
  const c = det.contadores

  return (
    <div className={`space-y-4 ${esTelefono ? 'pb-40' : 'pb-8'}`}>
      <CabeceraPagina
        titulo={titulo}
        descripcion={`${carga.archivo_nombre}${carga.sucursal_nombre ? ` · Entra a ${carga.sucursal_nombre}` : ''}`}
        acciones={
          <button type="button" disabled={ocupado} onClick={() => void descartar()}
            className="dax-btn-danger max-md:min-h-[44px] disabled:opacity-40">Descartar</button>
        }
        accionPrincipal={esRolHq(rol) ? (
          <button type="button" disabled={ocupado || !puedeAutorizar} onClick={() => void autorizar()}
            className="dax-btn-primary max-md:min-h-[44px] disabled:opacity-40">Autorizar</button>
        ) : undefined}
      />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {(['NUEVO', 'SUMA', 'EXISTE', 'YA_CARGADO', 'IGNORADO'] as const).map((k) => (
          <KpiCard key={k} etiqueta={CLASES[k]} valor={String(c[k])} />
        ))}
        <KpiCard etiqueta="Piezas" valor={cantidad(c.piezas)} />
      </div>
      {det.ultimos_conteos.length > 0 && (
        <div className="text-xs text-dax-muted space-y-0.5">
          {det.ultimos_conteos.map((u) => (
            <p key={u.departamento}>Último conteo de {u.departamento}: #{u.numero}, {fechaCorta(u.cerrado_at)}</p>
          ))}
        </div>
      )}

      {abiertas.length > 0 && (
        <section className="space-y-2" aria-label="Preguntas">
          <h2 className="text-sm font-black text-dax-text">Preguntas por resolver ({abiertas.length})</h2>
          {abiertas.map((d) => <TarjetaDuda key={d.numero} duda={d} ocupado={ocupado} onElegir={elegir} />)}
        </section>
      )}

      {rechazos.length > 0 && (
        <div role="alert" className="dax-card p-3 text-sm text-dax-warning space-y-1">
          <p className="font-bold">No se pudo aplicar esto:</p>
          {rechazos.map((r, i) => <p key={i}>{r}</p>)}
        </div>
      )}
      {cambio && <CambiosAntesDespues cambio={cambio} ocupado={ocupado} onDeshacer={deshacer} />}

      <TablaPlan grupos={det.grupos} />

      <div className={esTelefono ? 'fixed bottom-0 left-0 right-0 z-30 p-3 border-t border-dax-border-dim bg-dax-surface' : ''}>
        <div className="flex gap-2 items-end">
          <textarea className="dax-input flex-1 min-w-0 text-sm" rows={esTelefono ? 2 : 3} aria-label="Respuesta"
            placeholder="Contesta por número: 1. … 2. …" value={texto} onChange={(e) => setTexto(e.target.value)} />
          <button type="button" disabled={ocupado || !texto.trim()} onClick={enviar}
            className="dax-btn-primary max-md:min-h-[44px] disabled:opacity-40">Enviar</button>
        </div>
      </div>
    </div>
  )
}
