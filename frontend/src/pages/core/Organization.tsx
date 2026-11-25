import { useEffect, useState, useRef } from 'react'
import { organizationApi, type Organization, type ExchangeRateInfo } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { toast } from '../../store/toastStore'
import client from '../../api/client'
import { errorDetailText } from '../../utils/errorDetail'
import { MasOpciones } from '../../components/ui/MasOpciones'
import { useEnabledModulesStore, useModoBasico } from '../../store/enabledModulesStore'

// Vista previa del renglón del ticket (panel de Empresa).
//
// Los renglones están COPIADOS de la salida real de `app/pos_printer.py`
// (`_product_line` y `_product_lines_detailed`) para una chamarra Louis
// Vuitton mezclilla talla M de $4,000: 56 columnas en papel de 80 mm y 32 en
// el de 58 mm. Ver a la mitad de ancho lo que en papel sale recortado
// ("CHAMARRA MEZCLIL") era justamente no ver el problema.
const VISTA_PREVIA_COMPACTA = [
  '80 mm (56 columnas)',
  '1x  LOUIS VUITTON · CHAMARRA MEZCLIL@4000.00     4000.00',
  '',
  '58 mm (32 columnas)',
  '1x  LOUIS VUITTO@4000.00 4000.00',
].join('\n')
const VISTA_PREVIA_DETALLADA = [
  '80 mm (56 columnas)',
  '1x  LOUIS VUITTON',
  '    Chamarra mezclilla',
  '    Talla M                       @4,000.00     4,000.00',
  '',
  '58 mm (32 columnas)',
  '1x  LOUIS VUITTON',
  '    Chamarra mezclilla',
  '    Talla M   @4,000.00 4,000.00',
].join('\n')

/** Qué parte de los ajustes de la empresa se pinta. Sin `seccion`, todas. */
export type SeccionEmpresa = 'empresa' | 'ventas' | 'ticket'

/**
 * Ajustes de la organización. Vive dentro de `/configuracion` (una pestaña por
 * `seccion`); las sucursales tienen su propia pantalla (`Sucursales.tsx`).
 */
