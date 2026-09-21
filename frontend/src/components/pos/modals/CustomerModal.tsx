import { useEffect, useRef, useState } from 'react'
import { customersApi, type Customer } from '../../../api/customers'
import { usePOSStore } from '../../../store/posStore'
import { errorDetailText } from '../../../utils/errorDetail'

interface Props {
  onClose: () => void
}

/**
 * Asigna el cliente de la venta desde el carrito.
 *
 * Tres caminos, en orden de esfuerzo para el cajero: buscar en el CRM, usar
 * solo el nombre (sin alta, para el cliente de paso) o guardarlo en clientes.
 * El CRM puede estar apagado para la organización: si la búsqueda falla, el
 * modal sigue sirviendo para el nombre libre en vez de quedarse muerto.
 */
export function CustomerModal({ onClose }: Props) {
  const customerId = usePOSStore((s) => s.customerId)
  const customerName = usePOSStore((s) => s.customerName)
  const setCustomer = usePOSStore((s) => s.setCustomer)

  const [texto, setTexto] = useState(customerName ?? '')
  const [resultados, setResultados] = useState<Customer[]>([])
  const [buscando, setBuscando] = useState(false)
  const [sinCrm, setSinCrm] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [modoAlta, setModoAlta] = useState(false)
  const [telefono, setTelefono] = useState('')
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const nombre = texto.trim()
  const hayCliente = customerId != null || !!(customerName ?? '').trim()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Búsqueda con debounce de 300 ms. `vivo` descarta la respuesta de una
  // consulta que quedó atrás (una lenta no puede repintar sobre una nueva) y
  // evita tocar estado tras cerrar. El primer fallo marca `sinCrm` y ya no se
  // vuelve a pegar al CRM: el nombre libre sigue funcionando y reabrir el
  // modal lo reintenta (el componente se desmonta y el estado nace limpio).
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!nombre || sinCrm) { setResultados([]); return }
    let vivo = true
    debounceRef.current = setTimeout(async () => {
      setBuscando(true)
      try {
        const encontrados = await customersApi.search(nombre)
        if (vivo) setResultados(encontrados)
      } catch {
        if (vivo) { setResultados([]); setSinCrm(true) }
      } finally {
        if (vivo) setBuscando(false)
      }
    }, 300)
    return () => {
      vivo = false
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [nombre, sinCrm])

  const elegir = (c: Customer) => {
    setCustomer(c.id, c.name)
    onClose()
  }

  const usarSoloNombre = () => {
    if (!nombre) return
    setCustomer(null, nombre)
    onClose()
  }

  /** Enter: si el CRM ya devolvió algo, gana el primer resultado; si no, el nombre libre. */
  const confirmarConEnter = () => {
    if (resultados.length > 0) elegir(resultados[0])
    else usarSoloNombre()
  }

  const quitarCliente = () => {
    setCustomer(null, null)
    onClose()
  }

  const crear = async () => {
    if (!nombre || guardando) return
    setGuardando(true)
    setError(null)
    try {
      const c = await customersApi.create({ name: nombre, phone: telefono.trim() || undefined })
      setCustomer(c.id, c.name)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(errorDetailText(detail, 'No se pudo guardar el cliente'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="dax-card dax-modal p-6 pb-0 w-full max-w-md"
        role="dialog"
        aria-modal="true"
        aria-label="Cliente de la venta"
      >
        <h3 className="text-lg font-black mb-1" style={{ color: 'var(--dax-text)' }}>
          Cliente de la venta
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--dax-text-muted)' }}>
          Búscalo en clientes, guárdalo o usa solo el nombre.
        </p>

        <div className="relative">
          <input
            type="text"
            value={texto}
            onChange={(e) => { setTexto(e.target.value); setError(null) }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !modoAlta) confirmarConEnter() }}
            className="dax-input"
            placeholder="Nombre o teléfono del cliente"
            autoFocus
          />
          {buscando && (
            <i
              className="fa-solid fa-spinner fa-spin absolute right-3 top-1/2 -translate-y-1/2 text-xs"
              style={{ color: 'var(--dax-text-muted)' }}
            />
          )}
        </div>

        {!modoAlta && nombre && (
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--dax-text-muted)' }}>
            {resultados.length > 0 ? 'Enter: elegir el primero' : 'Enter: usar el nombre'}
          </p>
        )}

        {sinCrm && (
          <p className="text-[11px] mt-1.5" style={{ color: 'var(--dax-text-muted)' }}>
            Sin acceso a clientes; puedes usar solo el nombre
          </p>
        )}

        {resultados.length > 0 && (
          <div
            className="mt-3 max-h-48 overflow-y-auto rounded-xl"
            style={{ border: '1px solid var(--dax-border-dim)' }}
          >
            {resultados.map((c) => (
              <button
                key={c.id}
                onClick={() => elegir(c)}
                className="w-full text-left px-3 py-2.5 min-h-[44px] transition-colors hover:bg-indigo-500/10 focus:bg-indigo-500/10 focus:outline-none"
                style={{ borderBottom: '1px solid var(--dax-row-border)' }}
              >
                <p className="text-sm font-medium" style={{ color: 'var(--dax-text)' }}>{c.name}</p>
                {c.phone && (
                  <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>{c.phone}</p>
                )}
              </button>
            ))}
          </div>
        )}

        {modoAlta && (
          <div className="mt-3">
            <label
              htmlFor="cliente-telefono"
              className="block text-[10px] font-bold uppercase tracking-wider mb-1"
              style={{ color: 'var(--dax-text-muted)' }}
            >
              Teléfono (opcional)
            </label>
            <input
              id="cliente-telefono"
              type="tel"
              value={telefono}
              onChange={(e) => setTelefono(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') crear() }}
              className="dax-input"
              placeholder="Teléfono"
            />
          </div>
        )}

        {error && <p className="text-dax-danger text-xs mt-2">{error}</p>}

        <div className="dax-modal-footer flex flex-wrap gap-2 mt-1 pb-6">
          {hayCliente && (
            <button onClick={quitarCliente} className="dax-btn-secondary text-sm min-h-[44px]">
              Quitar cliente
            </button>
          )}
          <button
            onClick={usarSoloNombre}
            disabled={!nombre}
            className="dax-btn-secondary flex-1 text-sm justify-center disabled:opacity-40 min-h-[44px]"
          >
            Usar solo el nombre
          </button>
          {modoAlta ? (
            <button
              onClick={crear}
              disabled={!nombre || guardando}
              className="dax-btn-primary flex-1 text-sm justify-center min-h-[44px]"
            >
              {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Crear'}
            </button>
          ) : (
            <button
              onClick={() => setModoAlta(true)}
              disabled={!nombre}
              className="dax-btn-primary flex-1 text-sm justify-center min-h-[44px]"
            >
              Guardar en clientes
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
