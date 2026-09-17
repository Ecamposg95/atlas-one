import { beforeEach, describe, expect, it, vi } from 'vitest'

// El store pega a `organizationApi.getCardSurcharge`, que lanza tanto ante un
// 500 como ante una caída de red. Aquí solo interesa qué hace el store con ese
// error, así que el módulo del API va mockeado.
const getCardSurcharge = vi.fn()
vi.mock('../api/organization', () => ({
  organizationApi: { getCardSurcharge: () => getCardSurcharge() },
}))

const { useCardSurchargeStore } = await import('./cardSurchargeStore')

describe('useCardSurchargeStore.load ante un error', () => {
  beforeEach(() => {
    getCardSurcharge.mockReset()
    useCardSurchargeStore.getState().reset()
  })

  it('sin carga previa deja el porcentaje en 0 (falla cerrado)', async () => {
    getCardSurcharge.mockRejectedValue(new Error('Network Error'))
    await useCardSurchargeStore.getState().load()
    expect(useCardSurchargeStore.getState().pct).toBe(0)
    expect(useCardSurchargeStore.getState().loading).toBe(false)
  })

  it('tras una carga buena, una caída de red NO borra el porcentaje', async () => {
    // La regresión: el POS se quedaba cobrando sin comisión justo cuando se
    // pone a encolar ventas, y esas ventas se descartaban con 422 al volver.
    getCardSurcharge.mockResolvedValueOnce({ pct: 3.5 })
    await useCardSurchargeStore.getState().load()
    expect(useCardSurchargeStore.getState().pct).toBe(3.5)

    getCardSurcharge.mockRejectedValue(new Error('Network Error'))
    await useCardSurchargeStore.getState().load(true)
    expect(useCardSurchargeStore.getState().pct).toBe(3.5)
    expect(useCardSurchargeStore.getState().loading).toBe(false)
  })
})
