import { describe, it, expect } from 'vitest'

// Spec 2026-09-09 §3.4: en los archivos que esta rebanada tocó no vuelven
// colores fijos. Los tokens --p-* (alias) y --dax-* son la única vía; el
// único hex tolerado es blanco sobre el acento. Las demás páginas de
// /platform heredan la piel pero conservan sus hex puntuales — entran al
// candado cuando se toquen (flujos del tablero y de reportes).
// Los fuentes entran como texto (`?raw`, Vite) porque el proyecto no tiene
// @types/node y `node:fs` no compila con `tsc --noEmit`.
import platformLayout from '../../pages/platform/PlatformLayout.tsx?raw'
import platformNav from '../../pages/platform/platformNav.ts?raw'
import dataTable from '../../components/platform/DataTable.tsx?raw'
import dataTableCards from '../../components/platform/dataTableCards.ts?raw'
import platformPageShell from '../../components/platform/PlatformPageShell.tsx?raw'
import reportFilterBar from '../../components/platform/ReportFilterBar.tsx?raw'
import reportDrillDownDrawer from '../../components/platform/ReportDrillDownDrawer.tsx?raw'
import kpiCard from '../../components/platform/KPICard.tsx?raw'
import orgBoard from '../../pages/platform/org/OrgBoard.tsx?raw'
import orgKpis from '../../pages/platform/org/OrgKpis.tsx?raw'
import orgTable from '../../pages/platform/org/OrgTable.tsx?raw'
import attentionPanel from '../../pages/platform/org/AttentionPanel.tsx?raw'
import unitDrawer from '../../pages/platform/org/UnitDrawer.tsx?raw'
import orgFormat from '../../pages/platform/org/orgFormat.ts?raw'
import platformReports from '../../pages/platform/PlatformReports.tsx?raw'
import moneyTable from '../../pages/platform/reports/MoneyTable.tsx?raw'
import cashCutsTab from '../../pages/platform/reports/CashCutsTab.tsx?raw'
import returnsTab from '../../pages/platform/reports/ReturnsTab.tsx?raw'
import cancellationsTab from '../../pages/platform/reports/CancellationsTab.tsx?raw'
import biweeklyTab from '../../pages/platform/reports/BiweeklyTab.tsx?raw'
import moneyDetailDrawer from '../../pages/platform/reports/MoneyDetailDrawer.tsx?raw'
import compareFormat from '../../pages/platform/reports/compareFormat.ts?raw'
import reportsMoneyApi from '../../api/reportsMoney.ts?raw'

const FILES: [string, string][] = [
  ['pages/platform/PlatformLayout.tsx', platformLayout],
  ['pages/platform/platformNav.ts', platformNav],
  ['components/platform/DataTable.tsx', dataTable],
  ['components/platform/dataTableCards.ts', dataTableCards],
  ['components/platform/PlatformPageShell.tsx', platformPageShell],
  ['components/platform/ReportFilterBar.tsx', reportFilterBar],
  ['components/platform/ReportDrillDownDrawer.tsx', reportDrillDownDrawer],
  ['components/platform/KPICard.tsx', kpiCard],
  ['pages/platform/org/OrgBoard.tsx', orgBoard],
  ['pages/platform/org/OrgKpis.tsx', orgKpis],
  ['pages/platform/org/OrgTable.tsx', orgTable],
  ['pages/platform/org/AttentionPanel.tsx', attentionPanel],
  ['pages/platform/org/UnitDrawer.tsx', unitDrawer],
  ['pages/platform/org/orgFormat.ts', orgFormat],
  ['pages/platform/PlatformReports.tsx', platformReports],
  ['pages/platform/reports/MoneyTable.tsx', moneyTable],
  ['pages/platform/reports/CashCutsTab.tsx', cashCutsTab],
  ['pages/platform/reports/ReturnsTab.tsx', returnsTab],
  ['pages/platform/reports/CancellationsTab.tsx', cancellationsTab],
  ['pages/platform/reports/BiweeklyTab.tsx', biweeklyTab],
  ['pages/platform/reports/MoneyDetailDrawer.tsx', moneyDetailDrawer],
  ['pages/platform/reports/compareFormat.ts', compareFormat],
  ['api/reportsMoney.ts', reportsMoneyApi],
]
const TAILWIND = /\b(hover:)?(text|bg|border)-(slate|gray|zinc|indigo)-[0-9]{2,3}\b|\btext-white\b(?!\/)|backdrop-blur/g
const HEX = /#[0-9a-fA-F]{3,8}\b/g

describe.each(FILES)('%s sin colores fijos', (name, src) => {
  it('no usa clases slate/gray/zinc/indigo, text-white sólido ni backdrop-blur', () => {
    const hits = [...src.matchAll(TAILWIND)].map((m) => m[0])
    expect(hits, `restos en ${name}: ${[...new Set(hits)].join(', ')}`).toEqual([])
  })

  it('no usa hex salvo #fff', () => {
    const hits = [...src.matchAll(HEX)].map((m) => m[0].toLowerCase()).filter((h) => h !== '#fff' && h !== '#ffffff')
    expect(hits, `hex en ${name}: ${[...new Set(hits)].join(', ')}`).toEqual([])
  })
})
