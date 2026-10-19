// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { lazy, Suspense, useState } from 'react'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { LimiteDeError } from '../LimiteDeError'
import { toast, useToastStore } from '../../../store/toastStore'

afterEach(() => { cleanup(); useToastStore.setState({ toasts: [] }) })

// Misma forma que POS.tsx: carrito + modal lazy cuyo chunk no carga.
const Rota = lazy(() => Promise.reject(new Error('Failed to fetch dynamically imported module')))
function Pantalla() {
  const [abierto, setAbierto] = useState(true)
  return (
    <div>
      <p>Blusa x1 en el carrito</p>
      {abierto && (
        <LimiteDeError onError={() => { setAbierto(false); toast.error('No se pudo abrir el alta de producto. Termina la venta y recarga la página.') }}>
          <Suspense fallback={<span>Abriendo…</span>}><Rota /></Suspense>
        </LimiteDeError>
      )}
    </div>
  )
}

describe('LimiteDeError', () => {
  it('chunk que no carga: avisa, cierra el modal y el carrito sigue', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<Pantalla />)
    await waitFor(() => expect(useToastStore.getState().toasts.map(t => t.message))
      .toContain('No se pudo abrir el alta de producto. Termina la venta y recarga la página.'))
    expect(screen.queryByText('Abriendo…')).toBeNull()
    expect(screen.getByText('Blusa x1 en el carrito')).toBeTruthy()
  })
})
