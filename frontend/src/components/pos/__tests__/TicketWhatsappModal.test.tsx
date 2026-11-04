// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const getById = vi.fn()
vi.mock('../../../api/sales', () => ({ salesApi: { getById: (id: string) => getById(id) } }))

const { TicketWhatsappModal } = await import('../modals/TicketWhatsappModal')
const { useAuthStore } = await import('../../../store/authStore')

const venta = {
  id: 's1', doc_type: 'INVOICE', status: 'PAID', branch_id: 1, branch_name: 'Centro', seller_id: 1,
  customer_id: null, customer_name: null, series: 'A', folio: 7, subtotal: 300, tax_amount: 0,
  total_amount: 300, requires_invoice: false, created_at: '2026-11-04T18:00:00Z',
  lines: [{ id: 'l', variant_id: 'v', sku: 'JL7540', description: 'JL7540', quantity: 1, unit_price: 300, total_line: 300 }],
  payments: [{ id: 'p', method: 'CASH', amount: 300 }],
}

afterEach(() => { cleanup(); getById.mockReset() })

describe('TicketWhatsappModal', () => {
  it('lee la venta por id y arma el enlace wa.me con el número de la clienta', async () => {
    useAuthStore.setState({ org: { id: 1, name: 'Novedades Campanita' } } as never)
    getById.mockResolvedValue(venta)
    render(<TicketWhatsappModal saleId="s1" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText(/\*Novedades Campanita\*/)).toBeTruthy())
    expect(getById).toHaveBeenCalledWith('s1')
    const enlace = () => screen.getByRole('link', { name: 'Enviar por WhatsApp' }).getAttribute('href') ?? ''
    expect(enlace()).toMatch(/^https:\/\/wa\.me\/\?text=/)
    fireEvent.change(screen.getByLabelText(/WhatsApp de la clienta/), { target: { value: '5512345678' } })
    expect(enlace()).toMatch(/^https:\/\/wa\.me\/525512345678\?text=/)
    expect(decodeURIComponent(enlace())).toContain('Ticket A-0007')
  })

  it('con la venta completa no vuelve a pedirla; un número incompleto desactiva el envío', () => {
    render(<TicketWhatsappModal saleId="s1" venta={venta as never} onClose={() => {}} />)
    expect(getById).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText(/WhatsApp de la clienta/), { target: { value: '551' } })
    expect(screen.queryByRole('link', { name: 'Enviar por WhatsApp' })).toBeNull()
    expect(screen.getByText('Escribe un número de 10 dígitos')).toBeTruthy()
  })

  it('cerrado cuando no hay venta', () => {
    render(<TicketWhatsappModal saleId={null} onClose={() => {}} />)
    expect(screen.queryByText(/WhatsApp de la clienta/)).toBeNull()
  })
})
