import { describe, it, expect } from 'vitest'

import { planBranchStatusWrites } from '../branchFanout'

describe('planBranchStatusWrites', () => {
  it('sin variantes no hay nada que escribir', () => {
    expect(planBranchStatusWrites([], { is_active_pos: false })).toEqual({ bulk: null, patches: null })
  })

  it('con una sola talla todo va por PATCH — el comportamiento de siempre', () => {
    const plan = planBranchStatusWrites(['v1'], { is_active_pos: false })
    expect(plan.bulk).toBeNull()
    expect(plan.patches).toEqual({ variantIds: ['v1'], patch: { is_active_pos: false } })
  })

  it('apagar el POS con varias tallas las apaga TODAS, no solo la principal', () => {
    const plan = planBranchStatusWrites(['v1', 'v2', 'v3'], { is_active_pos: false })
    expect(plan.bulk).toEqual({ variantIds: ['v1', 'v2', 'v3'], isActivePos: false })
    expect(plan.patches).toBeNull()
  })

  it('el precio de sucursal se escribe en todas las tallas', () => {
    const plan = planBranchStatusWrites(['v1', 'v2'], { price_override: 199 })
    expect(plan.bulk).toBeNull()
    expect(plan.patches).toEqual({ variantIds: ['v1', 'v2'], patch: { price_override: 199 } })
  })

  it('limpiar el precio (null) también viaja a todas las tallas', () => {
    const plan = planBranchStatusWrites(['v1', 'v2'], { price_override: null })
    expect(plan.patches).toEqual({ variantIds: ['v1', 'v2'], patch: { price_override: null } })
  })

  it('un patch mixto usa el bulk para el POS y el PATCH para el resto', () => {
    const plan = planBranchStatusWrites(['v1', 'v2'], { is_active_pos: true, price_override: 50, min_stock_alert: 3 })
    expect(plan.bulk).toEqual({ variantIds: ['v1', 'v2'], isActivePos: true })
    expect(plan.patches).toEqual({ variantIds: ['v1', 'v2'], patch: { price_override: 50, min_stock_alert: 3 } })
  })

  it('un patch vacío no escribe nada', () => {
    expect(planBranchStatusWrites(['v1', 'v2'], {})).toEqual({ bulk: null, patches: null })
  })

  it('no muta el patch que recibe', () => {
    const patch = { is_active_pos: true, price_override: 10 }
    planBranchStatusWrites(['v1', 'v2'], patch)
    expect(patch).toEqual({ is_active_pos: true, price_override: 10 })
  })
})
