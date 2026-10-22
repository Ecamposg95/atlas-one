// Parámetros del tablero de Reportes según el perfil y el rol (modo básico).
// En básico la dueña (ADMINISTRADOR/DUEÑO) ve la org entera (`branch_id: 0`,
// igual que el Inicio) y "Semana" son 7 días contando hoy ("Últimos 7
// días"). Cajeras, gerentes y el perfil completo conservan el comportamiento
// de siempre.

export interface ParametrosReportes {
  branch_id?: 0
  /** Días hacia atrás para el inicio de "Semana". */
  diasSemana: number
}

export function parametrosReportes(perfil: 'basico' | 'completo', rol: string | null | undefined): ParametrosReportes {
  if (perfil === 'basico' && (rol === 'ADMINISTRADOR' || rol === 'DUEÑO')) {
    return { branch_id: 0, diasSemana: 6 }
  }
  return { diasSemana: 7 }
}
