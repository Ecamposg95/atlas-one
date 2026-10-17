import { describe, it, expect } from 'vitest'
import {
  armarPayloadAlta, armarPayloadEdicion, erroresDeApi, formDesdeProducto, totalInicial, validarProducto,
  type EntradaFormulario,
} from '../productoForm'
import { EMPTY_PRODUCT_FORM } from '../types'
import type { VariantRow } from '../variantMatrix'
import type { Product } from '../../../types/products'

const fila = (p: Partial<VariantRow>): VariantRow => ({
  key: 'k', color: '', size: '', sku: '', barcode: '', price: '', initial_stock: '', ...p,
})

const base = (extra: Partial<EntradaFormulario> = {}): EntradaFormulario => ({
  form: { ...EMPTY_PRODUCT_FORM, name: 'Tenis', sku: 'NK-TENIS', price: '4000', cost: '1500' },
  mode: 'create', isAdmin: true, userBranchId: null, enabledBranchIds: [20],
  prices: [], packagings: [], variantRows: [], hasVariantsModule: false,
  ...extra,
})

describe('validarProducto', () => {
  it('exige precio mayor a cero, como el backend', () => {
    expect(validarProducto(base({ form: { ...base().form, price: '0' } })).price).toBe('Precio mayor a 0')
    expect(validarProducto(base()).price).toBeUndefined()
  })
  it('admin: sucursal activa y sucursal de la existencia si hay piezas', () => {
    const e = validarProducto(base({ enabledBranchIds: [], form: { ...base().form, initial_stock: '3' } }))
    expect(e.target_branch_ids).toBe('Activa al menos una sucursal')
    expect(e.initial_stock_branch_id).toBe('Requerido con existencia inicial')
  })
  it('la existencia de las tallas hermanas también exige sucursal', () => {
    const rows = [fila({ key: 'a', size: '40', sku: 'NK-TENIS-40' }), fila({ key: 'b', size: '41', sku: 'NK-TENIS-41', initial_stock: '2' })]
    const e = validarProducto(base({ variantRows: rows, hasVariantsModule: true }))
    expect(e.initial_stock_branch_id).toBe('Requerido con existencia inicial')
  })
  it('cajero sin sucursal no puede dar de alta', () => {
    expect(validarProducto(base({ isAdmin: false, userBranchId: null })).target_branch_ids)
      .toBe('Tu usuario no tiene sucursal asignada')
  })
  it('empaques: unidades mayores a 0 y precio numérico', () => {
    const e = validarProducto(base({ packagings: [{ name: '', barcode: '', units_per_package: 0, package_price: -1 }] }))
    expect(e['packaging.0.name']).toBe('Requerido')
    expect(e['packaging.0.units_per_package']).toBe('Unidades mayores a 0')
    expect(e['packaging.0.package_price']).toBe('Número ≥ 0')
  })
  it('matriz: SKU de talla requerido y no repetido (incluye el base)', () => {
    const rows = [fila({ key: 'a', size: '40', sku: 'NK-TENIS-40' }), fila({ key: 'b', size: '41', sku: 'nk-tenis' })]
    const e = validarProducto(base({ variantRows: rows, hasVariantsModule: true }))
    expect(e['variants.0.sku']).toBe('SKU repetido')
  })
  it('en edición no valida stock ni sucursales', () => {
    const e = validarProducto(base({ mode: 'edit', enabledBranchIds: [], form: { ...base().form, initial_stock: '-1' } }))
    expect(e.target_branch_ids).toBeUndefined()
    expect(e.initial_stock).toBeUndefined()
  })
})

