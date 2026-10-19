export type Role =
  | 'ADMINISTRADOR'
  | 'DUEÑO'
  | 'GERENTE'
  | 'CAJERO'
  | 'VENDEDOR'
  | 'SOPORTE_OPERATIVO'
  | 'CLIENTE'

export type PlatformRole = 'SUPERADMIN' | 'SUPPORT' | 'NONE'

export type BranchType = 'HQ' | 'STORE' | 'WAREHOUSE' | 'OFFICE'

export interface Branch {
  id: number
  name: string
  branch_type: BranchType
  is_headquarters: boolean
}

export interface Organization {
  id: number
  name: string
  industry_type: string | null
  hq_branch_id: number | null
}

/** Plan comercial de la organización activa, tal como lo manda `/users/me/context`. */
export interface PlanOrg {
  clave: string
  nombre: string
}

export interface User {
  id: number
  username: string
  email: string | null
  full_name: string | null
  role: Role
  platform_role: PlatformRole
  branch_id: number | null
  branch_name?: string | null
  organization_id: number | null
  is_active: boolean
  created_at?: string | null
}

export interface AuthState {
  user: User | null
  token: string | null
  org: Organization | null
  branch: Branch | null
}
