# El punto de venta se adapta al giro — diseño

Fecha: 2026-09-24 · Caso guía: Eleven Fashion (boutique) y Novedades Kaory (punto de venta puro)

## 1. El problema

Una boutique de ropa y una tienda de novedades ven hoy la misma pantalla de cobro que un
restaurante. La propina está escrita fija en el carrito —con un comentario en el propio código
que dice `// Propina (gastro)`— y se muestra siempre.

La auditoría del 24/09/26 (`.superpowers/sdd/pos-presets/`) midió el alcance real:

| Medida | Valor |
|---|---|
| Elementos de pantalla en el punto de venta | 244 |
| De esos, sin ningún control (ni módulo, ni rol, ni dato) | 93 |
| Endpoints que consume el punto de venta | 56 |
| De esos, sin candado de módulo | 31 |
| Llamadas a `require_module` en TODA la aplicación | 9 |
| Capacidades del catálogo que alguien realmente comprueba | 6 de 37 |

El hallazgo que lo resume: **el punto de venta no consulta módulos ni una sola vez en sus 8,877
líneas**. El mecanismo existe y lo usan el menú lateral y dos formularios de producto; la pantalla
donde se cobra no lo toca.

Lo que eso produce hoy, con datos de producción:

- **Propina** en una boutique. Se suma a lo cobrado, **no se imprime en el ticket**, y su único
  reporte vive tras el módulo `tables`, que Eleven no tiene. Sería dinero cobrado que nadie en la
  tienda puede ver. Nadie la ha usado todavía: cero ventas con propina.
- **Casilla de factura**. Marcarla **sube el cobro 16 %** sin emitir ningún comprobante. El módulo
  `invoicing` existe en el catálogo y **no se comprueba en un solo endpoint**. Ya hay una venta
  marcada así.
- **Venta por caja**, de mayoreo. No es hipotético: Eleven tiene 2 escalones con "caja" en el
  nombre y Kaory 1, así que el botón aparece de verdad.
- **Equivalente en dólares**, que se carga al entrar al punto de venta sin preguntar nada.

## 2. Las dos preguntas, que son distintas

El diseño descansa en separar dos cosas que hoy se confunden:

> **El comportamiento se decide por MÓDULO. La apariencia se decide por PRESET.**

- **Módulo** = qué puede hacer esta tienda. Se prende y se apaga por organización.
- **Preset** = a qué giro pertenece. Se elige al darla de alta y casi nunca cambia. **Su único
  trabajo es sembrar qué módulos nacen encendidos.**

De ahí sale la regla dura: **ninguna función se esconde mirando el preset.** Si algo hay que poder
apagar y no tiene módulo, se crea el módulo. Es lo que hace que el vertical número doce sea
escribir renglones y no condicionales.

Esto resuelve sin contradicción el encargo "la propina solo para restaurante, bar y cafetería": se
crea el módulo `tips` y el preset gastronómico lo siembra encendido. Si mañana una cafetería de
otra cartera lo necesita, se prende sin tocar código.

La apariencia sí es del preset, porque es una pregunta de identidad, no de capacidad. El mecanismo
ya existe: `data-preset` en `<html>` dispara variables de CSS. Hay color para 11 presets y **faltan
`ATLAS_POS`, `ATLAS_POS_BOUTIQUE` y `CUSTOM`**, que es exactamente por qué Eleven y Kaory se ven
idénticas.

## 3. El catálogo de funciones

Un solo archivo declara qué se puede apagar. Lo leen el servidor y la pantalla, así que no pueden
contradecirse.

```json
{
  "clave": "propina",
  "modulo": "tips",
  "nombre": "Propina",
  "donde": ["pos.carrito"],
  "ayuda": "Botones de 10 % y 15 % al cobrar"
}
```

**La propiedad que lo hace seguro: el catálogo es una lista blanca de lo que SÍ se puede apagar.**
Todo lo que no está en él está siempre encendido.

