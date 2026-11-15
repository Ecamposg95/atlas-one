import { useEffect, useState } from 'react'
import {
  organizationApi, REGLAS_CARGA_POR_OMISION,
  type Branch, type Organization, type ReglasCarga as Reglas,
} from '../../api/organization'
import { productsApi } from '../../api/products'
import type { Brand, Department } from '../../types/products'
import { DaxCard } from '../../components/ui/DaxCard'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'

interface Props {
  org: Organization
  branches: Branch[]
  onGuardado: (org: Organization) => void
}

// Los mapas del backend se editan como filas (la clave es editable).
interface FilaTipo { tipo: string; codigo_sku: string; departamento: string }
interface FilaPar { clave: string; valor: string }
interface FilaPrecio { tipo: string; marca: string; precios: string }

const aLista = (t: string) => t.split(',').map((x) => x.trim()).filter(Boolean)

const filasTipos = (r: Reglas): FilaTipo[] =>
  Object.entries(r.tipos).map(([tipo, v]) => ({ tipo, codigo_sku: v.codigo_sku, departamento: v.departamento }))
const filasPares = (m: Record<string, string>): FilaPar[] =>
  Object.entries(m).map(([clave, valor]) => ({ clave, valor }))
const filasPrecios = (r: Reglas): FilaPrecio[] =>
  r.precios_familia.map((p) => ({ tipo: p.tipo, marca: p.marca ?? '', precios: p.precios.join(', ') }))

const paresAMapa = (filas: FilaPar[]) =>
  Object.fromEntries(filas.filter((f) => f.clave.trim()).map((f) => [f.clave.trim(), f.valor.trim()]))

