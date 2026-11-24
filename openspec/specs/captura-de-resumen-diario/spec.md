# captura-de-resumen-diario Specification

## Purpose
TBD - created by archiving change pulir-ventas-por-dia. Update Purpose after archive.
## Requirements
### Requirement: Endpoint para guardar el resumen de ventas de un día

El sistema SHALL exponer `POST /api/ventas/resumen-dia` protegido con JWT, que
acepta un cuerpo JSON con `fecha` (`YYYY-MM-DD`) y `categorias`, una lista de
`{ clave, monto }` donde `clave` es una de `papeleria`, `copias`, `dulces`,
`helados`, `recargas` y `monto` es un número mayor o igual a `0`. El endpoint
SHALL materializar la captura como filas de `lapape.venta` con
`origen = "resumen_manual"`, `metodo_pago = "resumen_manual"` y `fecha_hora` al
mediodía civil de `fecha` en la zona horaria del negocio, escribiendo directo a
BigQuery. El endpoint SHALL aceptar únicamente fechas de días **ya cerrados**:
`fecha` estrictamente anterior a hoy (zona horaria del negocio) y no anterior al
año calendario previo. El sistema MUST responder `400` si `fecha` no es una fecha
válida, si `fecha` es hoy o posterior, si `fecha` es anterior al año previo, si
`clave` no es una de las categorías permitidas, o si algún `monto` es negativo o
no numérico.

#### Scenario: Guardar un día sin registro previo

- **WHEN** se hace `POST /api/ventas/resumen-dia` con `fecha` de ayer y
  `categorias = [{ clave: "copias", monto: 120 }, { clave: "dulces", monto: 80 }]`
- **THEN** `GET /api/agregaciones?granularidad=dia` para esa fecha devuelve un
  bucket con `total = 200` y `desglose_categoria` de `120` en `copias` y `80` en
  `dulces`

#### Scenario: El día en curso no se puede editar

- **WHEN** se hace `POST /api/ventas/resumen-dia` con `fecha` igual a hoy (o una
  fecha futura)
- **THEN** el sistema responde `400` y no escribe ninguna fila (el día en curso
  se registra en vivo desde la pantalla de Vender)

#### Scenario: Categoría inválida

- **WHEN** el cuerpo incluye `{ clave: "juguetes", monto: 50 }`
- **THEN** el sistema responde `400` y no escribe ninguna fila

#### Scenario: Monto negativo

- **WHEN** el cuerpo incluye `{ clave: "copias", monto: -10 }`
- **THEN** el sistema responde `400` y no escribe ninguna fila

#### Scenario: Fecha fuera de rango

- **WHEN** `fecha` corresponde a hace dos años o más
- **THEN** el sistema responde `400` y no escribe ninguna fila

### Requirement: El modal es la autoridad del día y se reconcilia por diferencia

Los `monto` recibidos SHALL interpretarse como el **total del día** por categoría,
no como un ajuste aditivo. Al guardar una `fecha`, el sistema SHALL:

1. Calcular `base[cat]`, el agregado actual del día por categoría desde `venta`
   excluyendo las filas `origen = "resumen_manual"` y sus reversiones.
2. Revertir toda venta `origen = "resumen_manual"` vigente de esa fecha con una
   fila de reversión (`venta_original_id`), que `/api/agregaciones` netea.
3. Insertar una sola venta `origen = "resumen_manual"` con una línea
   `tipo = "categoria"` por cada categoría cuya diferencia `monto - base[cat]`
   sea distinta de cero; si no hay ninguna diferencia distinta de cero, no
   insertar la venta de captura (los pasos 1-2 igual dejan el día en el objetivo).

Tras la operación, el `total` del día por categoría en `/api/agregaciones` MUST
ser igual a los `monto` recibidos, y el `total` del día MUST ser igual a su suma.

#### Scenario: El total del día refleja exactamente lo enviado

- **WHEN** se guarda un día con `categorias` que suman `$200`
- **THEN** `/api/agregaciones` devuelve `total = 200` para ese día, coincidiendo
  con cada `monto` por categoría

