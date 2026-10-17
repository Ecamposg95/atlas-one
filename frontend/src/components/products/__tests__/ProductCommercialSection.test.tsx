// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { ProductCommercialSection } from '../ProductCommercialSection'
import { EMPTY_PRODUCT_FORM } from '../types'

afterEach(cleanup)
const ocultaFicha = { visibles: ['name'], ocultos: ['gender', 'model', 'material'] }
const props = { onChange: vi.fn(), errors: {}, departments: [], brands: [] }

describe('ProductCommercialSection: campos por giro', () => {
  it('sin campos (falla abierto) muestra género, modelo y material', () => {
    render(<ProductCommercialSection {...props} value={EMPTY_PRODUCT_FORM} />)
    expect(screen.getByText('Género')).toBeTruthy()
    expect(screen.getByText('Modelo')).toBeTruthy()
    expect(screen.getByText('Material')).toBeTruthy()
  })
  it('un giro sin ficha no los muestra', () => {
    render(<ProductCommercialSection {...props} value={EMPTY_PRODUCT_FORM} campos={ocultaFicha} />)
    expect(screen.queryByText('Género')).toBeNull()
    expect(screen.queryByText('Modelo')).toBeNull()
    expect(screen.queryByText('Material')).toBeNull()
  })
  it('nada se apaga: con valor capturado el campo sigue ahí', () => {
    render(<ProductCommercialSection {...props} value={{ ...EMPTY_PRODUCT_FORM, gender: 'MUJER' }} campos={ocultaFicha} />)
    expect(screen.getByText('Género')).toBeTruthy()
    expect(screen.queryByText('Modelo')).toBeNull()
  })
})
