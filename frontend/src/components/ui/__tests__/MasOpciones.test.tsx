// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { MasOpciones } from '../MasOpciones'

afterEach(cleanup)

describe('MasOpciones', () => {
  it('inactivo (completo): los hijos tal cual, sin botón ni envoltorio', () => {
    const { container } = render(<div><MasOpciones activo={false}><p>hijo</p></MasOpciones></div>)
    expect(screen.getByText('hijo')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
    expect(container.firstElementChild!.innerHTML).toBe('<p>hijo</p>')
  })

  it('activo (básico): plegado y sin montar hasta abrir', () => {
    render(<MasOpciones activo titulo="Más opciones del ticket"><p>hijo</p></MasOpciones>)
    const boton = screen.getByRole('button', { name: 'Más opciones del ticket' })
    expect(boton.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByText('hijo')).toBeNull()
    fireEvent.click(boton)
    expect(boton.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('hijo')).toBeTruthy()
  })
})
