# Novedades Coqueta se muda de rmazh a Atlas ONE — diseño

Fecha: 2026-09-30 · Origen: rmazh (Data X POS, repo Atlas-Rmazh) en Railway, proyecto
"Rmazh POS" `0953bba5-3e8f-45e7-9f6d-e92055ea8a0a`, entorno `beta` · Destino: Atlas ONE en
producción (VPS IONOS, contenedor `atlas-one-prod`, base `atlas_one_prod`, `app.atlasone.com.mx`)

## 1. Qué es Coqueta hoy (verificado en solo lectura el 2026-09-30)

| Dato | Valor medido |
|---|---|
| Organización | id 10 "Novedades Coqueta", ACTIVE, giro `DATAXPOS`, 16 módulos |
| Sucursales | 26 "HQ - Novedades Coqueta" (vacía, no vende) · **27 "Sucursal Principal"** (vende, impresora `POS-80`, ticket `DETAILED`, sin encabezado ni pie) |
| Usuarios | 41 **Mirna** (ADMINISTRADOR, sucursal 26, con PIN de reimpresión) · 42 **Jose** "Jose Rivas" (CAJERO, sucursal 27, autor de las 1,463 ventas) |
| Catálogo | 218 productos = 218 variantes, 200 con código de barras, ninguno con costo nulo, 1 departamento "Ncoqueta", 1 marca "Rmazh" |
| Escalones | 219: 173 variantes con 1 y 23 con 2. Nombres: Mayoreo 186, Caja 23, Precio 1 (9), Precio 2 (1) |
| Existencias | 218 filas, todas en la sucursal 27, 387,473 piezas nominales. 63 en cero, **30 en exactamente 10,000** (relleno), 47 con más de 500 |
| Ventas | 1,463 documentos (folios 1..1463 sin huecos), 1,463 pagos (1,400 efectivo, 58 tarjeta, 5 transferencia), 1,818 líneas. Sep-26: 200 tickets, $61,108 |
| Pendientes | Caja **1862** OPEN desde 2026-09-28 19:02 (Jose, 16 ventas dentro) · **3 devoluciones PENDING**: folios 1090 ($70), 1228 ($240), 1422 ($58) |
| Hashes | bcrypt `$2a$` con passlib en ambos sistemas: las contraseñas y el PIN se pueden copiar tal cual |

Coqueta **no existe** en Atlas ONE (orgs 14 Kaory, 15 Ginebra, 16 Imaltzin, 17 Eleven) y no hay
usuarios "Mirna" ni "Jose" en la base de producción.

Correcciones al encargo original, comprobadas en código:

- **Ningún importador existente lee el formato de rmazh.** `scripts/import_products.py` lee el CSV
  propio de Atlas ONE (`Nombre*, Categoria, Codigo…`) y no crea escalones. `scripts/import_datax_export.py`
  (el de Imaltzin) lee el xlsx de Data X POS (`¿Aplica Precio N?…`). El exportador de rmazh
  (`app/routers/products/import_export.py::export_products_template`) produce otra cosa:
  `SKU, Nombre, Descripcion, Unidad, Departamento, Marca, Codigo Barras, Precio Base, Costo, Stock,
  Incluye IVA, P1..P5 {Nombre, Min, Precio, Empaque}, E1..E3 {Nombre, Barcode, Cantidad, Precio}`.
- El README de los scripts está en `scripts/adhoc/2026-09-01/README.md`, un nivel arriba de `coqueta/`.
- El esquema de ventas y caja de los dos sistemas es **casi el mismo** (misma tabla, 3-4 columnas
  extra por lado). Traer el historial era posible; se decidió no hacerlo (§2).

## 2. Decisiones (con el usuario, 2026-09-30)

1. **Coqueta arranca con catálogo + existencias.** El historial de ventas y cortes se queda en rmazh
   para consulta con la cuenta de Mirna. Sin escrituras en Railway.
