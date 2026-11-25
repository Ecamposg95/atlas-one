import { useEffect, useState } from 'react'
import { Modal } from '../../components/ui/Modal'
import { customersApi, MAX_CAMPOS_PROPIOS, type CampoPropio, type TipoCampo } from '../../api/customers'
import { toast } from '../../store/toastStore'
import { apiErrorMessage } from './crmUtil'

const TIPOS: { clave: TipoCampo; label: string }[] = [
  { clave: 'TEXTO', label: 'Texto' },
  { clave: 'NUMERO', label: 'Número' },
  { clave: 'FECHA', label: 'Fecha' },
  { clave: 'LISTA', label: 'Lista de opciones' },
  { clave: 'SI_NO', label: 'Sí / No' },
]

/** Administrador y dueño definen qué más quiere saber la tienda de sus clientes. */
export function CamposPropiosModal({ onClose }: { onClose: () => void }) {
  const [campos, setCampos] = useState<CampoPropio[]>([])
  const [label, setLabel] = useState('')
  const [tipo, setTipo] = useState<TipoCampo>('TEXTO')
  const [opciones, setOpciones] = useState('')
  const [ocupado, setOcupado] = useState(false)

  const cargar = () => customersApi.campos().then(setCampos).catch(() => {})
  useEffect(() => { cargar() }, [])

  const lleno = campos.length >= MAX_CAMPOS_PROPIOS

  const agregar = async () => {
    if (!label.trim() || ocupado || lleno) return
    setOcupado(true)
    try {
      await customersApi.crearCampo({
        label: label.trim(), tipo,
        opciones: tipo === 'LISTA' ? opciones.split(',').map((o) => o.trim()).filter(Boolean) : undefined,
      })
      setLabel(''); setOpciones('')
      await cargar()
    } catch (e) {
      toast.error(apiErrorMessage(e, 'No se pudo agregar el campo'))
    } finally { setOcupado(false) }
  }

  const quitar = async (c: CampoPropio) => {
    setOcupado(true)
    try {
      await customersApi.quitarCampo(c.id)
      await cargar()
    } catch (e) {
      toast.error(apiErrorMessage(e, 'No se pudo quitar el campo'))
    } finally { setOcupado(false) }
  }

  return (
    <Modal open onClose={onClose} title="Campos propios de clientes" size="md"
      footer={<button type="button" className="dax-btn-primary" onClick={onClose}>Listo</button>}>
      <p className="text-sm text-dax-muted mb-3">
        Lo que tu tienda quiere saber de cada cliente (talla, ruta, zona…). Hasta {MAX_CAMPOS_PROPIOS}; llevas {campos.length}.
      </p>
      <ul className="space-y-1.5 mb-4">
        {campos.map((c) => (
          <li key={c.id} className="flex items-center gap-2 rounded-lg p-2 bg-dax-elevated border border-dax-border-dim text-sm">
            <span className="flex-1 min-w-0 text-dax-text">
              {c.label} <span className="text-xs text-dax-muted">· {TIPOS.find((t) => t.clave === c.tipo)?.label ?? c.tipo}{c.opciones?.length ? `: ${c.opciones.join(', ')}` : ''}</span>
            </span>
            <button type="button" className="dax-btn-icon text-dax-danger" disabled={ocupado} onClick={() => quitar(c)} aria-label={`Quitar ${c.label}`}>
              <i className="fa-solid fa-trash" aria-hidden="true" />
            </button>
          </li>
        ))}
        {campos.length === 0 && <li className="text-sm text-dax-muted">Todavía no hay campos propios.</li>}
      </ul>
      {lleno ? (
        <p className="text-sm text-dax-warning">Llegaste al tope de {MAX_CAMPOS_PROPIOS} campos. Quita uno para agregar otro.</p>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input aria-label="Nombre del campo" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60}
              placeholder="Nombre del campo" className="dax-input text-sm" />
            <select aria-label="Tipo de campo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoCampo)} className="dax-input text-sm">
              {TIPOS.map((t) => <option key={t.clave} value={t.clave}>{t.label}</option>)}
            </select>
          </div>
          {tipo === 'LISTA' && (
            <input aria-label="Opciones" value={opciones} onChange={(e) => setOpciones(e.target.value)}
              placeholder="Opciones separadas por coma: CH, M, G" className="dax-input text-sm w-full" />
          )}
          <button type="button" onClick={agregar} disabled={ocupado || !label.trim() || (tipo === 'LISTA' && !opciones.trim())}
            className="dax-btn-secondary text-sm disabled:opacity-50">
            <i className="fa-solid fa-plus" aria-hidden="true" /> Agregar campo
          </button>
        </div>
      )}
    </Modal>
  )
}
