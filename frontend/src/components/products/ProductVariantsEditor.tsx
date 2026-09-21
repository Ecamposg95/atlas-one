import { useState } from 'react'
import { Link } from 'react-router-dom'

import { productsApi } from '../../api/products'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { TablaDesplazable } from '../ui/TablaDesplazable'
import type { Product, ProductVariant } from '../../types/products'
import { errorDetailText } from '../../utils/errorDetail'
import { ProductVariantsSection } from './ProductVariantsSection'
import { toExtraVariants, variantDetailErrors, type VariantRow } from './variantMatrix'
import { usesColors, variantLabel, variantWords } from './variantWords'

interface Props {
  product: Product
  onChanged: (p: Product) => void
}

/** Valores distintos de un atributo, en el orden en que aparecen. */
function distintos(variants: ProductVariant[], campo: 'color' | 'size'): string[] {
  const out: string[] = []
  const vistos = new Set<string>()
  for (const v of variants) {
    const valor = (v[campo] ?? '').trim()
    if (!valor || vistos.has(valor.toLowerCase())) continue
    vistos.add(valor.toLowerCase())
    out.push(valor)
  }
  return out
}

/**
 * Variantes existentes de un producto (edición). Cada fila guarda por su
 * cuenta con PUT /api/products/variants/{id}; el formulario de arriba sigue
 * editando solo la principal. Retirar pasa por DELETE y el backend decide
 * (409 con existencia o ventas).
 *
 * Al agregar tallas a un producto que todavía no tiene ninguna, la primera no
 * se crea: se le asigna a la prenda que ya existe. Si no, el producto quedaba
 * con una variante "Estándar" invendible además de sus tallas.
 */
