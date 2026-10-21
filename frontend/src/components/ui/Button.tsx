/**
 * Button — envoltorio de las clases `dax-btn-*` (index.css), que son la API
 * oficial de botones del kit: `dax-btn-primary` / `-secondary` / `-danger` /
 * `-ghost` (+ `dax-btn-icon` para solo-icono en teléfono). Las pantallas de
 * admin usan las clases directo; este componente lo usa gastro. El padding y el
 * tamaño base los ponen las clases; `size` solo ajusta la letra (y el padding
 * en `sm`/`lg`, como siempre). Guardia: `src/__tests__/botonesDelKit.test.ts`.
 */
import { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: string
}

const variantMap: Record<Variant, string> = {
  primary: 'dax-btn-primary',
  secondary: 'dax-btn-secondary',
  danger: 'dax-btn-danger',
  ghost: 'dax-btn-ghost',
}

// `md` solo fija la letra (14 px, como siempre): el padding ya lo ponen las clases dax-btn-*.
const sizeMap = {
  sm: 'text-xs px-3 py-1.5',
  md: 'text-sm',
  lg: 'text-base px-6 py-3',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  className = '',
  disabled,
  ...props
}: Props) {
  return (
    <button
      className={`${variantMap[variant]} ${sizeMap[size]} inline-flex items-center gap-2 ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <i className="fa fa-spinner fa-spin text-sm" />
      ) : icon ? (
        <i className={`${icon} text-sm`} />
      ) : null}
      {children}
    </button>
  )
}
