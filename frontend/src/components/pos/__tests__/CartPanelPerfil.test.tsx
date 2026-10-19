// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'

vi.mock('../../../api/products', () => ({ productsApi: { getById: vi.fn(async () => null) } }))

const { CartPanel } = await import('../CartPanel')
const { usePOSStore } = await import('../../../store/posStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')
const { useExchangeRateStore } = await import('../../../store/exchangeRateStore')

const blusa = { product_id: 'p1', sku: 'BLU-1', name: 'Blusa', price: 100, base_price: 100, quantity: 1, discount: 0, subtotal: 100 }
const pintar = () => render(
  <CartPanel onPay={() => {}} onPark={() => {}} customerName={null} onClearCustomer={() => {}}
    sessionLocked={false} onOpenSession={() => {}} />,
)

beforeEach(() => {
  usePOSStore.setState({ cart: [blusa], globalDiscount: 0 } as never)
  useExchangeRateStore.setState({ rate: 18 } as never)
})
afterEach(cleanup)

describe('CartPanel según el perfil', () => {
  it('completo: Cliente, descuentos y dólares', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'completo' } as never)
    pintar()
    expect(screen.getByTitle('Asignar cliente a la venta')).toBeTruthy()
    expect(screen.getByTitle('Descuento')).toBeTruthy()
    expect(screen.getByText('Descuento global')).toBeTruthy()
    expect(screen.getByText(/T\.C\. 18\.00/)).toBeTruthy()
  })

  it('básico: sin Cliente, descuentos ni dólares; cobrar y pausar siguen', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    pintar()
    expect(screen.queryByTitle('Asignar cliente a la venta')).toBeNull()
    expect(screen.queryByTitle('Descuento')).toBeNull()
    expect(screen.queryByText('Descuento global')).toBeNull()
    expect(screen.queryByText(/T\.C\./)).toBeNull()
    for (const t of ['Efectivo', 'Tarjeta', 'Transfer.', 'Mixto', 'Aplicar caja']) expect(screen.getByText(t)).toBeTruthy()
    expect(screen.getByTitle('Guardar como pedido pendiente')).toBeTruthy()
  })

  it('contexto sin cargar: se pinta completo, nunca un básico a medias (Review Focus #1)', () => {
    useEnabledModulesStore.getState().reset()
    pintar()
    expect(screen.getByTitle('Asignar cliente a la venta')).toBeTruthy()
    expect(screen.getByText('Descuento global')).toBeTruthy()
  })

  it('básico con un ticket pausado que ya traía descuento: el descuento se sigue viendo', () => {
    useEnabledModulesStore.setState({ loaded: true, perfilUi: 'basico' } as never)
    usePOSStore.setState({ cart: [{ ...blusa, discount: 10 }], globalDiscount: 5 } as never)
    pintar()
    expect(screen.getByText('-10%')).toBeTruthy()
    expect(screen.getByText('Desc. -5%')).toBeTruthy()
  })
})