2. **Los folios de Atlas ONE arrancan en 1464**, para que nunca existan dos tickets con el mismo
   folio entre los dos sistemas y para que un traspaso posterior del historial (1..1463) no choque.
3. **Mirna y Jose conservan usuario, contraseña y PIN** copiando los hashes.
4. **Las existencias entran tal cual**, incluidas las 30 de 10,000. El dry-run imprime la lista de
   las que pasan de 500 para que Mirna las corrija por ajuste de inventario. Hay bandera `--tope N`
   por si el usuario cambia de opinión.
5. Departamento "Ncoqueta" y marca "Rmazh" **no se importan**: todo queda en "General".
6. Dry-run antes de cada escritura; respaldo de la base antes del alta; verificación con Jose (el
   cajero), no solo con Mirna.

## 3. Componentes

### 3.1 `scripts/import_rmazh_export.py` (nuevo)

Hermano de `import_datax_export.py`. Se copia su esqueleto y se cambia lo específico del formato;
no se importa desde él (son scripts sueltos, sin paquete) pero las funciones de apoyo se
transcriben con el mismo nombre para que un lector las reconozca.

Entrada: el xlsx que produce `export_coq2.py` (hoja `Plantilla`; la hoja `Listas_Validacion` se
ignora). Cabeceras normalizadas (sin acentos, minúsculas). Columnas leídas:

| Columna | Destino |
|---|---|
| `SKU` | `ProductVariant.sku` (desambiguado con sufijo `-2`, `-3` si ya existe en la org) |
| `Nombre` | `Product.name` (obligatorio; renglón sin nombre → incidencia y se omite) |
| `Descripcion` | `Product.description` |
| `Departamento` | `Department` de la org, **salvo** los excluidos (§2.5): "Ncoqueta" → sin departamento. Bandera `--conservar-departamentos` desactiva la exclusión |
| `Marca` | ignorada (bandera `--conservar-marcas` la crea) |
| `Codigo Barras` | `ProductVariant.barcode` (vacío → NULL) |
| `Precio Base` | `ProductVariant.price` (obligatorio, > 0) |
| `Costo` | `ProductVariant.cost` (vacío → 0, nunca NULL: un NULL tumba el POS con 500) |
| `Stock` | movimiento `ADJUSTMENT_IN` con referencia `"Carga inicial rmazh"`, autor el admin de la org |
| `Incluye IVA` | `has_iva` (`Si`→True, `No`→False, vacío→False) |
| `Pn Nombre / Pn Min / Pn Precio` (n=1..5) | un `ProductPrice` por cada n con nombre no vacío: `price_name` = nombre **original** (Mayoreo, Caja, Precio 1…), `min_quantity` = Min (vacío → 1), `unit_price` = Precio (obligatorio > 0 o incidencia) |
| `Pn Empaque`, `E1..E3 *`, `Unidad` | ignoradas (Coqueta tiene 0 empaques; se anota incidencia si alguna viene llena) |

Identidad de un renglón para la idempotencia: `(Codigo Barras, Nombre)` dentro de la organización,
igual que el importador de Data X. Re-correr refresca precio, costo, IVA, escalones y estado en
sucursal; **no** vuelve a cargar existencias (guard por la referencia del movimiento) ni duplica
productos.

Por cada variante también se crea `ProductBranchStatus` en la sucursal destino
(`is_active_pos=True`, `is_visible=True`) y la fila `StockOnHand` (`is_active=True`), como hace
el importador de Data X.

CLI: `import_rmazh_export.py archivo.xlsx --org N --branch M [--dry-run] [--tope N]
[--conservar-departamentos] [--conservar-marcas]`. Valida que la org y la sucursal existan y que la
sucursal sea de esa org antes de tocar nada. Todo en **un solo commit** al final. El resumen
imprime: productos creados/actualizados, escalones, movimientos, departamentos creados, y la lista
"existencias mayores a 500" (SKU, nombre, piezas).

