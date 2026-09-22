import { useCallback, useEffect, useMemo, useState } from 'react'

import { labelsApi, type LabelCandidate, type LabelPreview } from '../../api/labels'
import { productsApi } from '../../api/products'
import { AgentUnreachableError, printerApi } from '../../api/printer'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { confirm } from '../../components/ui/ConfirmDialog'
import {
  FILTROS_VACIOS, FiltrosEtiquetas, type EstadoFiltros,
} from '../../components/labels/FiltrosEtiquetas'
import { TablaEtiquetas } from '../../components/labels/TablaEtiquetas'
import { VistaPreviaEtiqueta } from '../../components/labels/VistaPreviaEtiqueta'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { toast } from '../../store/toastStore'
import type { Brand, Department } from '../../types/products'
import { errorDetailText } from '../../utils/errorDetail'
import { sortByName } from '../../utils/sortByName'
import {
  MAX_COPIAS, construirLote, copiasIniciales, mensajeExceso, normalizarCopias, ponerN,
  textoResumen, usarExistencia,
} from './lote'

/**
 * Etiquetas — pantalla de mostrador para la Zebra.
 *
 * El backend elige las variantes, calcula las copias y compone el ZPL; esta
 * pantalla decide QUÉ se imprime y CUÁNTO, y le pasa el trabajo en base64 al
 * agente local (`POST https://localhost:9100/print`), el mismo transporte del
 * ticket de venta. Nada de ZPL se arma aquí: la vista previa se dibuja con los
 * mismos elementos que generan el ZPL, así que la pantalla no puede mentir
 * sobre lo que sale del rollo.
 *
 * Diseño: `docs/superpowers/specs/2026-09-22-etiquetas-en-atlas-one-design.md`.
 */

/** La Zebra no es la impresora del ticket: su cola se recuerda aparte. */
const COLA_KEY = 'atlas_labels_printer'

