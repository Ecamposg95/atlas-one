// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { TarjetaTiendaEnLinea } from '../TarjetaTiendaEnLinea'
import { reportsApi } from '../../../api/reports'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('TarjetaTiendaEnLinea', () => {
  it('lista las piezas más consultadas y el número de prospectos', async () => {
    const espia = vi.spyOn(reportsApi, 'tiendaEnLinea').mockResolvedValue({
      piezas: [{ product_id: 'a', name: 'Bolsa Roja', consultas: 5 }, { product_id: 'b', name: 'Tenis', consultas: 2 }],
      prospectos: 1,
    })
    render(<TarjetaTiendaEnLinea desde="2026-11-01" hasta="2026-11-14" />)
    await waitFor(() => expect(screen.getByText('1. Bolsa Roja')).toBeTruthy())
    expect(espia).toHaveBeenCalledWith({ desde: '2026-11-01', hasta: '2026-11-14' })
    expect(screen.getByText('2. Tenis')).toBeTruthy()
    expect(screen.getByTestId('prospectos').textContent).toBe('1 prospecto')
  })

  it('sin consultas lo dice', async () => {
    vi.spyOn(reportsApi, 'tiendaEnLinea').mockResolvedValue({ piezas: [], prospectos: 0 })
    render(<TarjetaTiendaEnLinea desde="2026-11-01" hasta="2026-11-14" />)
    await waitFor(() => expect(screen.getByText('Sin consultas en el periodo.')).toBeTruthy())
    expect(screen.getByTestId('prospectos').textContent).toBe('0 prospectos')
  })
})
