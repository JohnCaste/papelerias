## Context

Con #10 migrado, `lapape.venta` tiene todo el histórico (`origen='migracion'`)
más lo capturado en vivo (`origen='pos'`). La tabla está **particionada por
`fecha_hora`** y clusterizada por `estado, metodo_pago` (`esquema/tablas.py`).
`venta.lineas` es un `RECORD REPEATED`: `{tipo, categoria, producto_id,
servicio_id, descripcion, cantidad, precio_unitario, costo_unitario, subtotal,
monto_comision}`.

Lo que hay hoy y se va:

- `backend/registros/valores.py` — lee `nuevas_tablas.cuentas`, trae el año a
  memoria, calcula semanas con `%W` / `round(...)` (frágil en bisiestos y meses
  que cruzan semana), arma JSON con `str(...).replace("'", '"')`. Ruta
  `GET /api/registros?año=`. Prueba: `tests/test_endpoint_valores.py`.
- `frontend/src/services/admin.ts::obtenerSemanas(anio)` y `pages/Ventas.tsx`
  consumen esa ruta y esperan `[{mes, mesStr, sem:[{num,status,datos,fechaInicio,
  fechaFin}]}]` con `status` ∈ `v|a|r`.

Patrones a reutilizar:

- `acceso_datos/repositorios/ventas.py::total_del_rango` ya suma
  `COALESCE(SUM(total),0)` + `COUNTIF(venta_original_id IS NULL)` filtrando por
  `DATE(fecha_hora) BETWEEN ...`. La nueva consulta es la versión "GROUP BY
  periodo + desgloses".
- `almacen_local/cierres.py::_calcular_desglose` produce `[{clave, monto}]` —
  mismo formato de salida, pero usa el atajo "primera línea + total de la
  venta". La agregación real debe sumar por `UNNEST(lineas)`.
- Tests de endpoint: `tests/test_endpoint_*.py` construyen la app con
  `crear_app()` y parchean el repositorio.

## Goals / Non-Goals

**Goals:**

- Un endpoint genérico `GET /api/agregaciones` con `granularidad` + rango.
- Totales y desgloses correctos: zona horaria del negocio, semanas ISO,
  cancelaciones neteadas, desglose por línea.
- Cerrar el issue #34 completo: quitar `valores.py`, migrar el frontend.

**Non-Goals:**

