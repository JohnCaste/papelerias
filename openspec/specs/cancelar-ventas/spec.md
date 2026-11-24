# cancelar-ventas Specification

## Purpose
TBD - created by archiving change cancelar-ventas. Update Purpose after archive.
## Requirements
### Requirement: Endpoint de cancelación de venta

El sistema SHALL exponer `POST /api/ventas/<venta_id>/cancelar` protegido con
JWT. El cuerpo SHALL aceptar `motivo` (texto), `fecha` (la fecha de la venta
original en formato `YYYY-MM-DD`, para localizarla en el journal local) y,
opcionalmente, `lineas` (lista de índices de línea de la venta original a
revertir). El sistema MUST responder `400` si `motivo` falta o es una cadena
vacía tras recortar espacios, si `fecha` no es una fecha válida, o si algún
índice de `lineas` no existe en la venta original. El sistema MUST responder
`404` si no hay ninguna venta con ese `venta_id` en el journal de esa `fecha`.

#### Scenario: Cancelación aceptada

- **WHEN** se hace `POST /api/ventas/v1/cancelar` con `motivo = "cobro doble"` y
  `fecha` igual a la de la venta `v1`
- **THEN** el sistema responde `201` con la fila de reversión creada, que tiene
  `venta_original_id = "v1"`, `total` negativo y `estado = "cancelada"`

#### Scenario: Motivo obligatorio

- **WHEN** se hace `POST /api/ventas/v1/cancelar` sin `motivo` o con `motivo`
  en blanco
- **THEN** el sistema responde `400` y no escribe nada en el journal

#### Scenario: Venta inexistente

- **WHEN** se pide cancelar un `venta_id` que no está en el journal de la
  `fecha` dada
- **THEN** el sistema responde `404`

### Requirement: La cancelación es un registro reversivo, nunca un borrado

