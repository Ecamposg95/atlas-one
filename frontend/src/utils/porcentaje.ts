/** Porcentaje de `parte` sobre `total`, redondeado a un decimal; 0 cuando no hay total. */
export function porcentaje(parte: number, total: number): number {
  if (!(total > 0)) return 0
  return Math.round((parte / total) * 1000) / 10
}
