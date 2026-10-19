// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { ProductPackagingSection } from '../ProductPackagingSection'

afterEach(cleanup)

describe('ProductPackagingSection', () => {
  it('sin empaques muestra el aviso y agrega una caja de 1', () => {
    const onChange = vi.fn()
    render(<ProductPackagingSection packagings={[]} onChange={onChange} />)
    expect(screen.getByText('Sin empaques definidos')).toBeTruthy()
    fireEvent.click(screen.getByText('Agregar empaque'))
    expect(onChange).toHaveBeenCalledWith([{ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 }])
  })

  it('pinta las filas, sus errores y quita la fila pedida', () => {
    const onChange = vi.fn()
    const filas = [
      { name: 'Caja', barcode: '', units_per_package: 12, package_price: 100 },
      { name: '', barcode: '', units_per_package: 0, package_price: 0 },
    ]
    render(<ProductPackagingSection packagings={filas} onChange={onChange}
      errors={{ 'packaging.1.name': 'Requerido', 'packaging.1.units_per_package': 'Unidades mayores a 0' }} />)
    expect(screen.getByText('Requerido')).toBeTruthy()
    expect(screen.getByText('Unidades mayores a 0')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Quitar el empaque 1'))
    expect(onChange).toHaveBeenCalledWith([filas[1]])
  })
})