Esto no es una preferencia de estilo, resuelve un peligro concreto: el módulo `users` está apagado
en las cuatro tiendas reales y todas administran usuarios. Un enfoque de "ponerle candado a todo"
dejaría sin dar de alta cajeras el primer día. Con lista blanca, administrar usuarios nunca entra
al catálogo y nunca se apaga.

## 4. Cómo se resuelve en vivo

`GET /api/users/me/context` ya entrega al navegador el preset y los módulos encendidos, pero hoy
solo copia la lista cruda de la base (`app/modules/users/router.py:108-119`). Ahí se inserta la
resolución, sin una llamada más ni un mecanismo nuevo:

```
context → { preset, enabled_modules, capacidades: ["propina", "factura", ...] }
```

La pantalla pregunta `puede('propina')` y **no sabe nada de módulos**. Si mañana una función
necesita dos módulos, o un permiso, o una bandera, solo cambia el resolvedor: ningún componente se
entera.

En el servidor, un candado `require_capability('propina')` que lee el mismo catálogo. El
`require_module` actual se conserva para lo que ya gatea.

## 5. El atajo desaparece

`app/core/permissions.py:27-29` hace que ADMINISTRADOR y DUEÑO se salten **todo** `require_module`.
Se elimina. La auditoría midió qué rompe:

| Módulo | Tiendas sin él | Qué rompe |
|---|---|---|
| `pos`, `crm`, `labels` | ninguna | Nada. El cobro no se toca. |
| `variants` | Kaory, Imaltzin | Escritura de variantes. Dos llamadas del frontend no consultan el módulo: `ProductsBranchView.tsx:696` y `StoreScanner.tsx:373,602`. Hay que gatearlas. |
| `quotes` | las cuatro | Cotizaciones por URL. Impacto real cero: **no hay un solo documento de cotización en producción**. |
| `warehouse` | las cuatro | Logística por URL. **Y destapa un error de clave**: el servidor exige `warehouse` y el menú consulta `logistics`. |

Además desenmascara dos fallos latentes del propio candado, que se arreglan en la misma ola:
ignora la cabecera de organización y no exime al SUPERADMIN.

## 6. La pantalla del dueño

Una pestaña "Módulos" dentro de Empresa, junto a Datos, Ticket y Sucursales. No una pantalla
nueva: el plan del administrador va hacia tener menos pantallas.

**También se genera del catálogo.** Solo aparecen los módulos que alguna función referencia; si un
módulo no apaga nada, no confunde al dueño. Cada renglón muestra **qué se enciende con él**, sacado
del catálogo: "Mesas: enciende Propina". La dueña ve consecuencias, no claves técnicas.

Administrador y dueño pueden cambiarlo, y queda registrado quién prendió o apagó qué y cuándo.
Apagar Devoluciones no es una preferencia, es una decisión de negocio.

Lo que da tranquilidad es la combinación: el candado se vuelve real **y** la dueña recibe la llave.
No hay ventana donde quede encerrada.

## 7. Módulos

### Se crean tres

| Módulo | Qué apaga | Nace encendido en |
|---|---|---|
| `tips` | Propina en el carrito | Restaurante, bar, cafetería, gastro |
| `bulk_pricing` | Venta por caja, escalones de mayoreo, rótulos "Mayoreo" y "Caja" | Mayoreo |
| `multi_currency` | Equivalente en dólares en carrito y ticket | Solo donde se cobre en dólares |

### Uno ya existe y solo hay que usarlo

`invoicing` está en el catálogo, apagado en las cuatro tiendas, y **no se comprueba en ningún
endpoint**. Es el arreglo más barato y de mayor impacto de toda la lista.

### Lo que NO es un módulo

Las auditorías propusieron hasta once. Se podan los que no son capacidad de la tienda sino permiso
de persona o detalle del aparato:

- **Precio libre** es un permiso. No es que la boutique no lo tenga contratado, es que no cualquiera
  debe usarlo. Va por rol, como el descuento de línea.