export function ProductVariantsEditor({ product, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [rows, setRows] = useState<VariantRow[]>([])
  // Errores por fila del backend ("variants[1]: el precio debe ser mayor a
  // cero", "El SKU 'PLY-L' ya existe…"): sin esto el aviso salía suelto arriba
  // y había que adivinar cuál de las cinco filas corregir.
  const [errores, setErrores] = useState<Record<string, string>>({})
  const variants = product.variants ?? []
  const principal = variants[0] ?? null

  const enTarjetas = useMediaQuery('(max-width: 767px)')
  const conColores = usesColors(variants)
  const palabra = variantWords(conColores)
  // Producto sin color ni talla: la primera fila nueva ES esta prenda.
  const asignaPrincipal = variants.length === 1 && !principal?.color && !principal?.size

  const save = async (v: ProductVariant, patch: Parameters<typeof productsApi.updateVariant>[1]) => {
    setBusyId(v.id); setMsg(null)
    try { onChanged(await productsApi.updateVariant(v.id, patch)) }
    catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, `No se pudo guardar la ${palabra.singular}.`))
    } finally { setBusyId(null) }
  }

  const remove = async (v: ProductVariant) => {
    if (!window.confirm(`¿Retirar la ${palabra.singular} ${variantLabel(v, product.name)}?`)) return
    setBusyId(v.id); setMsg(null)
    try {
      await productsApi.deleteVariant(v.id)
      // El DELETE ya aplicó — si el refetch falla, no es lo mismo que "no se
      // pudo retirar": la variante ya no existe, solo falta refrescar la vista.
      try {
        onChanged(await productsApi.getById(product.id))
      } catch {
        setMsg(`Se retiró la ${palabra.singular}; recarga la página para ver los cambios.`)
      }
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, `No se pudo retirar la ${palabra.singular}.`))
    } finally { setBusyId(null) }
  }

  const addRows = async () => {
    if (rows.length === 0) return
    setBusyId('new'); setMsg(null); setErrores({})
    let principalAsignada = false
    try {
      let actualizado = product
      let hermanas = rows
      if (asignaPrincipal && principal) {
        // La primera fila se le pone a la prenda que ya existe: conserva su
        // SKU, su código y su precio, solo estrena color/talla.
        const [primera, ...resto] = rows
        actualizado = await productsApi.updateVariant(principal.id, {
          color: primera.color || null,
          size: primera.size || null,
        })
        principalAsignada = true
        hermanas = resto
      }
      if (hermanas.length > 0) {
        actualizado = await productsApi.createVariants(product.id, toExtraVariants(hermanas))
      }
      onChanged(actualizado)
      setRows([]); setAdding(false); setErrores({})
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      // `variants[N]` se numera entre las HERMANAS: cuando la primera fila se
      // le asigna a la prenda que ya existe, esa no viaja en el POST.
      const porFila = variantDetailErrors(e?.response?.data?.detail,
                                          asignaPrincipal ? rows.slice(1) : rows)
      setErrores(porFila)
      // Si la primera talla ya se asignó y falló el resto, la pantalla no
      // puede quedarse con los datos viejos: se relee el producto y se quita
      // esa fila del generador para que un reintento no choque con ella.
      if (principalAsignada) {
        try {
          onChanged(await productsApi.getById(product.id))
          setRows((prev) => prev.slice(1))
        } catch { /* el mensaje de abajo ya pide recargar */ }
      }
      // Con la fila ya marcada, repetir el texto crudo del backend arriba solo
      // lo dice dos veces.
      const aviso = Object.keys(porFila).length > 0
        ? `Revisa la ${palabra.singular} marcada.`
        : errorDetailText(e?.response?.data?.detail, `No se pudieron crear las ${palabra.plural}.`)
      setMsg(aviso + (principalAsignada ? ` La primera ${palabra.singular} sí quedó asignada.` : ''))
    } finally { setBusyId(null) }
  }

  const titulo = conColores ? 'Variantes' : 'Tallas'
  const nuevas = asignaPrincipal ? Math.max(rows.length - 1, 0) : rows.length

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">{titulo} ({variants.length})</h3>
      {msg && <p className="text-sm text-amber-400">{msg}</p>}
      {/* Bajo `md` la tabla de 7 columnas con 5 campos pide ~660 px y, al
          desplazarla, se pierde de vista qué talla se está editando: cada
          variante pasa a ser una tarjeta. De `md` hacia arriba, la tabla. */}
      {enTarjetas ? (
        <div className="space-y-3">
          {variants.map((v) => (
            <VariantRowEditor key={v.id} v={v} modo="tarjeta" busy={busyId === v.id}
                              onSave={(patch) => save(v, patch)} onRemove={() => remove(v)} />
          ))}
        </div>
      ) : (
        <TablaDesplazable sangrado={false}>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-slate-400">
              <th className="py-1 pr-2">Color</th><th className="py-1 pr-2">Talla</th><th className="py-1 pr-2">SKU</th>
              <th className="py-1 pr-2">Código</th><th className="py-1 pr-2">Precio</th><th className="py-1 pr-2">Existencia</th><th />
            </tr></thead>
            <tbody>
              {variants.map((v) => (
                <VariantRowEditor key={v.id} v={v} modo="fila" busy={busyId === v.id}
                                  onSave={(patch) => save(v, patch)} onRemove={() => remove(v)} />
              ))}
            </tbody>
          </table>
        </TablaDesplazable>
      )}
      {!adding ? (
        <button type="button" className="dax-btn-secondary" onClick={() => setAdding(true)}>Agregar {palabra.plural}</button>
      ) : (
        <div className="space-y-2">
          {asignaPrincipal && (
            <p className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-2 text-xs text-indigo-200">
              Este producto todavía no tiene {palabra.plural}. La primera que escribas se le asigna a
              «{product.name}» —conserva su SKU, su código y su precio— y las demás se crean nuevas.
            </p>
          )}
          <ProductVariantsSection
            baseSku={principal?.sku ?? product.sku}
            rows={rows}
            onRowsChange={setRows}
            firstIsPrincipal={asignaPrincipal}
            errors={errores}
            // Las tallas que ya existen se precargan y no se regeneran: antes
            // el generador las proponía otra vez y el backend respondía 409.
            existing={asignaPrincipal ? [] : variants.map((v) => ({ color: v.color, size: v.size }))}
            defaultColors={distintos(variants, 'color').join(', ')}
            defaultSizes={distintos(variants, 'size').join(', ')}
          />
          <div className="flex gap-2">
            <button type="button" className="dax-btn-primary" disabled={busyId === 'new' || rows.length === 0} onClick={addRows}>
              {asignaPrincipal && nuevas === 0
                ? `Asignar ${rows.length === 1 ? `esta ${palabra.singular}` : `estas ${palabra.plural}`}`
                : `Crear ${nuevas} ${nuevas === 1 ? palabra.singular : palabra.plural}`}
            </button>
            <button type="button" className="dax-btn-secondary" onClick={() => { setAdding(false); setRows([]); setErrores({}); setMsg(null) }}>Cancelar</button>
          </div>
        </div>
      )}
    </section>
  )
}

