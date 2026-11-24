## 1. Modelo y esquema

- [x] 1.1 En `backend/acceso_datos/modelos_venta.py`, añadir a `construir_venta`
  los campos `motivo_cancelacion`, `cancelada_por` y `cancelada_en`
  (`datos.get(...)`, default `None`).
- [x] 1.2 En `backend/esquema/tablas.py`, añadir a `TABLA_VENTA` las columnas
  `motivo_cancelacion` (STRING NULLABLE), `cancelada_por` (STRING NULLABLE) y
  `cancelada_en` (TIMESTAMP NULLABLE). Corregir el comentario de `estado`: la
  cancelación NO cambia el estado de la fila original, inserta una fila de
  reversión con su propio `estado`.
- [x] 1.3 Columnas nuevas aplicadas a `mi-proyecto-gcp.lapape.venta`
  (ALTER ADD COLUMN NULLABLE, sin recrear, 2026-09-01).

## 2. Journal: buscar una venta

- [x] 2.1 En `backend/almacen_local/journal.py`, añadir
  `buscar_venta(id_, fecha, carpeta=None)` que use `leer_dia` y devuelva la
  venta con ese `id` o `None`.
- [x] 2.2 Prueba en `backend/tests/` del helper: encuentra una venta escrita,
  devuelve `None` si no existe y si el día no tiene journal.

## 3. Endpoint de cancelación

- [x] 3.1 Crear `backend/ventas/cancelaciones.py` con `cancelar_venta(venta_id)`
  (estilo `ventas/capturas.py`): lee `motivo`, `fecha` y `lineas` del JSON.
- [x] 3.2 Validaciones → `400`: `motivo` ausente o vacío tras `strip()`; `fecha`
  no parseable como `YYYY-MM-DD`; algún índice de `lineas` fuera de rango.
- [x] 3.3 `404` si `journal.buscar_venta(venta_id, fecha)` es `None`; `400` si la
  venta encontrada ya tiene `venta_original_id` (es una reversión).
- [x] 3.4 Construir las líneas revertidas: si `lineas` viene, sólo esos índices;
  si no, todas. Negar `cantidad`, `subtotal` y `monto_comision` (respetando
  `None`).
- [x] 3.5 Construir la fila de reversión: `total = -sum(subtotales revertidos)`,
  `venta_original_id = venta_id`, `metodo_pago`/`detallada` de la original,
  `origen = "pos"`, `estado = "devolucion_parcial"` si es subconjunto propio o
  `"cancelada"` si cubre todas las líneas, `motivo_cancelacion = motivo`,
  `cancelada_por = get_jwt_identity()`, `cancelada_en = now(UTC)`.
- [x] 3.6 `id` determinista de la reversión para tolerar reintentos
  (p. ej. `uuid5` de `venta_id` + estado + índices ordenados); escribir con
  `journal.escribir_venta(...)` y devolver `201` con la fila (formato ISO como
  en `capturas._a_json`).
- [x] 3.7 Registrar `POST /api/ventas/<venta_id>/cancelar` en
  `backend/main.py` con `@jwt_required(optional=False)`.

## 4. Reflejo en lecturas del día

- [x] 4.1 En `backend/ventas/capturas.py::listar_ventas_del_dia`: calcular el set
  de `venta_original_id` de las reversiones con `estado = "cancelada"`; marcar
  esas ventas como canceladas y excluir las filas de reversión de `ventas`
  (sin quitarlas del `total`).
- [x] 4.2 En `backend/reportes/dashboard.py::_ultimas_ventas`: misma lógica —
  añadir `estado = "cancelada"` y `cancelable` (bool) a cada entrada y no
  listar las filas de reversión. `total`/`num_ventas` siguen sumando todas las
  filas.
- [x] 4.3 Verificar `backend/ventas/desglose.py`: `por_categoria` suma
  `lineas.subtotal` (los negativos de la reversión netean solos) y
  `por_metodo_pago` suma `venta.total` (idem). Ajustar sólo si una prueba lo
  exige.