export function Organization({ seccion }: { seccion?: SeccionEmpresa } = {}) {
  const ve = (s: SeccionEmpresa) => !seccion || seccion === s
  const [org, setOrg] = useState<Organization | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [orgForm, setOrgForm] = useState<Partial<Organization>>({})
  const [logoUploading, setLogoUploading] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const [fxInfo, setFxInfo] = useState<ExchangeRateInfo | null>(null)
  const [fxRefreshing, setFxRefreshing] = useState(false)
  // Modo básico: logo, dólares, comisión y lo boutique del ticket van plegados.
  const modoBasico = useModoBasico()

  useEffect(() => {
    setLoading(true)
    Promise.all([
      organizationApi.getOrg().then((o) => { setOrg(o); setOrgForm(o) }),
      organizationApi.getExchangeRate().then(setFxInfo).catch(() => {}),
    ]).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const cargarFx = () => organizationApi.getExchangeRate().then(setFxInfo).catch(() => {})

  const saveOrg = async () => {
    setSaving(true)
    try {
      // Borrar el ajuste sobre el FIX o la comisión deja '' en el input
      // numérico, y el PUT responde 422 ("Input should be a valid decimal"):
      // vacío = sin ajuste / sin comisión.
      const margen = orgForm.usd_rate_margin
      const comision = orgForm.card_surcharge_pct
      // Igual con los dos ajustes de caja: vacío = el valor por omisión.
      const dias = orgForm.dias_ventas_caja
      const libre = orgForm.devolucion_libre_hasta
      // `perfil_ui` lo cambia solo la plataforma: no viaja en el PUT de tenant.
      const { perfil_ui: _perfil, ...datos } = orgForm
      const updated = await organizationApi.updateOrg({
        ...datos,
        usd_rate_margin: margen === '' || margen == null ? 0 : margen,
        card_surcharge_pct: comision === '' || comision == null ? 0 : comision,
        dias_ventas_caja: dias === '' || dias == null ? 30 : Math.max(0, Math.floor(Number(dias))),
        devolucion_libre_hasta: libre === '' || libre == null ? 0 : libre,
      })
      setOrg(updated); setOrgForm(updated)
      // El conteo ciego viaja en /me/context: se relee para que esta sesión lo tome ya.
      void useEnabledModulesStore.getState().load()
      await cargarFx()
    } catch (e: any) {
      // El 422 del PUT trae el motivo en español ("En modo manual hay que
      // capturar un tipo de cambio mayor que cero.").
      toast.error(errorDetailText(e?.response?.data?.detail, 'Error al guardar la organización'))
    } finally { setSaving(false) }
  }

  const refreshFx = async () => {
    setFxRefreshing(true)
    try {
      await organizationApi.refreshExchangeRate()
      await cargarFx()
      toast.success('Tipo de cambio actualizado')
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo bajar el tipo de cambio de Banxico'))
    } finally { setFxRefreshing(false) }
  }

  const uploadOrgLogo = async (file: File) => {
    setLogoError(null)
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setLogoError('Solo PNG, JPEG o WEBP')
      return
    }
    if (file.size > 1024 * 1024) {
      setLogoError('La imagen no debe superar 1 MB')
      return
    }
    setLogoUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await client.post('/organization/logo', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      setOrg(prev => prev ? { ...prev, logo_url: data.logo_url } : prev)
      setOrgForm(prev => ({ ...prev, logo_url: data.logo_url }))
    } catch { setLogoError('Error al subir logo') }
    finally { setLogoUploading(false) }
  }

  const deleteOrgLogo = async () => {
    try {
      await client.delete('/organization/logo')
      setOrg(prev => prev ? { ...prev, logo_url: null } : prev)
      setOrgForm(prev => ({ ...prev, logo_url: null }))
    } catch { /* ignore */ }
  }

  // `name` no se coacciona a null: un borrado momentáneo del campo (patrón
  // normal al retipear) no debe poder guardarse como razón social NULL — el
  // botón "Guardar" se deshabilita en su lugar (ver `nameInvalido`).
  const of = (field: keyof Organization, val: string) =>
    setOrgForm((prev) => ({ ...prev, [field]: field === 'name' ? val : (val || null) }))
  const nameInvalido = !orgForm.name?.trim()

  if (loading) return <Spinner text="Cargando organización..." />

  return (
    <div className="space-y-5">
      {org && (
        <div className="space-y-4">
          {ve('empresa') && <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">Información de la Empresa</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="dax-label">Razón social</label>
                <input value={orgForm.name ?? ''} onChange={(e) => of('name', e.target.value)} className="dax-input w-full" />
              </div>
              <div>
                <label className="dax-label">RFC</label>
                <input value={orgForm.tax_id ?? ''} onChange={(e) => of('tax_id', e.target.value)} className="dax-input w-full font-mono" placeholder="XAXX010101000" />
              </div>
              <div>
                <label className="dax-label">Teléfono</label>
                <input value={orgForm.phone ?? ''} onChange={(e) => of('phone', e.target.value)} className="dax-input w-full" />
              </div>
              <div>
                <label className="dax-label">Email</label>
                <input type="email" value={orgForm.email ?? ''} onChange={(e) => of('email', e.target.value)} className="dax-input w-full" />
              </div>
              <div>
                <label className="dax-label">Sitio web</label>
                <input value={orgForm.website ?? ''} onChange={(e) => of('website', e.target.value)} className="dax-input w-full" placeholder="mitienda.mx" />
                <p className="text-[10px] mt-1 text-slate-600">Se imprime en el ticket como «Web: …».</p>
              </div>
              <div className="sm:col-span-2">
                <label className="dax-label">Dirección</label>
                <input value={orgForm.address ?? ''} onChange={(e) => of('address', e.target.value)} className="dax-input w-full" />
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar cambios</>}
              </button>
            </div>
          </DaxCard>}

          {(ve('empresa') || ve('ventas')) && <MasOpciones activo={modoBasico && seccion !== 'ventas'}>
          {/* Logo de la empresa */}
          {ve('empresa') && <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-image mr-1.5" />Logo de la Empresa
            </p>
            <div className="flex items-start gap-4">
              {org.logo_url ? (
                <div className="flex flex-col items-center gap-2">
                  <img
                    src={org.logo_url}
                    alt="Logo"
                    className="h-20 w-20 object-contain rounded-xl border border-slate-700 bg-slate-800 p-1"
                  />
                  <button
                    onClick={deleteOrgLogo}
                    className="text-[10px] text-red-400 hover:text-red-300 flex items-center gap-1"
                  >
                    <i className="fa-solid fa-trash" /> Eliminar
                  </button>
                </div>
              ) : (
                <div className="h-20 w-20 rounded-xl border border-dashed border-slate-600 bg-slate-800/50 flex items-center justify-center flex-shrink-0">
                  <i className="fa-solid fa-image text-2xl text-slate-600" />
                </div>
              )}
              <div className="flex-1">
                <p className="text-xs text-slate-400 mb-2">
                  Se imprime en la parte superior del ticket. Formatos: PNG, JPEG, WEBP. Máx 1 MB.
                </p>
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) uploadOrgLogo(f) }}
                />
                <button
                  onClick={() => logoInputRef.current?.click()}
                  disabled={logoUploading}
                  className="dax-btn-secondary text-xs disabled:opacity-40"
                >
                  {logoUploading ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-upload" /> {org.logo_url ? 'Cambiar logo' : 'Subir logo'}</>}
                </button>
                {logoError && <p className="text-xs text-red-400 mt-1">{logoError}</p>}
              </div>
            </div>
          </DaxCard>}

          {ve('ventas') && <>
          {/* Tipo de cambio USD */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-dollar-sign mr-1.5" />Tipo de cambio USD
            </p>
            <p className="text-xs text-slate-400 mb-4">
              Muestra el equivalente en dólares en el punto de venta y en el ticket.
              El cobro sigue siendo en pesos. Con <b>Apagado</b> no se muestra nada.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="dax-label">Modo</label>
                <select
                  value={orgForm.usd_rate_mode ?? 'off'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_mode: e.target.value as Organization['usd_rate_mode'] }))}
                  className="dax-input w-full"
                >
                  <option value="off">Apagado</option>
                  <option value="auto">Automático (FIX de Banxico + ajuste)</option>
                  <option value="manual">Manual (tipo fijo)</option>
                </select>
              </div>
              <div>
                <label className="dax-label">Ajuste sobre el FIX</label>
                <input
                  type="number" step="0.01"
                  value={orgForm.usd_rate_margin ?? '0'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_margin: e.target.value }))}
                  disabled={(orgForm.usd_rate_mode ?? 'off') !== 'auto'}
                  className="dax-input w-full tabular-nums disabled:opacity-40"
                  placeholder="0.30"
                />
                <p className="text-[10px] mt-1 text-slate-600">Pesos que se suman al FIX. Puede ser negativo.</p>
              </div>
              <div>
                <label className="dax-label">Tipo de cambio manual</label>
                <input
                  type="number" step="0.0001"
                  value={orgForm.usd_rate_manual ?? ''}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_manual: e.target.value || null }))}
                  disabled={(orgForm.usd_rate_mode ?? 'off') !== 'manual'}
                  className="dax-input w-full tabular-nums disabled:opacity-40"
                  placeholder="19.5000"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
              <div className="text-xs text-slate-400">
                {fxInfo?.fix_rate != null ? (
                  <>FIX del {fxInfo.fix_date ?? '—'}: <b className="tabular-nums text-slate-200">{Number(fxInfo.fix_rate).toFixed(4)}</b></>
                ) : (
                  <>Sin FIX descargado todavía.</>
                )}
                {fxInfo?.rate != null && (
                  <> · Vigente: <b className="tabular-nums text-emerald-400">{Number(fxInfo.rate).toFixed(4)}</b></>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={refreshFx} disabled={fxRefreshing} className="dax-btn-secondary text-xs disabled:opacity-40">
                  {fxRefreshing ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-rotate" /> Actualizar ahora</>}
                </button>
                <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary text-xs disabled:opacity-40">
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
                </button>
              </div>
            </div>
          </DaxCard>

          {/* Comisión por pago con tarjeta */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-credit-card mr-1.5" />Comisión por pago con tarjeta
            </p>
            <p className="text-xs text-slate-400 mb-4">
              Se suma únicamente a la parte de la venta que se cobra con tarjeta; en un
              pago mixto, solo a esa parte. Aparece en el punto de venta, en el ticket,
              en el corte de caja y en los reportes, <b>separada del total de la
              mercancía</b>. <b>0 = sin comisión.</b>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="dax-label">Porcentaje (%)</label>
                <input
                  type="number" step="0.01" min="0" max="20"
                  value={orgForm.card_surcharge_pct ?? '0'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, card_surcharge_pct: e.target.value }))}
                  className="dax-input w-full tabular-nums"
                  placeholder="3.5"
                />
                <p className="text-[10px] mt-1 text-slate-600">0 = sin comisión. Máximo 20 %.</p>
              </div>
              <div className="sm:col-span-2 flex items-end">
                <p className="text-xs text-slate-400">
                  {Number(orgForm.card_surcharge_pct ?? 0) > 0 ? (
                    <>Una venta de <b className="tabular-nums text-slate-200">$1,000.00</b> pagada
                    con tarjeta se cobrará como <b className="tabular-nums text-emerald-400">
                    {(1000 * (1 + Number(orgForm.card_surcharge_pct) / 100)).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' })}</b>.</>
                  ) : (
                    <>La comisión está apagada: el punto de venta y el ticket no muestran nada.</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>

          {/* Ventas pasadas y devoluciones de la caja */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-rotate-left mr-1.5" />Ventas y devoluciones en caja
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="dias-ventas-caja" className="block text-xs text-slate-300 mb-1">Plazo de devolución (días)</label>
                <input
                  id="dias-ventas-caja" type="number" min={0} max={3650} step={1} inputMode="numeric"
                  className="dax-input w-32 text-xs"
                  value={orgForm.dias_ventas_caja ?? 30}
                  onChange={(e) => setOrgForm((p) => ({ ...p, dias_ventas_caja: e.target.value }))}
                />
                <span className="block text-[10px] text-slate-600 mt-1">
                  Quien cobra consulta, reimprime y devuelve las ventas de su sucursal de estos días hacia atrás,
                  sin ver totales. Con 0 solo ve las de hoy. Las más viejas las resuelve el gerente.
                </span>
              </div>
              <div>
                <label htmlFor="devolucion-libre" className="block text-xs text-slate-300 mb-1">Devuelve sin autorización hasta ($)</label>
                <input
                  id="devolucion-libre" type="number" min={0} step="0.01" inputMode="decimal"
                  className="dax-input w-32 text-xs"
                  value={orgForm.devolucion_libre_hasta ?? 0}
                  onChange={(e) => setOrgForm((p) => ({ ...p, devolucion_libre_hasta: e.target.value }))}
                />
                <span className="block text-[10px] text-slate-600 mt-1">
                  Hasta este monto la caja devuelve sola. Arriba de eso un gerente autoriza con su PIN
                  en la misma caja. Con 0 toda devolución pide gerente.
                </span>
              </div>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>

          {/* Conteo ciego del corte de caja */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-eye-slash mr-1.5" />Corte de caja
            </p>
            <div className="flex items-start gap-3">
              <input
                type="checkbox" id="conteo-ciego-chk" className="w-4 h-4 mt-0.5"
                checked={orgForm.conteo_ciego ?? true}
                onChange={e => setOrgForm(p => ({ ...p, conteo_ciego: e.target.checked }))}
              />
              <label htmlFor="conteo-ciego-chk" className="text-xs text-slate-300 cursor-pointer">
                Conteo ciego
                <span className="block text-[10px] text-slate-600">
                  Con el turno abierto, quien cobra no ve el efectivo esperado ni su desglose:
                  cuenta la caja y la diferencia aparece al cerrar. Apagado, lo ve antes de contar.
                </span>
              </label>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>

          {/* Precio por sucursal */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-tag mr-1.5" />Precios
            </p>
            <div className="flex items-start gap-3">
              <input
                type="checkbox" id="precio-sucursal-chk" className="w-4 h-4 mt-0.5"
                checked={orgForm.precio_por_sucursal ?? false}
                onChange={e => setOrgForm(p => ({ ...p, precio_por_sucursal: e.target.checked }))}
              />
              <label htmlFor="precio-sucursal-chk" className="text-xs text-slate-300 cursor-pointer">
                Cada sucursal con su precio
                <span className="block text-[10px] text-slate-600">
                  El precio que alguien de una sucursal cambia en un producto o una talla solo
                  cambia en su sucursal; las demás conservan el suyo. Administrador y dueño
                  editan el precio base y, en la ficha, el de cada sucursal. Apagado, cualquier
                  cambio de precio aplica a todas.
                </span>
              </label>
            </div>
            <div className="flex justify-end mt-4">
              <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>
          </>}
          </MasOpciones>}

          {/* Encabezado y pie de ticket */}
          {ve('ticket') && <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-receipt mr-1.5" />Encabezado y Pie de Ticket
            </p>
            <div className="space-y-4">
              <div>
                <label className="dax-label">Encabezado del ticket</label>
                <textarea
                  value={orgForm.ticket_header ?? ''}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_header: e.target.value || null }))}
                  rows={4}
                  maxLength={400}
                  className="dax-input w-full resize-none font-mono text-xs"
                  placeholder={"ATLAS POS - Nota de Venta\nHorario: Lun-Sáb 9am-8pm"}
                />
                <p className="text-[10px] mt-1 text-slate-600">Hasta 4 líneas · se muestra antes del nombre de la empresa.</p>
              </div>
              <div>
                <label className="dax-label">Pie de página del ticket</label>
                <textarea
                  value={orgForm.ticket_footer ?? ''}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_footer: e.target.value || null }))}
                  rows={2}
                  maxLength={200}
                  className="dax-input w-full resize-none font-mono text-xs"
                  placeholder={"Gracias por su compra!\nwww.mitienda.mx"}
                />
                <p className="text-[10px] mt-1 text-slate-600">Hasta 2 líneas · se muestra al final del ticket.</p>
              </div>
              <MasOpciones activo={modoBasico} titulo="Más opciones del ticket">
              <div>
                <label className="dax-label">Términos y condiciones</label>
                <textarea
                  value={orgForm.ticket_terms ?? ''}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_terms: e.target.value || null }))}
                  rows={5}
                  maxLength={2000}
                  className="dax-input w-full resize-none font-mono text-xs"
                  placeholder={'• Cambios dentro de los 15 días presentando este ticket.\n• No se aceptan cambios en ropa interior ni liquidación.'}
                />
                <div className="flex items-start justify-between gap-3 mt-1">
                  <p className="text-[10px] text-slate-600">Se imprimen al final del ticket. Cambios, garantías, política de devolución…</p>
                  <p className="text-[10px] text-slate-600 tabular-nums whitespace-nowrap">{(orgForm.ticket_terms ?? '').length}/2000</p>
                </div>
              </div>
              <div>
                <label className="dax-label">Enlace a la política completa</label>
                <input
                  value={orgForm.ticket_terms_url ?? ''}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_terms_url: e.target.value || null }))}
                  className="dax-input w-full"
                  placeholder="elevenboutique.mx/terminos"
                />
                <p className="text-[10px] mt-1 text-slate-600">Se imprime como código QR más la dirección en texto, debajo de los términos.</p>
              </div>
              <div>
                <p className="dax-label mb-2">Redes sociales</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-500"><i className="fa-brands fa-instagram mr-1" />Instagram</label>
                    <input
                      value={orgForm.ticket_instagram ?? ''}
                      onChange={e => setOrgForm(p => ({ ...p, ticket_instagram: e.target.value || null }))}
                      className="dax-input w-full" placeholder="@tu_tienda"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500"><i className="fa-brands fa-facebook mr-1" />Facebook</label>
                    <input
                      value={orgForm.ticket_facebook ?? ''}
                      onChange={e => setOrgForm(p => ({ ...p, ticket_facebook: e.target.value || null }))}
                      className="dax-input w-full" placeholder="Tu Tienda"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500"><i className="fa-brands fa-tiktok mr-1" />TikTok</label>
                    <input
                      value={orgForm.ticket_tiktok ?? ''}
                      onChange={e => setOrgForm(p => ({ ...p, ticket_tiktok: e.target.value || null }))}
                      className="dax-input w-full" placeholder="@tu_tienda"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500"><i className="fa-brands fa-whatsapp mr-1" />WhatsApp</label>
                    <input
                      value={orgForm.ticket_whatsapp ?? ''}
                      onChange={e => setOrgForm(p => ({ ...p, ticket_whatsapp: e.target.value || null }))}
                      className="dax-input w-full" placeholder="55 1234 5678"
                    />
                  </div>
                </div>
                <p className="text-[10px] mt-2 text-slate-600">
                  Cada red se imprime solo si la capturas. El sitio web se toma del campo <b>Sitio web</b> de arriba.
                </p>
              </div>
              <div>
                <label className="dax-label">Estilo de línea del ticket</label>
                <select
                  value={orgForm.ticket_line_style ?? 'compact'}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_line_style: e.target.value as 'compact' | 'detailed' }))}
                  className="dax-input w-full"
                >
                  <option value="compact">Compacto — una línea por prenda</option>
                  <option value="detailed">Detallado — marca, nombre completo y talla</option>
                </select>
                {/* Vista previa en texto: es lo que va a salir impreso, con la
                    misma sangría y el mismo orden que arma `pos_printer`. */}
                <pre className="mt-2 rounded-lg bg-slate-900/70 border border-slate-800 px-3 py-2 text-[11px] leading-relaxed font-mono text-slate-300 overflow-x-auto">
{(orgForm.ticket_line_style ?? 'compact') === 'detailed'
  ? VISTA_PREVIA_DETALLADA
  : VISTA_PREVIA_COMPACTA}
                </pre>
                <p className="text-[10px] mt-1 text-slate-600">
                  El detallado gasta dos renglones más por prenda, pero no recorta la marca ni la talla.
                </p>
              </div>
              <div className="flex items-start gap-3 pt-1">
                <input
                  type="checkbox" id="ticket-vendor-chk" className="w-4 h-4 mt-0.5"
                  checked={orgForm.ticket_show_vendor ?? false}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_show_vendor: e.target.checked }))}
                />
                <label htmlFor="ticket-vendor-chk" className="text-xs text-slate-300 cursor-pointer">
                  Mostrar «Sistema: Atlas One | Atlas Tech» al pie
                  <span className="block text-[10px] text-slate-600">Dos líneas al final del ticket con el proveedor del sistema.</span>
                </label>
              </div>
              </MasOpciones>
              <div className="flex justify-end">
                <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary disabled:opacity-40">
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar ticket</>}
                </button>
              </div>
            </div>
          </DaxCard>}

          {/* Modo básico: tope de "Se está acabando" del Inicio. */}
          {modoBasico && ve('ventas') && (
            <DaxCard>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
                <i className="fa-solid fa-boxes-stacked mr-1.5" />Lo que se está acabando
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
                <div>
                  <label className="dax-label" htmlFor="umbral-poca-existencia">Avisar cuando queden (piezas o menos)</label>
                  <input
                    id="umbral-poca-existencia"
                    type="number" min="0" max="1000" step="1"
                    value={orgForm.umbral_poca_existencia ?? ''}
                    onChange={(e) => setOrgForm((p) => ({ ...p, umbral_poca_existencia: e.target.value === '' ? null : Number(e.target.value) }))}
                    className="dax-input w-full tabular-nums"
                    placeholder="3"
                  />
                  <p className="text-[10px] mt-1 text-slate-600">Vacío = 3. Se ve en Inicio, en «Se está acabando».</p>
                </div>
                <div className="flex justify-end">
                  <button onClick={saveOrg} disabled={saving || nameInvalido} className="dax-btn-primary disabled:opacity-40">
                    {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar aviso</>}
                  </button>
                </div>
              </div>
            </DaxCard>
          )}
        </div>
      )}
    </div>
  )
}
