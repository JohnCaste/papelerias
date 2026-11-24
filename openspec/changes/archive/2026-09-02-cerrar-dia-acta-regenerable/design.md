## Context

El cierre de día (#50) ya existe y funciona local-first: `generar_cierre_dia`
consolida el journal en un acta, la escribe en `cierre-<fecha>.jsonl` (un evento
`cierre`, luego un evento `sincronizado`), y el `ProgramadorCierre` la dispara a
las 20:00 / al arrancar. Hoy la función es **idempotente por archivo**: si ya hay
un evento `cierre`, devuelve el existente y nunca reescribe.

Restricciones que se mantienen:

- **Local-first, sin bloqueo:** ninguna operación de acta puede esperar a
  BigQuery ni impedir capturar ventas. El journal (#14) es la fuente de verdad.
- **Append-only:** `cierre-<fecha>.jsonl` solo crece; los eventos no se editan.
- **Un proceso, una PC** (Flask/Waitress + hilos daemon). El `ProgramadorCierre`
  revisa cada 5 min.
- La tabla BigQuery `cierre` ya tiene `estado ∈ {'cerrado','corregido'}` y
  `cierres_repo.existe()` filtra `estado != 'corregido'` — o sea, ya está previsto
  el mecanismo de "acta corregida y reemplazada".

## Goals / Non-Goals

**Goals:**

- Permitir **regenerar** el acta del día en curso, tantas veces como haga falta,
  con los valores del journal al momento del click.
- Que un cierre forzado antes de las 20:00 sea **provisional** y el disparador
  automático lo **finalice** una vez, recogiendo las ventas posteriores.
- Que la pantalla VENDER guíe el flujo: botón bloqueado hasta la hora de cierre,
  "Forzar cierre ahora" explícito con confirmación, "Regenerar acta" cuando ya
  hay acta, y encabezado con la fecha del día.
- Re-subir el acta regenerada a BigQuery sin duplicar la fila de esa fecha.

**Non-Goals:**

- Regenerar o corregir actas de **días anteriores** (historial inmutable).
- Cambiar el corte de caja (#36), el dashboard (#35) o las agregaciones
  semanales/mensuales.
- Bloquear la venta en cualquier estado del día.
- PDF del acta (#51/#53).

## Decisions

### 1. Varios eventos `cierre` por archivo; se lee el último

`cierre-<fecha>.jsonl` pasa a admitir N eventos `cierre`. `obtener_cierre_local`
recorre el archivo y devuelve el **último** evento `cierre`; el flag
`sincronizado` es `True` solo si hay un evento `sincronizado` **después** del
último `cierre` (el orden de líneas = orden cronológico, garantizado por el
append con lock + fsync ya existente).

- *Alternativa descartada:* reescribir el único evento `cierre` in place. Rompe el
  invariante append-only y la auditabilidad ("¿a qué hora se cerró y cuántas
  veces se rehízo?").

### 2. `provisional` como campo explícito del evento `cierre`

El evento `cierre` gana `provisional: bool`. Lo pone `generar_cierre_dia`:

- `manual` (forzado) **antes** de `HORA_CIERRE` → `provisional = True`.
- `automatico`, `perezoso`, o regeneración post-hora → `provisional = False`.

- *Alternativa descartada:* derivar "provisional" en cada lectura comparando
  `generado_en` contra `HORA_CIERRE` con aritmética de zona horaria. Frágil y
  repetido en backend y frontend.

### 3. Nueva operación `regenerar_cierre_dia` + endpoint dedicado

`almacen_local/cierres.py` gana `regenerar_cierre_dia(fecha, generado_por)` que
**siempre** append-ea un evento `cierre` nuevo (no es idempotente) con los
valores actuales del journal y `generado_en` = ahora. `generar_cierre_dia`
mantiene su semántica idempotente para el primer cierre / cierre forzado.

`main.py` registra `POST /api/cierres/dia/regenerar` (JWT) →
`ventas/cierres.regenerar_cierre_dia_handler`, que:

- Rechaza con `409` si `fecha` (o el default) **no es hoy**.
- Si hoy no tiene acta, delega en `generar_cierre_dia` (primera acta).
- Si hoy ya tiene acta, llama `regenerar_cierre_dia(hoy, "regeneracion")`.

`generado_por` suma el valor `"regeneracion"` en el enum (backend y tipo del
frontend).

- *Alternativa descartada:* `POST /api/cierres/dia?regenerar=true`. Un verbo
  distinto en la misma ruta esconde una operación no idempotente detrás de una
  que sí lo es; una ruta aparte lo hace explícito y testeable.

### 4. El `ProgramadorCierre` finaliza el acta provisional una vez

`revisar_cierre_automatico` cambia a:

```
si ahora.time() < HORA_CIERRE: return
acta = obtener_cierre_local(hoy)
si acta is None:            generar_cierre_dia(hoy, "automatico")      # como hoy
si acta and acta.provisional: regenerar_cierre_dia(hoy, "automatico") # NUEVO: finaliza
si acta and not provisional:  return                                   # ya finalizada
```

El guard natural contra el bucle de 5 min es el propio `provisional`: tras la
regeneración automática el acta queda `provisional = False`, así que el siguiente
tick cae en la última rama y no escribe nada.

### 5. El gate horario del botón lo decide el backend, no el reloj del cliente

`GET /api/cierres/dia` (hoy) suma al payload:
`antes_de_hora_cierre: bool` y `hora_cierre: "20:00"`. El frontend usa ese
booleano para decidir si el botón principal va deshabilitado ("Se cierra
automáticamente a las 8:00 pm" + "Forzar cierre ahora") o habilitado como
respaldo. Así el comportamiento no depende del reloj del navegador.

- *Alternativa descartada:* comparar `new Date()` en el frontend. Skew de reloj
  del navegador vs. servidor produciría un botón inconsistente justo alrededor de
  las 20:00.

### 6. Re-subida a BigQuery: marcar la fila anterior `corregido` e insertar la nueva

Tras una regeneración el acta local queda "no sincronizada" (regla del §1), así
que `sincronizar_cierres_una_vez` la vuelve a tomar. El cambio: en vez de
`if not existe("dia", fecha): insertar(...)`, hace

```
vigente = cierres_repo.obtener_vigente("dia", fecha)
si vigente is None:                     cierres_repo.insertar(acta_local)
si vigente and vigente.id != acta_local.id:
    cierres_repo.marcar_corregido(vigente.id)   # UPDATE estado='corregido'
    cierres_repo.insertar(acta_local)
si vigente and vigente.id == acta_local.id:     pass   # ya está
```

Para que el `id` sea comparable, **cada regeneración conserva su propio `id`
nuevo** (uuid por evento) y ese `id` viaja al `.jsonl` y a BigQuery.
`obtener_vigente` ya ordena por `generado_en DESC`, y las agregaciones ya filtran
`estado != 'corregido'`, así que los lectores toman la versión correcta.

## Risks / Trade-offs

- **[DML de BigQuery sobre el streaming buffer]** `marcar_corregido` es un UPDATE;
  BigQuery rechaza DML sobre filas recién insertadas por streaming (hasta ~90
  min). → Mitigación: el sincronizador ya se corta al primer fallo y reintenta en
  el siguiente ciclo; hasta que el UPDATE prospere, `obtener_vigente` (orden por
  `generado_en DESC`) ya devuelve la versión nueva, y solo las lecturas que
  suman `WHERE estado != 'corregido'` sin dedupe por fecha podrían contar dos
  actas de un mismo día durante esa ventana. Confirmar en tareas si alguna
  agregación del rango diario es vulnerable; si lo es, dedupe por
  `MAX(generado_en)` por `fecha_inicio`.
- **[Regeneraciones múltiples dejan varias filas en BigQuery]** cada una con
  `estado='corregido'` salvo la última. → Aceptable: es exactamente el modelo que
  la tabla ya contempla; el volumen es de unas pocas filas por día.
- **[`estado_dia.cerrado_en` del dashboard cambia de significado]** pasa a ser la
  hora de la última regeneración, no la del primer cierre. → Aceptable y
  coherente con "marca de tiempo del cierre local"; se documenta, no se cambia el
  spec de `dashboard-del-dia`.
- **[Usuario del mostrador regenera de más]** no hay rol que lo limite (por
  decisión de producto). → Impacto nulo: la operación es determinista sobre el
  journal; regenerar dos veces seguidas da el mismo total.
- **[Cierre forzado y olvido de finalizar]** si la PC se apaga entre el forzado
  de las 18:00 y las 20:00, el acta queda provisional. → El disparador perezoso
  al arrancar debe tratar un acta `provisional` de un día ya pasado como
  pendiente de finalizar y regenerarla una vez (misma lógica que el automático,
  aplicada a días < hoy en el catch-up).

## Migration Plan

- Sin migración de datos: los `.jsonl` existentes tienen un solo evento `cierre`
  sin `provisional`; se tratan como `provisional = False` (ausente ⇒ no
  provisional).
- Las filas de `cierre` ya en BigQuery quedan como están; la primera regeneración
  de un día las marcará `corregido` si aplica.
- Rollback: revertir el código deja los `.jsonl` con varios eventos `cierre`;
  el `obtener_cierre_local` viejo lee el **primero** — se degrada a "el acta es
  la del primer cierre del día", sin pérdida de datos.

## Open Questions

- ¿Alguna agregación de rango diario (`reportes/agregaciones.py`,
  `acceso_datos/repositorios/agregaciones.py`) suma la tabla `cierre` en vez del
  journal? Si es así, necesita dedupe por última versión por fecha.
- ¿`HORA_CIERRE` debe ser configurable por `.env` (hoy es constante
  `HORA_CIERRE_POR_DEFECTO`)? Fuera de alcance salvo que se pida.
