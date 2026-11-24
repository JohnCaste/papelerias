# dashboard-del-dia Specification

## Purpose
Resumen operativo del día en curso (#35): `GET /api/dashboard/dia` calcula desde
el journal local —sin BigQuery, funciona sin internet— el total y número de
ventas, el desglose por categoría y método de pago, el porcentaje de dinero
capturado con detalle, la comparación con el mismo día de la semana anterior,
las últimas ventas (solo lectura) y el estado de cierre con aviso de días
pendientes. Incluye la pantalla `/dashboard` que lo muestra.
## Requirements
### Requirement: Endpoint de resumen del día

El sistema SHALL exponer `GET /api/dashboard/dia` protegido con JWT, que acepta
un parámetro opcional `fecha` (`YYYY-MM-DD`, por defecto el día de hoy) y
responde `400` si `fecha` no es una fecha válida. El endpoint SHALL calcular
todos los datos leyendo el **journal local** de ventas, no BigQuery. La
respuesta SHALL incluir `fecha`, `total`, `num_ventas`, `desglose_categoria`,
`desglose_metodo_pago`, `detalle`, `comparacion_semana_anterior`,
`ultimas_ventas` y `estado_dia`.

#### Scenario: Día con ventas

- **WHEN** el journal del día tiene 3 ventas por `$100`, `$200` y `$50`
- **THEN** la respuesta trae `total = 350` y `num_ventas = 3`

#### Scenario: Fecha inválida

- **WHEN** se pide `GET /api/dashboard/dia?fecha=13-2026`
- **THEN** el sistema responde `400`

#### Scenario: Día sin ventas

- **WHEN** el journal del día está vacío
- **THEN** la respuesta trae `total = 0`, `num_ventas = 0`, desgloses vacíos y
  `ultimas_ventas = []`, con `200`

### Requirement: Desglose por categoría y por método de pago

El sistema SHALL incluir `desglose_categoria` sumando `lineas.subtotal` de las
líneas con `tipo = 'categoria'` agrupado por `categoria`, y `desglose_metodo_pago`
sumando `venta.total` agrupado por `metodo_pago`. Cada desglose SHALL ser una
lista de `{ clave, monto }`. La suma de `monto` en `desglose_metodo_pago` MUST
ser igual a `total`.

#### Scenario: Venta con varias líneas de categoría

- **WHEN** una venta tiene una línea `categoria='copias'` de `$30` y otra
  `categoria='dulces'` de `$20`
- **THEN** `desglose_categoria` suma `$30` en `copias` y `$20` en `dulces`, no
  `$50` en una sola categoría

#### Scenario: El desglose por método cuadra con el total

- **WHEN** el día tiene `total = 500`
- **THEN** la suma de `monto` en `desglose_metodo_pago` es `500`

### Requirement: Porcentaje de dinero capturado con detalle

El sistema SHALL incluir `detalle` con `monto_total` (el `total` del día),
`monto_detallado` (suma de `total` de las ventas con `detallada = true`) y
`porcentaje` (`monto_detallado / monto_total`, redondeado, `0` cuando
`monto_total` es `0`).

#### Scenario: Parte del día capturado con producto

- **WHEN** el día tiene `$890` en total y `$620` corresponden a ventas con
  `detallada = true`
- **THEN** `detalle` es `{ monto_detallado: 620, monto_total: 890, porcentaje: 70 }`

#### Scenario: Día sin ventas detalladas

- **WHEN** ninguna venta del día tiene `detallada = true`
- **THEN** `detalle.porcentaje` es `0`

### Requirement: Comparación con el mismo día de la semana anterior

El sistema SHALL incluir `comparacion_semana_anterior` con la `fecha` de siete
días antes, su `total` y `num_ventas` leídos del journal de ese día, y
`delta_total` (`total` de hoy menos el de hace una semana). `delta_pct` SHALL
ser la variación relativa, o `null` cuando el total de hace una semana es `0`.

#### Scenario: Hay datos de la semana pasada

- **WHEN** hoy suma `$1200` y el mismo día de la semana pasada sumó `$1000`
- **THEN** `comparacion_semana_anterior` trae `total = 1000`, `delta_total = 200`
  y `delta_pct = 20`

#### Scenario: No hay datos de la semana pasada

- **WHEN** el journal de hace siete días no existe o está vacío
- **THEN** `comparacion_semana_anterior` trae `total = 0`, `num_ventas = 0` y
  `delta_pct = null`

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

### Requirement: Estado de cierre y días pendientes

El sistema SHALL incluir `estado_dia` con `cerrado` (bool) y `cerrado_en`
(marca de tiempo del cierre local o `null`), y `dias_sin_cerrar`: la lista de
fechas anteriores al día consultado, dentro de la ventana que revisa el
disparador perezoso de #50, que no tienen cierre local.

#### Scenario: Día ya cerrado

- **WHEN** existe un cierre local para la fecha consultada generado a las
  `20:00`
- **THEN** `estado_dia` es `{ cerrado: true, cerrado_en: "...20:00..." }`

#### Scenario: Quedan días anteriores sin cerrar

- **WHEN** el antier no tiene cierre local y ayer sí
- **THEN** `dias_sin_cerrar` contiene la fecha de antier y no la de ayer

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

