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

// El padding y el tamaño base los ponen las clases dax-btn-*; `md` no añade nada.
const sizeMap = {
  sm: 'text-xs',
  md: '',
  lg: 'text-sm px-6 py-3',
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
