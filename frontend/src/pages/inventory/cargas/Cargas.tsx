import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cargasApi, type CargaResumen, type EstadoCarga, type PropositoCarga } from '../../../api/cargas'
import { organizationApi, type Branch } from '../../../api/organization'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { Spinner } from '../../../components/ui/Spinner'
import { StatusChip, type Tone } from '../../../components/ui/StatusChip'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'

/**
 * Cargar mercancía — subida de un PDF o planilla y lista de cargas previas.
 *
 * Subir crea la carga y manda a su plan (`/inventory/cargas/:id`). Mientras
 * alguna carga esté leyendo o aplicando, la lista se refresca cada 5 s.
 */

const LIMITE_BYTES = 20 * 1024 * 1024
const CADA_MS = 5000

export const ESTADOS: Record<EstadoCarga, { label: string; tone: Tone }> = {
  leyendo:   { label: 'Leyendo',    tone: 'sky' },
  plan:      { label: 'Por revisar', tone: 'amber' },
  aplicando: { label: 'Aplicando',  tone: 'violet' },
  aplicada:  { label: 'Aplicada',   tone: 'green' },
  error:     { label: 'Error',      tone: 'red' },
  descartada: { label: 'Descartada', tone: 'slate' },
}

const enCurso = (c: CargaResumen) => c.estado === 'leyendo' || c.estado === 'aplicando'

function cuando(iso: string): string {
  return new Date(iso).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function Cargas() {
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const userBranchId = useAuthStore((s) => s.user?.branch_id)

  const [cargas, setCargas] = useState<CargaResumen[] | null>(null)
  const [sucursales, setSucursales] = useState<Branch[]>([])
  const [sucursalId, setSucursalId] = useState<string>('')
  const [proposito, setProposito] = useState<PropositoCarga>('entrada')
  const [subiendo, setSubiendo] = useState(false)
  const entrada = useRef<HTMLInputElement>(null)

  const cargar = useCallback(async () => {
    try {
      setCargas(await cargasApi.listar())
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar las cargas'))
      setCargas((previas) => previas ?? [])
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])

  const hayEnCurso = (cargas ?? []).some(enCurso)
  useEffect(() => {
    if (!hayEnCurso) return
    const t = setInterval(() => { void cargar() }, CADA_MS)
    return () => clearInterval(t)
  }, [hayEnCurso, cargar])

  useEffect(() => {
    let vigente = true
    void Promise.all([
      organizationApi.getBranches().catch(() => [] as Branch[]),
      organizationApi.getOrg().catch(() => null),
    ]).then(([bs, org]) => {
      if (!vigente) return
      const activas = bs.filter((b) => b.is_active !== false)
      setSucursales(activas)
      const porOmision = org?.reglas_carga?.sucursal_recibe ?? userBranchId ?? null
      if (porOmision != null && activas.some((b) => b.id === porOmision)) setSucursalId(String(porOmision))
    })
    return () => { vigente = false }
  }, [userBranchId])

  const elegirArchivo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''
    if (!archivo) return
    if (archivo.size > LIMITE_BYTES) {
      toast.error('El archivo pesa más de 20 MB. Divídelo o sube una versión más ligera.')
      return
    }
    setSubiendo(true)
    try {
      const alta = await cargasApi.subir(archivo, proposito, sucursalId ? Number(sucursalId) : undefined)
      navigate(`/inventory/cargas/${alta.id}`)
    } catch (err: any) {
      toast.error(errorDetailText(err?.response?.data?.detail, 'No se pudo subir el archivo'))
    } finally {
      setSubiendo(false)
    }
  }

  const ir = (c: CargaResumen) => navigate(`/inventory/cargas/${c.id}`)
  const chip = (c: CargaResumen) => <StatusChip tone={ESTADOS[c.estado].tone} label={ESTADOS[c.estado].label} />

  return (
    <div className="space-y-4 pb-24">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-file-import text-dax-accent-text text-xl" />
          <h1 className="text-2xl font-black text-dax-text">Cargar mercancía</h1>
        </div>}
        descripcion="Sube la lista de tu proveedor (PDF, Excel o CSV). Revisas el plan y nada entra al catálogo hasta que lo autorices."
      />

      <DaxCard>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs text-dax-muted">Propósito</span>
            <select className="dax-input w-full" aria-label="Propósito" value={proposito}
              onChange={(e) => setProposito(e.target.value as PropositoCarga)}>
              <option value="entrada">Entrada de mercancía</option>
              <option value="migracion">Migración de catálogo</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-dax-muted">Sucursal que recibe</span>
            <select className="dax-input w-full" aria-label="Sucursal que recibe" value={sucursalId}
              onChange={(e) => setSucursalId(e.target.value)}>
              <option value="">Por omisión</option>
              {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-3">
          <input ref={entrada} type="file" accept=".pdf,.xlsx,.csv" className="hidden" onChange={elegirArchivo} />
          <button type="button" disabled={subiendo} onClick={() => entrada.current?.click()}
            className="dax-btn-primary justify-center w-full max-md:min-h-[44px] disabled:opacity-40">
            {subiendo
              ? <><i className="fa-solid fa-spinner fa-spin" /> Subiendo…</>
              : <><i className="fa-solid fa-upload" /> Elegir archivo (PDF, XLSX o CSV, máx. 20 MB)</>}
          </button>
        </div>
      </DaxCard>

      {cargas === null ? <Spinner /> : esTelefono ? (
        <ListaTarjetas vacio={cargas.length === 0} textoVacio="Todavía no hay cargas. Sube la primera.">
          {cargas.map((c) => (
            <TarjetaFila
              key={c.id}
              titulo={`#${c.folio} · ${c.archivo_nombre}`}
              subtitulo={`${c.usuario} · ${cuando(c.created_at)}`}
              estado={chip(c)}
              datos={[{ etiqueta: 'Piezas', valor: c.piezas }, { etiqueta: 'Sucursal', valor: c.sucursal_nombre ?? '—' }]}
              onClick={() => ir(c)}
            />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard padding={false}>
          <table className="w-full text-sm">
            <thead className="text-xs text-dax-muted uppercase">
              <tr>
                <th className="text-left p-3">Folio</th><th className="text-left p-3">Archivo</th>
                <th className="text-left p-3">Estado</th><th className="text-right p-3">Piezas</th>
                <th className="text-left p-3">Quién</th><th className="text-left p-3">Cuándo</th>
              </tr>
            </thead>
            <tbody>
              {cargas.length === 0 && (
                <tr><td colSpan={6} className="p-6 text-center text-dax-muted">Todavía no hay cargas. Sube la primera.</td></tr>
              )}
              {cargas.map((c) => (
                <tr key={c.id} className="border-t border-dax-border-dim hover:bg-dax-elevated cursor-pointer" onClick={() => ir(c)}>
                  <td className="p-3 text-dax-text font-semibold">#{c.folio}</td>
                  <td className="p-3 text-dax-text">{c.archivo_nombre}</td>
                  <td className="p-3">{chip(c)}</td>
                  <td className="p-3 text-right tabular-nums text-dax-text">{c.piezas}</td>
                  <td className="p-3 text-dax-muted">{c.usuario}</td>
                  <td className="p-3 text-dax-muted">{cuando(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DaxCard>
      )}
    </div>
  )
}