## 5. Reconciliar el repositorio

- [x] 5.1 Reescribir `backend/acceso_datos/repositorios/ventas.py::cancelar`
  para pasar `motivo_cancelacion=motivo`, `cancelada_por=usuario_id`,
  `cancelada_en=now`; dejar `motivo_extemporanea` en `None`. Aceptar `lineas`
  opcional para paridad con el endpoint (o documentar que sólo hace total).
- [x] 5.2 Actualizar `backend/tests/test_repositorio_ventas.py` a los campos
  nuevos.

## 6. Pruebas backend

- [x] 6.1 `backend/tests/test_endpoint_cancelaciones.py` (parchea
  `journal.*` como `test_endpoint_dashboard.py`): `201` en cancelación
  aceptada; la fila de reversión tiene signo negativo, `venta_original_id`,
  `estado`, y los 3 campos de auditoría.
- [x] 6.2 `400` sin motivo / motivo en blanco / `fecha` inválida / índice de
  línea inexistente / cancelar una reversión; `404` venta inexistente.
- [x] 6.3 Devolución parcial: reversión con una sola línea,
  `total` = subtotal negado, `estado = "devolucion_parcial"`; la original
  sigue "activa".
- [x] 6.4 La fila original queda intacta en el journal tras cancelar; el total
  del día baja a `0` en el caso de una venta única cancelada.
- [x] 6.5 Reintento del endpoint con el mismo cuerpo no crea una segunda
  reversión (id determinista).
- [x] 6.6 `test_endpoint_ventas_integracion.py` / dashboard: la venta cancelada
  se lista marcada y la fila de reversión no aparece como venta.
- [x] 6.7 `almacen_local/sincronizador`: una reversión con línea de producto
  genera `movimiento_inventario` `tipo = "cancelacion"` con cantidad positiva
  (stock devuelto) e id determinista. Añadir/ajustar prueba en
  `test_repositorio_movimientos_inventario.py` o la del sincronizador.
- [x] 6.8 `cd backend && python -m pytest -q` en verde.

## 7. Frontend

- [x] 7.1 `frontend/src/services/ventas.ts`: `cancelarVenta(id, motivo,
  opciones?: { fecha: string; lineas?: number[] })` → `POST
  /api/ventas/<id>/cancelar`.
- [x] 7.2 `frontend/src/services/dashboard.ts`: `VentaResumen.estado` admite
  `"cancelada"`; añadir `cancelable: boolean`.
- [x] 7.3 `frontend/src/pages/Dashboard.tsx`: botón "Cancelar" en cada fila de
  `ultimas_ventas` con `cancelable`; modal con textarea de `motivo`
  (obligatorio) y checkboxes de líneas (por defecto todas); al confirmar,
  llamar a `cancelarVenta` y recargar `obtenerDashboardDia`.
- [x] 7.4 Filas con `estado = "cancelada"` atenuadas / con badge; el botón se
  deshabilita mientras la petición está en curso.
- [x] 7.5 `npm --prefix frontend run build` sin errores de tipos.

## 8. Validación y cierre

- [x] 8.1 `openspec validate cancelar-ventas --strict`.
- [x] 8.2 Smoke: `import main` OK, ruta registrada; cancelar una venta de prueba
  en un backend de desarrollo baja el total de `GET /api/ventas/dia` y
  `GET /api/dashboard/dia`.
- [~] 8.3 Verificación visual en `/dashboard`: cancelar deja la venta marcada,
  el total del día baja, nada desaparece.
- [ ] 8.4 Marcar en el issue #26 las tareas cubiertas (estado + inventario
  inverso, motivo, quién/cuándo, exclusión por neteo, devolución parcial).
- [ ] 8.5 `openspec archive cancelar-ventas`.
