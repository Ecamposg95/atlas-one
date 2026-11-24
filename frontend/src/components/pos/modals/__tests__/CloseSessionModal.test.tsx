// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { CloseSessionModal } from '../CloseSessionModal'
import { formatCurrency } from '../../../../utils/currency'
import { useEnabledModulesStore } from '../../../../store/enabledModulesStore'

const getSummary = vi.hoisted(() => vi.fn())
vi.mock('../../../../api/cash', () => ({ cashApi: { getSummary } }))

afterEach(() => { cleanup(); getSummary.mockReset(); useEnabledModulesStore.setState({ conteoCiego: true }) })

function capturar(monto: string) {
  fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: monto } })
  fireEvent.click(screen.getByRole('button', { name: /Cerrar Turno/ }))
}

describe('CloseSessionModal: conteo ciego', () => {
  it('no enseña esperado ni diferencia mientras se captura', () => {
    render(<CloseSessionModal onClose={vi.fn()} onConfirm={vi.fn()} />)
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '1000' } })
    expect(screen.queryByText('Esperado en caja')).toBeNull()
    expect(screen.queryByText(/\$/)).toBeNull() // ningún importe en pantalla
    expect(screen.queryByText('Diferencia')).toBeNull()
  })

  it('tras cerrar muestra esperado, contado y diferencia del backend, y "Listo" cierra', async () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn().mockResolvedValue({ difference: '-50' })
    render(<CloseSessionModal onClose={onClose} onConfirm={onConfirm} />)
    capturar('1000')

    await waitFor(() => expect(screen.getByRole('button', { name: 'Listo' })).toBeTruthy())
    expect(onConfirm).toHaveBeenCalledWith(1000, '')
    expect(screen.getByText(formatCurrency(1050))).toBeTruthy() // esperado = 1000 − (−50)
    expect(screen.getByText(formatCurrency(1000))).toBeTruthy() // contado
    expect(screen.getByText(/Faltante/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Cancelar' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Listo' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('si el cierre falla (null) se queda en captura sin revelar nada', async () => {
    const onConfirm = vi.fn().mockResolvedValue(null)
    render(<CloseSessionModal onClose={vi.fn()} onConfirm={onConfirm} />)
    capturar('1000')

    await waitFor(() => expect(onConfirm).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByRole('button', { name: /Cerrar Turno/ })).toBeTruthy())
    expect(screen.queryByRole('button', { name: 'Listo' })).toBeNull()
    expect(screen.queryByText('Esperado en caja')).toBeNull()
    expect(screen.queryByText(/\$/)).toBeNull() // ningún importe en pantalla
    expect(screen.getByPlaceholderText('0.00')).toBeTruthy()
  })
})

describe('CloseSessionModal: tienda sin conteo ciego', () => {
  it('enseña el esperado antes de contar, sin pre-llenar el campo ni la nota de conteo ciego', async () => {
    useEnabledModulesStore.setState({ conteoCiego: false })
    getSummary.mockResolvedValue({ expected_cash: 1234.5 })
    render(<CloseSessionModal onClose={vi.fn()} onConfirm={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(formatCurrency(1234.5))).toBeTruthy())
    expect(screen.getByText('Esperado en caja')).toBeTruthy()
    expect(screen.queryByText(/Conteo ciego/)).toBeNull()
    expect((screen.getByPlaceholderText('0.00') as HTMLInputElement).value).toBe('')
  })

  it('con conteo ciego no pide el resumen', () => {
    render(<CloseSessionModal onClose={vi.fn()} onConfirm={vi.fn()} />)
    expect(getSummary).not.toHaveBeenCalled()
  })
})
