// frontend/src/pages/__tests__/Login.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const { login, navigate } = vi.hoisted(() => ({ login: vi.fn(), navigate: vi.fn() }))
vi.mock('../../api/auth', () => ({ authApi: { login } }))
vi.mock('react-router-dom', async (original) => ({
  ...(await original<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))

import { LoginPage } from '../Login'

/** jsdom no trae matchMedia: `telefono` decide si `(max-width: 767px)` coincide (useEsTelefono). */
const anchoDePantalla = (telefono: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: telefono && query === '(max-width: 767px)', media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
const pintar = () => render(<MemoryRouter><LoginPage /></MemoryRouter>)

const entrar = (usuario: string, clave: string) => {
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: usuario } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: clave } })
  fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
}

beforeEach(() => {
  anchoDePantalla(false)
  login.mockReset()
  navigate.mockReset()
})
afterEach(cleanup)

describe('LoginPage', () => {
  it('muestra el formulario sin interacción', () => {
    pintar()
    expect(screen.getByLabelText('Usuario')).toBeTruthy()
    expect(screen.getByLabelText('Contraseña')).toBeTruthy()
    expect(screen.getByLabelText('Usuario').getAttribute('autocomplete')).toBe('username')
    expect(screen.getByLabelText('Contraseña').getAttribute('autocomplete')).toBe('current-password')
  })

  it('lleva los copys del sitio', () => {
    pintar()
    expect(screen.getByText('Software de operación')).toBeTruthy()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.textContent).toContain('Un punto de venta por')
    expect(h1.textContent).toContain('cada giro.')
    expect(screen.getByRole('heading', { name: 'Entra a tu tienda' })).toBeTruthy()
    const enlace = screen.getByRole('link', { name: /Conoce Atlas ONE/ })
    expect(enlace.getAttribute('href')).toBe('https://atlasone.com.mx')
    expect(screen.getByText('Atlas ONE — Atlas Tech')).toBeTruthy()
  })

  it('pinta la terminal decorativa sin estorbar al lector de pantalla, también en teléfono', () => {
    const { container, unmount } = pintar()
    const terminal = container.querySelector('.login-terminal')
    expect(terminal).not.toBeNull()
    expect(terminal!.closest('[aria-hidden="true"]')).not.toBeNull()
    unmount()
    anchoDePantalla(true)
    const r = pintar()
    expect(r.container.querySelector('.login-terminal')).not.toBeNull()
    expect(screen.getByLabelText('Usuario')).toBeTruthy()
  })

  it('CAJERO entra al POS', async () => {
    login.mockResolvedValue({
      access_token: 't', organization: null, branch: null,
      user: { id: 1, username: 'caja', role: 'CAJERO', platform_role: null },
    })
    pintar()
    entrar('caja', 'secreta')
    expect(login).toHaveBeenCalledWith('caja', 'secreta')
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/atlas-pos'), { timeout: 2000 })
  })

  it('muestra el error cuando el login falla', async () => {
    login.mockRejectedValue({ response: { data: { detail: 'Credenciales inválidas' } } })
    pintar()
    entrar('caja', 'mala')
    const alerta = await screen.findByRole('alert')
    expect(alerta.textContent).toBe('Usuario o contraseña incorrectos. Intenta de nuevo.')
    expect(navigate).not.toHaveBeenCalled()
  })

  it('el ojo alterna el tipo de la contraseña', () => {
    pintar()
    const clave = screen.getByLabelText('Contraseña')
    expect(clave.getAttribute('type')).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(clave.getAttribute('type')).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(clave.getAttribute('type')).toBe('password')
  })
})