El sistema MUST NOT modificar ni eliminar la fila de la venta original. Cancelar
SHALL escribir una **fila nueva** en el journal local del día en curso mediante
la misma ruta que la captura (#20/#14), con `fecha_hora` igual al instante de la
cancelación, `venta_original_id` apuntando a la venta original, `origen = "pos"`,
y `total`, `cantidad`, `subtotal` y `monto_comision` de cada línea revertida con
**signo opuesto** al de la original. El sistema MUST rechazar con `400` cancelar
una fila que ya es una reversión (que ya tiene `venta_original_id`).

#### Scenario: La fila original queda intacta

- **WHEN** se cancela la venta `v1` de `total = 100`
- **THEN** el journal sigue teniendo la fila `v1` con `total = 100` sin cambios,
  y además una fila nueva con `venta_original_id = "v1"` y `total = -100`

#### Scenario: No se cancela una reversión

- **WHEN** se pide cancelar una fila que tiene `venta_original_id` no nulo
- **THEN** el sistema responde `400`

### Requirement: Registro de motivo, autor y momento

La fila de reversión SHALL guardar `motivo_cancelacion` con el texto recibido,
`cancelada_por` con la identidad del JWT que hizo la petición, y `cancelada_en`
con la marca de tiempo de la cancelación. Estos tres campos SHALL existir en el
modelo de venta compartido (`construir_venta`) y en el esquema de la tabla
`venta`, como `NULLABLE`, y MUST quedar en `null` para las ventas normales.

#### Scenario: Se guarda quién y cuándo

- **WHEN** el usuario `ana` cancela la venta `v1` con `motivo = "error de tecleo"`
- **THEN** la fila de reversión tiene `motivo_cancelacion = "error de tecleo"`,
  `cancelada_por = "ana"` y `cancelada_en` con la hora de la cancelación

#### Scenario: Venta normal sin campos de cancelación

- **WHEN** se captura una venta por el flujo normal (#20)
- **THEN** su fila tiene `motivo_cancelacion`, `cancelada_por` y `cancelada_en`
  en `null`

### Requirement: Devolución parcial de líneas

El sistema SHALL soportar revertir un subconjunto de líneas de la venta. Cuando
la petición trae `lineas` con un subconjunto de índices, la fila de reversión
MUST contener solo esas líneas (con cantidad, subtotal y comisión negativos) y
su `total` MUST ser la suma negada de los subtotales de esas líneas, no el total
completo de la venta original; en ese caso la fila de reversión MUST llevar
`estado = "devolucion_parcial"`. Cuando `lineas` se omite o incluye todas las
líneas, la reversión SHALL cubrir la venta completa y llevar
`estado = "cancelada"`.

#### Scenario: Se devuelven algunas líneas

- **WHEN** la venta `v1` tiene líneas por `$60` y `$40` y se cancela pasando solo
  el índice de la línea de `$40`
- **THEN** la fila de reversión tiene una sola línea de `subtotal = -40`,
  `total = -40` y `estado = "devolucion_parcial"`

#### Scenario: Devolución total explícita

- **WHEN** se pasan todos los índices de línea de la venta `v1`
- **THEN** la fila de reversión cubre el `total` completo negado y lleva
  `estado = "cancelada"`

### Requirement: El dinero cancelado se excluye del total por neteo

El sistema MUST calcular los totales del día sumando el `total` de **todas** las
filas del journal, sin filtrar por `estado`: la fila de reversión resta
exactamente lo que sumó la original. El sistema MUST NOT introducir un filtro
por `estado` en el cálculo del total ni un ajuste manual del total del día.

#### Scenario: El total del día baja al cancelar

- **WHEN** el día tiene una sola venta de `$100` y se cancela
- **THEN** el total del día pasa a `$0`, con dos filas en el journal (`+100` y
  `-100`) y ninguna borrada

### Requirement: Movimientos de inventario inversos

El sistema SHALL dejar que el sincronizador (#15) genere los
`movimiento_inventario` de la cancelación a partir de la fila de reversión: por
cada línea `tipo = "producto"` con cantidad negativa, un movimiento
`tipo = "cancelacion"` que **devuelve** stock, con id determinista para que un
reintento no lo aplique dos veces. La cancelación MUST NOT escribir movimientos
de inventario de forma síncrona en el endpoint.

#### Scenario: El stock regresa tras cancelar una venta detallada

- **WHEN** se cancela una venta con una línea de producto de `cantidad = 3` y esa
  reversión se sincroniza a BigQuery
- **THEN** existe un `movimiento_inventario` `tipo = "cancelacion"` de
  `cantidad = +3` para ese producto y el stock calculado sube en 3

### Requirement: La venta cancelada permanece visible en el historial

`GET /api/ventas/dia` y el resumen del dashboard (#35) SHALL seguir mostrando la
venta original, marcada como cancelada cuando exista una fila de reversión total
que la referencie, y SHALL ocultar de la lista las filas de reversión en sí
(que quedan contadas en el total pero no se listan como ventas). El sistema
MUST NOT quitar la venta original de la respuesta.

#### Scenario: La venta cancelada se lista marcada

- **WHEN** el día tiene la venta `v1` y su reversión total
- **THEN** `GET /api/ventas/dia` lista `v1` con su estado de cancelada y no
  lista una entrada aparte para la fila de reversión

### Requirement: Reconciliación del repositorio de ventas

`acceso_datos/repositorios/ventas.cancelar` SHALL escribir `motivo` en el campo
`motivo_cancelacion` y poblar `cancelada_por` y `cancelada_en`, y MUST NOT
seguir usando `motivo_extemporanea` para el motivo de cancelación.

#### Scenario: El repositorio usa el campo correcto

- **WHEN** se llama a `repositorios.ventas.cancelar(v1, "ana", "duplicada")`
- **THEN** la fila resultante tiene `motivo_cancelacion = "duplicada"` y
  `motivo_extemporanea = null`

