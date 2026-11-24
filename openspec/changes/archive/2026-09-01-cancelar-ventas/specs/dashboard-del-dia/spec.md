## MODIFIED Requirements

### Requirement: Últimas ventas del día en solo lectura

El sistema SHALL incluir `ultimas_ventas` con las ventas del día ordenadas de
más reciente a más antigua, cada una con `id`, `hora`, `total`, `metodo_pago`,
`detallada`, `estado` (pendiente de sincronizar, enviada o `cancelada`) y
`cancelable` (bool: `false` si la venta ya está cancelada o si es una fila de
reversión). Las filas de reversión NO se listan como ventas aparte, pero su
`total` negativo sigue contando en `total` y `num_ventas` del día. Salvo la
acción de cancelar descrita en el requisito de la pantalla de dashboard, el
sistema MUST NOT exponer otras acciones de edición sobre esas ventas.

#### Scenario: Orden y forma

- **WHEN** el día tiene 5 ventas
- **THEN** `ultimas_ventas` las lista de la más reciente a la más antigua, cada
  una con `id`, `hora`, `total`, `metodo_pago`, `detallada`, `estado` y
  `cancelable`

#### Scenario: Venta cancelada en la lista

- **WHEN** el día tiene la venta `v1` y su fila de reversión total
- **THEN** `ultimas_ventas` incluye `v1` con `estado = "cancelada"` y
  `cancelable = false`, y no incluye una entrada para la fila de reversión

### Requirement: Pantalla de dashboard en el frontend

El frontend SHALL exponer una ruta `/dashboard` con una página que consume
`GET /api/dashboard/dia` y muestra, de un vistazo, el total y número de ventas
del día, los dos desgloses, el porcentaje capturado con detalle, la comparación
con la semana anterior, las últimas ventas y el estado de cierre (incluido el
aviso de días sin cerrar). La página SHALL ser accesible desde el menú. En la
lista de últimas ventas, cada venta con `cancelable = true` SHALL ofrecer una
acción "Cancelar" que abre un modal donde se exige un `motivo` no vacío y se
puede elegir revertir todas las líneas o un subconjunto; al confirmar, la
página llama a `POST /api/ventas/<id>/cancelar` y refresca los datos. Las
ventas con `estado = "cancelada"` SHALL mostrarse atenuadas o con un distintivo,
sin desaparecer de la lista.

#### Scenario: Carga del dashboard

- **WHEN** se abre `/dashboard`
- **THEN** se hace una petición a `/api/dashboard/dia` y se pintan los totales,
  desgloses, porcentaje de detalle, comparación, últimas ventas y estado de
  cierre

#### Scenario: Aviso de días sin cerrar

- **WHEN** la respuesta trae `dias_sin_cerrar` no vacío
- **THEN** la página muestra un aviso visible con esas fechas

#### Scenario: Cancelar una venta desde el dashboard

- **WHEN** el usuario pulsa "Cancelar" en una venta `cancelable`, escribe un
  motivo y confirma
- **THEN** la página llama a `POST /api/ventas/<id>/cancelar` con el motivo (y
  las líneas elegidas si es parcial), y al volver refresca el dashboard con el
  total del día ya reducido y la venta marcada como cancelada

#### Scenario: Motivo vacío en el modal

- **WHEN** el usuario intenta confirmar la cancelación sin escribir un motivo
- **THEN** el modal no envía la petición y pide el motivo
