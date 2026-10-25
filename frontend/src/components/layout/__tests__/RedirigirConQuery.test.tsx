// frontend/src/components/layout/__tests__/RedirigirConQuery.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'
import { RedirigirConQuery } from '../RedirigirConQuery'

function Destino() {
  const { pathname, search, hash } = useLocation()
  return <p data-testid="destino">{pathname}{search}{hash}</p>
}
const pintar = (inicial: string) => render(
  <MemoryRouter initialEntries={[inicial]}>
    <Routes>
      <Route path="hq/sales" element={<RedirigirConQuery a="/sales" />} />
      <Route path="hq/inventory" element={<RedirigirConQuery a="/inventory" />} />
      <Route path="admin/catalog" element={<RedirigirConQuery a="/products" />} />
      <Route path="*" element={<Destino />} />
    </Routes>
  </MemoryRouter>,
)
afterEach(cleanup)

describe('RedirigirConQuery (URL viejas del admin, spec §4.1)', () => {
  it('conserva la consulta al redirigir', () => {
    pintar('/hq/inventory?q=ABR-1&variant=v9')
    expect(screen.getByTestId('destino').textContent).toBe('/inventory?q=ABR-1&variant=v9')
  })
  it('sin consulta llega limpio', () => {
    pintar('/hq/sales')
    expect(screen.getByTestId('destino').textContent).toBe('/sales')
  })
  it('conserva también el hash', () => {
    pintar('/admin/catalog?x=1#arriba')
    expect(screen.getByTestId('destino').textContent).toBe('/products?x=1#arriba')
  })
})