- Generar o modificar `cierre` (es #50–#52). Esta agregación es de solo lectura
  sobre `venta`.
- PDF / Excel de reportes (#43, #44).
- Cachear resultados. Si el costo de escaneo se vuelve un problema, se aborda
  aparte; hoy el volumen es trivial.
- Rediseñar la pantalla de Ventas; solo se cambia de dónde saca los datos y
  dónde se calcula el color de la semana.

## Decisions

### 1. Endpoint genérico con buckets planos

`GET /api/agregaciones?granularidad=<dia|semana|mes|anio>&desde=YYYY-MM-DD&hasta=YYYY-MM-DD`
→ `200` con:

```json
[
  {
    "periodo_inicio": "2026-02-09",
    "periodo_fin": "2026-02-15",
    "etiqueta": "Semana del 9 al 15 de febrero de 2026",
    "total": 1234.5,
    "num_ventas": 12,
    "desglose_categoria":   [{ "clave": "copias", "monto": 300 }, ...],
    "desglose_servicio":    [{ "clave": "Copia B/N", "monto": 120 }, ...],
    "desglose_metodo_pago": [{ "clave": "efectivo", "monto": 900 }, ...]
  }
]
```

- **Por qué plano y no el árbol mes→semana→día:** el árbol actual está atado a
  una sola pantalla. Con buckets planos, #35 (dashboard) y #52 (cierre
  mensual/anual) consumen lo mismo. La pantalla de Ventas arma su calendario a
  partir de los buckets `granularidad=dia`.
- **Validación:** `granularidad` fuera de la lista → 400; `desde`/`hasta` no
  parseables o `desde > hasta` → 400. Sin límite de rango por ahora.

### 2. Bucketing en `America/Mexico_City`

Todas las consultas cortan el periodo con la fecha civil local:

```sql
DATE(fecha_hora, 'America/Mexico_City')                     -- dia
DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), WEEK(MONDAY))  -- semana ISO
DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), MONTH)  -- mes
DATE_TRUNC(DATE(fecha_hora, 'America/Mexico_City'), YEAR)   -- anio
```

- Consistente con el cierre de día (#50), que usa `datetime.date.today()` local.
- El filtro del rango es **exacto y podable** sin doble condición:
  `fecha_hora >= TIMESTAMP(@desde, 'America/Mexico_City') AND
  fecha_hora < TIMESTAMP(DATE_ADD(@hasta, INTERVAL 1 DAY), 'America/Mexico_City')`.
  `TIMESTAMP(date, tz)` da el instante UTC de la medianoche local, así que el
  rango cae directo sobre la columna de partición (`fecha_hora`) y a la vez
  respeta el corte en hora local. (La implementación descartó el "colchón
  ±1 día" que este documento proponía antes: no hace falta.)
- `periodo_inicio`/`periodo_fin` se devuelven como las fechas locales del
  bucket; `etiqueta` se arma en Python (reutilizar `utilidades/utils.obtenerMes`).

### 3. Suma correcta ante cancelaciones y multi-línea

- **Total y conteo:** `SUM(total)` de todas las filas (la reversión #26 ya trae
  `total` negativo) y `COUNTIF(venta_original_id IS NULL)` — igual que
  `ventas.total_del_rango`. No se filtra por `estado`.
- **Desglose categoría/servicio:** subconsulta con `UNNEST(lineas) l`, agrupando
  `SUM(l.subtotal)` por `l.categoria` (líneas `tipo='categoria'`) y por
  `l.servicio_id` (`tipo='servicio'`). Las líneas de una reversión traen
  `subtotal` negativo, así que también netean.
- **Desglose método de pago:** `SUM(venta.total)` por `venta.metodo_pago`. Su
  suma cuadra con `total` del bucket (invariante que se prueba).
- **`servicio_id` → nombre:** el desglose de servicio devuelve el `servicio_id`;
  la resolución al nombre legible (`servicio.nombre`) se hace con un `JOIN` a
  `servicio` o un segundo query + map en Python. Decisión: `LEFT JOIN` en la
  misma consulta, `clave = COALESCE(s.nombre, l.servicio_id)`.

### 4. Estructura de archivos

- `backend/acceso_datos/repositorios/agregaciones.py` — `agregar_por_periodo(
  granularidad, desde, hasta) -> list[dict]`. Arma el SQL (la única pieza que
  varía es la expresión de `DATE_TRUNC`), ejecuta con `ejecutar_query`, devuelve
  filas crudas por periodo.
- `backend/reportes/agregaciones.py` — `obtener_agregaciones()` lee y valida
  `request.args`, llama al repositorio, añade `etiqueta` y `periodo_fin`,
  `jsonify`. (Carpeta `reportes/` nueva; `registros/` se borra.)
- `backend/main.py` — `from reportes import agregaciones`; registra
  `GET /api/agregaciones`; quita el import de `registros.valores` y la ruta
  `/api/registros`.

### 5. Frontend

- `admin.ts`: `obtenerSemanas(anio)` → `obtenerAgregaciones(granularidad, desde,
  hasta)` contra `/api/agregaciones`. Para la pantalla actual: `granularidad=dia`,
  `desde=<anio>-01-01`, `hasta=<anio>-12-31`.
- `Ventas.tsx`: agrupar los buckets diarios en meses y semanas ISO en el cliente
  y calcular `status` (`v` si hay actividad ≥ 6 días de la semana, `a` si 1–5,
  `r` si 0) — la misma regla que hoy vive en `valores._UMBRAL_SEMANA_COMPLETA`.
- `test_endpoint_valores.py` se elimina; su intención (semanas correctas en
  bisiestos, JSON válido con apóstrofes) se recrea en
  `test_endpoint_agregaciones.py`.

## Risks / Trade-offs

- **Poda de partición con filtro en hora local** → si se filtra solo por
  `DATE(fecha_hora, tz)`, BigQuery no poda la partición (que es sobre el
  TIMESTAMP UTC) y escanea toda la tabla. Mitigación: filtro doble (decisión 2)
  con un colchón de ±1 día en UTC. Verificar con `--dry_run` / `totalBytesProcessed`.
- **DST de México** → `America/Mexico_City` observó cambios de horario hasta
  2022; BigQuery usa la base tzdata, así que fechas históricas se resuelven con
  las reglas de su año. Aceptable: el cuadre con el Excel es por totales de
  periodo, no por segundos.
- **Ventas con `metodo_pago='desconocido'`** (histórico migrado en #10) →
  aparecen como una clave más en `desglose_metodo_pago`. Es correcto y esperado;
  se documenta para que el frontend no lo trate como error.
- **Las ventas migradas en #10 tienen `fecha_hora` en medianoche UTC** → en
  `America/Mexico_City` (UTC−6) eso es las 18:00 del día anterior. Verificado en
  el smoke test: la venta migrada del `2024-01-01` cae en el bucket **2023** al
  agrupar en hora local. Efecto acotado (solo filas del 1 de enero cambian de
  año) y monto trivial frente al total histórico; se acepta. Si el cuadre con
  el Excel lo exige, se corrige en una pasada aparte sobre esas filas.
- **Cambio BREAKING de API** → `/api/registros` desaparece en el mismo cambio en
  que el frontend deja de usarla; no hay clientes externos. Si algún build viejo
  del frontend queda desplegado, verá 404 en esa pantalla hasta recompilar.
- **`num_ventas` con días sin ventas** → un bucket sin filas no se devuelve
  desde SQL; el endpoint SHALL rellenar los periodos vacíos del rango con
  `total=0, num_ventas=0` y desgloses vacíos, para que el frontend no tenga que
  adivinar huecos.

## Migration Plan

1. Repositorio + endpoint + tests, con `/api/registros` todavía viva.
2. Migrar `admin.ts` y `Ventas.tsx`; correr el frontend y verificar el
   calendario contra un año conocido.
3. Borrar `registros/valores.py`, `registros/`, `test_endpoint_valores.py`, y la
   ruta `/api/registros` de `main.py`.
4. Validar contra el Excel histórico: totales por año y por mes de un periodo
   conocido deben coincidir (criterio de aceptación del issue).
5. Rollback: revertir el commit; no hay cambios de datos ni de esquema.

## Open Questions

- ¿El desglose de servicio se quiere por `servicio_id` resuelto a nombre, o
  basta el id? (propuesta en decisión 3: nombre vía `LEFT JOIN servicio`).
- ¿Hace falta un tope máximo de rango (p. ej. 5 años) para acotar el costo de
  escaneo? (propuesta: no por ahora, revisar si `totalBytesProcessed` crece).
