## Why

El requisito original de reportes pide totales por venta, día, semana, mes y
año. La regla de #8 es que **solo se almacena la venta**; todo lo demás son
consultas agregadas — guardar totales precalculados garantiza que se
desincronicen. Hoy el único endpoint que agrega (`backend/registros/valores.py`)
lee la tabla legada `nuevas_tablas.cuentas`, trae el año completo a memoria,
calcula las semanas del mes con `%W` y `round((ultimoDia.day + diaSemana) / 7)`
—frágil en años bisiestos y meses que cruzan semanas— y arma el JSON con
`str(respuesta).replace("'", '"')`, que produce JSON inválido en cuanto un texto
trae un apóstrofe. Con #10 ya migrado, todo el histórico vive en `lapape.venta`
y se puede reemplazar por una agregación real.

## What Changes

- **Nuevo endpoint** `GET /api/agregaciones?granularidad=<dia|semana|mes|anio>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD`
  (JWT, como el resto). Devuelve una lista de buckets planos ordenados por
  fecha, cada uno con `periodo_inicio`, `periodo_fin`, `etiqueta`, `total`,
  `num_ventas`, `desglose_categoria`, `desglose_servicio`, `desglose_metodo_pago`.
- **Agregación 100% sobre `lapape.venta`**, aprovechando su partición por
  `fecha_hora`. Nunca lee ni escribe `cierre` ni totales precalculados.
- **Bucketing en `America/Mexico_City`**: los periodos se cortan con
  `DATE(fecha_hora, 'America/Mexico_City')`, consistente con el cierre de día
  (#50). Las semanas son **ISO (lunes–domingo)** vía `DATE_TRUNC(..., WEEK(MONDAY))`.
- **Cancelaciones (#26):** se suman todas las filas del rango sin filtrar por
  `estado`; la fila de reversión resta lo que sumó la original. `num_ventas`
  cuenta solo filas con `venta_original_id IS NULL`.
- **Desglose correcto por línea:** `desglose_categoria` y `desglose_servicio`
  suman `lineas.subtotal` agrupando por `UNNEST(lineas)`, no el `total` de la
  venta contra su primera línea (atajo que usa el cierre local).
- **Índice / partición (tarea 4 del issue):** en BigQuery no hay índices;
  `venta` ya está particionada por `fecha_hora` y clusterizada por
  `estado, metodo_pago` (ver `esquema/tablas.py`). Se documenta y se verifica
  que las consultas filtran por `fecha_hora` para no escanear toda la tabla.
- **BREAKING — se elimina `backend/registros/valores.py`** y la ruta
  `GET /api/registros?año=`. `frontend/src/services/admin.ts` y `Ventas.tsx`
  pasan al nuevo endpoint; el coloreo de semanas (`v` / `a` / `r`) se calcula
  en el frontend a partir de los buckets diarios.
- Se retira `registros/` (carpeta) y `tests/test_endpoint_valores.py`; se
  añaden pruebas nuevas para el endpoint de agregaciones.

## Capabilities

### New Capabilities

- `agregaciones-de-ventas`: consulta agregada de ventas por granularidad
  (día / semana ISO / mes / año) y rango de fechas, con desglose por categoría,
  servicio y método de pago, calculada siempre desde `lapape.venta` en la zona
  horaria del negocio y correcta ante cancelaciones.

### Modified Capabilities

<!-- Ninguna capability de OpenSpec existente. `registros/valores.py` nunca
     tuvo spec; su reemplazo se describe entero en la nueva capability. -->

## Impact

- **Nuevo:** `backend/reportes/agregaciones.py` (endpoint) +
  `backend/acceso_datos/repositorios/agregaciones.py` (consulta) +
  `backend/tests/test_endpoint_agregaciones.py` y
  `test_repositorio_agregaciones.py`.
- **Modificado:** `backend/main.py` (registra `/api/agregaciones`, quita
  `/api/registros`), `frontend/src/services/admin.ts`,
  `frontend/src/pages/Ventas.tsx`.
- **Eliminado:** `backend/registros/valores.py`, `backend/registros/`,
  `backend/tests/test_endpoint_valores.py`.
- **Depende de:** `acceso_datos/consultas.ejecutar_query`, esquema `venta` de
  `esquema/tablas.py`, credenciales BigQuery de `backend/.env`.
- **Desbloquea:** #35 (dashboard del día) y #52 (cierre mensual/anual) pueden
  consumir esta agregación en lugar de reimplementarla.
