import { describe, expect, it } from 'vitest'
import { sortByName } from '../sortByName'

describe('sortByName', () => {
  it('ordena alfabeticamente sin importar mayusculas/minusculas', () => {
    const items = [{ name: 'zapatos' }, { name: 'Bolsas' }, { name: 'abrigos' }]
    expect(sortByName(items).map((i) => i.name)).toEqual(['abrigos', 'Bolsas', 'zapatos'])
  })

  it('ordena acentos junto a su letra base', () => {
    const items = [{ name: 'Zapatos' }, { name: 'Ábaco' }, { name: 'Bolsas' }]
    expect(sortByName(items).map((i) => i.name)).toEqual(['Ábaco', 'Bolsas', 'Zapatos'])
  })

  it('no muta el arreglo de entrada', () => {
    const items = [{ name: 'zapatos' }, { name: 'abrigos' }]
    const original = [...items]
    sortByName(items)
    expect(items).toEqual(original)
  })
})
