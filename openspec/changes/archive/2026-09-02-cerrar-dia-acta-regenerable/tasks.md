## 1. Almacén local: acta con varios eventos y regeneración

- [x] 1.1 En `backend/almacen_local/cierres.py`, hacer que `obtener_cierre_local`
  recorra todos los eventos y devuelva el **último** `cierre`; calcular
  `sincronizado` como "hay un evento `sincronizado` posterior al último `cierre`".
- [x] 1.2 Añadir el campo `provisional: bool` al evento `cierre` en
  `generar_cierre_dia`: `True` solo si `generado_por == "manual"` y
  `datetime.now().time() < HORA_CIERRE`; `False` en cualquier otro caso. Tratar
  `provisional` ausente como `False` al leer.
- [x] 1.3 Añadir `regenerar_cierre_dia(fecha, generado_por, carpeta_journal=None,
  carpeta_cierre=None)` que **siempre** append-ea un evento `cierre` nuevo (id
  uuid nuevo, `generado_en` = ahora, `provisional=False`) con el total/num_ventas/
  desgloses recalculados del journal. No es idempotente.
- [x] 1.4 Mantener `generar_cierre_dia` idempotente para la primera acta / cierre
  forzado (si ya hay acta, devuelve la última sin escribir).
- [x] 1.5 Importar `HORA_CIERRE_POR_DEFECTO` desde `programador_cierre` o mover la
  constante a `cierres.py` para evitar import circular (decidir al implementar).
- [x] 1.6 Actualizar/añadir pruebas en `backend/tests/` para: varios eventos
  `cierre` → se lee el último; `sincronizado` se invalida tras un `cierre`
  posterior; `provisional` según hora; `regenerar_cierre_dia` recalcula.

## 2. Programador de cierre: finalizar acta provisional

- [x] 2.1 En `backend/almacen_local/programador_cierre.py`,
  `revisar_cierre_automatico`: si ya pasó `HORA_CIERRE` y el acta de hoy existe y
  es `provisional`, llamar `regenerar_cierre_dia(hoy, "automatico")` una sola vez
  (el flag `provisional=False` resultante evita repetirlo en el siguiente tick).
- [x] 2.2 Si el acta de hoy no existe, comportamiento actual
  (`generar_cierre_dia(hoy, "automatico")`).
- [x] 2.3 En `cerrar_dias_pendientes` (catch-up perezoso): para un día pasado con
  acta `provisional`, regenerarla una vez para finalizarla.
- [x] 2.4 Pruebas: acta forzada a las 18:00 + ventas nuevas → a las 20:05 el
  automático regenera y deja `provisional=False`; segundo tick no escribe; día
  pasado provisional se finaliza en el arranque.

## 3. Endpoints de cierre

- [x] 3.1 En `backend/ventas/cierres.py`, en `cerrar_dia_manual`: pasar por la
  ruta idempotente y añadir a la respuesta la marca de `provisional` del acta.
- [x] 3.2 Añadir `regenerar_cierre_dia_handler`: valida `fecha` (default hoy),
  responde `409` si no es hoy; si hoy no tiene acta → `generar_cierre_dia`; si ya
  tiene → `regenerar_cierre_dia(hoy, "regeneracion")`; responde `201` con el acta.
- [x] 3.3 En `obtener_estado_dia`: cuando la fecha es hoy, añadir al payload
  `antes_de_hora_cierre: bool` y `hora_cierre: "HH:MM"`; incluir `provisional` en
  el objeto `cierre`.
- [x] 3.4 En `backend/main.py`, registrar `POST /api/cierres/dia/regenerar`
  (`@jwt_required`).
- [x] 3.5 Extender el enum `generado_por` a
  `automatico | perezoso | manual | regeneracion` donde se valide/documente.
- [x] 3.6 Pruebas en `backend/tests/test_endpoint_cierres.py`: regenerar hoy →
  `201` y nuevo total; regenerar ayer → `409`; estado de hoy trae
  `antes_de_hora_cierre` y `provisional`.

## 4. Sincronización a BigQuery

