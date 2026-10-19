// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CustomerFormModal } from '../CustomerFormModal'

vi.mock('../../../api/customers', () => ({ customersApi: { create: vi.fn(), update: vi.fn() } }))

afterEach(cleanup)

describe('CustomerFormModal', () => {
  it('se pinta con el Modal del kit, apila los campos bajo sm y Escape no descarta lo escrito', () => {
    const onClose = vi.fn()
    render(<CustomerFormModal customer={null} onClose={onClose} onSaved={() => {}} />)
    expect(screen.getByRole('dialog').querySelector('.dax-modal')).not.toBeNull()
    expect(screen.getByRole('button', { name: /Guardar/ }).closest('.dax-modal-footer')).not.toBeNull()
    const rejillas = Array.from(document.querySelectorAll('[class*="grid-cols-2"]'))
    expect(rejillas.length).toBeGreaterThan(0)
    for (const r of rejillas) expect(r.className).toMatch(/grid-cols-1 sm:grid-cols-2/)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Cancelar/ }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
