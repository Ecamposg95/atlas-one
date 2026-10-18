// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ConfirmDialogProvider, confirm } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('usa la tarjeta y el pie del kit, y Escape cancela', async () => {
    render(<ConfirmDialogProvider><div /></ConfirmDialogProvider>)
    let resultado: Promise<boolean>
    act(() => { resultado = confirm({ title: '¿Eliminar la marca?', message: 'No se puede deshacer', variant: 'danger' }) })
    const titulo = await screen.findByText('¿Eliminar la marca?')
    const tarjeta = titulo.closest('.dax-modal')
    expect(tarjeta).not.toBeNull()
    expect(tarjeta!.querySelector('.dax-modal-footer')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Cancelar' }).className).toContain('dax-btn-secondary')
    expect(screen.getByRole('button', { name: 'Confirmar' }).className).toContain('dax-btn-danger')
    fireEvent.keyDown(document, { key: 'Escape' })
    await expect(resultado!).resolves.toBe(false)
  })
  it('no fija colores fuera de los tokens', () => {
    const fuente = readFileSync(resolve(__dirname, '../ConfirmDialog.tsx'), 'utf8')
    expect(fuente).not.toMatch(/#ffffff|bg-slate-900|rgba\(255,255,255/)
  })
})