function VariantRowEditor({ v, busy, modo, onSave, onRemove }: {
  v: ProductVariant; busy: boolean
  /** `fila` = celda de tabla (md+); `tarjeta` = bloque apilado (teléfono). */
  modo: 'fila' | 'tarjeta'
  onSave: (patch: { color?: string | null; size?: string | null; sku?: string; barcode?: string | null; price?: number }) => void
  onRemove: () => void
}) {
  const [color, setColor] = useState(v.color ?? '')
  const [size, setSize] = useState(v.size ?? '')
  const [sku, setSku] = useState(v.sku)
  const [barcode, setBarcode] = useState(v.barcode ?? '')
  const [price, setPrice] = useState(String(v.price))
  const priceNum = Number(price)
  const priceOk = price.trim() !== '' && Number.isFinite(priceNum) && priceNum > 0
  const otherDirty = color !== (v.color ?? '') || size !== (v.size ?? '') || sku !== v.sku || barcode !== (v.barcode ?? '')
  const priceDirty = priceOk && priceNum !== Number(v.price)
  const dirty = otherDirty || priceDirty

  const acciones = (
    <>
      <button type="button" className="dax-btn-primary" disabled={!dirty || busy || !priceOk}
              onClick={() => onSave({ color: color || null, size: size || null, sku, barcode: barcode || null, price: priceNum })}>Guardar</button>
      <button type="button" className="dax-btn-secondary" disabled={busy} onClick={onRemove}>Retirar</button>
    </>
  )

  if (modo === 'tarjeta') {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 space-y-2">
        <p className="text-xs font-bold text-slate-200">
          {[v.color, v.size].filter(Boolean).join(' / ') || v.sku}
          <span className="ml-2 font-normal text-slate-500">· {Number(v.stock_total ?? 0)} en existencia</span>
        </p>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-[10px] text-slate-400">Color</span>
            <input className="dax-input w-full" value={color} onChange={(e) => setColor(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[10px] text-slate-400">Talla</span>
            <input className="dax-input w-full" value={size} onChange={(e) => setSize(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[10px] text-slate-400">SKU</span>
            <input className="dax-input w-full" value={sku} onChange={(e) => setSku(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[10px] text-slate-400">Código</span>
            <input className="dax-input w-full" value={barcode} onChange={(e) => setBarcode(e.target.value)} />
          </label>
          <label className="block">
            <span className="text-[10px] text-slate-400">Precio</span>
            <input className="dax-input w-full" value={price} inputMode="decimal" onChange={(e) => setPrice(e.target.value)} />
            {!priceOk && <span className="text-rose-400 text-[11px] block">Precio mayor a 0</span>}
          </label>
          <div className="flex items-end">
            {/* La existencia no se edita aquí (necesita motivo y kardex). */}
            <Link to={`/inventory?variant=${v.id}&q=${encodeURIComponent(v.sku)}`}
                  className="dax-btn-secondary w-full justify-center text-xs">Ajustar existencia</Link>
          </div>
        </div>
        <div className="flex gap-2 [&>button]:flex-1 [&>button]:justify-center [&>button]:min-h-[44px]">{acciones}</div>
      </div>
    )
  }

  return (
    <tr>
      <td className="py-1 pr-2"><input className="dax-input" value={color} onChange={(e) => setColor(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={size} onChange={(e) => setSize(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={sku} onChange={(e) => setSku(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={barcode} onChange={(e) => setBarcode(e.target.value)} /></td>
      <td className="py-1 pr-2">
        <input className="dax-input" value={price} inputMode="decimal" onChange={(e) => setPrice(e.target.value)} />
        {!priceOk && <span className="text-rose-400 text-[11px] block">Precio mayor a 0</span>}
      </td>
      <td className="py-1 pr-2 text-slate-300">
        {Number(v.stock_total ?? 0)}
        {/* La existencia no se edita aquí (necesita motivo y kardex): el enlace
            lleva al inventario, que es donde se ajusta. */}
        <Link to={`/inventory?variant=${v.id}&q=${encodeURIComponent(v.sku)}`}
              className="block text-[11px] text-indigo-400 hover:underline">Ajustar</Link>
      </td>
      {/* El `flex` iba en el propio `<td>`: la celda dejaba de ser
          `table-cell` y se salía del reparto de columnas de la tabla. */}
      <td className="py-1 whitespace-nowrap">
        <div className="flex gap-1">{acciones}</div>
      </td>
    </tr>
  )
}
