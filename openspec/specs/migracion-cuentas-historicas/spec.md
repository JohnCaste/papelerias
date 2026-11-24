# migracion-cuentas-historicas Specification

## Purpose
Reglas de la migración única (#10) del histórico diario agregado de
`nuevas_tablas.cuentas` al esquema `venta` / `venta.lineas` de #8: una venta por
fila legada con `origen = 'migracion'` y `detallada = false`, una línea por
categoría con monto, valores centinela para lo que el legado no registra,
idempotencia y criterio de aceptación por cuadre de totales anuales.
## Requirements
### Requirement: Cada fila del legado produce una venta

El sistema SHALL crear exactamente una fila de `lapape.venta` por cada fila de
`nuevas_tablas.cuentas` que tenga al menos una categoría con monto distinto de
cero. El `venta.id` MUST ser `CONCAT('migracion-', <id legado>)`, reutilizando
el UUID de la fila de `cuentas` para poder rastrear el origen. La venta creada
MUST tener `detallada = false`, `origen = 'migracion'`, `estado = 'activa'`,
`extemporanea = false` y `fecha_hora` igual a la medianoche UTC (`00:00:00`) de
`cuentas.fecha`. El campo `total` MUST ser la suma de los montos de categoría no
nulos y distintos de cero de esa fila; `creado_en` MUST registrar el instante de
ejecución de la migración. Cuando varias filas del legado comparten `fecha`
(caso real en los datos), cada una produce su propia venta independiente.

#### Scenario: Fila con varias categorías

- **WHEN** una fila de `cuentas` tiene `id = 'abc'`, `fecha = 2024-01-01` y
  montos `productos = 259`, `copias = 23`, `dulces = 204`, `helados = 57`,
  `recargas = 150`
- **THEN** se inserta una `venta` con `id = 'migracion-abc'`,
  `fecha_hora = 2024-01-01T00:00:00Z`, `total = 693`, `detallada = false`,
  `origen = 'migracion'`, `estado = 'activa'` y `extemporanea = false`

#### Scenario: Varias filas legadas en la misma fecha

- **WHEN** tres filas de `cuentas` distintas tienen `fecha = 2024-01-02`
- **THEN** se insertan tres ventas independientes, cada una con su propio
  `id = 'migracion-<id legado>'` y su propio `total`

#### Scenario: Fila sin ningún monto

- **WHEN** una fila de `cuentas` tiene las cinco categorías en 0 o NULL
- **THEN** no se inserta ninguna `venta` para esa fila

### Requirement: Una línea por categoría con monto distinto de cero

El sistema SHALL agregar a `venta.lineas` una entrada por cada una de las cinco
categorías del legado (`productos`, `copias`, `dulces`, `helados`, `recargas`)
cuyo monto sea no NULL y distinto de cero. Cada línea MUST tener
`tipo = 'categoria'`, `categoria` igual al nombre de columna de la categoría,
`descripcion` igual al nombre legible de la categoría, `cantidad = 1`,
`precio_unitario` y `subtotal` iguales al monto de esa categoría, y
`producto_id`, `servicio_id`, `costo_unitario` y `monto_comision` en NULL.
Las categorías con monto cero o NULL MUST omitirse.

#### Scenario: Solo se materializan las categorías con monto

- **WHEN** una fila de `cuentas` tiene `productos = 456`, `copias = 567`,
  `dulces = NULL`, `helados = NULL`, `recargas = NULL`
- **THEN** la venta migrada tiene exactamente 2 líneas (`productos`, `copias`),
  cada una con `cantidad = 1` y `subtotal` igual a su monto

#### Scenario: La suma de las líneas cuadra con el total

- **WHEN** se migra cualquier fila de `cuentas`
- **THEN** `SUM(lineas.subtotal)` de la venta creada es igual a su `total`

### Requirement: Valores centinela para campos sin equivalente legado

El sistema SHALL rellenar los campos requeridos por `venta` que no existen en
`cuentas` con centinelas fijos y documentados: `metodo_pago = 'desconocido'` y
`usuario_id = 'sistema'`. El sistema MUST NOT inventar métodos de pago ni
usuarios reales para las filas migradas.

#### Scenario: Venta migrada expone el centinela

- **WHEN** se inserta una venta a partir de `cuentas`
- **THEN** `metodo_pago = 'desconocido'` y `usuario_id = 'sistema'`

### Requirement: La migración es idempotente

El sistema SHALL abortar sin escribir si `lapape.venta` ya contiene al menos una
fila con `origen = 'migracion'`, a menos que se pase la opción `--forzar`. El
sistema SHALL ofrecer una opción `--dry-run` que reporta los conteos y no
escribe nada. La migración MUST NOT modificar ni borrar `nuevas_tablas.cuentas`.

#### Scenario: Segunda ejecución sin bandera

- **WHEN** ya existen ventas con `origen = 'migracion'` y se ejecuta la
  migración sin `--forzar`
- **THEN** el proceso termina con error, sin insertar filas

#### Scenario: Dry run

- **WHEN** se ejecuta la migración con `--dry-run`
- **THEN** se imprimen los conteos de filas leídas, ventas y líneas a insertar,
  y no se escribe nada en `lapape.venta`

### Requirement: Criterio de aceptación por cuadre de totales anuales

El sistema SHALL verificar, tras insertar, que para cada año presente en
`cuentas` el `SUM(total)` de las ventas con `origen = 'migracion'` de ese año es
igual a la suma de todos los montos de categoría de `cuentas` en el mismo año.
Si algún año no cuadra, el sistema MUST reportarlo como fallo y la migración
NO se considera válida.

#### Scenario: Todos los años cuadran

- **WHEN** termina la inserción y para cada año los totales de `venta`
  (`origen = 'migracion'`) coinciden con `cuentas`
- **THEN** el sistema informa que la migración es válida

#### Scenario: Un año no cuadra

- **WHEN** el total migrado de un año difiere del total legado de ese año
- **THEN** el sistema reporta el año, ambos totales y la diferencia, y marca la
  migración como no válida