- [x] 4.1 En `backend/acceso_datos/repositorios/cierres.py`, añadir
  `marcar_corregido(id)` (UPDATE `estado='corregido'` por `id`).
- [x] 4.2 En `backend/almacen_local/sincronizador.py`,
  `sincronizar_cierres_una_vez`: reemplazar el `if not existe(...)` por la lógica
  de `obtener_vigente("dia", fecha)` — insertar si no hay vigente; si el `id`
  vigente difiere del local, `marcar_corregido(vigente.id)` + `insertar(local)`;
  si coincide, nada. Mantener el corte al primer fallo y el `marcar_sincronizado`
  local solo tras éxito.
- [x] 4.3 Confirmar que el acta local re-marcada como no sincronizada (regla 1.1)
  vuelve a entrar en el rango que revisa el sincronizador.
- [x] 4.4 Revisar `reportes/agregaciones.py` y
  `acceso_datos/repositorios/agregaciones.py`: si alguna suma la tabla `cierre`
  por rango diario sin filtrar la última versión por fecha, añadir dedupe por
  `MAX(generado_en)` por `fecha_inicio` (o dejar constancia de que no aplica).
- [x] 4.5 Pruebas: regenerar un acta ya sincronizada → el sincronizador marca la
  anterior `corregido` e inserta la nueva; sin conexión, la regeneración no
  bloquea y se sube después.

## 5. Frontend: servicio de cierres

- [x] 5.1 En `frontend/src/services/cierres.ts`, extender `Cierre.generado_por`
  con `"regeneracion"` y añadir `provisional?: boolean`; en `EstadoDia` añadir
  `antes_de_hora_cierre?: boolean` y `hora_cierre?: string`.
- [x] 5.2 Añadir `regenerarActaDia(): Promise<Cierre>` → `POST
  /api/cierres/dia/regenerar`.
- [x] 5.3 Mantener `cerrarDiaManual` para "Forzar cierre ahora".

## 6. Frontend: pantalla VENDER (PuntoVenta)

- [x] 6.1 Encabezado del día: mostrar "Día abierto · Hoy, {fecha}" cuando
  `!estadoDia.cerrado`, y "Día cerrado · {fecha}" cuando hay acta (formatear la
  fecha en es-MX).
- [x] 6.2 Estado sin acta y `antes_de_hora_cierre === true`: botón principal
  deshabilitado con texto "Se cierra automáticamente a las 8:00 pm"; render de un
  botón secundario "Forzar cierre ahora".
- [x] 6.3 "Forzar cierre ahora": diálogo de confirmación (Modal de
  react-bootstrap, patrón existente) → `cerrarDiaManual()` → `cargarEstadoDia()`.
- [x] 6.4 Estado sin acta y `antes_de_hora_cierre === false`: botón principal
  "Cerrar el día" habilitado → `cerrarDiaManual()`.
- [x] 6.5 Estado con acta (provisional o no): ocultar el botón de cierre y
  mostrar "Regenerar acta" → `regenerarActaDia()` → `cargarEstadoDia()`;
  reflejar el nuevo total. Mostrar un distintivo cuando `cierre.provisional`.
- [x] 6.6 `npm --prefix frontend run build` sin errores de tipos.

## 7. Validación y cierre

- [x] 7.1 `cd backend && python -m pytest -q` en verde.
- [x] 7.2 Smoke backend: `import main` OK, ruta `/api/cierres/dia/regenerar`
  registrada; forzar cierre 18:00 (simulado) → `provisional=True`; regenerar →
  total actualizado; simular tick 20:05 → `provisional=False`.
- [~] 7.3 Verificación visual en dev (frontend + backend corriendo, login): las
  tres formas del botón según hora/estado, encabezado con fecha, y que capturar
  una venta sigue funcionando con el día cerrado.
- [x] 7.4 `openspec validate cerrar-dia-acta-regenerable --strict`.
- [ ] 7.5 Actualizar el issue #50 con lo cubierto; `openspec archive
  cerrar-dia-acta-regenerable`.
