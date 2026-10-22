// frontend/src/pages/inventory/conteos/ConteoReporte.tsx
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { conteosApi, type Conteo, type FilaReporte, type Reporte } from '../../../api/conteos'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { Spinner } from '../../../components/ui/Spinner'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'
import { num, seccionesReporte, textoDiferencia, type Seccion } from './avance'

/** Reporte del conteo: abierto = avance en vivo; cerrado = congelado. Spec 2026-10-22 §5-§6. */
export function ConteoReporte() {
  const { id } = useParams()
  const conteoId = Number(id)
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const [conteo, setConteo] = useState<Conteo | null>(null)
  const [reporte, setReporte] = useState<Reporte | null>(null)
  const [abiertas, setAbiertas] = useState<Record<string, boolean>>({ faltantes: true })

  const cargar = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([conteosApi.ver(conteoId), conteosApi.reporte(conteoId)])
      setConteo(c); setReporte(r)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cargar el reporte')) }
  }, [conteoId])
  useEffect(() => { void cargar() }, [cargar])

  const cerrar = async () => {
    const ok = await confirm({ title: 'Cerrar el conteo', message: 'Se congela el reporte con lo contado hasta ahora.', confirmText: 'Cerrar', variant: 'warning' })
    if (!ok) return
    try { await conteosApi.cerrar(conteoId); await cargar() } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cerrar')) }
  }

  if (!conteo || !reporte) return <Spinner />
  const secciones = seccionesReporte(reporte)
  const t = reporte.totales

  const filas = (s: Seccion): FilaReporte[] =>
    s.clave === 'desconocidos'
      ? reporte.desconocidos.map((d) => ({ variant_id: d.codigo, sku: d.codigo, nombre: `Código ${d.codigo}`, marca: null, talla: null, color: null, departamento: null, sistema: '0', contado: d.contado, diferencia: d.contado, corregida: false }))
      : reporte[s.clave]

  return (
    <div className="space-y-4 pb-24">
      <CabeceraPagina
        titulo={<div>
          <h1 className="text-2xl font-black text-white">{reporte.alcance.departamento ?? 'Toda la tienda'}</h1>
          <p className="text-xs text-slate-400">{reporte.alcance.sucursal} · {conteo.status === 'CERRADO' ? `cerrado ${conteo.closed_at ? new Date(conteo.closed_at).toLocaleString('es-MX') : ''}` : 'avance en vivo'}{conteo.created_by ? ` · ${conteo.created_by}` : ''}</p>
        </div>}
        acciones={<Link to="/inventory/conteos" className="dax-btn-ghost text-xs">Todos los conteos</Link>}
        accionPrincipal={conteo.status === 'ABIERTO'
          ? <div className="flex gap-2"><button onClick={() => navigate(`/inventory/conteos/${conteoId}`)} className="dax-btn-secondary text-xs">Seguir contando</button><button onClick={cerrar} className="dax-btn-primary text-xs">Cerrar conteo</button></div>
          : undefined}
      />

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {[
          ['Esperadas', `${t.esperadas_variantes} tallas · ${num(t.esperadas_piezas)} pzas`],
          ['Contadas', `${t.contadas_variantes} tallas · ${num(t.contadas_piezas)} pzas`],
          ['Cuadradas', `${t.cuadradas_variantes} tallas`],
          ['Diferencia', `−${num(t.faltantes_piezas)} / +${num(t.sobrantes_piezas)} pzas`],
          ['Fichas corregidas', `${num(t.corregidas)} tallas`],
        ].map(([k, v]) => <DaxCard key={k}><div className="text-xs text-slate-400">{k}</div><div className="text-sm text-white font-bold">{v}</div></DaxCard>)}
      </div>

      {secciones.map((s) => (
        <DaxCard key={s.clave} padding={false}>
          <button className="w-full flex items-center justify-between p-3 text-left" onClick={() => setAbiertas((a) => ({ ...a, [s.clave]: !a[s.clave] }))}>
            <span className="text-white font-bold">{s.titulo} <span className="text-slate-400 font-normal text-xs">· {s.filas} {s.clave === 'desconocidos' ? 'códigos' : 'tallas'} · {s.piezas} pzas</span></span>
            <i className={`fa-solid ${abiertas[s.clave] ? 'fa-chevron-up' : 'fa-chevron-down'} text-slate-500`} />
          </button>
          {abiertas[s.clave] && (filas(s).length === 0 ? <p className="px-3 pb-3 text-xs text-slate-500">Nada aquí.</p> : esTelefono ? (
            <div className="px-3 pb-3"><ListaTarjetas>
              {filas(s).map((f) => (
                <TarjetaFila key={f.variant_id} titulo={<>{f.nombre} {f.corregida && <i className="fa-solid fa-pen text-indigo-400" title="Ficha corregida" />}</>} subtitulo={[f.sku, f.departamento].filter(Boolean).join(' · ')}
                  importe={<span className={num(f.diferencia) < 0 ? 'text-rose-400' : num(f.diferencia) > 0 ? 'text-amber-400' : 'text-slate-300'}>{textoDiferencia(num(f.diferencia))}</span>}
                  datos={[{ etiqueta: 'Sistema', valor: num(f.sistema) }, { etiqueta: 'Contado', valor: num(f.contado) }]} />
              ))}
            </ListaTarjetas></div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-400 uppercase"><tr><th className="text-left px-3 py-2">Pieza</th><th className="text-left px-3 py-2">SKU</th><th className="text-right px-3 py-2">Sistema</th><th className="text-right px-3 py-2">Contado</th><th className="text-right px-3 py-2">Diferencia</th></tr></thead>
              <tbody>
                {filas(s).map((f) => (
                  <tr key={f.variant_id} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-white">{f.nombre} {f.corregida && <i className="fa-solid fa-pen text-indigo-400" title="Ficha corregida" />}{f.departamento && s.clave === 'fuera_de_alcance' ? <span className="text-xs text-slate-400"> · {f.departamento}</span> : null}</td>
                    <td className="px-3 py-2 text-slate-400">{f.sku}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{num(f.sistema)}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{num(f.contado)}</td>
                    <td className={`px-3 py-2 text-right ${num(f.diferencia) < 0 ? 'text-rose-400' : num(f.diferencia) > 0 ? 'text-amber-400' : 'text-slate-300'}`}>{textoDiferencia(num(f.diferencia))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </DaxCard>
      ))}
    </div>
  )
}
