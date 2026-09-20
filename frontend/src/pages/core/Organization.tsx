import { useEffect, useState, useRef } from 'react'
import { organizationApi, type Organization, type Branch, type BranchCreate, type ExchangeRateInfo } from '../../api/organization'
import { DaxCard } from '../../components/ui/DaxCard'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { toast } from '../../store/toastStore'
import { confirm as confirmDialog } from '../../components/ui/ConfirmDialog'
import client from '../../api/client'
import { errorDetailText } from '../../utils/errorDetail'

const BRANCH_TYPES: Branch['branch_type'][] = ['HQ', 'STORE', 'WAREHOUSE', 'OFFICE']
const branchTypeLabel = (t: string) =>
  ({ HQ: 'Casa Matriz', STORE: 'Sucursal', WAREHOUSE: 'Almacén', OFFICE: 'Oficina' }[t] ?? t)

interface BranchForm { name: string; branch_type: Branch['branch_type']; address: string; phone: string }
const EMPTY_BRANCH: BranchForm = { name: '', branch_type: 'STORE', address: '', phone: '' }

export function Organization() {
  const [tab, setTab] = useState<'org' | 'branches'>('org')
  const [org, setOrg] = useState<Organization | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [orgForm, setOrgForm] = useState<Partial<Organization>>({})
  const [branchModal, setBranchModal] = useState<'create' | 'edit' | null>(null)
  const [editingBranch, setEditingBranch] = useState<Branch | null>(null)
  const [branchForm, setBranchForm] = useState<BranchForm>(EMPTY_BRANCH)
  const [branchSaving, setBranchSaving] = useState(false)
  const [logoUploading, setLogoUploading] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const [fxInfo, setFxInfo] = useState<ExchangeRateInfo | null>(null)
  const [fxRefreshing, setFxRefreshing] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      organizationApi.getOrg().then((o) => { setOrg(o); setOrgForm(o) }),
      organizationApi.getBranches().then(setBranches),
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
      const updated = await organizationApi.updateOrg({
        ...orgForm,
        usd_rate_margin: margen === '' || margen == null ? 0 : margen,
        card_surcharge_pct: comision === '' || comision == null ? 0 : comision,
      })
      setOrg(updated); setOrgForm(updated)
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

  const openCreateBranch = () => { setBranchForm(EMPTY_BRANCH); setEditingBranch(null); setBranchModal('create') }
  const openEditBranch = (b: Branch) => {
    setBranchForm({ name: b.name, branch_type: b.branch_type, address: b.address ?? '', phone: b.phone ?? '' })
    setEditingBranch(b); setBranchModal('edit')
  }

  const saveBranch = async () => {
    setBranchSaving(true)
    try {
      const payload: BranchCreate = { name: branchForm.name, branch_type: branchForm.branch_type, address: branchForm.address || undefined, phone: branchForm.phone || undefined }
      if (branchModal === 'create') await organizationApi.createBranch(payload)
      else if (editingBranch) await organizationApi.updateBranch(editingBranch.id, payload)
      setBranchModal(null)
      organizationApi.getBranches().then(setBranches).catch(() => {})
    } catch { toast.error('Error al guardar la sucursal') } finally { setBranchSaving(false) }
  }

  const deleteBranch = async (branch: Branch) => {
    const ok = await confirmDialog({
      title: 'Eliminar sucursal',
      message: `¿Eliminar la sucursal "${branch.name}"?`,
      variant: 'danger',
      confirmText: 'Eliminar',
    })
    if (!ok) return
    try {
      await organizationApi.deleteBranch(branch.id)
      setBranches((prev) => prev.filter((b) => b.id !== branch.id))
    } catch { toast.error('Error al eliminar la sucursal') }
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

  const of = (field: keyof Organization, val: string) => setOrgForm((prev) => ({ ...prev, [field]: val || null }))
  const bf = (field: keyof BranchForm, val: string) => setBranchForm((prev) => ({ ...prev, [field]: val }))

  if (loading) return <Spinner text="Cargando organización..." />

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <i className="fa-solid fa-building text-indigo-400 text-xl" />
        <h1 className="text-2xl font-black text-white">Empresa y Sucursales</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-800/50 p-1 rounded-lg w-fit">
        {(['org', 'branches'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${tab === t ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'}`}>
            {t === 'org' ? 'Datos de Empresa' : `Sucursales (${branches.length})`}
          </button>
        ))}
      </div>

      {tab === 'org' && org && (
        <div className="space-y-4">
          <DaxCard>
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
              <button onClick={saveOrg} disabled={saving} className="dax-btn-primary disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar cambios</>}
              </button>
            </div>
          </DaxCard>

          {/* Logo de la empresa */}
          <DaxCard>
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
          </DaxCard>

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
                <button onClick={saveOrg} disabled={saving} className="dax-btn-primary text-xs disabled:opacity-40">
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
              <button onClick={saveOrg} disabled={saving} className="dax-btn-primary text-xs disabled:opacity-40">
                {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </DaxCard>

          {/* Encabezado y pie de ticket */}
          <DaxCard>
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
              <div>
                <label className="dax-label">Términos y condiciones</label>
                <textarea
                  value={orgForm.ticket_terms ?? ''}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_terms: e.target.value || null }))}
                  rows={5}
                  maxLength={600}
                  className="dax-input w-full resize-none font-mono text-xs"
                  placeholder={'Cambios dentro de los 15 días presentando este ticket.\nNo se aceptan cambios en ropa interior ni liquidación.'}
                />
                <p className="text-[10px] mt-1 text-slate-600">Se imprimen al final del ticket. Cambios, garantías, política de devolución…</p>
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
              <div className="flex items-start gap-3 pt-1">
                <input
                  type="checkbox" id="ticket-vendor-chk" className="w-4 h-4 mt-0.5"
                  checked={orgForm.ticket_show_vendor ?? true}
                  onChange={e => setOrgForm(p => ({ ...p, ticket_show_vendor: e.target.checked }))}
                />
                <label htmlFor="ticket-vendor-chk" className="text-xs text-slate-300 cursor-pointer">
                  Mostrar «Sistema: Atlas One | Atlas Tech» al pie
                  <span className="block text-[10px] text-slate-600">Dos líneas al final del ticket con el proveedor del sistema.</span>
                </label>
              </div>
              <div className="flex justify-end">
                <button onClick={saveOrg} disabled={saving} className="dax-btn-primary disabled:opacity-40">
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar ticket</>}
                </button>
              </div>
            </div>
          </DaxCard>
        </div>
      )}

      {tab === 'branches' && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <button onClick={openCreateBranch} className="dax-btn-primary text-xs">
              <i className="fa-solid fa-plus" /> Nueva Sucursal
            </button>
          </div>
          <DaxCard padding={false}>
            {branches.length === 0 ? (
              <div className="p-12 text-center text-slate-600">Sin sucursales</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="dax-table w-full">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Tipo</th>
                      <th>Teléfono</th>
                      <th>Dirección</th>
                      <th>Estado</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {branches.map((b) => (
                      <tr key={b.id}>
                        <td className="font-semibold text-white">{b.name}</td>
                        <td><Badge variant={b.branch_type === 'HQ' ? 'yellow' : 'blue'}>{branchTypeLabel(b.branch_type)}</Badge></td>
                        <td className="text-slate-400 text-sm">{b.phone ?? '—'}</td>
                        <td className="text-slate-400 text-sm max-w-[200px] truncate">{b.address ?? '—'}</td>
                        <td>
                          <Badge variant={b.is_active ? 'green' : 'slate'}>
                            {b.is_active ? 'Activa' : 'Inactiva'}
                          </Badge>
                        </td>
                        <td className="flex gap-1">
                          <button onClick={() => openEditBranch(b)} className="dax-btn-icon text-slate-500 hover:text-white text-xs">
                            <i className="fa-solid fa-pen" />
                          </button>
                          {!b.is_headquarters && (
                            <button onClick={() => deleteBranch(b)} className="dax-btn-icon text-slate-600 hover:text-red-400 text-xs ml-1">
                              <i className="fa-solid fa-trash" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DaxCard>
        </div>
      )}

      {/* Modal sucursal */}
      {branchModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={() => setBranchModal(null)}>
          <div className="dax-card p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-black text-white">{branchModal === 'create' ? 'Nueva Sucursal' : 'Editar Sucursal'}</h3>
              <button onClick={() => setBranchModal(null)} className="dax-btn-icon text-slate-500 hover:text-white"><i className="fa-solid fa-xmark text-lg" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="dax-label">Nombre</label>
                <input value={branchForm.name} onChange={(e) => bf('name', e.target.value)} className="dax-input w-full" placeholder="Sucursal Centro" />
              </div>
              <div>
                <label className="dax-label">Tipo</label>
                <select value={branchForm.branch_type} onChange={(e) => bf('branch_type', e.target.value)} className="dax-input w-full">
                  {BRANCH_TYPES.map((t) => <option key={t} value={t}>{branchTypeLabel(t)}</option>)}
                </select>
              </div>
              <div>
                <label className="dax-label">Teléfono</label>
                <input value={branchForm.phone} onChange={(e) => bf('phone', e.target.value)} className="dax-input w-full" />
              </div>
              <div>
                <label className="dax-label">Dirección</label>
                <input value={branchForm.address} onChange={(e) => bf('address', e.target.value)} className="dax-input w-full" />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setBranchModal(null)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button onClick={saveBranch} disabled={branchSaving || !branchForm.name} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {branchSaving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
