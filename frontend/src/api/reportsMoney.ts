import client from './client'
import type {
  BiweeklyRow, BiweeklyUnit, CancellationsDetail, CancellationsRow,
  CashCutDetail, CashCutRow, ReturnsDetail, ReturnsRow,
} from '../types/reportsMoney'
import type { PaginatedReport, ReportParams } from '../types/reports'

const REPORT_TIMEOUT_MS = 60_000

async function downloadCsv(url: string, params: Record<string, unknown>, baseName: string): Promise<void> {
  const resp = await client.get(url, { params, responseType: 'blob', timeout: REPORT_TIMEOUT_MS })
  const blobUrl = URL.createObjectURL(resp.data as Blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = `${baseName}.csv`
  a.click()
  URL.revokeObjectURL(blobUrl)
}

export const reportsMoneyApi = {
  getCashCuts: async (params: ReportParams): Promise<PaginatedReport<CashCutRow>> => {
    const { data } = await client.get('/platform/reports/cash-cuts', { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getCashCutDetail: async (branchId: number, params: ReportParams): Promise<CashCutDetail> => {
    const { data } = await client.get(`/platform/reports/cash-cuts/${branchId}/detail`, { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getReturns: async (params: ReportParams): Promise<PaginatedReport<ReturnsRow>> => {
    const { data } = await client.get('/platform/reports/returns', { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getReturnsDetail: async (branchId: number, params: ReportParams): Promise<ReturnsDetail> => {
    const { data } = await client.get(`/platform/reports/returns/${branchId}/detail`, { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getCancellations: async (params: ReportParams): Promise<PaginatedReport<CancellationsRow>> => {
    const { data } = await client.get('/platform/reports/cancellations', { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getCancellationsDetail: async (branchId: number, params: ReportParams): Promise<CancellationsDetail> => {
    const { data } = await client.get(`/platform/reports/cancellations/${branchId}/detail`, { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  getBiweekly: async (params: ReportParams & { unit: BiweeklyUnit }): Promise<PaginatedReport<BiweeklyRow>> => {
    const { data } = await client.get('/platform/reports/payment-methods-biweekly', { params, timeout: REPORT_TIMEOUT_MS })
    return data
  },
  exportCashCutsCsv: (params: ReportParams) =>
    downloadCsv('/platform/reports/cash-cuts.csv', params as Record<string, unknown>, 'reporte_cortes'),
  exportReturnsCsv: (params: ReportParams) =>
    downloadCsv('/platform/reports/returns.csv', params as Record<string, unknown>, 'reporte_devoluciones'),
  exportCancellationsCsv: (params: ReportParams) =>
    downloadCsv('/platform/reports/cancellations.csv', params as Record<string, unknown>, 'reporte_cancelaciones'),
  exportBiweeklyCsv: (params: ReportParams & { unit: BiweeklyUnit }) =>
    downloadCsv('/platform/reports/payment-methods-biweekly.csv', params as unknown as Record<string, unknown>, 'reporte_quincenal_metodo'),
}
