# corte-de-caja Specification

## Purpose
Arqueo de efectivo al cierre (#36): apertura de caja con efectivo inicial (que se
teclea cada día, no se arrastra), registro de retiros y entradas de efectivo
durante el día, y corte que compara el conteo físico contra el esperado
(`inicial + ventas_efectivo + entradas − retiros`). El backend rechaza el corte
(`400`) si la diferencia supera el umbral y no trae nota. Local-first,
desacoplado del cierre de día (#50): un día se cierra con o sin corte.
## Requirements
### Requirement: Apertura de caja con efectivo inicial

El sistema SHALL exponer `POST /api/caja/apertura` (JWT) que recibe
`efectivo_inicial` (número ≥ 0) y registra la apertura del día en el store local
con el usuario del JWT y la marca de tiempo. El `efectivo_inicial` SHALL tomarse
tal cual del cuerpo de la petición; el sistema MUST NOT arrastrarlo del corte del
día anterior. Si la caja del día ya está abierta, el sistema SHALL devolver la
apertura existente sin crear otra. El sistema MUST responder `400` si
`efectivo_inicial` falta o es negativo.

#### Scenario: Primera apertura del día

- **WHEN** se hace `POST /api/caja/apertura` con `efectivo_inicial = 500` y no
  hay apertura para hoy
- **THEN** se registra la apertura con `efectivo_inicial = 500`, el usuario del
  JWT y la hora, y se responde `201`

#### Scenario: Segunda apertura el mismo día

- **WHEN** ya hay una apertura de hoy con `efectivo_inicial = 500` y se hace otra
  con `efectivo_inicial = 800`
- **THEN** el sistema devuelve la apertura existente (`efectivo_inicial = 500`)
  sin registrar una nueva

#### Scenario: Monto inválido

- **WHEN** `efectivo_inicial` es `-100` o no viene
- **THEN** el sistema responde `400`

### Requirement: Movimientos de efectivo durante el día

El sistema SHALL exponer `POST /api/caja/movimiento` (JWT) que recibe `tipo`
(`retiro` o `entrada`), `monto` (número > 0) y `motivo` (texto no vacío), y lo
registra en el store local del día con el usuario y la marca de tiempo. El
sistema MUST responder `400` si `tipo` no es válido, si `monto` no es positivo o
si falta `motivo`.

#### Scenario: Retiro con motivo

- **WHEN** se hace `POST /api/caja/movimiento` con `tipo = "retiro"`,
  `monto = 200`, `motivo = "pago a proveedor"`
- **THEN** el movimiento queda registrado y se responde `201`

#### Scenario: Movimiento sin motivo

- **WHEN** se manda un movimiento sin `motivo` o con `motivo` vacío
- **THEN** el sistema responde `400`

#### Scenario: Tipo inválido

- **WHEN** `tipo` es `"ajuste"`
- **THEN** el sistema responde `400`

### Requirement: Cálculo del efectivo esperado

El sistema SHALL calcular el efectivo esperado como
`efectivo_inicial + ventas_efectivo + entradas − retiros`, donde
`ventas_efectivo` es la suma de `total` de las ventas del día en el journal local
con `metodo_pago == 'efectivo'`, `entradas` es la suma de los movimientos
`entrada` y `retiros` la de los movimientos `retiro`. Cuando no hay apertura,
`efectivo_inicial` SHALL tratarse como `0` para este cálculo.

#### Scenario: Esperado con ventas y movimientos

- **WHEN** el día tiene `efectivo_inicial = 500`, `$1200` en ventas de efectivo,
  una entrada de `$100` y dos retiros que suman `$300`
- **THEN** el esperado es `1500`

#### Scenario: Las ventas con otro método no cuentan

- **WHEN** el día tiene `$1200` en efectivo y `$800` en tarjeta
- **THEN** solo los `$1200` entran en `ventas_efectivo`

### Requirement: Corte con conteo y diferencia

El sistema SHALL exponer `POST /api/caja/corte` (JWT) que recibe
`efectivo_contado` (número ≥ 0) y `nota` (opcional). El sistema SHALL registrar
en el store local un evento `corte` con `efectivo_contado`, el `esperado`
calculado, `diferencia = efectivo_contado − esperado`, la `nota`, el usuario y la
marca de tiempo, y responder `201` con esos datos. Si el día ya tiene un corte,
el sistema SHALL devolver el existente sin registrar otro.

#### Scenario: Cuadra la caja

- **WHEN** el esperado es `1500` y se hace el corte con `efectivo_contado = 1500`
- **THEN** el corte queda con `diferencia = 0` y se responde `201`

#### Scenario: Falta dinero

- **WHEN** el esperado es `1500` y `efectivo_contado = 1440`
- **THEN** el corte queda con `diferencia = -60`

#### Scenario: Segundo corte el mismo día

- **WHEN** ya hay un corte de hoy y se hace `POST /api/caja/corte` otra vez
- **THEN** el sistema devuelve el corte existente sin registrar uno nuevo

### Requirement: Nota obligatoria cuando la diferencia supera el umbral

El sistema SHALL rechazar el corte con `400` cuando el valor absoluto de la
diferencia supera el umbral configurado en el backend y el cuerpo no incluye una
`nota` no vacía. Cuando `|diferencia|` no supera el umbral, la `nota` SHALL ser
opcional.

#### Scenario: Diferencia grande sin nota

- **WHEN** el umbral es `$20`, el esperado `1500` y `efectivo_contado = 1400`
  (diferencia `-100`), sin `nota`
- **THEN** el sistema responde `400` y no registra el corte

#### Scenario: Diferencia grande con nota

- **WHEN** los mismos datos pero con `nota = "cobré de más un vuelto"`
- **THEN** el corte se registra con `diferencia = -100` y la nota, y responde `201`

#### Scenario: Diferencia chica sin nota

- **WHEN** el umbral es `$20` y la diferencia es `-5`, sin `nota`
- **THEN** el corte se registra normalmente

### Requirement: Estado de la caja del día

El sistema SHALL exponer `GET /api/caja/dia?fecha=YYYY-MM-DD` (JWT, por defecto
hoy, `400` si la fecha no es válida) que devuelve `abierta` (bool),
`efectivo_inicial`, `movimientos` (lista con `tipo`, `monto`, `motivo`, `hora`),
`ventas_efectivo`, `esperado` (calculado al momento) y `corte` (el evento de
corte del día o `null`).

#### Scenario: Caja abierta sin corte

- **WHEN** hoy tiene apertura y ventas pero aún no se hace el corte
- **THEN** la respuesta trae `abierta = true`, el `esperado` en curso y
  `corte = null`

#### Scenario: Día sin apertura

- **WHEN** hoy no tiene apertura
- **THEN** `abierta = false`, `efectivo_inicial = 0`, `movimientos = []` y el
  `esperado` refleja solo las ventas de efectivo y los movimientos

### Requirement: Historial de cortes

El sistema SHALL exponer `GET /api/caja/historial?desde=&hasta=` (JWT, fechas
`YYYY-MM-DD`, `400` si son inválidas o `desde > hasta`) que devuelve la lista de
cortes en el rango, cada uno con `fecha`, `efectivo_inicial`, `esperado`,
`efectivo_contado`, `diferencia`, `nota` y `usuario`, ordenada por fecha.

#### Scenario: Rango con varios cortes

- **WHEN** se pide el historial de un mes con tres cortes
- **THEN** la respuesta lista los tres con su `diferencia`, ordenados por fecha

### Requirement: El corte no bloquea el cierre de día

El corte de caja MUST NOT ser requisito para que el cierre de día (#50) ocurra ni
para que las ventas se guarden. Un día SHALL poder quedar cerrado sin corte de
caja.

#### Scenario: Día cerrado sin corte

- **WHEN** llega la hora de cierre y nadie hizo el corte de caja
- **THEN** el día se cierra igual y el corte simplemente no existe para esa fecha

### Requirement: Persistencia local y sincronización

El sistema SHALL persistir apertura, movimientos y corte en un archivo local
append-only por día (`datos_locales/caja/`), escrito con `fsync`, sin depender de
BigQuery ni de internet. El sincronizador (#15) SHALL subir los cortes a la tabla
`corte_caja` de BigQuery de forma idempotente, sin bloquear ninguna operación de
caja si la subida falla.

#### Scenario: Corte sin internet

- **WHEN** se hace un corte y no hay conexión
- **THEN** el corte queda registrado localmente y se responde `201`; la subida a
  BigQuery ocurre después

### Requirement: Pantalla de corte de caja

El frontend SHALL exponer una ruta `/corte`, accesible desde el menú, con una
página que permite abrir la caja (efectivo inicial), registrar retiros y entradas
con motivo, y hacer el corte mostrando el `esperado` y la `diferencia` en vivo
conforme se teclea el `efectivo_contado`. La página SHALL exigir una nota antes
de enviar el corte cuando la diferencia supera el umbral, y SHALL mostrar el
historial de cortes con sus diferencias.

#### Scenario: Diferencia sobre el umbral en la pantalla

- **WHEN** el usuario teclea un `efectivo_contado` que deja una diferencia mayor
  al umbral
- **THEN** la página resalta la diferencia y no deja enviar el corte hasta que se
  escribe una nota

#### Scenario: Historial visible

- **WHEN** se abre `/corte`
- **THEN** se muestran los cortes recientes con su fecha y diferencia

