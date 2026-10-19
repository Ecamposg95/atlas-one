import { Component, type ReactNode } from 'react'

interface Props {
  /** Se llama una vez cuando un hijo falla (p. ej. un chunk `lazy()` que no cargó). */
  onError: (error: unknown) => void
  children: ReactNode
}

/**
 * Límite de error mínimo: contiene el fallo de un hijo para que no tire todo el
 * árbol (y con él el carrito abierto del POS). Al fallar no pinta nada.
 */
export class LimiteDeError extends Component<Props, { fallo: boolean }> {
  state = { fallo: false }

  static getDerivedStateFromError() {
    return { fallo: true }
  }

  componentDidCatch(error: unknown) {
    this.props.onError(error)
  }

  render() {
    return this.state.fallo ? null : this.props.children
  }
}