Pruebas (`tests/test_import_rmazh_export.py`, SQLite): xlsx mínimo generado con openpyxl en la
prueba con 4 renglones: uno normal con 2 escalones (Mayoreo, Caja), uno sin código de barras, uno
con departamento "Ncoqueta", uno con stock 10,000. Se comprueba: conteos, nombres de escalón,
exclusión del departamento, `cost` nunca NULL, `has_iva`, movimiento con la referencia, idempotencia
(segunda corrida sin cambios de conteo ni segundo movimiento), `--dry-run` sin escrituras, `--tope`.

### 3.2 `scripts/import_rmazh_users.py` (nuevo)

Entrada: JSON con la lista que imprime `export_coq2.py` (`id, username, full_name, email,
personal_email, phone, rol, is_active, password_hash, reprint_pin_hash`). **El archivo vive en el
scratchpad; nunca se versiona ni se pega en el chat.**

Por cada usuario: si `username` no existe, crea `User` con `role` = rol de rmazh (los nombres del
enum coinciden: ADMINISTRADOR, CAJERO), `branch_id` = la sucursal destino, `platform_role=NONE`,
`password_hash` y `reprint_pin_hash` copiados tal cual, `is_active` respetado; y el
`UserOrganization` con `org_role` = `ADMIN` para ADMINISTRADOR, `OWNER` para DUEÑO y `MEMBER` para el resto. Si el
`username` **ya existe y pertenece a la org destino** (el admin que creó `onboard_org.py`),
actualiza `full_name`, `password_hash`, `reprint_pin_hash` y `branch_id`. Si existe en **otra**
organización, falla sin escribir nada: `users.username` es único global.

CLI: `import_rmazh_users.py usuarios.json --org N --branch M [--dry-run]`. Un commit.

Pruebas (`tests/test_import_rmazh_users.py`): crea dos usuarios, reemplaza el hash del admin
existente, rechaza un username ajeno, idempotencia, dry-run.

### 3.3 Folios desde 1464

- `app/modules/tenants/models.py::Branch`: `folio_inicial = Column(Integer, nullable=True)`.
- `scripts/railway_init.py`: `("branches", "folio_inicial", "ALTER TABLE branches ADD COLUMN folio_inicial INTEGER;")`
  en la lista de ALTERs idempotentes.
- `app/utils/folios.py::get_next_folio`: tras calcular `siguiente = 1 if max_folio is None else
  max_folio + 1`, lee `Branch.folio_inicial` de la sucursal y devuelve `max(siguiente,
  folio_inicial)` cuando no es nulo. Se aplica a **todas las series** de la sucursal (cotizaciones
  incluidas): es aceptable, Coqueta no usa cotizaciones, y evita una regla especial por serie.
- Pruebas en `tests/test_folios.py`: sucursal con `folio_inicial=1464` sin ventas → 1464; con una
  venta 1464 → 1465; con `folio_inicial` menor al máximo → máximo+1; nulo → comportamiento de hoy.
- Es el **único cambio en código de la aplicación** y toca `create_sale` indirectamente. Va en la
  misma rama pero se despliega a `main` **antes** del alta, con permiso explícito, y se verifica
  con una venta de Kaory o Eleven (que no tienen `folio_inicial`) siguiendo su numeración normal.

### 3.4 Alta en producción (orden de ejecución)

Cada paso se corre por `ssh ionos` + `docker cp`/`docker exec` en `atlas-one-prod`; si el
clasificador de permisos bloquea una escritura remota, el comando se entrega al usuario para que lo
corra con `!`.

0. `main` desplegado con §3.3 (`.commit_desplegado` y `/health` verificados).
1. **Respaldo**: `pg_dump` de `atlas_one_prod` a `/srv/backups/antes_coqueta_<fecha>.sql.gz`.
2. **Alta**: `onboard_org.py --name "Novedades Coqueta" --industry ATLAS_POS --admin Mirna
   --branch "Novedades Coqueta" --full-name Mirna`. Crea la matriz con `can_sell=True`. La
   contraseña generada se descarta (paso 3 la reemplaza).
