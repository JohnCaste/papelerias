# Capa de acceso a BigQuery (issue #7)

Reemplaza el patrón anterior (un `bigquery.Client()` nuevo por función,
con SQL armado por f-strings) por un cliente único y consultas siempre
parametrizadas.

## Archivos

| Archivo | Qué hace |
|---|---|
| `cliente.py` | Cliente de BigQuery, construido una vez y reutilizado |
| `parametros.py` | Traduce `{nombre: valor}` a `ScalarQueryParameter`, infiriendo el tipo |
| `consultas.py` | `ejecutar_query` / `ejecutar_uno` — lecturas parametrizadas, con reintento ante errores transitorios |
| `escrituras.py` | `insertar_filas` — inserción por streaming (`insert_rows_json`), no por DML |
| `repositorios/` | Un módulo por entidad: `productos`, `servicios`, `ventas`, `movimientos_inventario`, `cierres`, `usuarios` |

## Regla de oro

**Ninguna función arma SQL concatenando datos de entrada.** El único
texto variable permitido en un string de SQL es el que decide el propio
código (qué condiciones incluir), nunca contenido que venga del usuario
— eso siempre va en `valores` y se traduce a parámetro. Ver `parametros.py`.

## `sqlalchemy-bigquery`

Se evaluó y se descartó para el camino de venta (ver la discusión en
#7): sus `INSERT`
vía ORM son DML fila por fila, y su soporte de `REPEATED RECORD` es
parcial — justo lo que necesita `venta.lineas`. **No implementado en
esta pasada**: `producto`/`servicio` quedaron también sobre el cliente
nativo, por simplicidad y para no arriesgar que el esquema del ORM se
desincronice del definido en `esquema/tablas.py`. Sigue siendo una
opción válida más adelante si se vuelve necesario, no bloqueante.

## Decisiones que valen la pena explicar

**`eliminar` en `productos.py`/`servicios.py` es borrado lógico**
(`activo = FALSE`), no `DELETE`. Un `DELETE` físico dejaría huérfanas
las referencias `producto_id` de ventas y movimientos ya hechos —
se perdería la trazabilidad de qué se vendió.

**Cancelar una venta no modifica la fila original** (`ventas.cancelar`).
Inserta una fila de reversión con signo contrario, referenciada por
`venta_original_id`. Consecuencia práctica: sumar `total` de **todas**
las filas del período (sin filtrar por `estado`) ya da el neto correcto,
porque la reversión resta exactamente lo que sumó la original. Ver el
docstring de `repositorios/ventas.py` para el detalle.

**La deduplicación de `insert_rows_json` es "best effort" y de ventana
corta** (documentado en `escrituras.py`). No basta por sí sola para
garantizar cero duplicados tras una caída larga de internet — el diseño
de la cola de sincronización (#55) debe llevar su propio control de qué
ya se envió.

**Los repositorios no validan reglas de negocio** (por ejemplo, que
`total` cuadre con la suma de las líneas). Son la capa de persistencia;
esa validación le toca a la pantalla de venta (#20, #21, #22).

## Tests

```bash
cd backend
PYTHONPATH=. pytest tests/ -v
```

Todos los tests usan clientes falsos (`monkeypatch` / objetos que
imitan al cliente de BigQuery) — no requieren credenciales ni red. Son
pruebas de la lógica de cada módulo (inferencia de tipos, construcción
de SQL y parámetros, serialización, la reversión de cancelación), no
pruebas de integración contra BigQuery real.

**Pendiente, bloqueado igual que #8**: pruebas de integración contra un
dataset de pruebas en BigQuery. Requieren credenciales que hoy están
comprometidas — no correrlas hasta resolver
#1 y
#2.

## Lo que NO cambió en esta pasada

Los endpoints existentes (`catalogos/productos.py`, `registros/valores.py`,
`autentificacion/credenciales.py`) siguen usando el patrón viejo — con la
inyección SQL sin cerrar. Reconectarlos a esta capa es
#11 y
#4, no este issue.
