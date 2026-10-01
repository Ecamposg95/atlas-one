import client from './client'
import type {
  ReportParams,
  PaginatedReport,
  ProductRow,
  BranchRow,
  SellerRow,
  CustomerRow,
  ProductDetailResponse,
  BranchDetailResponse,
  SellerDetailResponse,
  CustomerDetailResponse,
} from '../types/reports'

// ── Types ────────────────────────────────────────────────────────────────────

export interface PlatformOrg {
  id: number
  name: string
  legal_name: string | null
  tax_id: string | null
  tax_regime: string | null
  email: string | null
  phone: string | null
  address: string | null
  website: string | null
  logo_url: string | null
  ticket_header: string | null
  ticket_footer: string | null
  printer_name: string | null
  timezone: string | null
  industry_type: string | null
  status: string | null
  is_active: boolean
  created_at: string
  plan: string | null
}

export interface OrgDependencies {
  branches: number
  users: number
}

export interface BranchDependencies {
  users: number
  sales: number
  cash_sessions: number
}

export interface PlatformBranch {
  id: number
  name: string
  branch_type: string
  organization_id: number
  is_active: boolean
  can_sell?: boolean
  address: string | null
  address_line1?: string | null
  address_line2?: string | null
  neighborhood?: string | null
  city?: string | null
  state?: string | null
  postal_code?: string | null
  country?: string | null
  phone: string | null
  email?: string | null
  printer_name?: string | null
  ticket_header?: string | null
  ticket_footer?: string | null
  paper_width_mm?: number | null
  // Optional KPIs / alerts (backend may not expose yet; UI degrades to dashes)
  sales_today?: number | null
  tickets_today?: number | null
  last_sync_at?: string | null
  alerts_count?: number | null
}

export interface PlatformUser {
  id: number
  username: string
  full_name: string
  email: string | null
  role: string
  platform_role: string
  branch_id: number | null
  branch_name?: string | null
  organization_id: number | null
  is_active: boolean
  created_at: string
  last_login?: string | null
}

export interface GlobalStats {
  organizations: {
    total: number
    active: number
    suspended: number
    new_this_month: number
    delta_30d: number
  }
  users: number
  branches: number
  sales: {
    revenue: number
    count: number
    today: number
    today_delta: number
  }
  activity_rate: number
}

export interface TrendsResponse {
  revenue_trend: { date: string; revenue: number; count: number }[]
  org_registrations: { date: string; count: number }[]
}

export interface TopTenant {
  id: number
  name: string
  revenue: number
  transactions: number
  industry_type?: string | null
}

export interface AuditLog {
  id: number
  actor_user_id: number
  action: string
  entity_type: string
  entity_id: string
  payload: string | null
  created_at: string
}

export interface PlatformAlert {
  id: number
  organization_id: number
  organization_name: string | null
  severity: 'critical' | 'warning' | 'info'
  kind: 'revenue_drop' | 'no_sales_24h' | 'user_churn' | 'custom' | string
  title: string
  detail: string | null
  first_seen: string
  acked_at: string | null
  acked_by: number | null
  resolved_at: string | null
}

export interface PlatformAlertCounts {
  active: number
  critical: number
  warning: number
  info: number
  acked: number
  resolved: number
}

export interface PlatformAlertScanResult {
  created: number
  skipped: number
}

export interface PlatformAdmin {
  id: number
  email: string | null
  username: string
  full_name: string | null
  platform_role: string
  is_active: boolean
  last_login: string | null
}

export interface PlatformAdminUser {
  id: number
  email: string
  username: string
  full_name: string | null
  platform_role: string
  is_active: boolean
  last_login: string | null
}

export interface PlatformAdminInviteResponse {
  id: number
  email: string
  temp_password: string
  platform_role: string
}

export interface PlatformAdminManualCreatePayload {
  email: string
  full_name?: string
  platform_role: 'SUPERADMIN' | 'SUPPORT'
  password: string
}

export interface PlatformAdminManualCreateResponse {
  user_id: number
  email: string
  platform_role: string
  created_at: string | null
}

export interface Module {
  key: string
  name: string
  description: string | null
  scope: string
  status: string
}

// Alias used by M7 (PlatformModules); matches the contract documented in the
// platform admin pack plan ("PlatformModuleDef").
export type PlatformModuleDef = Module

export interface ModuleDependencies {
  module_key: string
  presets: Array<{ id: number; industry_type: string; display_name: string }>
  orgs: Array<{ id: number; name: string }>
}

export interface OrgModule {
  key: string
  name: string
  scope: string
  status: string
  is_enabled: boolean
  plan_minimo: string | null
  permitido_por_plan: boolean
}