- **Impresión y cajón de dinero** son universales. Que la impresora sea Bluetooth es del aparato.
- **Tickets pausados** los usa cualquier giro.
- **Escáner** ya tiene módulo propio.
- **Recargo de tarjeta** ya es un dato de la organización (el 4 % de Eleven).

## 8. El mapa de tiendas

| Tienda | Preset | Estado |
|---|---|---|
| Eleven Fashion | `ATLAS_POS_BOUTIQUE` | Activa. El preset se está definiendo sobre ella. |
| Novedades Kaory | `ATLAS_POS` | Activa. **Punto de venta puro**: sin clientes ni etiquetas (9 módulos). |
| Importaciones Imaltzin | `ATLAS_POS` | Activa. Preset **sin definir**; es mayoreo (937 escalones de precio). |
| Novedades Ginebra | `ATLAS_POS` | **Desactivada** el 24/09/26. Dejó de usar el sistema. |

## 9. Las olas

| Ola | Qué entrega | Se nota |
|---|---|---|
| 1 | Catálogo con las primeras funciones, color propio para los tres presets que no lo tienen, propina fuera de la boutique, y `invoicing` usado de verdad | Un día. La cajera lo ve. |
| 2 | Candados reales en el servidor, sin el atajo, uno por uno con su prueba. Incluye la clave `warehouse`/`logistics` y las dos llamadas de variantes sin gatear | Nadie lo ve, es la base |
| 3 | Pantalla donde la dueña prende y apaga módulos, con bitácora | La dueña recupera el control |
| 4 | El resto de la aplicación, incluido el lado del administrador | Cierra el trabajo |

## 10. Cómo se prueba

Tres redes, y lo importante es que **las pruebas salen del catálogo, no se escriben a mano**:
agregar una función genera sus pruebas, así que ninguna queda sin cubrir.

1. **Coherencia del catálogo.** Cada función apunta a un módulo que existe. Atrapa errores como la
   clave `warehouse` que nadie tiene.
2. **Coherencia de la pantalla.** Cada clave usada en el frontend existe en el catálogo. Atrapa que
   alguien invente una y nunca se apague.
3. **Por función, dos pruebas de servidor**: con el módulo encendido responde; apagado devuelve 403.

Más una prueba de que **un preset sin `tips` no puede cobrar propina**, que es el caso que originó
todo: hoy el servidor acepta propina de cualquier tienda y lo único que valida es que no sea
negativa (`app/routers/sales.py:827-836`).

## 11. Fuera de alcance

- **No se toca el acomodo del punto de venta.** Esconder lo que estorba sí; rediseñar dónde va cada
  cosa, no.
- **No se cambia tipografía ni iconos por giro.** Solo color, que es lo que ya existe.
- **No se le pone candado a los doce routers que no lo tienen** por el hecho de no tenerlo. Solo a
  los que representen una función del catálogo, uno por uno y con su prueba.

## 12. Hallazgos que salieron de la auditoría y NO entran aquí

Se registran para que no se pierdan. Son defectos reales, pero de otra naturaleza:

| Hallazgo | Por qué importa |
|---|---|
| **Cancelar una venta no pide supervisor** (`app/routers/sales.py`, `cancel_sale`). Reimprimir sí pide PIN; cancelar, que repone inventario y revierte deuda, no pide nada | Seguridad de dinero |
| **Las devoluciones sellan la sucursal de quien captura, no la de la venta** (`app/routers/returns.py:87`) | El efectivo sale del cajón equivocado. Solo explotable en Kaory, la única con dos sucursales |
| **67 de 67 recomendaciones de compra sin organización** | Hoy todas son de Kaory, pero una segunda tienda las mezclaría sin forma de separarlas |
| **`recipes` y `tables` nunca se suscriben** (`app/main.py:80` solo llama a abasto) | Código muerto en producción |
| **Dar de baja una tienda no corta el acceso.** `organization.is_active` no lo lee nadie; lo que corta es el usuario y su vínculo | Se descubrió al desactivar Ginebra |
| **`cash_management` y `returns` están encendidos en las cuatro tiendas y no los lee nadie** | Módulos decorativos |