/** Sección "Reglas de carga" de Empresa (visible solo con el módulo `ai`). */
export function ReglasCarga({ org, branches, onGuardado }: Props) {
  const inicial: Reglas = { ...REGLAS_CARGA_POR_OMISION, ...(org.reglas_carga ?? {}) }
  const [r, setR] = useState<Reglas>(inicial)
  const [tipos, setTipos] = useState<FilaTipo[]>(() => filasTipos(inicial))
  const [tallas, setTallas] = useState<FilaPar[]>(() => filasPares(inicial.mapa_tallas))
  const [generos, setGeneros] = useState<FilaPar[]>(() => filasPares(inicial.genero_por_marca))
  const [precios, setPrecios] = useState<FilaPrecio[]>(() => filasPrecios(inicial))
  const [aparte, setAparte] = useState(inicial.materiales_aparte.join(', '))
  const [marcas, setMarcas] = useState<Brand[]>([])
  const [deptos, setDeptos] = useState<Department[]>([])
  const [guardando, setGuardando] = useState(false)
  const [errores, setErrores] = useState<{ ruta: string; msg: string }[]>([])

  useEffect(() => {
    productsApi.getBrands().then(setMarcas).catch(() => {})
    productsApi.getDepartments().then(setDeptos).catch(() => {})
  }, [])

  const set = <K extends keyof Reglas>(k: K, v: Reglas[K]) => setR((p) => ({ ...p, [k]: v }))
  const erroresDe = (campo: string) => errores.filter((e) => e.ruta === campo || e.ruta.startsWith(`${campo}.`))
  const Err = ({ campo }: { campo: string }) => (
    <>{erroresDe(campo).map((e, i) => <p key={i} className="text-xs text-dax-danger mt-1">{e.msg}</p>)}</>
  )
  const cambiarFila = <T,>(lista: T[], set: (l: T[]) => void, i: number, parche: Partial<T>) =>
    set(lista.map((f, j) => (j === i ? { ...f, ...parche } : f)))
  const quitar = <T,>(lista: T[], set: (l: T[]) => void, i: number) => set(lista.filter((_, j) => j !== i))

  const guardar = async () => {
    setGuardando(true)
    setErrores([])
    const payload: Reglas = {
      ...r,
      fraccion: String(r.fraccion),
      mapa_tallas: paresAMapa(tallas),
      tipos: Object.fromEntries(
        tipos.filter((t) => t.tipo.trim()).map((t) => [t.tipo.trim(), { codigo_sku: t.codigo_sku.trim(), departamento: t.departamento }]),
      ),
      materiales_aparte: aLista(aparte),
      genero_por_marca: paresAMapa(generos),
      precios_familia: precios.filter((p) => p.tipo.trim()).map((p) => ({
        tipo: p.tipo.trim(), marca: p.marca.trim() || null, precios: aLista(p.precios),
      })),
      material_normal: r.material_normal?.trim() || null,
      genero_por_omision: r.genero_por_omision?.trim() || null,
      sufijo_dama: r.sufijo_dama?.trim() || null,
    }
    try {
      const nueva = await organizationApi.updateOrg({ reglas_carga: payload })
      onGuardado(nueva)
      toast.success('Reglas de carga guardadas')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (Array.isArray(detail)) {
        setErrores(detail.map((d: any) => {
          const loc: unknown[] = Array.isArray(d?.loc) ? d.loc : []
          return { ruta: loc.slice(2).join('.'), msg: String(d?.msg ?? 'Valor no válido') }
        }))
      }
      toast.error(errorDetailText(detail, 'No se pudieron guardar las reglas de carga'))
    } finally { setGuardando(false) }
  }

  const titulo = 'text-[10px] font-bold text-dax-faint uppercase tracking-widest mb-3'
  const fila = 'grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end'

  return (
    <DaxCard>
      <p className="text-[10px] font-bold text-dax-faint uppercase tracking-widest mb-1">Reglas de carga</p>
      <p className="text-xs text-dax-muted mb-4">Cómo se interpretan los archivos y facturas al cargar mercancía con IA.</p>

      <div className="space-y-6">
        <section>
          <p className={titulo}>Costo e IVA</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <fieldset>
              <legend className="dax-label">Si falta el costo</legend>
              <label className="flex items-center gap-2 text-sm text-dax-text min-h-[44px] sm:min-h-0">
                <input type="radio" name="costo_si_falta" checked={r.costo_si_falta === 'preguntar'} onChange={() => set('costo_si_falta', 'preguntar')} />
                Preguntar
              </label>
              <label className="flex items-center gap-2 text-sm text-dax-text min-h-[44px] sm:min-h-0">
                <input type="radio" name="costo_si_falta" checked={r.costo_si_falta === 'fraccion_precio'} onChange={() => set('costo_si_falta', 'fraccion_precio')} />
                Calcular como fracción del precio
              </label>
              <Err campo="costo_si_falta" />
            </fieldset>
            <div>
              <label htmlFor="rc-fraccion" className="dax-label">Fracción del precio</label>
              <input id="rc-fraccion" type="number" step="0.01" min="0" value={r.fraccion}
                onChange={(e) => set('fraccion', e.target.value)} disabled={r.costo_si_falta !== 'fraccion_precio'}
                className="dax-input w-full tabular-nums disabled:opacity-40" />
              <p className="text-[10px] mt-1 text-dax-faint">0.5 = el costo es la mitad del precio.</p>
              <Err campo="fraccion" />
            </div>
            <label className="flex items-center gap-2 text-sm text-dax-text min-h-[44px] sm:min-h-0 sm:col-span-2">
              <input type="checkbox" role="switch" aria-label="IVA incluido en los precios" checked={r.iva} onChange={(e) => set('iva', e.target.checked)} className="w-4 h-4" />
              IVA incluido en los precios
            </label>
          </div>
        </section>

        <section>
          <p className={titulo}>Dónde entra la mercancía</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="rc-sucursal" className="dax-label">Sucursal que recibe</label>
              <select id="rc-sucursal" value={r.sucursal_recibe ?? ''} className="dax-input w-full"
                onChange={(e) => set('sucursal_recibe', e.target.value ? Number(e.target.value) : null)}>
                <option value="">La del usuario</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
              <Err campo="sucursal_recibe" />
            </div>
            <div>
              <label htmlFor="rc-activar" className="dax-label">Activar el producto en</label>
              <select id="rc-activar" value={r.activar_en} className="dax-input w-full"
                onChange={(e) => set('activar_en', e.target.value as Reglas['activar_en'])}>
                <option value="todas_las_que_venden">Todas las sucursales que venden</option>
                <option value="sucursal_recibe">Solo la sucursal que recibe</option>
              </select>
              <Err campo="activar_en" />
            </div>
          </div>
        </section>

        <section>
          <p className={titulo}>Mapa de tallas</p>
          <p className="text-[10px] mb-2 text-dax-faint">Cómo viene escrita la talla → como se guarda.</p>
          <div className="space-y-2">
            {tallas.map((t, i) => (
              <div key={i} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
                <input aria-label={`Talla en el archivo ${i + 1}`} placeholder="Chica" value={t.clave} className="dax-input w-full"
                  onChange={(e) => cambiarFila(tallas, setTallas, i, { clave: e.target.value })} />
                <input aria-label={`Talla guardada ${i + 1}`} placeholder="Ch" value={t.valor} className="dax-input w-full"
                  onChange={(e) => cambiarFila(tallas, setTallas, i, { valor: e.target.value })} />
                <button type="button" aria-label={`Quitar talla ${i + 1}`} className="dax-btn-icon" onClick={() => quitar(tallas, setTallas, i)}>
                  <i className="fa-solid fa-trash" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="dax-btn-secondary text-xs mt-2" onClick={() => setTallas([...tallas, { clave: '', valor: '' }])}>
            <i className="fa-solid fa-plus" /> Agregar talla
          </button>
          <Err campo="mapa_tallas" />
        </section>

        <section>
          <p className={titulo}>Tipos de prenda</p>
          <div className="space-y-2">
            {tipos.map((t, i) => (
              <div key={i} className={fila}>
                <input aria-label={`Tipo de prenda ${i + 1}`} placeholder="camisa" value={t.tipo} className="dax-input w-full"
                  onChange={(e) => cambiarFila(tipos, setTipos, i, { tipo: e.target.value })} />
                <input aria-label={`Código SKU ${i + 1}`} placeholder="CAM" value={t.codigo_sku} className="dax-input w-full font-mono"
                  onChange={(e) => cambiarFila(tipos, setTipos, i, { codigo_sku: e.target.value })} />
                <select aria-label={`Departamento ${i + 1}`} value={t.departamento} className="dax-input w-full"
                  onChange={(e) => cambiarFila(tipos, setTipos, i, { departamento: e.target.value })}>
                  <option value="">Departamento…</option>
                  {t.departamento && !deptos.some((d) => d.name === t.departamento) && <option value={t.departamento}>{t.departamento}</option>}
                  {deptos.map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}
                </select>
                <button type="button" aria-label={`Quitar tipo ${i + 1}`} className="dax-btn-icon" onClick={() => quitar(tipos, setTipos, i)}>
                  <i className="fa-solid fa-trash" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="dax-btn-secondary text-xs mt-2" onClick={() => setTipos([...tipos, { tipo: '', codigo_sku: '', departamento: '' }])}>
            <i className="fa-solid fa-plus" /> Agregar tipo de prenda
          </button>
          <Err campo="tipos" />
        </section>

        <section>
          <p className={titulo}>Materiales</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="rc-aparte" className="dax-label">Materiales que van aparte</label>
              <input id="rc-aparte" value={aparte} onChange={(e) => setAparte(e.target.value)} className="dax-input w-full" placeholder="piel, mezclilla" />
              <p className="text-[10px] mt-1 text-dax-faint">Separados por coma: se cargan como producto distinto.</p>
              <Err campo="materiales_aparte" />
            </div>
            <div>
              <label htmlFor="rc-normal" className="dax-label">Material normal</label>
              <input id="rc-normal" value={r.material_normal ?? ''} onChange={(e) => set('material_normal', e.target.value)} className="dax-input w-full" placeholder="algodón" />
              <Err campo="material_normal" />
            </div>
          </div>
        </section>

        <section>
          <p className={titulo}>Género</p>
          <div className="space-y-2">
            {generos.map((g, i) => (
              <div key={i} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
                <select aria-label={`Marca ${i + 1}`} value={g.clave} className="dax-input w-full"
                  onChange={(e) => cambiarFila(generos, setGeneros, i, { clave: e.target.value })}>
                  <option value="">Marca…</option>
                  {g.clave && !marcas.some((m) => m.name === g.clave) && <option value={g.clave}>{g.clave}</option>}
                  {marcas.map((m) => <option key={m.id} value={m.name}>{m.name}</option>)}
                </select>
                <input aria-label={`Género de la marca ${i + 1}`} placeholder="Dama" value={g.valor} className="dax-input w-full"
                  onChange={(e) => cambiarFila(generos, setGeneros, i, { valor: e.target.value })} />
                <button type="button" aria-label={`Quitar marca ${i + 1}`} className="dax-btn-icon" onClick={() => quitar(generos, setGeneros, i)}>
                  <i className="fa-solid fa-trash" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="dax-btn-secondary text-xs mt-2" onClick={() => setGeneros([...generos, { clave: '', valor: '' }])}>
            <i className="fa-solid fa-plus" /> Agregar género por marca
          </button>
          <Err campo="genero_por_marca" />
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
            <div>
              <label htmlFor="rc-gen" className="dax-label">Género por omisión</label>
              <input id="rc-gen" value={r.genero_por_omision ?? ''} onChange={(e) => set('genero_por_omision', e.target.value)} className="dax-input w-full" />
              <Err campo="genero_por_omision" />
            </div>
            <div>
              <label htmlFor="rc-sufijo" className="dax-label">Sufijo de dama</label>
              <input id="rc-sufijo" value={r.sufijo_dama ?? ''} onChange={(e) => set('sufijo_dama', e.target.value)} className="dax-input w-full font-mono" placeholder="-MUJ" />
              <Err campo="sufijo_dama" />
            </div>
            <div>
              <label htmlFor="rc-matriz" className="dax-label">Matriz por omisión</label>
              <select id="rc-matriz" value={r.matriz_por_omision} className="dax-input w-full"
                onChange={(e) => set('matriz_por_omision', e.target.value as Reglas['matriz_por_omision'])}>
                <option value="solo_lo_que_hay">Solo lo que hay</option>
                <option value="completa">Completa</option>
              </select>
              <Err campo="matriz_por_omision" />
            </div>
          </div>
        </section>

        <section>
          <p className={titulo}>Precios por familia</p>
          <p className="text-[10px] mb-2 text-dax-faint">Lista de precios por tipo y marca opcional, separados por coma.</p>
          <div className="space-y-2">
            {precios.map((p, i) => (
              <div key={i} className={fila}>
                <input aria-label={`Tipo de la familia ${i + 1}`} placeholder="camisa" value={p.tipo} className="dax-input w-full"
                  onChange={(e) => cambiarFila(precios, setPrecios, i, { tipo: e.target.value })} />
                <select aria-label={`Marca de la familia ${i + 1}`} value={p.marca} className="dax-input w-full"
                  onChange={(e) => cambiarFila(precios, setPrecios, i, { marca: e.target.value })}>
                  <option value="">Cualquier marca</option>
                  {p.marca && !marcas.some((m) => m.name === p.marca) && <option value={p.marca}>{p.marca}</option>}
                  {marcas.map((m) => <option key={m.id} value={m.name}>{m.name}</option>)}
                </select>
                <input aria-label={`Lista de precios ${i + 1}`} placeholder="500, 650, 800" value={p.precios} className="dax-input w-full tabular-nums"
                  onChange={(e) => cambiarFila(precios, setPrecios, i, { precios: e.target.value })} />
                <button type="button" aria-label={`Quitar familia ${i + 1}`} className="dax-btn-icon" onClick={() => quitar(precios, setPrecios, i)}>
                  <i className="fa-solid fa-trash" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <button type="button" className="dax-btn-secondary text-xs mt-2" onClick={() => setPrecios([...precios, { tipo: '', marca: '', precios: '' }])}>
            <i className="fa-solid fa-plus" /> Agregar precios por familia
          </button>
          <Err campo="precios_familia" />
        </section>

        <section>
          <label htmlFor="rc-ventana" className="dax-label">Días para avisar "ya cargado"</label>
          <input id="rc-ventana" type="number" min="0" value={r.ventana_ya_cargado_dias} className="dax-input w-full sm:w-40 tabular-nums"
            onChange={(e) => set('ventana_ya_cargado_dias', e.target.value === '' ? 0 : Number(e.target.value))} />
          <Err campo="ventana_ya_cargado_dias" />
        </section>
      </div>

      <div className="flex justify-end mt-5">
        <button type="button" onClick={guardar} disabled={guardando} className="dax-btn-primary disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar reglas de carga</>}
        </button>
      </div>
    </DaxCard>
  )
}