export interface Plan {
  clave: string
  nombre: string
  lema: string
  precio_mxn: number
  precio_desde: boolean
  max_usuarios: number | null
  max_sucursales_venta: number | null
  modulos_crecimiento: string[]
  permite_todo: boolean
}

export interface PlanUso {
  plan: Plan
  usuarios_activos: number
  sucursales_venta: number
  modulos_fuera_de_plan: string[]
}

export const NOMBRE_PLAN: Record<string, string> = {
  FREE: 'ONE FREE', START: 'ONE START', PRO: 'ONE PRO', BUSINESS: 'BUSINESS', SCALE: 'SCALE', ULTRA_PLUS: 'ULTRA+',
}
export const nombrePlan = (clave: string | null | undefined) => NOMBRE_PLAN[clave ?? 'FREE'] ?? (clave || 'ONE FREE')

export interface IndustryPreset {
  id: number
  industry_type: string
  display_name: string
  description: string | null
  modules: string[]
  is_system: boolean
  is_deprecated?: boolean
}

// ── Module Upsell System (2026-05-13) ───────────────────────────────────────

export interface UpsellRecommendation {
  module_key: string
  module_name: string
  description: string | null
  category: 'base' | 'advanced' | 'vertical' | null
  status: 'STABLE' | 'BETA'
  in_recommended_preset: boolean
  recommended_presets: string[]
  value_props: string[]
  upgrade_prompt: string | null
  icon: string | null
  sort_hint: number
  plan_minimo: string | null
}

export interface UpsellResponse {
  org_id: number
  active_preset: string | null
  active_modules: string[]
  recommendations: UpsellRecommendation[]
  grouped_by_preset: Record<string, string[]>
}

// ── Announcements (Sprint 1 · D4) ────────────────────────────────────────────

export type AnnouncementSeverity = 'info' | 'warning' | 'critical' | 'success'
export type AnnouncementStatus = 'draft' | 'published' | 'expired'

export interface AnnouncementTargets {
  industries?: string[]
  plans?: string[]
  org_ids?: number[]
}

export interface PlatformAnnouncement {
  id: number
  title: string
  body_md: string
  severity: AnnouncementSeverity
  targets: AnnouncementTargets | null
  published_at: string | null
  expires_at: string | null
  created_by: number | null
  created_at: string | null
  updated_at: string | null
  status: AnnouncementStatus
}

export interface AnnouncementCreatePayload {
  title: string
  body_md: string
  severity: AnnouncementSeverity
  targets?: AnnouncementTargets
  expires_at?: string | null
  publish_now?: boolean
}

export interface AnnouncementUpdatePayload {
  title?: string
  body_md?: string
  severity?: AnnouncementSeverity
  targets?: AnnouncementTargets
  expires_at?: string | null
}

// ── Health matrix (Sprint 1 · A2) ────────────────────────────────────────────

export interface HealthRow {
  organization_id: number
  name: string
  industry_type: string | null
  is_active: boolean
  last_sale_at: string | null
  days_since_last_sale: number | null
  sales_count_7d: number
  sales_count_30d: number
  revenue_7d: number
  revenue_30d: number
  active_users_7d: number
  total_users: number
  total_branches: number
  modules_enabled: number
  modules_total: number
  errors_24h: number
  health_score: number
}

// ── API ──────────────────────────────────────────────────────────────────────

