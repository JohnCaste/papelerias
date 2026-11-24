## 1. Repositorio de agregación

- [x] 1.1 Crear `backend/acceso_datos/repositorios/agregaciones.py` con
  `GRANULARIDADES = {"dia", "semana", "mes", "anio"}` y el mapa granularidad →
  expresión SQL de periodo (`DATE(...)`, `DATE_TRUNC(..., WEEK(MONDAY)/MONTH/YEAR)`),
  todas sobre `DATE(fecha_hora, 'America/Mexico_City')`.
- [x] 1.2 `agregar_por_periodo(granularidad, desde, hasta)`: valida
  `granularidad`; filtro de rango exacto y podable
  (`fecha_hora >= TIMESTAMP(@desde, tz)` … `< TIMESTAMP(@hasta+1d, tz)`);
  `GROUP BY periodo`. (Sin colchón: `TIMESTAMP(date, tz)` ya cae sobre la
  columna de partición.)
- [x] 1.3 En el mismo SQL: `SUM(total)` como `total`,
  `COUNTIF(venta_original_id IS NULL)` como `num_ventas`.
- [x] 1.4 Subconsulta `UNNEST(lineas)` para `desglose_categoria`
  (`SUM(subtotal)` por `categoria`, `tipo='categoria'`) y `desglose_servicio`
  (`SUM(subtotal)` por servicio, `tipo='servicio'`, `LEFT JOIN servicio` →
  `clave = COALESCE(s.nombre, servicio_id)`).
- [x] 1.5 `desglose_metodo_pago`: `SUM(total)` por `metodo_pago`.
- [x] 1.6 Devolver filas crudas por periodo (una dict por bucket con los tres
  desgloses como listas `{clave, monto}`), ordenadas por periodo.

## 2. Endpoint

- [x] 2.1 Crear `backend/reportes/__init__.py` y
  `backend/reportes/agregaciones.py` con `obtener_agregaciones()`.
- [x] 2.2 Leer y validar `request.args`: `granularidad` en el set,
  `desde`/`hasta` parseables como `date`, `desde <= hasta`; si no, `400` con
  mensaje (sin ejecutar consulta).
- [x] 2.3 Llamar `agregaciones_repo.agregar_por_periodo(...)`.
- [x] 2.4 Rellenar los periodos vacíos del rango (`total=0`, `num_ventas=0`,
  desgloses `[]`) según la granularidad, para no dejar huecos.
- [x] 2.5 Añadir `periodo_fin` y `etiqueta` a cada bucket (reutilizar
  `utilidades/utils.obtenerMes`); `jsonify` la lista ordenada por
  `periodo_inicio`.
- [x] 2.6 Registrar en `backend/main.py`: `from reportes import agregaciones`,
  ruta `GET /api/agregaciones` con `@jwt_required(optional=False)`.

## 3. Retirar el endpoint legado

- [x] 3.1 Quitar de `backend/main.py` el import `registros.valores` y la ruta
  `GET /api/registros`.
- [x] 3.2 Borrar `backend/registros/valores.py` y la carpeta
  `backend/registros/` (incluye `__pycache__`).
- [x] 3.3 Borrar `backend/tests/test_endpoint_valores.py`.

## 4. Frontend

- [x] 4.1 `frontend/src/services/admin.ts`: reemplazar `obtenerSemanas(anio)`
  por `obtenerAgregaciones(granularidad, desde, hasta)` contra
  `/api/agregaciones`.
- [x] 4.2 `frontend/src/pages/Ventas.tsx`: pedir `granularidad=dia` para el año,
  agrupar los buckets en meses y semanas ISO en el cliente, y calcular
  `status` (`v` si ≥ 6 días con actividad, `a` si 1–5, `r` si 0).
- [x] 4.3 Ajustar `calcularTotal` / render de la tabla para usar el `total` del
  bucket diario en vez de sumar `copias+dulces+...`.
- [x] 4.4 `npm --prefix frontend run build` sin errores de tipos.

## 5. Pruebas

- [x] 5.1 `backend/tests/test_repositorio_agregaciones.py`: `granularidad`
  inválida lanza; el SQL generado usa `America/Mexico_City` y el `DATE_TRUNC`
  correcto por granularidad; el filtro de rango es un `fecha_hora >= TIMESTAMP(...)`
  podable (cliente falso estilo `test_consultas.py`).
- [x] 5.2 `backend/tests/test_endpoint_agregaciones.py` (parchea el repositorio):
  - `400` para granularidad inválida, fechas inválidas y rango invertido.
  - Buckets vacíos rellenados en el rango.
  - `etiqueta` / `periodo_fin` presentes; orden ascendente.
  - JSON válido cuando un texto (p. ej. nombre de servicio) trae apóstrofe
    (regresión del hack viejo de `valores.py`).
- [x] 5.3 Test de semanas ISO en año bisiesto (2028-02) y en mes que cruza
  semana — la intención de `test_endpoint_valores.py`, ahora sobre el nuevo
  agrupador.
- [x] 5.4 Test de invariantes con datos sintéticos: `SUM(desglose_metodo_pago)
  == total`; una venta + su reversión aportan `0` al total y `1` a `num_ventas`;
  venta multi-categoría reparte `subtotal` por categoría.
- [x] 5.5 `cd backend && python -m pytest -q` en verde (incluye que ya no exista
  `test_endpoint_valores.py`).

## 6. Validación y cierre

- [~] 6.1 Smoke test contra BigQuery real (`scratchpad/smoke_agregaciones.py`):
  el SQL de las 4 granularidades corre, los buckets cuadran contra
  `SUM(venta.total)` por año, y los desgloses son coherentes. **Falta** el
  cruce contra el Excel histórico real (no disponible en esta sesión).
- [x] 6.2 Poda de partición: la consulta acotada es un `dry_run` válido con
  filtro directo sobre `fecha_hora`. La tabla hoy es diminuta (~320 B), así que
  el ahorro no se aprecia todavía, pero la forma del filtro sí poda.
- [ ] 6.3 Correr el frontend, abrir la pantalla de Ventas y comparar el
  calendario de un año contra lo que mostraba antes. (Solo se hizo
  `npm run build` / typecheck; falta la verificación visual.)
- [x] 6.4 `openspec validate agregaciones-de-ventas --strict`.
- [ ] 6.5 Marcar tareas del issue #34 y comentar el resultado de la validación
  contra el Excel.
- [x] 6.6 `openspec archive agregaciones-de-ventas`.
