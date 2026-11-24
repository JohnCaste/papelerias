## ADDED Requirements

### Requirement: Endpoint de agregación por granularidad y rango

El sistema SHALL exponer `GET /api/agregaciones` protegido con JWT, que acepta
los parámetros `granularidad` (uno de `dia`, `semana`, `mes`, `anio`), `desde` y
`hasta` (fechas `YYYY-MM-DD`, ambas inclusivas). El endpoint SHALL responder con
un arreglo JSON de buckets ordenados de forma ascendente por `periodo_inicio`,
donde cada bucket tiene `periodo_inicio` y `periodo_fin` (fechas `YYYY-MM-DD`),
`etiqueta` (texto legible del periodo), `total` (número), `num_ventas` (entero),
y los objetos `desglose_categoria`, `desglose_servicio` y `desglose_metodo_pago`
(cada uno una lista de `{ clave, monto }`). El sistema MUST devolver `400` si
`granularidad` no es uno de los valores válidos, si `desde` o `hasta` no son
fechas válidas, o si `desde` es posterior a `hasta`.

#### Scenario: Agregación semanal de un rango

- **WHEN** se pide `GET /api/agregaciones?granularidad=semana&desde=2026-02-02&hasta=2026-03-01`
- **THEN** la respuesta es un arreglo de buckets, uno por semana ISO tocada por
  el rango, cada uno con su `total`, `num_ventas` y los tres desgloses, ordenados
  por `periodo_inicio`

#### Scenario: Granularidad inválida

- **WHEN** se pide `GET /api/agregaciones?granularidad=quincena&desde=2026-01-01&hasta=2026-01-31`
- **THEN** el sistema responde `400` sin ejecutar ninguna consulta

#### Scenario: Rango invertido

- **WHEN** `desde` es `2026-05-01` y `hasta` es `2026-04-01`
- **THEN** el sistema responde `400`

### Requirement: Los periodos se cortan en la zona horaria del negocio

El sistema SHALL asignar cada venta a su periodo usando la fecha civil de
`fecha_hora` en `America/Mexico_City`, no en UTC. Para `granularidad=semana` los
periodos SHALL ser semanas ISO de lunes a domingo. Para `dia`, `mes` y `anio` el
periodo SHALL ser el día, mes calendario y año calendario locales
correspondientes.

#### Scenario: Venta nocturna cuenta en el día local

- **WHEN** una venta tiene `fecha_hora = 2026-02-10T05:30:00Z` (23:30 del
  2026-02-09 en `America/Mexico_City`) y se pide `granularidad=dia`
- **THEN** esa venta se suma en el bucket cuyo `periodo_inicio` es `2026-02-09`

#### Scenario: Semanas ISO de lunes a domingo

- **WHEN** se piden buckets con `granularidad=semana`
- **THEN** cada bucket tiene `periodo_inicio` en lunes y `periodo_fin` en el
  domingo siguiente, sin huecos ni solapamientos entre buckets consecutivos

### Requirement: La agregación se calcula solo desde las ventas

El sistema SHALL calcular todos los totales y desgloses consultando
`lapape.venta`. El sistema MUST NOT leer la tabla `cierre` ni ninguna otra
fuente de totales precalculados, y MUST NOT escribir totales agregados en
ninguna tabla.

#### Scenario: No se tocan totales precalculados

- **WHEN** se atiende cualquier petición a `/api/agregaciones`
- **THEN** la única tabla consultada es `venta` y no se ejecuta ninguna
  escritura

### Requirement: Las cancelaciones se netean sin filtrar por estado

El sistema SHALL sumar el campo `total` de todas las filas de `venta` del rango,
incluidas las filas de reversión (`venta_original_id IS NOT NULL`), sin filtrar
por `estado`. El sistema SHALL contar en `num_ventas` únicamente las filas con
`venta_original_id IS NULL`.

#### Scenario: Venta cancelada no infla ni el total ni el conteo

- **WHEN** en el rango hay una venta de `$100` y su fila de reversión de `-$100`
- **THEN** el bucket correspondiente aporta `0` al `total` y `1` a `num_ventas`

### Requirement: Desglose por línea, no por venta

El sistema SHALL construir `desglose_categoria` sumando `lineas.subtotal`
agrupado por `lineas.categoria` sobre las líneas con `tipo = 'categoria'`, y
`desglose_servicio` sumando `lineas.subtotal` agrupado por `lineas.servicio_id`
(o su nombre resuelto) sobre las líneas con `tipo = 'servicio'`. El sistema
SHALL construir `desglose_metodo_pago` sumando `venta.total` agrupado por
`venta.metodo_pago`. La suma de los montos de `desglose_metodo_pago` de un
bucket MUST ser igual al `total` de ese bucket.

#### Scenario: Venta con varias categorías reparte el subtotal

- **WHEN** una venta tiene una línea `categoria='copias'` de `$30` y otra
  `categoria='dulces'` de `$20`
- **THEN** `desglose_categoria` del bucket suma `$30` en `copias` y `$20` en
  `dulces`, no `$50` en la primera categoría

#### Scenario: El desglose por método de pago cuadra con el total

- **WHEN** un bucket tiene `total = 500`
- **THEN** la suma de `monto` en `desglose_metodo_pago` es `500`

### Requirement: Se retira el endpoint de registros legado

El sistema MUST NOT seguir exponiendo `GET /api/registros?año=` y el archivo
`backend/registros/valores.py` SHALL eliminarse junto con su prueba. El frontend
(`admin.ts`, `Ventas.tsx`) SHALL obtener los datos del calendario de ventas
desde `GET /api/agregaciones` con `granularidad=dia`, y calcular el color de
cada semana (`v` con actividad la mayoría de días, `a` con actividad parcial,
`r` sin actividad) a partir de los buckets diarios.

#### Scenario: El frontend ya no llama a /api/registros

- **WHEN** se carga la pantalla de Ventas
- **THEN** la petición de datos va a `/api/agregaciones` y no existe ninguna
  llamada a `/api/registros`

#### Scenario: La ruta legada deja de existir

- **WHEN** un cliente pide `GET /api/registros?año=2026`
- **THEN** el backend responde `404`