export const platformApi = {
  // Stats
  globalStats: () =>
    client.get<GlobalStats>('/platform/stats/global').then((r) => r.data),

  trends: () =>
    client.get<TrendsResponse>('/platform/stats/trends').then((r) => r.data),

  industryDistribution: () =>
    client.get<{ industry: string; count: number }[]>('/platform/stats/industry-distribution').then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  topTenants: (limit = 5) =>
    client.get<TopTenant[]>(
      `/platform/stats/top-tenants?limit=${limit}`
    ).then((r) => Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []),

  // Organizations
  getOrgs: (params?: { include_archived?: boolean }) =>
    client.get<PlatformOrg[]>('/platform/organizations', { params }).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  getOrgDependencies: (id: number) =>
    client.get<OrgDependencies>(`/platform/organizations/${id}/dependencies`).then((r) => r.data),

  archiveOrg: (id: number) =>
    client.post(`/platform/organizations/${id}/archive`).then((r) => r.data),

  unarchiveOrg: (id: number) =>
    client.post(`/platform/organizations/${id}/unarchive`).then((r) => r.data),

  getOrg: (id: number) =>
    client.get<PlatformOrg>(`/platform/organizations/${id}`).then((r) => r.data),

  createOrg: (data: Partial<PlatformOrg>) =>
    client.post<PlatformOrg>('/platform/organizations', data).then((r) => r.data),

  updateOrg: (id: number, data: Partial<PlatformOrg>) =>
    client.put<PlatformOrg>(`/platform/organizations/${id}`, data).then((r) => r.data),

  deleteOrg: (id: number, force?: boolean) =>
    client.delete(`/platform/organizations/${id}${force ? '?force=true' : ''}`).then((r) => r.data),

  suspendOrg: (id: number) =>
    client.post(`/platform/organizations/${id}/suspend`).then((r) => r.data),

  activateOrg: (id: number) =>
    client.post(`/platform/organizations/${id}/activate`).then((r) => r.data),

  bootstrapOrg: (id: number) =>
    client.post<{ message: string }>(`/platform/organizations/${id}/bootstrap`).then((r) => r.data),

  exportOrg: (id: number) =>
    client.get(`/platform/organizations/${id}/export`).then((r) => r.data),

  setIndustry: (id: number, industry_type: string) =>
    client.patch(`/platform/organizations/${id}/industry?industry_type=${industry_type}`).then((r) => r.data),

  applyPreset: (id: number) =>
    client.post(`/platform/organizations/${id}/apply-preset`).then((r) => r.data),

  resetPreset: (id: number) =>
    client.post(`/platform/organizations/${id}/reset-preset`).then((r) => r.data),

  addAdmin: (id: number, data: { username: string; password: string; full_name?: string; email?: string }) =>
    client.post(`/platform/organizations/${id}/admins`, data).then((r) => r.data),

  // Org modules
  getOrgModules: (orgId: number) =>
    client.get<OrgModule[]>(`/platform/organizations/${orgId}/modules`).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  getPlans: () => client.get<Plan[]>('/platform/plans').then((r) => r.data),
  getPlanUso: (orgId: number) => client.get<PlanUso>(`/platform/organizations/${orgId}/plan-uso`).then((r) => r.data),

  toggleModule: (orgId: number, moduleKey: string, enable: boolean) =>
    client.patch(`/platform/organizations/${orgId}/modules/${moduleKey}?enable=${enable}`).then((r) => r.data),

  // Branches
  getBranches: (orgId?: number, params?: { include_archived?: boolean }) =>
    client.get<PlatformBranch[]>('/platform/branches', {
      params: { ...(orgId ? { organization_id: orgId } : {}), ...(params ?? {}) },
    }).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  getBranchDependencies: (id: number) =>
    client.get<BranchDependencies>(`/platform/branches/${id}/dependencies`).then((r) => r.data),

  archiveBranch: (id: number) =>
    client.post(`/platform/branches/${id}/archive`).then((r) => r.data),

  unarchiveBranch: (id: number) =>
    client.post(`/platform/branches/${id}/unarchive`).then((r) => r.data),

  createBranch: (data: Partial<PlatformBranch> & { organization_id: number }) =>
    client.post<PlatformBranch>('/platform/branches', data).then((r) => r.data),

  updateBranch: (id: number, data: Partial<PlatformBranch>) =>
    client.put<PlatformBranch>(`/platform/branches/${id}`, data).then((r) => r.data),

  deleteBranch: (id: number, force?: boolean) =>
    client.delete(`/platform/branches/${id}${force ? '?force=true' : ''}`).then((r) => r.data),

  // Users
  getUsers: (params?: { organization_id?: number; branch_id?: number; include_inactive?: boolean }): Promise<PlatformUser[]> =>
    client.get<PlatformUser[]>('/platform/users', { params }).then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []) as PlatformUser[]
    ),

  createUser: (data: Partial<PlatformUser> & { password: string }) =>
    client.post<PlatformUser>('/platform/users', data).then((r) => r.data),

  updateUser: (id: number, data: Partial<PlatformUser>) =>
    client.put<PlatformUser>(`/platform/users/${id}`, data).then((r) => r.data),

  deleteUser: (id: number, force?: boolean) =>
    client.delete(`/platform/users/${id}${force ? '?force=true' : ''}`).then((r) => r.data),

  getUserDependencies: (id: number) =>
    client.get<{
      organizations: number
      branch_assignments: number
      sales_created: number
      cash_sessions: number
      quotes_created: number
      expenses_created: number
    }>(`/platform/users/${id}/dependencies`).then((r) => r.data),

  resetUserPassword: (id: number) =>
    client.post<{ id: number; email: string | null; temp_password: string }>(
      `/platform/users/${id}/reset-password`,
      {},
    ).then((r) => r.data),

  changeUserRole: (id: number, role: string) =>
    client.patch<{ id: number; role: string }>(
      `/platform/users/${id}/role`,
      { role },
    ).then((r) => r.data),

  // Modules catalog
  getModulesCatalog: () =>
    client.get<Module[]>('/platform/modules/catalog').then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  createModule: (body: { key: string; name: string; description?: string; scope?: string; status?: string }) =>
    client.post<PlatformModuleDef>('/platform/modules', body).then((r) => r.data),

  updateModule: (key: string, body: Partial<{ name: string; description: string; scope: string; status: string }>) =>
    client.put<PlatformModuleDef>(`/platform/modules/${key}`, body).then((r) => r.data),

  deleteModule: (key: string) =>
    client.delete(`/platform/modules/${key}`).then((r) => r.data),

  getModuleDependencies: (key: string) =>
    client.get<ModuleDependencies>(`/platform/modules/${key}/dependencies`).then((r) => r.data),

  /** Conteos agregados de presets/orgs por módulo en UNA sola query.
   *  Reemplaza N llamadas paralelas a /modules/{key}/dependencies. */
  getModulesCounts: () =>
    client.get<Record<string, { presets: number; orgs: number }>>(
      '/platform/modules/counts'
    ).then((r) => r.data ?? {}),

  // Presets
  getPresets: () =>
    client.get<IndustryPreset[]>('/platform/presets').then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []
    ),

  createPreset: (data: Partial<IndustryPreset>) =>
    client.post<IndustryPreset>('/platform/presets', data).then((r) => r.data),

  updatePreset: (id: number, data: Partial<IndustryPreset>) =>
    client.put<IndustryPreset>(`/platform/presets/${id}`, data).then((r) => r.data),

  deletePreset: (id: number) =>
    client.delete(`/platform/presets/${id}`).then((r) => r.data),

  // Upsell recommendations
  getUpsellRecommendations: (orgId: number) =>
    client.get<UpsellResponse>(`/platform/organizations/${orgId}/upsell-recommendations`)
      .then((r) => r.data),

  // Audit
  getAuditLogs: (params?: {
    start_date?: string
    end_date?: string
    actor_user_id?: number
    action?: string
    entity_type?: string
    limit?: number
    offset?: number
    skip?: number
  }): Promise<{ items: AuditLog[]; total: number }> =>
    client.get<{ items: AuditLog[]; total: number } | AuditLog[]>('/platform/audit/logs', { params }).then((r) => {
      if (Array.isArray(r.data)) return { items: r.data, total: r.data.length }
      return { items: (r.data as any)?.items ?? [], total: (r.data as any)?.total ?? 0 }
    }),

  // Platform admins (used by audit log filters and admins page)
  getPlatformAdmins: (): Promise<PlatformAdmin[]> =>
    client.get<PlatformAdmin[]>('/platform/admins').then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []) as PlatformAdmin[]
    ),

  // M8 — Admins CRUD
  listPlatformAdmins: (): Promise<PlatformAdminUser[]> =>
    client.get<PlatformAdminUser[]>('/platform/admins').then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []) as PlatformAdminUser[]
    ),

  invitePlatformAdmin: (body: { email: string; full_name?: string; platform_role: string; temp_password?: string }) =>
    client.post<PlatformAdminInviteResponse>('/platform/admins', body).then((r) => r.data),

  changePlatformAdminRole: (id: number, platform_role: string) =>
    client.patch(`/platform/admins/${id}/role`, { platform_role }).then((r) => r.data),

  revokePlatformAdmin: (id: number) =>
    client.delete(`/platform/admins/${id}`).then((r) => r.data),

  createPlatformAdminManual: async (body: PlatformAdminManualCreatePayload): Promise<PlatformAdminManualCreateResponse> => {
    const { data } = await client.post('/platform/admins/manual', body)
    return data
  },

  // Impersonation (support context)
  impersonate: (orgId: number, reason: string) =>
    client.post(`/platform/impersonate?org_id=${orgId}&reason=${encodeURIComponent(reason)}`).then((r) => r.data),

  exitImpersonate: () =>
    client.post('/platform/impersonate/exit').then((r) => r.data),

  // Health matrix (Sprint 1 · A2)
  healthMatrix: (): Promise<HealthRow[]> =>
    client.get<HealthRow[]>('/platform/health/matrix').then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? []) as HealthRow[]
    ),

  // ─── F3: Metrics expansion (2026-04-30) ────────────────────────────────
  kpisExtended: async (range: StatsRange = '30d'): Promise<KpisExtendedResponse> => {
    const { data } = await client.get(`/platform/stats/kpis-extended`, { params: { range } })
    return data
  },
  trendsMulti: async (range: StatsRange = '30d', series?: string[]): Promise<TrendsMultiResponse> => {
    const params: any = { range }
    if (series && series.length) params.series = series.join(',')
    const { data } = await client.get(`/platform/stats/trends-multi`, { params })
    return data
  },
  tenantSizeDistribution: async (): Promise<TenantSizeBucket[]> => {
    const { data } = await client.get(`/platform/stats/tenant-size-distribution`)
    return Array.isArray(data) ? data : (data?.items ?? [])
  },
  branchDistribution: async (): Promise<BranchBucket[]> => {
    const { data } = await client.get(`/platform/stats/branch-distribution`)
    return Array.isArray(data) ? data : (data?.items ?? [])
  },
  topBranches: async (limit = 10): Promise<TopBranchRow[]> => {
    const { data } = await client.get(`/platform/stats/top-branches`, { params: { limit } })
    return Array.isArray(data) ? data : (data?.items ?? [])
  },
  topProducts: async (limit = 10, range: StatsRange = '30d'): Promise<TopProductRow[]> => {
    const { data } = await client.get(`/platform/stats/top-products`, { params: { limit, range } })
    return Array.isArray(data) ? data : (data?.items ?? [])
  },
  cohortRetention: async (): Promise<CohortRow[]> => {
    const { data } = await client.get(`/platform/stats/cohort-retention`)
    return Array.isArray(data) ? data : (data?.items ?? [])
  },
  activityHeatmap: async (range: StatsRange = '30d'): Promise<HeatmapResponse> => {
    const { data } = await client.get(`/platform/stats/activity-heatmap`, { params: { range } })
    return data
  },
  paymentMethods: async (range: StatsRange = '30d'): Promise<PaymentMethodsResponse> => {
    const { data } = await client.get(`/platform/stats/payment-methods`, { params: { range } })
    return data
  },
  branchComparison: async (limit = 5, range: StatsRange = '30d'): Promise<BranchComparisonResponse> => {
    const { data } = await client.get(`/platform/stats/branch-comparison`, { params: { limit, range } })
    return data
  },
}

