# Cliente en el POS de escritorio — diseño

**Problema.** La cajera no tiene dónde poner el nombre del cliente en el POS de
escritorio. `CustomerSelector.tsx` existe pero ningún panel lo monta (código muerto
desde el rediseño); el carrito solo muestra el nombre cuando la venta viene de un
ticket pausado que ya traía `customer_id`; el cobro manda solo `customer_id` y nunca
`customer_name`, así que hasta una venta con cliente de CRM se guarda con
`customer_name = NULL` y el historial/ticket dicen "Público general". El ticket
térmico no imprime al cliente en ningún caso.

**Objetivo.** Desde el carrito, con un toque, la cajera elige un cliente del CRM
(búsqueda por nombre/teléfono), lo crea rápido (nombre + teléfono), o escribe solo
un nombre libre. El nombre viaja en la venta (`customer_name`), se imprime en el
ticket, sobrevive a pausar/reanudar, y se limpia al terminar cada venta.

**Decisiones.**
- El nombre libre va en `customer_name` sin crear cliente en CRM. `customer_id`
  queda null. Es el mismo contrato que ya acepta `SaleCreate`.
- Si llega `customer_id` sin `customer_name`, el backend rellena el nombre desde el
  registro del cliente de la misma organización. Un solo bloque nuevo en
  `create_sale`, sin tocar totales ni pagos.
- El ticket imprime `Cliente: <nombre>` como cuarta línea del encabezado solo cuando
  hay nombre y no es "Público General" (comparación sin mayúsculas/espacios).
- Un modal único (`CustomerModal`) reemplaza a `CustomerSelector`, que se borra.
  Un solo campo de texto sirve para buscar y como nombre libre: debajo aparecen los
  resultados del CRM; el pie ofrece "Usar solo el nombre" (siempre que haya texto)
  y "Guardar en clientes" (crea con nombre + teléfono opcional). Si la búsqueda del
  CRM falla (módulo apagado, sin permiso, sin red) el modal sigue sirviendo para el
  nombre libre: nunca bloquea el cobro.
- Pausar guarda `customer_name` dentro de `cart_json`; reanudar lo restaura junto
  con `customer_id`. No hay cambio de esquema.
- Nada de esto cambia el flujo de cobro cuando no se elige cliente: el payload es
  idéntico al de hoy salvo que `customer_name` viaja solo si hay texto.

**Fuera de alcance.** Editar cliente, crédito, historial de compras del cliente en
el modal, POS móvil (ya tiene su buscador).
