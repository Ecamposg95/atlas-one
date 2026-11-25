import { useState } from 'react'
import { Modal } from '../../ui/Modal'
import { valesApi, type Vale } from '../../../api/vales'
import { formatCurrency } from '../../../utils/currency'
import { errorDetailText } from '../../../utils/errorDetail'

interface Props {
  onClose: () => void
  /** Carga el vale en la venta en curso. */
  onUsar: (vale: { code: string; balance: number }) => void
}

/** La caja teclea o escanea el código del vale, ve su saldo y lo usa en la venta. */
export function ValeModal({ onClose, onUsar }: Props) {
  const [codigo, setCodigo] = useState('')
  const [vale, setVale] = useState<Vale | null>(null)
  const [buscando, setBuscando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const buscar = async () => {
    if (!codigo.trim() || buscando) return
    setBuscando(true)
    setError(null)
    setVale(null)
    try {
      setVale(await valesApi.consultar(codigo))
    } catch (err: any) {
      setError(errorDetailText(err?.response?.data?.detail, 'No se pudo consultar el vale.'))
    } finally { setBuscando(false) }
  }

  const saldo = Number(vale?.balance ?? 0)
  const usable = vale?.status === 'ACTIVO' && saldo > 0

  return (
    <Modal
      open onClose={onClose} title="Vale de tienda" size="sm"
      footer={<>
        <button type="button" className="dax-btn-secondary" onClick={onClose}>Cerrar</button>
        <button
          type="button" className="dax-btn-primary disabled:opacity-50" disabled={!usable}
          onClick={() => { if (vale && usable) { onUsar({ code: vale.code, balance: saldo }); onClose() } }}
        >
          Usar en esta venta
        </button>
      </>}
    >
      <label htmlFor="vale-codigo" className="block text-xs font-semibold mb-1 text-dax-muted">Código del vale</label>
      <div className="flex gap-2 mb-3">
        <input
          id="vale-codigo" autoFocus autoComplete="off" value={codigo}
          onChange={(e) => setCodigo(e.target.value.toUpperCase())}
          onKeyDown={(e) => { if (e.key === 'Enter') buscar() }}
          className="dax-input flex-1 font-mono tracking-widest" placeholder="ABCD2345"
        />
        <button type="button" className="dax-btn-secondary disabled:opacity-50" onClick={buscar} disabled={buscando || !codigo.trim()}>
          {buscando ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : 'Consultar'}
        </button>
      </div>
      {error && <p className="text-sm text-dax-danger" role="alert">{error}</p>}
      {vale && (
        <div className="rounded-xl p-3 text-sm bg-dax-elevated border border-dax-border-dim" data-testid="vale-encontrado">
          <div className="flex justify-between text-dax-muted">
            <span>Vale</span><span className="font-mono">{vale.code}</span>
          </div>
          <div className="flex justify-between font-bold text-dax-text">
            <span>Saldo</span><span>{formatCurrency(saldo)}</span>
          </div>
          {vale.customer_name && <p className="text-xs mt-1 text-dax-muted">A nombre de {vale.customer_name}</p>}
          {!usable && (
            <p className="text-xs mt-2 text-dax-danger">
              {vale.status === 'CANCELADO' ? 'Este vale está cancelado.' : 'Este vale ya no tiene saldo.'}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}