// ── Announcements API (Sprint 1 · D4) ────────────────────────────────────────

export interface TenantAnnouncement {
  id: number
  title: string
  body_md: string
  severity: AnnouncementSeverity
  published_at: string | null
  expires_at: string | null
}

export const announcementsApi = {
  /** Avisos vigentes para la organizacion en sesion, vistos por el inquilino.
   *  Vive fuera de /platform/* porque ese paquete exige rol de plataforma:
   *  `active` (abajo) sigue siendo la vista previa del superadministrador. */
  activeForTenant: () =>
    client.get<TenantAnnouncement[]>('/announcements/active').then((r) =>
      Array.isArray(r.data) ? r.data : [],
    ),

  list: (params?: { status?: 'draft' | 'published' | 'expired' | 'all'; severity?: AnnouncementSeverity }) =>
    client.get<PlatformAnnouncement[]>('/platform/announcements', { params }).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? [],
    ),

  get: (id: number) =>
    client.get<PlatformAnnouncement>(`/platform/announcements/${id}`).then((r) => r.data),

  create: (body: AnnouncementCreatePayload) =>
    client.post<PlatformAnnouncement>('/platform/announcements', body).then((r) => r.data),

  update: (id: number, body: AnnouncementUpdatePayload) =>
    client.put<PlatformAnnouncement>(`/platform/announcements/${id}`, body).then((r) => r.data),

  publish: (id: number) =>
    client.post<PlatformAnnouncement>(`/platform/announcements/${id}/publish`).then((r) => r.data),

  unpublish: (id: number) =>
    client.post<PlatformAnnouncement>(`/platform/announcements/${id}/unpublish`).then((r) => r.data),

  remove: (id: number) =>
    client.delete<{ deleted: boolean; id: number }>(`/platform/announcements/${id}`).then((r) => r.data),

  active: (orgId?: number) =>
    client.get<PlatformAnnouncement[]>('/platform/announcements/active', {
      params: orgId ? { org_id: orgId } : undefined,
    }).then((r) => (Array.isArray(r.data) ? r.data : (r.data as any)?.items ?? [])),
}

