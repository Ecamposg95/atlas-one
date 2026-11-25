import { useCallback, useEffect, useState } from 'react'
import { Modal } from '../../components/ui/Modal'
import { customersApi, type Seguimiento } from '../../api/customers'
import { SeguimientoLista } from './SeguimientoLista'

/** Todo lo que el equipo tiene pendiente con clientes, lo más urgente arriba. */
export function SeguimientoModal({ onClose, onCambio }: { onClose: () => void; onCambio?: () => void }) {
  const [items, setItems] = useState<Seguimiento[] | null>(null)
  const cargar = useCallback(() => {
    customersApi.seguimiento({ estado: 'PENDIENTE' }).then((r) => setItems(r.items)).catch(() => setItems([]))
  }, [])
  useEffect(() => { cargar() }, [cargar])
  return (
    <Modal open onClose={onClose} title="Seguimiento de clientes" size="lg"
      footer={<button type="button" className="dax-btn-primary" onClick={onClose}>Cerrar</button>}>
      {items === null
        ? <p className="text-sm text-dax-muted">Cargando…</p>
        : <SeguimientoLista items={items} conCliente onCambio={() => { cargar(); onCambio?.() }} />}
      <p className="text-xs text-dax-muted mt-3">Para agendar uno nuevo, abre al cliente y usa «Seguimiento» en su ficha.</p>
    </Modal>
  )
}
