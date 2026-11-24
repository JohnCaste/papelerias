## Why

Hoy no hay forma de deshacer una venta mal capturada (#26). La única salida es
editar el total del día a mano, que es justo lo que destruye la trazabilidad y
donde se esconden faltantes y errores. El resto del sistema ya asume que la
cancelación existe —el esquema de `venta` reserva `estado`/`venta_original_id`,
el sincronizador (#15) ya sabe emitir `movimiento_inventario` tipo
`cancelacion`, y `agregaciones` (#34) ya netea reversiones— pero no hay endpoint
ni pantalla que las cree. El botón "cancelar" del dashboard (#35) quedó
explícitamente diferido a este cambio.

## What Changes

- **Nueva capability `cancelar-ventas`**: una cancelación es un **registro
  nuevo que revierte**, nunca un `DELETE` ni un `UPDATE` sobre la fila
  original (append-only #8). La reversión se escribe al **journal local**
  (#14) igual que la captura (#20), para funcionar sin internet; el
  sincronizador (#15) la sube y genera los `movimiento_inventario` inversos.
- **Nuevo endpoint** `POST /api/ventas/<venta_id>/cancelar` (JWT). Cuerpo:
  `motivo` (obligatorio, texto no vacío), `fecha` de la venta original
  (`YYYY-MM-DD`, para localizarla en el journal) y `lineas` opcional (subconjunto
  de índices de línea) para **devolución parcial**.
- La fila de reversión lleva `venta_original_id`, `total` y `lineas` (cantidad,
  subtotal, comisión) **con signo negativo**, `estado = "cancelada"` (o
  `"devolucion_parcial"` si es un subconjunto) y tres campos nuevos:
  `motivo_cancelacion`, `cancelada_por` (usuario del JWT) y `cancelada_en`.
- **Modelo y esquema**: `acceso_datos/modelos_venta.construir_venta` y la tabla
  BigQuery `venta` ganan `motivo_cancelacion`, `cancelada_por`, `cancelada_en`
  (todos `NULLABLE`). Se corrige el comentario del esquema que dice que la
  cancelación "cambia el estado de la fila original" (no lo hace: es append-only).
- **Totales**: no cambian de fórmula. Sumar `total` de todas las filas del día
  ya da el neto correcto porque la reversión resta exactamente lo que sumó la
  original. El dashboard (#35) y `GET /api/ventas/dia` **marcan la venta
  original como cancelada** (derivado: existe una fila de reversión total que la
  referencia) y ocultan las filas de reversión de la lista, manteniéndolas
  contadas en el total.
- **Frontend**: acción "Cancelar" en `ultimas_ventas` del dashboard con un modal
  que exige motivo y permite elegir líneas; servicio
  `cancelarVenta(id, motivo, opciones)`. Las ventas canceladas se muestran
  atenuadas / con badge, nunca desaparecen del historial.
- Se reescribe `acceso_datos/repositorios/ventas.cancelar` para usar los campos
  nuevos en vez del hack actual (mete el motivo en `motivo_extemporanea`).

## Capabilities

### New Capabilities

- `cancelar-ventas`: cancelación de una venta como registro reversivo
  journal-first: endpoint `POST /api/ventas/<id>/cancelar` que exige motivo,
  guarda quién y cuándo, escribe una fila de signo contrario (total o parcial)
  con `venta_original_id`, y deja que el sincronizador (#15) genere los
  `movimiento_inventario` inversos. El dinero se excluye del total por neteo,
  no por filtro, y la venta sigue visible en el historial marcada como
  cancelada.

### Modified Capabilities

- `dashboard-del-dia`: la lista `ultimas_ventas` deja de ser estrictamente de
  solo lectura — cada venta trae si es cancelable y su `estado` puede ser
  `cancelada`; la pantalla `/dashboard` añade la acción de cancelar (botón +
  modal con motivo y selección de líneas) sobre esa lista.

## Impact

- **Nuevo:** `backend/ventas/cancelaciones.py` (endpoint),
  `backend/tests/test_endpoint_cancelaciones.py`,
  `openspec/changes/cancelar-ventas/specs/cancelar-ventas/spec.md`.
- **Modificado backend:** `backend/main.py` (ruta
  `POST /api/ventas/<venta_id>/cancelar`),
  `backend/acceso_datos/modelos_venta.py` (3 campos nuevos),
  `backend/esquema/tablas.py` (columnas nuevas en `venta` + comentario),
  `backend/acceso_datos/repositorios/ventas.py` (`cancelar` usa los campos
  nuevos), `backend/almacen_local/journal.py` (buscar una venta por id+fecha),
  `backend/reportes/dashboard.py` y `backend/ventas/capturas.py`
  (`listar_ventas_del_dia`) para marcar la original y ocultar reversiones,
  `backend/ventas/desglose.py` (verificar que el subtotal negativo netea).
- **Modificado frontend:** `frontend/src/services/ventas.ts` (`cancelarVenta`),
  `frontend/src/services/dashboard.ts` (tipos `estado: "cancelada"`,
  `cancelable`), `frontend/src/pages/Dashboard.tsx` (botón + modal de
  cancelación), estilos de fila cancelada.
- **Sin cambio (ya lo soportan):** `almacen_local/sincronizador.py`
  (`_generar_movimientos_de_venta` ya usa `venta_original_id` y la cantidad con
  signo), `reportes/agregaciones.py` (ya netea sin filtrar por `estado`).
- **Depende de:** journal local (#14), sincronizador (#15), captura de ventas
  (#20), dashboard del día (#35).