// ── Incidents (Sprint 2 · D3) ────────────────────────────────────────────────

export type IncidentScopeType = 'industry' | 'plan' | 'org_ids' | 'all'
export type IncidentStatusFilter = 'active' | 'resolved' | 'all'

export interface IncidentAffectedSnapshotEntry {
  id: number
  name: string
  was_active: boolean
  was_status: string
}

export interface IncidentAffectedDetail {
  id: number
  name: string
  was_active: boolean
  was_status: string
  current_status: string | null
  current_is_active: boolean | null
}

export interface PlatformIncident {
  id: number
  title: string
  reason: string | null
  scope_type: IncidentScopeType
  scope_value: string | null
  banner_html: string | null
  started_at: string | null
  started_by: number | null
  resolved_at: string | null
  resolved_by: number | null
  affected_count: number
  affected_snapshot: IncidentAffectedSnapshotEntry[] | null
  affected: Array<{ id: number; name: string }> | IncidentAffectedDetail[] | null
  is_active: boolean
}

export interface IncidentCreatePayload {
  title: string
  reason?: string | null
  scope_type: IncidentScopeType
  scope_value?: string | null
  banner_html?: string | null
}

export interface IncidentResolveResult {
  id: number
  restored: number
  skipped: number
  resolved_at: string | null
}