3. **Ajustes de sucursal** (una fila por Python dentro del contenedor; `folio_inicial` no se expone por la API):
   `printer_name='POS-80'`, `folio_inicial=1464`, `ticket_header` y `ticket_footer` vacíos.
4. **Usuarios**: `import_rmazh_users.py --dry-run` → real. Mirna recupera su hash y PIN; Jose nace
   CAJERO en la matriz.
5. **Catálogo**: exportación **fresca** de rmazh el mismo día (`export_coq2.py` por `railway ssh`,
   solo lectura), luego `import_rmazh_export.py --dry-run` → revisar incidencias y la lista de
   existencias altas → real.
6. **Verificación** (§4).

### 3.5 En la tienda (usuario o Mirna)

Instalar `atlas-print-agent-setup-3.1.0.exe` (release v3.1.0 del 2026-09-28), apuntarlo a
`https://app.atlasone.com.mx`, impresora `POS-80`. Entrar como **Jose**, abrir caja, cobrar una
venta de prueba e imprimir el ticket: debe salir **A-1464**. Después el usuario decide si se cancela
o se deja.

## 4. Criterios de aceptación

En `atlas_one_prod`, para la org nueva:

| Comprobación | Esperado |
|---|---|
| `products` / `product_variants` activos | 218 / 218 (más los que rmazh haya dado de alta hasta el día del corte) |
| `product_prices` | 219, con `price_name` en {Mayoreo, Caja, Precio 1, Precio 2} |
| `stock_on_hand` en la matriz | suma igual a la del xlsx del día; 0 filas negativas |
| `inventory_movements` con referencia "Carga inicial rmazh" | uno por variante con stock > 0 |
| `product_variants.cost IS NULL` | 0 |
| Usuarios | Mirna ADMINISTRADOR con PIN; Jose CAJERO; ambos en la matriz y en `user_organizations` |
| `GET /api/branches/{id}` | `can_sell = true`, `printer_name = "POS-80"` |
| `GET /api/products/pos/search?q=cascanueces` **como Jose** | 200 con resultados |
| Venta de prueba | folio `A-1464`, ticket impreso en la PC de Coqueta |
| Railway | cero escrituras (solo `railway ssh` con scripts de lectura) |

## 5. Fuera de alcance

- Traer ventas, pagos, cortes, devoluciones o movimientos históricos.
- Apagar a los usuarios en rmazh (lo hace el usuario desde su otra sesión cuando §3.5 esté listo).
- Cerrar la caja 1862 y resolver las 3 devoluciones PENDING en rmazh (Jose/Mirna, antes del corte).
- Marca y departamento de rmazh (se descartan a propósito).
- Empaques (`E1..E3`): Coqueta tiene cero.

## 6. Riesgos y avisos

- **Las existencias cambian hasta el último minuto.** La exportación de hoy sirve para construir y
  ensayar; la carga real usa la del día del corte. Si Jose vende después de exportar y antes de
  apagarlo, esas piezas hay que descontarlas a mano (lección de Kaory: "existencias de Railway menos
  lo vendido hoy").
- **`users.username` es único global.** Hoy no hay "Mirna" ni "Jose" en Atlas ONE; si alguien los
  crea antes del alta, el script de usuarios se detiene.
- **rmazh también parece mudarse del Railway** (`/srv/backups/rmazh/rmazh_ensayo_20260930_*.dump`
  y `/srv/apps/rmazh` en el VPS). "El historial queda consultable en Railway" vale mientras rmazh
  viva ahí; conviene pensar la consulta del historial sobre donde termine rmazh.
- **`folio_inicial` aplica a todas las series de la sucursal.** Si Coqueta usara cotizaciones,
  arrancarían en Q-1464. Aceptado.
- **El entorno local no tiene `.venv`** (CLAUDE.md está desactualizado en eso); el Python 3.12 del
  sistema trae FastAPI y SQLAlchemy. Las pruebas se corren con ese intérprete o dentro de Docker.