#### Scenario: Reguardar el mismo día no duplica el total

- **WHEN** un día ya guardado con `total = 200` se vuelve a guardar con
  `categorias` que suman `200`
- **THEN** `/api/agregaciones` para ese día sigue devolviendo `total = 200`, no
  `400` (la captura manual previa se revierte antes de registrar la nueva)

#### Scenario: Reguardar con montos distintos refleja el último valor

- **WHEN** un día con `total = 200` se reguarda con `categorias` que suman `350`
- **THEN** el `total` del día pasa a ser `350`

#### Scenario: Guardar todo en cero limpia la captura manual

- **WHEN** un día con captura manual se guarda con todas las categorías en `0`
- **THEN** se revierte la captura manual y el `total` del día vuelve a lo que
  aporten las ventas individuales de ese día (o `0` si no hay ninguna)

### Requirement: Las ventas individuales de punto de venta no se pisan

Reemplazar o limpiar la captura manual de una fecha MUST revertir únicamente
filas `origen = "resumen_manual"`. El sistema MUST NOT alterar, revertir ni
eliminar las ventas individuales del punto de venta (`origen = "pos"`) ni las
migradas (`origen = "migracion"`) de ese día.

#### Scenario: Un día con ventas de POS ajusta solo la diferencia

- **WHEN** un día tiene `$300` en ventas de punto de venta (todas en `papeleria`)
  y se guarda una captura manual con `papeleria = 500` y el resto en `0`
- **THEN** el `total` del día en `/api/agregaciones` es `$500`, y las ventas de
  punto de venta siguen intactas

#### Scenario: Limpiar la captura manual conserva las ventas de POS

- **WHEN** ese mismo día se reguarda la captura manual con todo en `0`
- **THEN** el `total` del día vuelve a `$300` y las ventas de punto de venta
  siguen intactas

### Requirement: El modal de día guarda contra el endpoint y refresca la vista

El `ModalVentaDia` del frontend SHALL enviar los montos editados por categoría a
`POST /api/ventas/resumen-dia` al pulsar `Guardar`, y al confirmarse SHALL cerrar
el modal y disparar la recarga del resumen anual para que la card del día, la
card del mes y el total del año reflejen los nuevos montos. El valor mostrado en
`Total del día` dentro del modal MUST coincidir con el total que luego muestra la
card del mes para ese día. El modal SHALL usar las claves `papeleria`, `copias`,
`dulces`, `helados`, `recargas`, etiquetando la fila de `copias` como
"Copias y Hojas", y al leer `desglose_categoria` de un día SHALL plegar las
claves legadas `productos` → `papeleria` y `hojas` → `copias`.

Cuando la fecha del modal es hoy o posterior, el modal SHALL mostrarse en solo
lectura: campos y botones `Guardar` / `Limpiar` deshabilitados y un aviso de que
el día en curso se registra desde Vender.

#### Scenario: Guardar desde el modal actualiza las cards

- **WHEN** el usuario edita las categorías de un día para que sumen `$200` y
  pulsa `Guardar`
- **THEN** el modal se cierra y la card de ese día muestra `$200`, y el total del
  mes y del año quedan consistentes con ese valor

#### Scenario: Fallo de red mantiene el modal abierto

- **WHEN** la petición de guardado falla
- **THEN** el modal permanece abierto, muestra el aviso de error y conserva los
  montos editados para reintentar

#### Scenario: La historia migrada se muestra bajo Papelería

- **WHEN** un día solo tiene ventas migradas con la línea de categoría `productos`
- **THEN** el modal muestra ese monto en la fila "Papelería", no en cero

#### Scenario: El modal de hoy es de solo lectura

- **WHEN** se abre el `ModalVentaDia` sobre el día en curso
- **THEN** los campos y los botones `Guardar` y `Limpiar` están deshabilitados y
  se muestra el aviso de que el día en curso se registra desde Vender