export const incidentsApi = {
  list: (status: IncidentStatusFilter = 'active'): Promise<PlatformIncident[]> =>
    client.get<PlatformIncident[]>('/platform/incidents', { params: { status } }).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as { items?: PlatformIncident[] })?.items ?? []
    ),

  get: (id: number): Promise<PlatformIncident> =>
    client.get<PlatformIncident>(`/platform/incidents/${id}`).then((r) => r.data),

  create: (body: IncidentCreatePayload, force = false): Promise<PlatformIncident> =>
    client.post<PlatformIncident>('/platform/incidents', body, {
      params: force ? { force: true } : undefined,
    }).then((r) => r.data),

  resolve: (id: number): Promise<IncidentResolveResult> =>
    client.post<IncidentResolveResult>(`/platform/incidents/${id}/resolve`).then((r) => r.data),
}

// ── Alerts (anomaly detection · Sprint 1 · A3) ──────────────────────────────

export interface AlertsListParams {
  severity?: 'critical' | 'warning' | 'info'
  kind?: string
  acked?: boolean
  from?: string
  to?: string
  skip?: number
  limit?: number
}

export const alertsApi = {
  listAlerts: (params?: AlertsListParams): Promise<PlatformAlert[]> =>
    client.get<{ items: PlatformAlert[]; total: number } | PlatformAlert[]>(
      '/platform/alerts',
      { params },
    ).then((r) =>
      Array.isArray(r.data) ? r.data : (r.data as { items?: PlatformAlert[] })?.items ?? []
    ),

  scanAlerts: (): Promise<PlatformAlertScanResult> =>
    client.post<PlatformAlertScanResult>('/platform/alerts/scan').then((r) => r.data),

  ackAlert: (id: number): Promise<void> =>
    client.post(`/platform/alerts/${id}/ack`).then(() => undefined),

  resolveAlert: (id: number): Promise<void> =>
    client.post(`/platform/alerts/${id}/resolve`).then(() => undefined),

  alertCounts: (): Promise<PlatformAlertCounts> =>
    client.get<PlatformAlertCounts>('/platform/alerts/counts').then((r) => r.data),
}


// ── API keys (Sprint 2 · H1) ─────────────────────────────────────────────────

/** Safe display shape — server NEVER returns `hashed_key`. */
export interface ApiKey {
  id: number
  organization_id: number
  org_name: string | null
  name: string
  prefix: string
  scopes: string[] | null
  last_used_at: string | null
  last_used_ip: string | null
  created_at: string | null
  created_by: number | null
  revoked_at: string | null
  revoked_by: number | null
}

/** One-time payload returned by `POST /api-keys` — includes the full key. */
export interface ApiKeyCreateResponse {
  id: number
  organization_id: number
  org_name: string | null
  name: string
  prefix: string
  scopes: string[]
  created_at: string | null
  full_key: string
}

export interface ApiKeyCreatePayload {
  organization_id: number
  name: string
  scopes?: string[]
}

export interface ApiKeyListParams {
  organization_id?: number
  /** true = only active (non-revoked); false = only revoked; undefined = all */
  active?: boolean
  q?: string
}

export const API_KEY_SCOPES = [
  'read:all',
  'write:sales',
  'write:inventory',
  'admin:all',
] as const

export type ApiKeyScope = typeof API_KEY_SCOPES[number]

export const apiKeysApi = {
  list: (params?: ApiKeyListParams): Promise<ApiKey[]> =>
    client.get<ApiKey[]>('/platform/api-keys', { params }).then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as { items?: ApiKey[] })?.items ?? []) as ApiKey[]
    ),

  listForOrg: (orgId: number): Promise<ApiKey[]> =>
    client.get<ApiKey[]>(`/platform/api-keys/for-org/${orgId}`).then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as { items?: ApiKey[] })?.items ?? []) as ApiKey[]
    ),

  get: (id: number): Promise<ApiKey> =>
    client.get<ApiKey>(`/platform/api-keys/${id}`).then((r) => r.data),

  create: (body: ApiKeyCreatePayload): Promise<ApiKeyCreateResponse> =>
    client.post<ApiKeyCreateResponse>('/platform/api-keys', body).then((r) => r.data),

  revoke: (id: number): Promise<ApiKey> =>
    client.post<ApiKey>(`/platform/api-keys/${id}/revoke`).then((r) => r.data),

  remove: (id: number): Promise<{ deleted: boolean; id: number }> =>
    client.delete<{ deleted: boolean; id: number }>(`/platform/api-keys/${id}`).then((r) => r.data),
}

