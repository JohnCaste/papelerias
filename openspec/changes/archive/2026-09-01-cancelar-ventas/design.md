## Context

La captura de ventas (#20) es *journal-first*: al oprimir Enter, la venta se
escribe en el journal local (`almacen_local/journal.py`, #14) con `fsync` y se
responde en milisegundos; el sincronizador (#15,
`almacen_local/sincronizador.py`) la sube a BigQuery en segundo plano y, de
paso, genera un `movimiento_inventario` por cada línea `tipo = "producto"`.

El terreno para cancelar ya está preparado en varios sitios, sin que exista aún
la operación:

- El esquema de `venta` (`backend/esquema/tablas.py`) tiene `estado`
  (`'activa' | 'cancelada'`) y `venta_original_id` (apunta a la venta que una
  reversión cancela), y clusteriza por `estado`.
- `sincronizador._generar_movimientos_de_venta` ya mira `venta_original_id`:
  si está presente, marca los movimientos como `tipo = "cancelacion"` y usa la
  `cantidad` de la línea con su signo (negativa en la reversión) para devolver
  stock. Los ids de movimiento son `uuid5(venta_id, índice)` — deterministas,
  idempotentes.
- `reportes/agregaciones.py` (#34) ya netea cancelaciones **sin filtrar por
  `estado`**: suma `total` de todas las filas del rango.
- `acceso_datos/repositorios/ventas.py` ya tiene una función `cancelar()` que
  inserta la fila de reversión directo a BigQuery, pero **no está conectada a
  ningún endpoint** y mete el motivo en `motivo_extemporanea` (un hack).
- El dashboard (#35) dejó `ultimas_ventas` como solo lectura y difirió
  explícitamente el botón "cancelar" a este cambio (#26).

Lo que falta: el endpoint, la escritura *journal-first* de la reversión, tres
campos de auditoría, el reflejo en el dashboard / `GET /api/ventas/dia`, y la UI.

## Goals / Non-Goals

**Goals:**

- Cancelar una venta como **registro nuevo de signo contrario**, respetando el
  append-only de #8: nunca `UPDATE` ni `DELETE` sobre la fila original.
- Que la cancelación funcione **sin internet**, por la misma ruta que la
  captura: escribir al journal local y dejar que el sincronizador haga el resto.
- Exigir `motivo`; guardar `cancelada_por` y `cancelada_en`.
- Soportar **devolución parcial** (un subconjunto de líneas).
- Que el total del día **baje solo**, por neteo, sin filtros ni ajustes
  manuales, y que la venta original **siga visible** en el historial marcada
  como cancelada.
- Cerrar el botón "Cancelar" del dashboard.

**Non-Goals:**

- Reabrir / "descancelar" una venta: si la cancelación fue un error, se captura
  la venta de nuevo. No se cancela una reversión.
- Reconciliar cancelaciones de días ya cerrados contra el corte de caja (#36) o
  el cierre de día (#50) de esa fecha pasada: la reversión se fecha *hoy* y
  afecta el total de *hoy*; los cierres pasados quedan intactos. Ajustar un día
  cerrado es alcance de #54.
- Editar montos de una línea "en el sitio": cancelar + recapturar es el flujo.
- Permisos por rol para cancelar (todo usuario con JWT puede): un control de
  autorización más fino queda fuera.

## Decisions

### 1. La reversión se escribe al journal local, no directo a BigQuery

**Qué:** el endpoint construye la fila de reversión y la escribe con
`journal.escribir_venta(...)` (día en curso). El sincronizador la sube y genera
los `movimiento_inventario` inversos en su próximo ciclo.

**Por qué:** es la misma garantía que #20 — cancelar no puede depender de que
haya internet ni bloquearse esperando a BigQuery. Reutiliza `construir_venta`,
el `fsync`, y toda la maquinaria de sincronización/idempotencia ya probada.

**Alternativa descartada:** llamar a `repositorios.ventas.cancelar()`
(directo a BigQuery). Rompe el modo offline y duplica la lógica de movimientos
de inventario que el sincronizador ya hace. En su lugar, esa función se
**reescribe** para alinear los campos nuevos y se deja como ruta de
mantenimiento / scripts, no como camino del endpoint.

### 2. `estado` vive en la fila de reversión; el de la original se deriva al leer

**Qué:** la fila original **no se toca** — sigue con `estado = "activa"`. La
fila de reversión lleva `estado = "cancelada"` (total) o
`estado = "devolucion_parcial"` (subconjunto). Al leer el día, `dashboard.py` y
`capturas.listar_ventas_del_dia` construyen el set de `venta_original_id` de las
reversiones **totales** y marcan esas ventas originales como canceladas en la
respuesta; las filas de reversión no se listan como ventas (pero su `total`
negativo ya está sumado).

**Por qué:** append-only. El comentario del esquema que dice que la cancelación
"cambia este estado de la fila que referencia" es engañoso y se corrige — con
journal-first + BigQuery streaming no hay `UPDATE` barato ni atómico, y el
estado derivado es suficiente para todo lo que se consume hoy.

**Alternativa descartada:** un `UPDATE` a la fila original en BigQuery. Caro,
no atómico con el insert de la reversión, e imposible de replicar en el journal
local sin reescribir líneas (que el journal justamente prohíbe).

### 3. Localizar la venta original por `id` + `fecha`

**Qué:** el cuerpo del `POST` incluye `fecha` (día de la venta original). El
backend hace `journal.leer_dia(fecha)` y busca por `id`. Se añade un helper
`journal.buscar_venta(id, fecha)` que devuelve la venta o `None`.

**Por qué:** el journal está particionado por día y los `id` son `uuid4` (no
codifican fecha). El frontend siempre conoce la fecha del contexto en que
muestra la venta (el dashboard consulta un día concreto; `GET /api/ventas/dia`
también). Pedir la fecha evita escanear 30 archivos por cancelación.

**Alternativa descartada:** barrer los últimos N días del journal buscando el
`id`. Innecesario cuando el llamador ya tiene la fecha; se puede añadir después
si aparece un caso sin fecha.

### 4. Devolución parcial: la reversión sólo lleva las líneas devueltas

**Qué:** si `lineas` (lista de índices) viene en el cuerpo, la reversión
contiene sólo esas líneas negadas y `total = -sum(subtotales de esas líneas)`;
`estado = "devolucion_parcial"`. Si se omite o están todas, cubre la venta
completa con `estado = "cancelada"`.

**Por qué:** el sincronizador ya genera un `movimiento_inventario` por línea de
producto presente en la fila — si la reversión sólo trae las líneas devueltas,
el stock que regresa es exactamente el correcto, sin casos especiales. El neteo
del total también sale solo.

**Consecuencia:** una venta con devoluciones parciales puede tener varias filas
de reversión. La original se marca "cancelada" sólo cuando existe una reversión
**total**; con parciales queda "activa" y su neto es total − Σ parciales.

### 5. Campos de auditoría en el modelo compartido

**Qué:** `construir_venta` gana `motivo_cancelacion`, `cancelada_por`,
`cancelada_en` (default `None`). El esquema BigQuery `venta` gana las tres
columnas `NULLABLE`. `_quitar_campos_locales` del sincronizador no necesita
cambios (sólo quita `estado_local`).

**Por qué:** el modelo es la única fuente de la forma de una fila de venta,
compartida entre journal y BigQuery (lo dice su docstring). Poner ahí los campos
mantiene las dos rutas sincronizadas. Son `NULLABLE` porque el 99% de las filas
(ventas normales) los llevan vacíos.

**Nota de despliegue:** BigQuery permite añadir columnas `NULLABLE` a una tabla
existente sin recrearla; las filas viejas quedan con `NULL`.

## Risks / Trade-offs

- **Cancelar una venta de un día ya cerrado descuadra ese cierre** → La
  reversión se fecha *hoy*, así que reduce el total de *hoy*, no el del día
  cerrado. Es deliberado (Non-Goal: reconciliación de días cerrados es #54).
  Mitigación: el `motivo` queda registrado y la venta original sigue visible;
  el descuadre entre "total del día cerrado" y "neto real" es auditable.
- **Doble clic / reintento del endpoint crea dos reversiones** → El journal no
  deduplica reversiones por sí solo. Mitigación: derivar un `id` determinista
  para la fila de reversión (p. ej. `uuid5(venta_original_id + ":rev")` para la
  total; incluir el conjunto de líneas para las parciales) y que
  `journal.escribir_venta` / la lectura ignoren duplicados por `id`; como
  respaldo, el frontend deshabilita el botón al enviar.
- **Índices de línea como contrato frágil** → si el orden de `lineas` en la
  venta original cambiara, los índices apuntarían mal. Mitigación: los índices
  se resuelven contra la misma fila leída del journal en la petición; la venta
  ya está congelada (no se edita). Aun así, validar rango y devolver `400` si
  algún índice no existe.
- **`movimiento_inventario` sólo se genera al sincronizar** → si el negocio
  cancela y mira el stock sin internet, verá el stock viejo unos segundos.
  Mitigación: es el mismo retraso que ya tiene la venta normal (#21); "el stock
  real manda, no el sistema".
- **`agregaciones` con un rango que parte original y reversión** → si el rango
  incluye la venta pero no su reversión (fechada otro día), el total no netea.
  Es correcto por diseño (cada día refleja su propio movimiento de caja), pero
  conviene documentarlo en el spec de agregaciones si genera dudas; no se
  cambia código.
