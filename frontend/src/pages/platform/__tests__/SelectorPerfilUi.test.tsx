// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { OPCIONES_PERFIL_UI, SelectorPerfilUi, PerfilEfectivoHint, perfilEfectivoUi } from '../SelectorPerfilUi'

afterEach(cleanup)

describe('SelectorPerfilUi', () => {
  it('tres opciones; sin valor guardado muestra Automático', () => {
    render(<SelectorPerfilUi valor={null} onCambio={() => {}} />)
    const sel = screen.getByLabelText('Perfil de interfaz') as HTMLSelectElement
    expect(sel.value).toBe('auto')
    expect(OPCIONES_PERFIL_UI.map((o) => o.valor)).toEqual(['auto', 'basico', 'completo'])
    expect(sel.options).toHaveLength(3)
  })

  it('avisa el valor elegido', () => {
    const onCambio = vi.fn()
    render(<SelectorPerfilUi valor="basico" onCambio={onCambio} />)
    fireEvent.change(screen.getByLabelText('Perfil de interfaz'), { target: { value: 'completo' } })
    expect(onCambio).toHaveBeenCalledWith('completo')
  })
})

describe('Efectivo', () => {
  it('forzado manda; auto deriva del plan (solo FREE = básico)', () => {
    expect(perfilEfectivoUi('completo', 'FREE')).toBe('completo')
    expect(perfilEfectivoUi('basico', 'PRO')).toBe('basico')
    expect(perfilEfectivoUi('auto', 'FREE')).toBe('basico')
    expect(perfilEfectivoUi(null, 'PRO')).toBe('completo')
    expect(perfilEfectivoUi(null, null)).toBe('completo')
  })
  it('pinta la línea', () => {
    render(<PerfilEfectivoHint perfilUi={null} plan="FREE" />)
    expect(screen.getByText('Efectivo: básico')).toBeTruthy()
  })
})