// ── Feature flags (Sprint 2 · F1) ────────────────────────────────────────────

export interface FeatureFlag {
  key: string
  description: string | null
  default_enabled: boolean
  rollout_pct: number
  is_killed: boolean
  overrides_count: number
  enabled_orgs_count: number | null
  created_at: string | null
  updated_at: string | null
}

export interface FeatureFlagCreatePayload {
  key: string
  description?: string | null
  default_enabled?: boolean
  rollout_pct?: number
}

export interface FeatureFlagUpdatePayload {
  description?: string | null
  default_enabled?: boolean
  rollout_pct?: number
  is_killed?: boolean
}

export interface OrgFeatureOverride {
  id: number
  organization_id: number
  organization_name: string | null
  flag_key: string
  enabled: boolean
  reason: string | null
  created_at: string | null
  created_by: number | null
}

export interface FlagOverrideUpsertPayload {
  enabled: boolean
  reason?: string | null
}

export type FlagResolveSource = 'override' | 'killed' | 'rollout' | 'default'

export interface FlagResolvePreview {
  flag_key: string
  organization_id: number
  organization_name: string
  resolved: boolean
  source: FlagResolveSource
  reason: string
}

export const flagsApi = {
  list: (): Promise<FeatureFlag[]> =>
    client.get<FeatureFlag[]>('/platform/flags').then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as { items?: FeatureFlag[] })?.items ?? []) as FeatureFlag[]
    ),

  create: (body: FeatureFlagCreatePayload): Promise<FeatureFlag> =>
    client.post<FeatureFlag>('/platform/flags', body).then((r) => r.data),

  update: (key: string, body: FeatureFlagUpdatePayload): Promise<FeatureFlag> =>
    client.patch<FeatureFlag>(`/platform/flags/${encodeURIComponent(key)}`, body).then((r) => r.data),

  remove: (key: string): Promise<{ deleted: boolean; key: string; overrides_deleted: number }> =>
    client.delete<{ deleted: boolean; key: string; overrides_deleted: number }>(
      `/platform/flags/${encodeURIComponent(key)}`,
    ).then((r) => r.data),

  listOverrides: (key: string): Promise<OrgFeatureOverride[]> =>
    client.get<OrgFeatureOverride[]>(
      `/platform/flags/${encodeURIComponent(key)}/overrides`,
    ).then((r) =>
      (Array.isArray(r.data) ? r.data : (r.data as { items?: OrgFeatureOverride[] })?.items ?? []) as OrgFeatureOverride[]
    ),

  upsertOverride: (
    key: string,
    orgId: number,
    body: FlagOverrideUpsertPayload,
  ): Promise<OrgFeatureOverride> =>
    client.put<OrgFeatureOverride>(
      `/platform/flags/${encodeURIComponent(key)}/overrides/${orgId}`,
      body,
    ).then((r) => r.data),

  removeOverride: (
    key: string,
    orgId: number,
  ): Promise<{ deleted: boolean; flag_key: string; organization_id: number }> =>
    client.delete<{ deleted: boolean; flag_key: string; organization_id: number }>(
      `/platform/flags/${encodeURIComponent(key)}/overrides/${orgId}`,
    ).then((r) => r.data),

  preview: (key: string, orgId: number): Promise<FlagResolvePreview> =>
    client.get<FlagResolvePreview>(
      `/platform/flags/${encodeURIComponent(key)}/preview`,
      { params: { org_id: orgId } },
    ).then((r) => r.data),

  resolved: (orgId: number): Promise<Record<string, boolean>> =>
    client.get<Record<string, boolean>>('/platform/flags/resolved', {
      params: { org_id: orgId },
    }).then((r) => r.data ?? {}),
}

// ─── F3: Metrics expansion (2026-04-30) ─────────────────────────────────

export interface MetricSpark {
  total?: number
  value?: number
  delta_pct: number | null
  spark: number[]
}

export interface KpisExtendedResponse {
  range: string
  revenue: MetricSpark
  sales_count: MetricSpark
  aov: MetricSpark
  active_tenants: MetricSpark
  active_branches: MetricSpark
  mrr_proxy: MetricSpark
  activation_rate: MetricSpark
  suspension_rate: MetricSpark
}

