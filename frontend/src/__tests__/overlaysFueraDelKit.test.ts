import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const raiz = resolve(__dirname, '..')
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.(ts|tsx)$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}

// El kit mismo sí puede tener overlays.
const DEL_KIT = ['/components/ui/Modal.tsx', '/components/ui/ConfirmDialog.tsx']

/** Overlays hechos a mano que existían el 2026-10-18 (deuda conocida; ver spec SP5).
 *  Para añadir uno nuevo: usa components/ui/Modal. Para quitar uno: bórralo de aquí. */
const CONOCIDOS: Record<string, number> = {
  '/components/branch/CashBranchView.tsx': 1,
  '/components/branch/MovementModal.tsx': 1,
  '/components/branch/OpenShiftModal.tsx': 1,
  '/components/branch/ProductsBranchView.tsx': 1,
  '/components/catalog/ProductAuditDrawer.tsx': 1,
  '/components/catalog/ProductBranchMatrix.tsx': 1,
  '/components/pos/PrinterInstallWizard.tsx': 1,
  '/components/pos/modals/CardPaymentModal.tsx': 1,
  '/components/pos/modals/CashMovementModal.tsx': 1,
  '/components/pos/modals/CashPaymentModal.tsx': 1,
  '/components/pos/modals/CloseSessionModal.tsx': 1,
  '/components/pos/modals/CustomerModal.tsx': 1,
  '/components/pos/modals/MixedPaymentModal.tsx': 1,
  '/components/pos/modals/ReprintPinModal.tsx': 1,
  '/components/pos/modals/ReturnModal.tsx': 1,
  '/components/pos/modals/SaleSuccessModal.tsx': 1,
  '/components/pos/modals/SessionModal.tsx': 1,
  '/components/pos/modals/TransferPaymentModal.tsx': 1,
  '/components/pos/modals/VariantPickerModal.tsx': 1,
  '/components/tables/TableFormModal.tsx': 1,
  '/pages/core/Brands.tsx': 1,
  '/pages/core/Departments.tsx': 1,
  '/pages/core/Organization.tsx': 1,
  '/pages/core/Users.tsx': 1,
  '/pages/crm/Customers.tsx': 1,
  '/pages/finance/CashHistory.tsx': 2,
  '/pages/hq/HQInventory.tsx': 1,
  '/pages/hq/HQReturns.tsx': 2,
  '/pages/hq/HQSalesLog.tsx': 1,
  '/pages/inventory/Inventory.tsx': 1,
  '/pages/inventory/Products.tsx': 1,
  '/pages/labels/Labels.tsx': 1,
  '/pages/pos/POS.tsx': 2,
  '/pages/sales/Returns.tsx': 2,
  '/pages/sales/SalesHistory.tsx': 1,
}

describe('overlays fuera del kit', () => {
  it('no aparece ningún overlay manual nuevo fuera de ui/Modal (ni queda uno migrado sin borrar de la lista)', () => {
    const encontrados: Record<string, number> = {}
    for (const f of archivos(raiz).sort()) {
      const ruta = f.replace(raiz, '')
      if (DEL_KIT.includes(ruta)) continue
      const n = readFileSync(f, 'utf8').split('fixed inset-0').length - 1
      if (n > 0) encontrados[ruta] = n
    }
    expect(encontrados).toEqual(CONOCIDOS)
  })
})