export function Labels() {
  const esTelefono = useEsTelefono()

  const [filtros, setFiltros] = useState<EstadoFiltros>(FILTROS_VACIOS)
  // La búsqueda libre se APLICA al enviar (Enter o el botón); los selectores y
  // la casilla recargan solos. Teclear no debe disparar una consulta por letra.
  const [busqueda, setBusqueda] = useState('')

  const [departamentos, setDepartamentos] = useState<Department[]>([])
  const [marcas, setMarcas] = useState<Brand[]>([])

  const [items, setItems] = useState<LabelCandidate[]>([])
  const [cargando, setCargando] = useState(true)
  const [errorLista, setErrorLista] = useState<string | null>(null)

  const [copias, setCopias] = useState<Record<string, number>>({})
  const [seleccion, setSeleccion] = useState<Set<string>>(new Set())
  const [nLote, setNLote] = useState('1')

  const [activa, setActiva] = useState<LabelCandidate | null>(null)
  const [previa, setPrevia] = useState<LabelPreview | null>(null)
  const [previaCargando, setPreviaCargando] = useState(false)
  const [previaError, setPreviaError] = useState<string | null>(null)

  const [colas, setColas] = useState<string[]>([])
  const [cola, setCola] = useState<string>(() => localStorage.getItem(COLA_KEY) ?? '')
  const [agenteVivo, setAgenteVivo] = useState<boolean | null>(null)
  const [imprimiendo, setImprimiendo] = useState(false)

  // ── Catálogos de los filtros ───────────────────────────────────────────
  useEffect(() => {
    void productsApi.getDepartments().then((d) => setDepartamentos(sortByName(d))).catch(() => setDepartamentos([]))
    void productsApi.getBrands().then((b) => setMarcas(sortByName(b))).catch(() => setMarcas([]))
  }, [])

  // ── Colas del agente local ─────────────────────────────────────────────
  const cargarColas = useCallback(async () => {
    const vivo = await printerApi.pingAgent()
    setAgenteVivo(vivo)
    if (!vivo) { setColas([]); return }
    const lista = await printerApi.getLocalPrinters()
    setColas(lista)
    // Sin cola recordada (o si la recordada ya no existe) se propone la primera.
    setCola((actual) => (actual && lista.includes(actual) ? actual : (lista[0] ?? '')))
  }, [])

  useEffect(() => { void cargarColas() }, [cargarColas])

  useEffect(() => {
    if (cola) localStorage.setItem(COLA_KEY, cola)
  }, [cola])

  // ── Candidatos ─────────────────────────────────────────────────────────
  const cargar = useCallback(async () => {
    setCargando(true)
    setErrorLista(null)
    try {
      const res = await labelsApi.candidates({
        search: busqueda,
        department_id: filtros.department_id,
        brand_id: filtros.brand_id,
        gender: filtros.gender,
        only_with_stock: filtros.only_with_stock,
      })
      setItems(res.items)
      setCopias(copiasIniciales(res.items))
      // La selección y la vista previa se quedarían apuntando a variantes que
      // ya no están en pantalla: mandar a imprimir algo que no se ve es la
      // forma más fácil de gastar rollo sin querer.
      setSeleccion(new Set())
      setActiva(null)
      setPrevia(null)
      setPreviaError(null)
    } catch (e: any) {
      const status = e?.response?.status
      setItems([])
      setErrorLista(
        status === 403
          ? 'Tu tienda no tiene activo el módulo de Etiquetas. Pídelo a soporte.'
          : errorDetailText(e?.response?.data?.detail, 'No se pudo cargar el catálogo de etiquetas.'),
      )
    } finally {
      setCargando(false)
    }
  }, [busqueda, filtros.department_id, filtros.brand_id, filtros.gender, filtros.only_with_stock])

  useEffect(() => { void cargar() }, [cargar])

  // ── Vista previa ───────────────────────────────────────────────────────
  const verPrevia = useCallback(async (item: LabelCandidate) => {
    setActiva(item)
    setPrevia(null)
    setPreviaError(null)
    setPreviaCargando(true)
    try {
      setPrevia(await labelsApi.preview(item.variant_id))
    } catch (e: any) {
      setPreviaError(errorDetailText(e?.response?.data?.detail, 'No se pudo armar la vista previa.'))
    } finally {
      setPreviaCargando(false)
    }
  }, [])

  // ── Selección y copias ─────────────────────────────────────────────────
  const alternar = (variantId: string) => {
    setSeleccion((s) => {
      const next = new Set(s)
      if (next.has(variantId)) next.delete(variantId); else next.add(variantId)
      return next
    })
  }

  const alternarTodo = () => {
    const imprimibles = items.filter((i) => i.printable)
    setSeleccion((s) => (
      imprimibles.length > 0 && imprimibles.every((i) => s.has(i.variant_id))
        ? new Set()
        : new Set(imprimibles.map((i) => i.variant_id))
    ))
  }

  const cambiarCopias = (variantId: string, valor: string) => {
    setCopias((c) => ({ ...c, [variantId]: normalizarCopias(valor) }))
  }

  const resumen = useMemo(
    () => construirLote(items, copias, seleccion),
    [items, copias, seleccion],
  )

  // ── Impresión ──────────────────────────────────────────────────────────
  const mandarAlAgente = async (base64: string, queEs: string) => {
    if (!cola) { toast.error('Elige la cola de la Zebra antes de imprimir.'); return }
    try {
      await printerApi.printViaAgent(cola, base64)
      toast.success(`${queEs} enviado a ${cola}.`)
    } catch (e: any) {
      // El agente apagado y el certificado sin aceptar fallan igual en el
      // navegador: `AgentUnreachableError` ya trae el mensaje que cubre ambos.
      toast.error(e instanceof AgentUnreachableError ? e.message : (e?.message ?? 'No se pudo imprimir.'))
      void cargarColas()
    }
  }

  const imprimir = async () => {
    if (resumen.excede) { toast.error(mensajeExceso(resumen.etiquetas)); return }
    if (resumen.items.length === 0) {
      toast.warning(
        resumen.omitidas.length > 0
          ? 'Ninguno de los renglones tiene código de barras imprimible.'
          : 'No hay nada que imprimir: pon copias en al menos un renglón.',
      )
      return
    }
    if (!cola) { toast.error('Elige la cola de la Zebra antes de imprimir.'); return }

    const ok = await confirm({
      title: `Imprimir ${resumen.etiquetas} ${resumen.etiquetas === 1 ? 'etiqueta' : 'etiquetas'}`,
      variant: 'warning',
      confirmText: 'Imprimir',
      message: (
        <div className="space-y-2">
          <p>
            {resumen.items.length} {resumen.items.length === 1 ? 'renglón' : 'renglones'} a la cola{' '}
            <span className="font-semibold">{cola}</span>
            {seleccion.size === 0 && ' (todo lo visible: no hay filas marcadas)'}.
          </p>
          {resumen.sinCopias > 0 && (
            <p>{resumen.sinCopias} {resumen.sinCopias === 1 ? 'renglón queda' : 'renglones quedan'} fuera por estar en 0 copias.</p>
          )}
          {resumen.omitidas.length > 0 && (
            <div>
              <p className="font-semibold">Se omiten {resumen.omitidas.length}:</p>
              <ul className="list-disc ml-5 max-h-32 overflow-y-auto">
                {resumen.omitidas.slice(0, 12).map((o) => (
                  <li key={o.variant_id}>{o.sku || 'sin SKU'} — {o.reason}</li>
                ))}
                {resumen.omitidas.length > 12 && <li>…y {resumen.omitidas.length - 12} más.</li>}
              </ul>
            </div>
          )}
        </div>
      ),
    })
    if (!ok) return

    setImprimiendo(true)
    try {
      const job = await labelsApi.createJob(resumen.items)
      // El backend también omite renglones (variante borrada, otra sucursal):
      // su `skipped` manda sobre lo que esta pantalla calculó.
      if (job.skipped.length > 0) {
        toast.warning(`Se omitieron ${job.skipped.length}: ${job.skipped.map((s) => s.sku || s.variant_id).slice(0, 3).join(', ')}…`)
      }
      if (!job.content_base64 || job.labels === 0) {
        toast.error('El trabajo salió vacío: ningún renglón se pudo imprimir.')
        return
      }
      await mandarAlAgente(job.content_base64, `${job.labels} ${job.labels === 1 ? 'etiqueta' : 'etiquetas'}`)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo armar el lote de etiquetas.'))
    } finally {
      setImprimiendo(false)
    }
  }

  const imprimirPrueba = async () => {
    setImprimiendo(true)
    try {
      const b64 = await labelsApi.testLabel()
      if (!b64) { toast.error('El backend no devolvió la etiqueta de prueba.'); return }
      await mandarAlAgente(b64, 'Etiqueta de prueba')
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo generar la etiqueta de prueba.'))
    } finally {
      setImprimiendo(false)
    }
  }

  const panelPrevia = (
    <VistaPreviaEtiqueta
      preview={previa}
      cargando={previaCargando}
      error={previaError}
      titulo={activa ? `${activa.sku} · ${activa.sale_name || activa.product_name}` : undefined}
    />
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-black text-white">Etiquetas</h1>
          <p className="text-xs text-slate-500">
            Etiqueta de 51 × 25 mm para la Zebra. Se imprime por el agente local.
          </p>
        </div>
        <button
          type="button"
          className="dax-btn-secondary text-sm"
          onClick={() => void imprimirPrueba()}
          disabled={imprimiendo || !cola}
          title="Imprime la etiqueta de calibración para ajustar la Zebra antes de gastar rollo"
        >
          <i className="fa-solid fa-vial" /> Etiqueta de prueba
        </button>
      </div>

      <DaxCard>
        <FiltrosEtiquetas
          valor={filtros}
          onChange={setFiltros}
          departamentos={departamentos}
          marcas={marcas}
          onBuscar={() => setBusqueda(filtros.search)}
          cargando={cargando}
        />
      </DaxCard>

      {/* Acciones en lote + cola + imprimir */}
      <DaxCard>
        <div className="flex flex-wrap items-end gap-3">
          <button
            type="button"
            className="dax-btn-secondary text-sm"
            onClick={() => setCopias((c) => usarExistencia(items, c, seleccion))}
            disabled={items.length === 0}
            title={seleccion.size === 0 ? 'Aplica a todo lo visible' : `Aplica a ${seleccion.size} seleccionados`}
          >
            <i className="fa-solid fa-boxes-stacked" /> Usar existencia
          </button>

          <div className="flex items-end gap-2">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Copias
              </label>
              <input
                type="number" min={0} max={MAX_COPIAS} step={1} inputMode="numeric"
                className="dax-input w-20 text-sm text-center"
                value={nLote}
                onChange={(e) => setNLote(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="dax-btn-secondary text-sm"
              onClick={() => setCopias((c) => ponerN(items, c, seleccion, nLote))}
              disabled={seleccion.size === 0}
              title={seleccion.size === 0 ? 'Marca al menos un renglón' : `Aplica a ${seleccion.size} seleccionados`}
            >
              Poner a los seleccionados
            </button>
          </div>

          <div className="min-w-[12rem] flex-1">
            <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
              Cola de la Zebra
            </label>
            <div className="flex gap-2">
              <select
                className="dax-input w-full text-sm"
                value={cola}
                onChange={(e) => setCola(e.target.value)}
                disabled={colas.length === 0}
              >
                {colas.length === 0 && <option value="">Sin colas</option>}
                {colas.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <button
                type="button"
                className="dax-btn-secondary px-3 text-sm"
                onClick={() => void cargarColas()}
                title="Volver a preguntarle al agente"
              >
                <i className="fa-solid fa-rotate" />
              </button>
            </div>
          </div>

          <button
            type="button"
            className="dax-btn-primary text-sm"
            onClick={() => void imprimir()}
            disabled={imprimiendo || resumen.items.length === 0 || !cola}
          >
            <i className={`fa-solid ${imprimiendo ? 'fa-spinner fa-spin' : 'fa-print'}`} />
            Imprimir {resumen.etiquetas > 0 ? resumen.etiquetas : ''}
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
          <span className="text-slate-400">{textoResumen(resumen)}</span>
          {seleccion.size > 0
            ? <span className="text-slate-500">{seleccion.size} seleccionados</span>
            : <span className="text-slate-500">Sin selección: las acciones toman todo lo visible</span>}
          {resumen.excede && <span className="text-red-400 font-semibold">{mensajeExceso(resumen.etiquetas)}</span>}
          {agenteVivo === false && (
            <span className="text-amber-300">
              <i className="fa-solid fa-plug-circle-xmark mr-1" />
              El agente de impresión no responde. Ábrelo y acepta su certificado en https://localhost:9100.
            </span>
          )}
        </div>
      </DaxCard>

      {/* Tabla + vista previa */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <div className="lg:col-span-2">
          <DaxCard padding={false}>
            <div className="p-4">
              {cargando ? <Spinner text="Buscando prendas…" />
                : errorLista ? (
                  <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                    {errorLista}
                  </div>
                ) : (
                  <TablaEtiquetas
                    items={items}
                    copias={copias}
                    seleccion={seleccion}
                    activa={activa?.variant_id ?? null}
                    onAlternar={alternar}
                    onAlternarTodo={alternarTodo}
                    onCopias={cambiarCopias}
                    onVerPrevia={(it) => void verPrevia(it)}
                    esTelefono={esTelefono}
                  />
                )}
            </div>
          </DaxCard>
        </div>

        {/* En escritorio la previa vive al lado; en teléfono se convierte en
            hoja inferior (`.dax-modal`) para no empujar la tabla. */}
        {!esTelefono && (
          <DaxCard className="lg:sticky lg:top-4">{panelPrevia}</DaxCard>
        )}
      </div>

      {esTelefono && activa && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => { setActiva(null); setPrevia(null); setPreviaError(null) }}
        >
          <div className="dax-card dax-modal p-4 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            {panelPrevia}
            <div className="dax-modal-footer flex justify-end">
              <button
                type="button"
                className="dax-btn-secondary text-sm"
                onClick={() => { setActiva(null); setPrevia(null); setPreviaError(null) }}
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Labels