export interface TrendsMultiPoint {
  date: string
  label: string
  revenue: number
  sales: number
  signups: number
}

export interface TrendsMultiResponse {
  range: string
  points: TrendsMultiPoint[]
}

export interface TenantSizeBucket {
  bucket: 'S' | 'M' | 'L'
  label: string
  count: number
  revenue_total: number
}

export interface BranchBucket {
  bucket: string
  label: string
  count: number
}

export interface TopBranchRow {
  branch_id: number
  branch_name: string
  org_id: number
  org_name: string
  revenue_30d: number
  sales_count_30d: number
}

export interface TopProductRow {
  product_id: string
  product_name: string
  variant_description: string | null
  sku: string | null
  quantity_sold: number
  revenue: number
  org_count: number
}

export interface CohortRow {
  cohort: string
  cohort_label: string
  size: number
  ret_30d: number | null
  ret_60d: number | null
  ret_90d: number | null
  ret_180d: number | null
}

export interface HeatmapCell {
  dow: number
  hour: number
  count: number
}

export interface HeatmapResponse {
  range: string
  cells: HeatmapCell[]
  max_count: number
}

export type StatsRange = '7d' | '30d' | '90d' | 'ytd'

export interface PaymentMethodRow {
  method: 'CASH' | 'CARD' | 'TRANSFER' | 'STORE_CREDIT' | 'CHECK' | 'OTHER' | string
  label: string
  count: number
  revenue: number
  pct: number
}

export interface PaymentMethodsResponse {
  range: string
  total_revenue: number
  total_count: number
  items: PaymentMethodRow[]
}

export interface BranchComparisonRow {
  branch_id: number
  branch_name: string
  org_id: number
  org_name: string
  revenue: number
  sales_count: number
  aov: number
  peak_hour: number | null
  peak_hour_count: number
}

export interface BranchComparisonResponse {
  range: string
  items: BranchComparisonRow[]
}

// ─── F4: Reports module (2026-04-30) ──────────────────────────────────────

export const reportApi = {
  getProducts: async (params: ReportParams): Promise<PaginatedReport<ProductRow>> => {
    const { data } = await client.get('/platform/reports/products', { params })
    return data
  },
  getBranches: async (params: ReportParams): Promise<PaginatedReport<BranchRow>> => {
    const { data } = await client.get('/platform/reports/branches', { params })
    return data
  },
  getSellers: async (params: ReportParams): Promise<PaginatedReport<SellerRow>> => {
    const { data } = await client.get('/platform/reports/sellers', { params })
    return data
  },
  getCustomers: async (params: ReportParams): Promise<PaginatedReport<CustomerRow>> => {
    const { data } = await client.get('/platform/reports/customers', { params })
    return data
  },
  getProductDetail: async (
    id: string,
    params: Omit<ReportParams, 'sort'>,
  ): Promise<ProductDetailResponse> => {
    const { data } = await client.get(`/platform/reports/products/${id}/detail`, { params })
    return data
  },
  getBranchDetail: async (
    id: number,
    params: Omit<ReportParams, 'sort'>,
  ): Promise<BranchDetailResponse> => {
    const { data } = await client.get(`/platform/reports/branches/${id}/detail`, { params })
    return data
  },
  getSellerDetail: async (
    id: number,
    params: Omit<ReportParams, 'sort'>,
  ): Promise<SellerDetailResponse> => {
    const { data } = await client.get(`/platform/reports/sellers/${id}/detail`, { params })
    return data
  },
  getCustomerDetail: async (
    id: number,
    params: Omit<ReportParams, 'sort'>,
  ): Promise<CustomerDetailResponse> => {
    const { data } = await client.get(`/platform/reports/customers/${id}/detail`, { params })
    return data
  },
  exportProductsCsv: async (params: ReportParams): Promise<void> =>
    downloadCsv('/platform/reports/products.csv', params, 'productos'),
  exportBranchesCsv: async (params: ReportParams): Promise<void> =>
    downloadCsv('/platform/reports/branches.csv', params, 'sucursales'),
  exportSellersCsv: async (params: ReportParams): Promise<void> =>
    downloadCsv('/platform/reports/sellers.csv', params, 'vendedores'),
  exportCustomersCsv: async (params: ReportParams): Promise<void> =>
    downloadCsv('/platform/reports/customers.csv', params, 'clientes'),
}

async function downloadCsv(url: string, params: any, baseName: string): Promise<void> {
  const resp = await client.get(url, { params, responseType: 'blob' })
  const blob = new Blob([resp.data], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  a.href = objectUrl
  a.download = `report_${baseName}_${new Date().toISOString().split('T')[0]}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objectUrl)
}

