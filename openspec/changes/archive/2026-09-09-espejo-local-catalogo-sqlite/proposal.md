## Why

Cada búsqueda del catálogo paga la latencia fija de red de BigQuery
(0.5-2s por consulta), sin importar cuántos productos tenga la tienda.
El debounce ya reduce cuántas búsquedas se disparan al teclear (ver
`openspec/changes/archive/2026-09-09-optimizar-catalogo-y-logging/`),
pero cada búsqueda que sí se ejecuta sigue viajando a la nube y de vuelta.
Con clientes esperando en el mostrador, ese medio segundo a dos segundos
por búsqueda es justo lo que se siente "tedioso".

Antes de comprometerse a migrar el motor completo a MySQL (un cambio de
infraestructura mayor, con más riesgo y esfuerzo), vale la pena validar
si un almacén de lectura local resuelve el problema real: la latencia de
red, no el motor de base de datos en sí. Un espejo de solo lectura del
catálogo en SQLite (viene con Python, cero instalación adicional en la PC
del negocio) puede responder búsquedas en milisegundos sin tocar la red,
y confirma o descarta la necesidad de MySQL con datos reales antes de
invertir en esa migración.

## What Changes

- Nuevo componente en segundo plano (`almacen_local/espejo_catalogo.py`,
  mismo patrón de hilo daemon que `Sincronizador` y `ProgramadorCierre`)
  que mantiene una copia local en SQLite de `producto` (activos),
  `categoria` (activas) y el stock agregado por producto
  (`SUM(movimiento_inventario.cantidad)`), refrescándola periódicamente
  desde BigQuery.
- Los endpoints de lectura del catálogo —
  `GET /api/catalogo/buscar`, `/api/catalogo/paginador`,
  `/api/catalogo/categorias`, `/api/catalogo/marcas` — pasan a leer del
  espejo local en vez de BigQuery directo. Su contrato HTTP (parámetros,
  forma de la respuesta) **no cambia**.
- Un alta/edición/baja de producto (que sigue escribiendo directo en
  BigQuery, sin journal de por medio) actualiza también el espejo local
  de inmediato después de confirmarse en BigQuery, para que el catálogo
  no muestre datos obsoletos justo después de editar desde la misma PC.
- Si el espejo todavía no existe (primer arranque, antes del primer
  refresco) o su lectura falla por cualquier motivo, el sistema **SHALL**
  responder igual usando BigQuery directo como respaldo — el catálogo
  nunca debe romperse ni quedar vacío por culpa del espejo.
- El espejo se puede borrar en cualquier momento sin pérdida de datos: se
  reconstruye solo en el siguiente ciclo de refresco. No es una segunda
  fuente de verdad, es una proyección de lectura.
- Fuera de alcance de este cambio: la búsqueda por código de barras del
  escaneo directo (`obtener_por_codigo_barras`, usada por el flujo de
  Vender) y las operaciones de escritura (`crear`/`actualizar`/`eliminar`
  producto) siguen exactamente igual que hoy, contra BigQuery.

## Capabilities

### New Capabilities
- `espejo-local-catalogo`: mantenimiento en segundo plano de una copia
  local de solo lectura del catálogo (producto, categoría, stock), con
  refresco periódico desde BigQuery y reconstrucción automática si se
  borra.

### Modified Capabilities
- `busqueda-de-catalogo`: los cuatro endpoints de lectura del catálogo
  pasan a responder desde el espejo local en vez de BigQuery directo,
  con BigQuery como respaldo si el espejo no está disponible. El
  contrato de request/response de cada endpoint no cambia.

## Impact

- **Backend (nuevo)**:
  - `almacen_local/espejo_catalogo.py` — hilo de refresco periódico.
  - `acceso_datos/repositorios/productos_local.py` (o similar) —
    equivalente de `buscar_con_total`/`listar`/`marcas_distintas` contra
    SQLite en vez de BigQuery.
  - `backend/datos_locales/catalogo_espejo.sqlite3` — archivo nuevo,
    mismo patrón de `datos_locales/` que journal y cierres (no se sube a
    git, se reconstruye solo).
- **Backend (modificado)**:
  - `catalogos/productos.py` — los 4 endpoints de lectura usan el nuevo
    repositorio local con respaldo a BigQuery; `crear`/`actualizar`/
    `eliminar` ganan un paso adicional que actualiza el espejo tras
    escribir en BigQuery.
  - `main.py` — arranca el nuevo hilo del espejo junto a
    `Sincronizador`/`ProgramadorCierre`.
- **Tests**: nuevos tests para el repositorio local, el refresco, el
  fallback a BigQuery, y la actualización del espejo tras escribir.
- **Sin cambios**: esquema de BigQuery, contrato HTTP de los endpoints,
  frontend, flujo de Vender / escaneo de código de barras.
