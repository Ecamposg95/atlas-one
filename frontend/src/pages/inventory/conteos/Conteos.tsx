import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { conteosApi, type Conteo } from '../../../api/conteos'
import { organizationApi } from '../../../api/organization'
import { productsApi } from '../../../api/products'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import type { Branch } from '../../../types/auth'
import type { Department } from '../../../types/products'
import { errorDetailText } from '../../../utils/errorDetail'
import { estadoConteo, num, porcentajeAvance } from './avance'

/**
 * Conteo de inventario — lista de sesiones y alta de una nueva.
 *
 * Una sesión es una sucursal y un departamento (o toda la tienda). Abierta
 * entra a la pantalla de escaneo; cerrada, al reporte; cancelada no abre nada
 * (se descartó sin congelar reporte). La sucursal se
 * recuerda en el dispositivo con la misma clave que el Escáner.
 * Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §6.
 */

const BRANCH_KEY = 'atlas_scanner_branch_id'
const TODA_LA_TIENDA = ''

function fecha(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
}

export function Conteos() {
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const user = useAuthStore((s) => s.user)

  const [conteos, setConteos] = useState<Conteo[] | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [departamentos, setDepartamentos] = useState<Department[]>([])
  const [abrir, setAbrir] = useState(false)
  const [branchId, setBranchId] = useState<number | null>(() => {
    const s = localStorage.getItem(BRANCH_KEY)
    return s ? Number(s) : null
  })
  const [departmentId, setDepartmentId] = useState<string>(TODA_LA_TIENDA)
  const [notes, setNotes] = useState('')
  const [guardando, setGuardando] = useState(false)

  const effectiveBranchId = user?.branch_id ?? branchId

  const cargar = useCallback(async () => {
    try {
      setConteos(await conteosApi.listar())
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar los conteos'))
      setConteos([])
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])
  useEffect(() => {
    void productsApi.getDepartments().then(setDepartamentos).catch(() => setDepartamentos([]))
    if (!user?.branch_id) {
      void organizationApi.getBranches()
        .then((bs) => setBranches(bs.filter((b) => b.branch_type !== 'HQ')))
        .catch(() => setBranches([]))
    }
  }, [user?.branch_id])

  const crear = async () => {
    if (!effectiveBranchId) { toast.warning('Elige la sucursal que vas a contar'); return }
    setGuardando(true)
    try {
      if (!user?.branch_id && branchId) localStorage.setItem(BRANCH_KEY, String(branchId))
      const c = await conteosApi.crear({
        branch_id: effectiveBranchId, department_id: departmentId || null, notes: notes.trim() || undefined,
      })
      setAbrir(false)
      navigate(`/inventory/conteos/${c.id}`)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir el conteo'))
    } finally {
      setGuardando(false)
    }
  }

  const abrible = (c: Conteo) => c.status !== 'CANCELADO'
  const ir = (c: Conteo) => {
    if (!abrible(c)) return
    navigate(c.status === 'ABIERTO' ? `/inventory/conteos/${c.id}` : `/inventory/conteos/${c.id}/reporte`)
  }

  const avanceTxt = (c: Conteo) =>
    `${num(c.avance.contadas_piezas)} / ${num(c.avance.esperadas_piezas)} piezas · ${porcentajeAvance(c.avance.contadas_variantes, c.avance.esperadas_variantes)}%`

  return (
    <div className="space-y-4 pb-24">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-list-check text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Conteo de inventario</h1>
        </div>}
        descripcion="Escanea un departamento completo y compara contra el sistema. Nada se ajusta hasta que tú lo decidas."
        accionPrincipal={<button onClick={() => setAbrir(true)} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nuevo conteo
        </button>}
      />

      {conteos === null ? <Spinner /> : esTelefono ? (
        <ListaTarjetas vacio={conteos.length === 0} textoVacio="Todavía no hay conteos. Abre el primero.">
          {conteos.map((c) => {
            const estado = estadoConteo(c.status)
            return (
            <TarjetaFila
              key={c.id}
              titulo={c.department_name ?? 'Toda la tienda'}
              subtitulo={`${c.branch_name ?? ''} · ${fecha(c.created_at)}${c.created_by ? ` · ${c.created_by}` : ''}`}
              estado={<span className={estado.clase}>{estado.texto}</span>}
              datos={[{ etiqueta: 'Avance', valor: avanceTxt(c) }]}
              onClick={abrible(c) ? () => ir(c) : undefined}
            />
            )
          })}
        </ListaTarjetas>
      ) : (
        <DaxCard padding={false}>
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-400 uppercase">
              <tr><th className="text-left p-3">Departamento</th><th className="text-left p-3">Sucursal</th><th className="text-left p-3">Fecha</th><th className="text-left p-3">Avance</th><th className="text-left p-3">Estado</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {conteos.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-slate-400">Todavía no hay conteos. Abre el primero.</td></tr>}
              {conteos.map((c) => {
                const estado = estadoConteo(c.status)
                return (
                <tr key={c.id} className={`border-t border-slate-800 ${abrible(c) ? 'hover:bg-slate-800/40 cursor-pointer' : ''}`}
                  onClick={abrible(c) ? () => ir(c) : undefined}>
                  <td className="p-3 text-white font-semibold">{c.department_name ?? 'Toda la tienda'}</td>
                  <td className="p-3 text-slate-300">{c.branch_name}</td>
                  <td className="p-3 text-slate-300">{fecha(c.created_at)}{c.created_by ? ` · ${c.created_by}` : ''}</td>
                  <td className="p-3 text-slate-300">{avanceTxt(c)}</td>
                  <td className={`p-3 ${estado.clase}`}>{estado.texto}</td>
                  <td className="p-3 text-right">{abrible(c) && <i className="fa-solid fa-chevron-right text-slate-500" />}</td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </DaxCard>
      )}

      <Modal open={abrir} onClose={() => setAbrir(false)} title="Nuevo conteo" size="sm"
        footer={<>
          <button onClick={() => setAbrir(false)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={crear} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Abrir conteo'}
          </button>
        </>}>
        <div className="space-y-3">
          {!user?.branch_id && (
            <label className="block">
              <span className="text-xs text-slate-400">Sucursal</span>
              <select className="dax-input w-full" value={branchId ?? ''} onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Elige…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
          )}
          <label className="block">
            <span className="text-xs text-slate-400">Departamento</span>
            <select className="dax-input w-full" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value={TODA_LA_TIENDA}>Toda la tienda</option>
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-slate-400">Notas (opcional)</span>
            <input className="dax-input w-full" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Pared izquierda, estante 2…" />
          </label>
        </div>
      </Modal>
    </div>
  )
}
