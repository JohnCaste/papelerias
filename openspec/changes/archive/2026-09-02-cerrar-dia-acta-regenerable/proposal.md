## Why

Hoy "Cerrar el día" (#50) genera un acta **congelada e idempotente**: en cuanto
existe, ya no se puede rehacer. Eso obliga a una disyuntiva incómoda en el
mostrador — si se cierra temprano, las ventas posteriores nunca entran al acta;
si se espera, no hay forma de adelantar el cierre los días que el negocio cierra
antes. Además, en la pantalla VENDER el botón está siempre activo, invitando a
cerrar a mano cuando el cierre automático de las 20:00 ya lo hace solo.

Queremos que el acta se pueda **regenerar** mientras el día está en curso y que
el botón guíe el flujo esperado (dejar que cierre solo a las 20:00), sin dejar de
permitir un cierre forzado explícito.

## What Changes

- **Acta regenerable (día en curso).** `generar_cierre_dia` deja de ser un no-op
  cuando ya existe acta: se añade una operación de regeneración que **append-ea**
  un nuevo evento `cierre` al `.jsonl` append-only con los valores del journal al
  momento, y **resetea el marcador de sincronización** para que el sincronizador
  (#15) vuelva a subir el acta a BigQuery. `obtener_cierre_local` pasa a devolver
  el **último** evento `cierre`, no el primero.
- **Endpoint de regeneración.** Nuevo `POST /api/cierres/dia/regenerar` (JWT) que
  regenera el acta **solo del día en curso**. Días anteriores quedan como
  historial inmutable (responde `409`/`400`).
- **Cierre forzado explícito.** `POST /api/cierres/dia` (el actual) se mantiene
  como "forzar cierre ahora" y su respuesta indica que el acta es provisional.
- **Cierre automático que finaliza.** El `ProgramadorCierre` de las 20:00, si el
  día ya tiene un acta provisional (forzada antes de la hora), la **regenera**
  una vez para consolidar las ventas que entraron después; si no hay acta, la
  crea como hoy.
- **VENDER — botón "Cerrar el día".**
  - Antes de las 20:00 y día abierto: botón principal deshabilitado con el texto
    "Se cierra automáticamente a las 8:00 pm" y una acción secundaria "Forzar
    cierre ahora" con diálogo de confirmación.
  - Con acta ya existente (forzada / automática / perezosa): el botón principal
    deja de cerrar y aparece "Regenerar acta", que reescribe el acta con los
    valores actuales.
- **VENDER — encabezado del día.** Mostrar siempre la fecha: "Día abierto · Hoy,
  {fecha}" / "Día cerrado · {fecha}".
- **La venta nunca se bloquea.** En ningún estado (abierto, forzado, cerrado) se
  impide capturar ventas; el journal local (#14) sigue siendo la fuente de
  verdad.

## Capabilities

### New Capabilities

- `cierre-de-dia`: consolidación del journal local del día en un acta local-first
  (total, nº de ventas, desgloses), con tres disparadores (automático a las
  20:00, perezoso al arrancar, manual/forzado), acta **regenerable** mientras el
  día está en curso, sincronización idempotente a BigQuery y la presentación en
  la pantalla VENDER (encabezado con fecha, botón con estados). Formaliza el
  comportamiento existente de #50 más los cambios de esta propuesta.

### Modified Capabilities

<!-- Ninguna. `dashboard-del-dia` sigue leyendo estado_dia.cerrado / cerrado_en
     sin cambio de requisitos: cerrado_en pasa a reflejar la última regeneración,
     lo cual sigue siendo "marca de tiempo del cierre local". -->

## Impact

- **Backend**
  - `backend/almacen_local/cierres.py`: nueva función de regeneración;
    `obtener_cierre_local` lee el último evento `cierre`; reset del marcador de
    sync (nuevo evento que invalida el `sincronizado` previo).
  - `backend/almacen_local/programador_cierre.py`: `revisar_cierre_automatico`
    regenera una vez si el día tiene acta provisional (forzada).
  - `backend/ventas/cierres.py`: nuevo handler `regenerar_cierre_dia`; el handler
    de cierre manual marca la respuesta como provisional.
  - `backend/main.py`: registrar `POST /api/cierres/dia/regenerar`.
  - `backend/almacen_local/sincronizador.py`: reconocer un acta re-marcada como
    pendiente y re-subirla idempotentemente (upsert por `id`/fecha).
  - `backend/reportes/dashboard.py`: sin cambio funcional; `estado_dia.cerrado_en`
    ahora refleja la regeneración más reciente.
- **Frontend**
  - `frontend/src/services/cierres.ts`: `regenerarActaDia()`; tipo `EstadoDia`
    con marca de provisionalidad y `generado_por` extendido.
  - `frontend/src/pages/PuntoVenta.tsx`: encabezado con fecha; lógica de botón
    (deshabilitado antes de 20:00, "Forzar cierre ahora" con confirmación,
    "Regenerar acta" cuando ya hay acta).
- **Tests**
  - `backend/tests/test_endpoint_cierres.py`, `test_capturas.py` y las de
    `programador_cierre` / `sincronizador` afectadas por el último-evento y la
    regeneración.
- **Sin migración de datos.** El formato `.jsonl` append-only no cambia; solo se
  admiten múltiples eventos `cierre` por archivo.
