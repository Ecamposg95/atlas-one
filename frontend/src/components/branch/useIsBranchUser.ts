import { useAuthStore } from '../../store/authStore'

const BRANCH_ROLES = new Set(['CAJERO', 'GERENTE', 'VENDEDOR'])

export function useIsBranchUser(): boolean {
  const user = useAuthStore((s) => s.user)
  if (!user) return false
  return BRANCH_ROLES.has(user.role) && user.branch_id != null
}
