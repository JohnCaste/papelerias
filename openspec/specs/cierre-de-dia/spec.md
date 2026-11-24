# cierre-de-dia Specification

## Purpose
TBD - created by archiving change cerrar-dia-acta-regenerable. Update Purpose after archive.
## Requirements
### Requirement: Generación del acta del día

El sistema SHALL consolidar las ventas del journal local (#14) de una fecha en un
**acta** con al menos `id`, `tipo = "dia"`, `fecha_inicio`, `fecha_fin`, `total`
(suma de `total` de las ventas del día), `num_ventas`, `desglose_categoria`,
`desglose_metodo_pago`, `generado_en`, `generado_por` y `estado = "cerrado"`. El
acta SHALL poder generarse por tres disparadores: `automatico` (al cruzarse la
hora de cierre configurada, 20:00 por defecto), `perezoso` (al arrancar el
backend, para días anteriores sin acta) y `manual` (forzado desde la pantalla).
El acta MUST NOT ser condición para que una venta se guarde: cada venta ya es
durable en el journal desde que se confirma.

#### Scenario: Cierre automático a la hora configurada

- **WHEN** son las 20:05, el día de hoy tiene ventas en el journal y no tiene acta
- **THEN** el sistema genera el acta con `generado_por = "automatico"`, `total` y
  `num_ventas` iguales a los del journal en ese momento y `estado = "cerrado"`

#### Scenario: Cierre perezoso de días anteriores

- **WHEN** el backend arranca y un día dentro de los 7 anteriores no tiene acta
- **THEN** el sistema genera su acta con `generado_por = "perezoso"`, incluso si
  ese día no tuvo ninguna venta

#### Scenario: Un día sin ventas también se cierra

- **WHEN** se genera el acta de un día sin ventas en el journal
- **THEN** el acta queda con `total = 0`, `num_ventas = 0` y desgloses vacíos

### Requirement: Persistencia local append-only del acta

El sistema SHALL persistir el acta en un archivo local por día
(`datos_locales/cierres/cierre-<fecha>.jsonl`), escrito con `fsync`, sin depender
de internet ni de BigQuery. El archivo SHALL ser append-only: los eventos nunca
se reescriben ni se borran. El sistema SHALL admitir **más de un** evento
`{"evento": "cierre", ...}` en el mismo archivo (uno por cada generación o
regeneración) y eventos `{"evento": "sincronizado", ...}` que registran subidas a
BigQuery.

#### Scenario: El acta se escribe sin conexión

- **WHEN** se genera o regenera un acta y no hay internet
- **THEN** el evento `cierre` queda escrito en el `.jsonl` con `fsync` y la
  operación responde con éxito; la subida a BigQuery ocurre después

#### Scenario: Varios eventos cierre en un archivo

- **WHEN** un día se cierra de forma forzada y luego se regenera dos veces
- **THEN** el `.jsonl` del día contiene tres eventos `cierre`, en orden de
  escritura, sin que ninguno se modifique

### Requirement: El acta local refleja el último cierre

El sistema SHALL exponer, cuando un archivo de día contiene varios eventos
`cierre`, el estado correspondiente al **último** evento `cierre` escrito
(`obtener_cierre_local` y el endpoint de estado). El campo que indica si el acta
ya se subió a BigQuery MUST considerarse verdadero solo si hay un evento
`sincronizado` posterior al último evento `cierre`.

#### Scenario: Lectura tras regenerar

- **WHEN** un día tiene un evento `cierre` con `total = 800` y luego otro con
  `total = 950`
- **THEN** el estado del día reporta `total = 950` y `generado_en` del segundo
  evento

#### Scenario: Sincronización invalidada por regeneración

- **WHEN** el acta se subió (`sincronizado`) y después se regenera
- **THEN** el estado del día vuelve a reportar el acta como **no sincronizada**
  hasta que haya un nuevo evento `sincronizado`

### Requirement: Regeneración del acta del día en curso

El sistema SHALL exponer `POST /api/cierres/dia/regenerar` (JWT) que, **solo para
el día en curso**, vuelve a consolidar el journal y append-ea un nuevo evento
`cierre` con los valores al momento de la petición, `generado_por` que identifica
la regeneración y `generado_en` actualizado, y responde `201` con el acta
resultante. La operación SHALL invalidar el estado de sincronización previo. El
sistema MUST responder `409` (o `400`) si la `fecha` solicitada no es la de hoy,
sin escribir nada: las actas de días anteriores son historial inmutable.

#### Scenario: Regenerar el acta de hoy

- **WHEN** hoy ya tiene acta con `total = 800` y entran ventas por `$150` más,
  luego se hace `POST /api/cierres/dia/regenerar`
- **THEN** se append-ea un evento `cierre` con `total = 950`, se responde `201` y
  el estado del día pasa a no sincronizado

#### Scenario: Regenerar un día pasado está prohibido

- **WHEN** se hace `POST /api/cierres/dia/regenerar` con `fecha` de ayer
- **THEN** el sistema responde `409`/`400` y no escribe ningún evento

#### Scenario: Regenerar un día que aún no tiene acta

- **WHEN** hoy no tiene acta todavía y se hace `POST /api/cierres/dia/regenerar`
- **THEN** el sistema genera la primera acta del día y responde `201`

### Requirement: Cierre forzado anticipado

El sistema SHALL exponer `POST /api/cierres/dia` (JWT) como "forzar cierre ahora":
si el día no tiene acta, genera la primera con `generado_por = "manual"`; si ya
tiene acta, responde el acta vigente sin escribir un evento nuevo (idempotente).
La respuesta SHALL indicar que el acta es **provisional** cuando se genera antes
de la hora de cierre configurada.

#### Scenario: Forzar cierre antes de las 20:00

- **WHEN** son las 18:00 y se hace `POST /api/cierres/dia`
- **THEN** el sistema genera el acta con `generado_por = "manual"` y la respuesta
  marca el acta como provisional

#### Scenario: Forzar cierre cuando ya hay acta

- **WHEN** el día ya tiene acta y se hace `POST /api/cierres/dia` otra vez
- **THEN** el sistema responde el acta vigente sin append-ear un evento `cierre`

### Requirement: El cierre automático finaliza el acta provisional

El disparador automático SHALL regenerar una sola vez el acta del día de hoy
cuando, al cruzarse la hora de cierre configurada, esa acta existe y es
**provisional** (generada por un cierre forzado anterior a esa hora),
consolidando las ventas que entraron después y dejándola como no provisional. Si
el día no tiene acta, la crea. Si el día ya tiene un acta no provisional, no hace
nada.

#### Scenario: Se forzó a las 18:00 y siguieron ventas

- **WHEN** el acta se forzó a las 18:00 con `total = 800`, luego entraron `$300`
  en ventas y son las 20:05
- **THEN** el disparador automático regenera el acta con `total = 1100` y la deja
  como no provisional

#### Scenario: Día ya finalizado

- **WHEN** son las 20:05 y el día ya tiene un acta no provisional
- **THEN** el disparador automático no escribe ningún evento

#### Scenario: PC apagada a las 20:00

- **WHEN** la PC estuvo apagada a las 20:00 y arranca al día siguiente
- **THEN** el disparador perezoso genera el acta del día anterior que quedó sin
  cerrar

### Requirement: Estado del día

El sistema SHALL exponer `GET /api/cierres/dia?fecha=YYYY-MM-DD` (JWT, por
defecto hoy, `400` si la fecha no es válida) que devuelve `fecha`, `cerrado`
(bool) y `cierre`: el acta correspondiente al último evento `cierre` (con su
estado de sincronización) o `null` si el día no tiene acta. Cuando la fecha es la
de hoy y el acta es provisional, la respuesta SHALL indicarlo.

#### Scenario: Día abierto

- **WHEN** hoy no tiene ningún evento `cierre`
- **THEN** la respuesta es `{ cerrado: false, cierre: null }`

#### Scenario: Día con acta provisional

- **WHEN** hoy tiene un acta forzada antes de las 20:00
- **THEN** la respuesta trae `cerrado: true`, el acta y la marca de provisional

#### Scenario: Día cerrado no provisional

- **WHEN** el día consultado tiene un acta generada a las 20:00 o regenerada
  después
- **THEN** la respuesta trae `cerrado: true`, el acta y sin marca de provisional

### Requirement: Sincronización idempotente del acta

El sincronizador (#15) SHALL subir el acta del último evento `cierre` a BigQuery
de forma idempotente por `id`/fecha (upsert), y tras una subida exitosa
append-ear un evento `sincronizado`. Una regeneración SHALL hacer que el acta
vuelva a considerarse pendiente y se re-suba, reemplazando la fila anterior sin
duplicarla. Ninguna falla de subida SHALL bloquear la venta, el cierre ni la
regeneración.

#### Scenario: Re-subida tras regenerar

- **WHEN** un acta ya sincronizada se regenera y hay conexión
- **THEN** el sincronizador vuelve a subir el acta, la fila de BigQuery de esa
  fecha queda con los valores nuevos y se append-ea un nuevo evento
  `sincronizado`

#### Scenario: Regenerar sin conexión

- **WHEN** se regenera el acta y no hay internet
- **THEN** la regeneración responde `201` y el acta queda pendiente de subir; el
  sincronizador la sube cuando vuelve la conexión

### Requirement: La venta nunca se bloquea por el estado del día

El sistema MUST NOT impedir capturar ventas ni alterar el flujo de captura en
ningún estado del día (abierto, provisional, cerrado, cerrado y sincronizado).
Las ventas registradas después de un acta entran al journal con normalidad y son
recogidas por la siguiente regeneración o por el cierre automático.

#### Scenario: Vender después de cerrar

- **WHEN** el día ya tiene acta y se captura una venta nueva
- **THEN** la venta se guarda en el journal igual que siempre y el acta no cambia
  hasta que se regenere o el disparador automático la finalice

### Requirement: Encabezado del día en la pantalla VENDER

La pantalla VENDER (`PuntoVenta`) SHALL mostrar siempre la fecha del día en curso
junto al estado: "Día abierto · Hoy, {fecha}" cuando no hay acta, y "Día cerrado
· {fecha}" cuando ya hay acta. VENDER SHALL operar siempre sobre el día actual
del sistema.

#### Scenario: Día abierto

- **WHEN** se abre VENDER y hoy no tiene acta
- **THEN** el encabezado muestra "Día abierto · Hoy, {fecha}"

#### Scenario: Día cerrado

- **WHEN** se abre VENDER y hoy ya tiene acta
- **THEN** el encabezado muestra "Día cerrado · {fecha}"

### Requirement: Estados del botón de cierre en la pantalla VENDER

La pantalla VENDER SHALL presentar el control de cierre según el estado del día:

- **Día abierto, antes de la hora de cierre configurada**: el botón principal
  SHALL estar deshabilitado con el texto "Se cierra automáticamente a las
  8:00 pm", y SHALL ofrecerse una acción secundaria "Forzar cierre ahora" que
  pide confirmación antes de llamar a `POST /api/cierres/dia`.
- **Día abierto, pasada la hora de cierre**: el botón principal "Cerrar el día"
  SHALL estar habilitado como respaldo por si el disparador automático no corrió.
- **Día con acta (provisional o no)**: en lugar del botón de cierre SHALL
  mostrarse "Regenerar acta", disponible para cualquier usuario del mostrador,
  que llama a `POST /api/cierres/dia/regenerar` y refresca el estado.

#### Scenario: Antes de las 20:00

- **WHEN** son las 15:00 y el día está abierto
- **THEN** el botón "Cerrar el día" está deshabilitado con el texto de cierre
  automático y aparece "Forzar cierre ahora"

#### Scenario: Confirmar el cierre forzado

- **WHEN** el usuario pulsa "Forzar cierre ahora" y confirma el diálogo
- **THEN** el frontend llama a `POST /api/cierres/dia` y el encabezado pasa a
  "Día cerrado · {fecha}"

#### Scenario: Acta existente

- **WHEN** el día ya tiene acta
- **THEN** no se muestra el botón de cierre sino "Regenerar acta"; al pulsarlo se
  llama a `POST /api/cierres/dia/regenerar` y se actualiza el total mostrado

#### Scenario: Pasada la hora sin acta

- **WHEN** son las 21:00, el día sigue abierto y el disparador automático no corrió
- **THEN** el botón "Cerrar el día" está habilitado y al pulsarlo cierra el día

