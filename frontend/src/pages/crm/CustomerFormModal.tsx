import { useEffect, useState } from 'react'
import { Modal } from '../../components/ui/Modal'
import { customersApi, type CampoPropio, type Customer, type CustomerPayload } from '../../api/customers'

interface Props {
  customer: Customer | null // null = alta
  onClose: () => void
  onSaved: (c: Customer) => void
  /** Cajera y vendedor: alta rápida (nombre, teléfono, correo y nota). Lo demás lo edita la gerencia. */
  deCaja?: boolean
}

export function CustomerFormModal({ customer, onClose, onSaved, deCaja = false }: Props) {
  const isEdit = customer !== null
  const [form, setForm] = useState<CustomerPayload>({
    name: customer?.name ?? '',
    phone: customer?.phone ?? '',
    email: customer?.email ?? '',
    tax_id: customer?.tax_id ?? '',
    address: customer?.address ?? '',
    zip_code: customer?.zip_code ?? '',
    notes: customer?.notes ?? '',
    has_credit: customer?.has_credit ?? false,
    credit_limit: customer?.credit_limit ?? 0,
    credit_days: customer?.credit_days ?? 0,
    tipo: customer?.tipo ?? 'MENUDEO',
    birthday: customer?.birthday ?? '',
    company: customer?.company ?? '',
  })
  // Campos propios de la tienda y sus valores para este cliente.
  const [defs, setDefs] = useState<CampoPropio[]>([])
  const [propios, setPropios] = useState<Record<string, unknown>>({ ...(customer?.campos ?? {}) })
  useEffect(() => {
    if (deCaja) return
    customersApi.campos().then(setDefs).catch(() => {})
  }, [deCaja])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (k: keyof CustomerPayload, v: unknown) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.name.trim()) { setError('El nombre es obligatorio'); return }
    setSaving(true); setError(null)
    // Strings vacíos → null para no chocar con validaciones de unicidad/EmailStr
    const payload: CustomerPayload = deCaja
      // La caja solo manda lo que el servidor le acepta (403 con lo demás).
      ? { name: form.name.trim(), phone: form.phone || null, email: form.email || null, notes: form.notes || null }
      : {
          ...form,
          name: form.name.trim(),
          phone: form.phone || null,
          email: form.email || null,
          tax_id: form.tax_id || null,
          address: form.address || null,
          zip_code: form.zip_code || null,
          notes: form.notes || null,
          birthday: form.birthday || null,
          company: form.company || null,
          campos: Object.fromEntries(defs.map((d) => [d.key, propios[d.key] ?? null])),
        }
    try {
      const saved = isEdit
        ? await customersApi.update(customer.id, payload)
        : await customersApi.create(payload)
      onSaved(saved)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Error al guardar el cliente')
    } finally { setSaving(false) }
  }

  const field = (label: string, key: keyof CustomerPayload, type = 'text', placeholder = '') => (
    <div>
      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">{label}</label>
      <input type={type} value={String(form[key] ?? '')} placeholder={placeholder}
        onChange={(e) => set(key, e.target.value)} className="dax-input w-full text-sm" />
    </div>
  )

  return (
    <Modal open onClose={onClose} size="lg" closeOnEscape={false} closeOnBackdrop={false}
      title={<><i className={`fa-solid ${isEdit ? 'fa-pen' : 'fa-user-plus'} mr-2 text-indigo-400`} />{isEdit ? 'Editar cliente' : 'Nuevo cliente'}</>}
      footer={<>
        <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
        <button onClick={submit} disabled={saving || !form.name.trim()}
          className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
        </button>
      </>}>
      <div className="space-y-3">
        {field('Nombre *', 'name', 'text', 'Nombre o razón social')}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {field('Teléfono', 'phone', 'tel', '10 dígitos')}
          {field('Email', 'email', 'email')}
        </div>
        {field('Notas', 'notes')}
        {deCaja && (
          <p className="text-xs text-dax-muted">
            <i className="fa-solid fa-circle-info mr-1" aria-hidden="true" />
            Alta rápida. El crédito, los datos fiscales y el resto de la ficha los completa el gerente.
          </p>
        )}
        {!deCaja && <>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label htmlFor="cliente-tipo" className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Tipo de cliente</label>
            <select id="cliente-tipo" value={form.tipo ?? 'MENUDEO'} onChange={(e) => set('tipo', e.target.value)} className="dax-input w-full text-sm">
              <option value="MENUDEO">Menudeo</option>
              <option value="MAYOREO">Mayoreo</option>
            </select>
          </div>
          {field('Cumpleaños', 'birthday', 'date')}
          {field('Negocio', 'company', 'text', 'Nombre de su negocio')}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {field('RFC', 'tax_id', 'text', 'XAXX010101000')}
          {field('C.P.', 'zip_code')}
        </div>
        {field('Dirección', 'address')}

        {defs.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="campos-propios">
            {defs.map((d) => (
              <div key={d.key}>
                <label htmlFor={`campo-${d.key}`} className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">{d.label}</label>
                {d.tipo === 'LISTA' ? (
                  <select id={`campo-${d.key}`} value={String(propios[d.key] ?? '')} className="dax-input w-full text-sm"
                    onChange={(e) => setPropios((p) => ({ ...p, [d.key]: e.target.value || null }))}>
                    <option value="">—</option>
                    {(d.opciones ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : d.tipo === 'SI_NO' ? (
                  <label className="flex items-center gap-2 text-sm text-slate-300 min-h-[38px]">
                    <input id={`campo-${d.key}`} type="checkbox" checked={!!propios[d.key]}
                      onChange={(e) => setPropios((p) => ({ ...p, [d.key]: e.target.checked }))} />
                    Sí
                  </label>
                ) : (
                  <input id={`campo-${d.key}`} className="dax-input w-full text-sm"
                    type={d.tipo === 'NUMERO' ? 'number' : d.tipo === 'FECHA' ? 'date' : 'text'}
                    value={String(propios[d.key] ?? '')}
                    onChange={(e) => setPropios((p) => ({ ...p, [d.key]: e.target.value || null }))} />
                )}
              </div>
            ))}
          </div>
        )}

        <div className="dax-card p-3 space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={!!form.has_credit}
              onChange={(e) => set('has_credit', e.target.checked)} />
            Venta a crédito habilitada
          </label>
          {form.has_credit && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Límite de crédito</label>
                <input type="number" step="0.01" min="0" value={form.credit_limit ?? 0}
                  onChange={(e) => set('credit_limit', parseFloat(e.target.value) || 0)}
                  className="dax-input w-full text-sm" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Días de crédito</label>
                <input type="number" min="0" value={form.credit_days ?? 0}
                  onChange={(e) => set('credit_days', parseInt(e.target.value) || 0)}
                  className="dax-input w-full text-sm" />
              </div>
            </div>
          )}
        </div>
        </>}

        {error && (
          <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/30 rounded px-3 py-2">
            <i className="fa-solid fa-circle-exclamation mr-1" /> {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