describe('armarPayloadAlta', () => {
  it('sin módulo de variantes no viajan color, talla ni extra_variants', () => {
    const p = armarPayloadAlta(base({ variantRows: [fila({ size: '40', sku: 'X-40' })], hasVariantsModule: false }))
    expect(p.color).toBeUndefined(); expect(p.size).toBeUndefined(); expect(p.extra_variants).toBeUndefined()
    expect(p.uses_inventory).toBe(true)
    expect(p.branch_id).toBeNull()
    expect(p.target_branch_ids).toEqual([20])
  })
  it('con matriz: la primera fila es la principal y las demás van en extra_variants', () => {
    const rows = [fila({ key: 'a', color: 'Negro', size: '40', sku: 'NK-TENIS-NEG-40', initial_stock: '1' }),
      fila({ key: 'b', color: 'Negro', size: '41', sku: 'NK-TENIS-NEG-41', initial_stock: '2', price: '4200' })]
    const p = armarPayloadAlta(base({ variantRows: rows, hasVariantsModule: true,
      form: { ...base().form, initial_stock: '1', initial_stock_branch_id: '20' } }))
    expect(p.color).toBe('Negro'); expect(p.size).toBe('40')
    expect(p.extra_variants).toEqual([{ color: 'Negro', size: '41', sku: 'NK-TENIS-NEG-41', price: 4200, initial_stock: 2 }])
    expect(p.branch_id).toBe(20)
  })
  it('cajero: la sucursal es la suya y no manda target_branch_ids', () => {
    const p = armarPayloadAlta(base({ isAdmin: false, userBranchId: 7, enabledBranchIds: [7],
      form: { ...base().form, initial_stock: '2' } }))
    expect(p.branch_id).toBe(7)
    expect(p.target_branch_ids).toBeUndefined()
  })
  it('manda empaques y escalones capturados; sin IVA la tasa es 0', () => {
    const p = armarPayloadAlta(base({
      prices: [{ price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }],
      packagings: [{ name: 'Caja', barcode: '', units_per_package: 12, package_price: 40000 }],
    }))
    expect(p.prices).toEqual([{ price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }])
    expect(p.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(p.tax_rate).toBe(0)
  })
})

const producto = (extra: Partial<Product> = {}): Product => ({
  id: 'p1', name: 'Tenis', sku: 'NK-TENIS-NEG-40', price: 4000, cost: 1500, unit: 'pza',
  is_active: true, uses_inventory: true,
  variants: [
    { id: 'v1', sku: 'NK-TENIS-NEG-40', color: 'Negro', size: '40', price: 4000, cost: 1500, barcode: '111' },
    { id: 'v2', sku: 'NK-TENIS-NEG-41', color: 'Negro', size: '41', price: 4000, cost: 1500, barcode: '222' },
  ],
  prices: [{ id: 'pr1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500, linked_package_id: null }],
  packaging_units: [{ id: 'pk1', name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }],
  ...extra,
} as Product)

describe('formDesdeProducto', () => {
  it('lee precio y código de la principal, y carga escalones y empaques', () => {
    const s = formDesdeProducto(producto())
    expect(s.form.sku).toBe('NK-TENIS-NEG-40'); expect(s.form.barcode).toBe('111'); expect(s.form.price).toBe('4000')
    expect(s.form.uses_inventory).toBe(true)
    expect(s.prices).toEqual([{ id: 'pr1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }])
    expect(s.packagings).toEqual([{ id: 'pk1', name: 'Caja', barcode: '', units_per_package: 12, package_price: 40000 }])
  })
  it('con una talla no principal, SKU y código son los de esa talla', () => {
    const s = formDesdeProducto(producto(), 'v2')
    expect(s.form.sku).toBe('NK-TENIS-NEG-41'); expect(s.form.barcode).toBe('222')
  })
})

describe('armarPayloadEdicion', () => {
  const entrada = (variantId?: string, extra: Partial<EntradaFormulario> = {}) => {
    const s = formDesdeProducto(producto(), variantId)
    return { ...base({ mode: 'edit' as const, prices: s.prices, packagings: s.packagings, form: s.form, ...extra }),
      loaded: producto(), variantId, precioATodas: true }
  }
  it('principal: SKU y código van al producto; empaques cargados se conservan', () => {
    const plan = armarPayloadEdicion(entrada())
    expect(plan.productPatch.sku).toBe('NK-TENIS-NEG-40')
    expect(plan.productPatch.barcode).toBe('111')
    expect(plan.productPatch.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(plan.productPatch.precio_a_todas_las_tallas).toBe(true)
    expect(plan.productPatch.uses_inventory).toBe(true)
    expect(plan.variantPatch).toBeNull()
  })
  it('talla no principal: SKU y código cambiados van a la talla, nunca al producto', () => {
    const e = entrada('v2')
    e.form = { ...e.form, sku: 'NK-TENIS-NEG-41B' }
    const plan = armarPayloadEdicion(e)
    expect(plan.productPatch.sku).toBeUndefined()
    expect(plan.productPatch.barcode).toBeUndefined()
    expect(plan.variantPatch).toEqual({ variantId: 'v2', patch: { sku: 'NK-TENIS-NEG-41B' } })
  })
  it('con una sola talla no manda precio_a_todas_las_tallas', () => {
    const uno = producto({ variants: [producto().variants![0]] })
    const s = formDesdeProducto(uno)
    const plan = armarPayloadEdicion({ ...base({ mode: 'edit', form: s.form }), loaded: uno, precioATodas: true })
    expect(plan.productPatch.precio_a_todas_las_tallas).toBeUndefined()
  })
})

describe('erroresDeApi', () => {
  const rows = [fila({ key: 'a', size: '40', sku: 'A-40' }), fila({ key: 'b', size: '41', sku: 'A-41' })]
  it('409 de SKU cae en el campo sku con el texto del servidor', () => {
    const r = erroresDeApi({ response: { status: 409, data: { detail: "El SKU 'A' ya existe en esta organización." } } }, [], 'create')
    expect(r.errors.sku).toContain('ya existe')
    expect(r.mensaje).toContain('ya existe')
  })
  it('422 en lista marca el campo', () => {
    const r = erroresDeApi({ response: { status: 422, data: { detail: [{ loc: ['body', 'price'], msg: 'mayor a 0' }] } } }, [], 'edit')
    expect(r.errors.price).toBeTruthy()
  })
  it('sin detalle usable da el mensaje genérico del modo', () => {
    expect(erroresDeApi(new Error('x'), rows, 'create').mensaje).toBe('No se pudo crear el producto.')
    expect(erroresDeApi({}, rows, 'edit').mensaje).toBe('No se pudo actualizar el producto.')
  })
  it('el 409 de una talla marca su fila', () => {
    const r = erroresDeApi({ response: { status: 409, data: { detail: "El SKU 'A-41' ya existe en esta organización." } } }, rows, 'create')
    expect(r.errors['variants.0.sku'] ?? r.errors['variants.1.sku']).toBeTruthy()
    expect(r.mensaje).toBe('Revisa la variante marcada.')
  })
})
