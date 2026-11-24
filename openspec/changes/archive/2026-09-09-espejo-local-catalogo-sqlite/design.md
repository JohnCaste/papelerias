## Context

El catálogo (`producto`, `categoria`) y el stock derivado
(`movimiento_inventario`) viven en BigQuery, elegido para el resto del
sistema por ser append-only, sin servidor que administrar, y ya con
respaldo en la nube. Es un buen motor analítico, pero cada consulta paga
latencia de red fija (crear el job + ida y vuelta), sin importar cuántas
filas tenga la tabla — mal ajuste para responder un catálogo mientras
alguien teclea en el mostrador.

El proyecto ya tiene un patrón establecido para "algo en disco local que
se sincroniza con BigQuery en segundo plano": el journal de ventas
(`almacen_local/journal.py`) + `Sincronizador`
(`almacen_local/sincronizador.py`), que sube ventas locales a BigQuery.
Este cambio necesita el flujo **inverso** — bajar catálogo de BigQuery a
un almacén local — así que es un componente nuevo, no una extensión del
`Sincronizador` existente (que está especializado en subir ventas y
cierres, con su propio manejo de journal/backoff).

`producto` no pasa por journal: `crear`/`actualizar`/`eliminar` en
`acceso_datos/repositorios/productos.py` escriben directo a BigQuery de
forma síncrona (baja frecuencia — altas/ediciones de catálogo, no ventas).
Esto simplifica el espejo: no hay que reconciliar una cola de escritura
local, solo mantener una copia de lectura al día.

## Goals / Non-Goals

**Goals:**
- Que `GET /api/catalogo/buscar` (y paginador/categorías/marcas) respondan
  en milisegundos, sin depender de la latencia de red hacia BigQuery.
- Que el catálogo siga funcionando sin internet (leyendo del espejo tal
  como quedó en el último refresco exitoso).
- Que un alta/edición/baja hecha en la misma PC se vea reflejada en el
  catálogo de inmediato (no solo tras el siguiente ciclo de refresco).
- Que el espejo sea prescindible: borrarlo no pierde nada, se reconstruye
  solo. BigQuery sigue siendo la única fuente de verdad para escritura.
- Validar con datos reales del negocio si esto resuelve el problema de
  latencia percibida, antes de decidir si además hace falta migrar el
  motor completo a MySQL.

**Non-Goals:**
- No se migra el motor de base de datos (MySQL) — este cambio es la
  validación previa, no la migración.
- No se espeja `venta`, `movimiento_inventario` completo, `cierre`, ni
  ninguna otra tabla — solo lo que necesita el catálogo de lectura:
  `producto`, `categoria`, y el stock agregado por producto.
- No se toca `obtener_por_codigo_barras` (escaneo en Vender) ni
  `obtener_por_id` — quedan contra BigQuery directo. Son consultas
  puntuales (`LIMIT 1`), no las que generan el problema de "24 llamadas
  al teclear"; ampliar el alcance ahí puede ser un cambio futuro si hace
  falta, no de este.
- No se implementa un mecanismo de invalidación fina (p.ej. notificar a
  otras PCs que el catálogo cambió) — el refresco periódico + la
  actualización local tras escribir cubren el caso real de este negocio
  (una sola PC operando el catálogo).

## Decisions

### 1. SQLite como almacén del espejo, vía el módulo estándar `sqlite3`

Alternativas consideradas: mantenerlo en memoria (un dict/lista
en el proceso Python) — se descarta porque se perdería en cada reinicio
del backend y el primer refresco tarda lo mismo que una consulta a
BigQuery (mala primera impresión al arrancar). SQLite persiste en disco,
no agrega ninguna dependencia nueva (`sqlite3` es parte de la librería
estándar de Python, ya usada implícitamente por el propio Python), y da
consultas indexadas reales (`LIKE`, rango de precio, `ORDER BY`) sin
reescribir la lógica de filtrado a mano.

Archivo: `backend/datos_locales/catalogo_espejo.sqlite3` — mismo
directorio que ya usan journal y cierres, mismo criterio de "no se sube a
git, se reconstruye sola" (`.gitignore` ya cubre `backend/datos_locales/`
completo).

### 2. Refresco periódico completo, no incremental

Cada ciclo (intervalo por defecto: 30 segundos) el espejo vuelve a leer
de BigQuery **todo** `producto` activo, **toda** `categoria` activa, y
**todo** el stock agregado (`SELECT producto_id, SUM(cantidad) ... GROUP
BY producto_id`), y reemplaza el contenido local completo dentro de una
transacción SQLite (borra e inserta, o `INSERT OR REPLACE`) — nunca dos
estados a medias visibles a un lector concurrente.

Alternativa considerada: sincronización incremental por
`actualizado_en > ultimo_refresco` — más eficiente en llamadas a
BigQuery, pero: (a) requeriría manejar borrados lógicos y altas nuevas
con cuidado adicional, (b) a la escala de este negocio (cientos de
productos, no millones) una lectura completa de `producto`/`categoria`
sigue siendo rápida y cabe sobrada en una sola consulta, y (c) simplicidad
gana — un refresco completo es trivialmente correcto (nunca puede quedar
"a medias" divergente de BigQuery) y más fácil de razonar. Si el catálogo
creciera órdenes de magnitud, ahí sí valdría la pena lo incremental.

30 segundos como intervalo por defecto: bajo costo de red/cómputo (3
consultas ligeras cada 30s) contra que cualquier cambio hecho desde OTRA
PC (si algún día hay más de una) tarda como máximo esos 30s en
reflejarse. Configurable, no hay necesidad identificada de exponerlo
todavía.

### 3. Actualización síncrona del espejo tras escribir (además del refresco periódico)

`crear`/`actualizar`/`eliminar` en `catalogos/productos.py`, justo
después de que la escritura en BigQuery se confirma, hacen un
`INSERT OR REPLACE` (o `UPDATE`) puntual de esa fila en el espejo local.
Esto evita la ventana de hasta 30s en la que un admin edita un producto y
lo sigue viendo con el valor viejo en la misma pantalla. Si esa
actualización puntual falla (excepción de SQLite, disco lleno, etc.), se
registra con `logger.warning` y NO se propaga como error al cliente: la
escritura en BigQuery (la fuente de verdad) ya se confirmó, y el próximo
ciclo de refresco periódico corrige el espejo de todos modos. El espejo
nunca debe poder tumbar una operación de escritura real.

### 4. Fallback transparente a BigQuery si el espejo no responde

El nuevo repositorio local (`productos_local.py`) expone las mismas
funciones que ya usa `catalogos/productos.py` (`buscar_con_total`,
`listar`, `marcas_distintas`). `catalogos/productos.py` intenta primero
el repositorio local; si lanza una excepción (archivo no existe todavía,
corrupción, lo que sea) o el espejo reporta que nunca se completó un
refresco exitoso, cae a las funciones equivalentes que ya existen contra
BigQuery (`acceso_datos/repositorios/productos.py`), sin que quien llama
note la diferencia salvo por la latencia. Esto cubre: primer arranque en
una PC nueva (antes del primer refresco), y cualquier fallo inesperado
del espejo — el catálogo sigue funcionando, solo más lento, exactamente
como hoy.

### 5. Hilo daemon nuevo, mismo patrón que `Sincronizador`/`ProgramadorCierre`

`EspejoCatalogo` en `almacen_local/espejo_catalogo.py`: mismo esqueleto
(`iniciar()`/`detener()`/`_bucle()` con `threading.Event`, nunca debe
poder tumbar el proceso — cualquier excepción del ciclo se atrapa y se
reintenta). Se construye en `crear_app()` (para que un futuro endpoint de
estado, si hiciera falta, siempre tenga a quien preguntarle — igual
criterio que `Sincronizador`) pero solo se arranca (`.iniciar()`) desde
`__main__` en `main.py`, para no disparar hilos reales al importar el
módulo en tests.

### 6. Esquema del espejo: espejo, no copia 1:1 de columnas de BigQuery

La tabla SQLite `producto` guarda solo las columnas que el catálogo de
lectura necesita (id, codigo_barras, codigo_interno, nombre, categoria,
marca, descripcion, imagen, precio, costo, stock_minimo, cantidad
[stock ya agregado], actualizado_en) — no hace falta reproducir
`activo`/`creado_en` en el espejo porque el refresco ya filtra
`activo = TRUE` del lado de BigQuery antes de guardar. Índices en
`nombre` (para `LIKE`), `codigo_barras`, `categoria`, `marca`, `precio`
— los mismos campos por los que hoy se filtra en BigQuery.

`NORMALIZE(..., NFD)` (para ignorar acentos) no existe en SQLite. Se
resuelve normalizando el texto en Python (quitando diacríticos con
`unicodedata`) tanto al guardar `nombre` en una columna auxiliar
`nombre_normalizado` como al armar el término de búsqueda, y comparando
esa columna con `LIKE` — mismo resultado funcional que hoy
(insensible a mayúsculas/acentos), sin depender de una función que SQLite
no tiene.

## Risks / Trade-offs

- **[Riesgo]** Divergencia temporal: un cambio hecho desde otra fuente (o
  si en el futuro hay más de una PC) tarda hasta 30s en verse.
  → **Mitigación**: aceptable para este negocio (una sola PC editando el
  catálogo); la escritura local se refleja de inmediato (Decisión 3), que
  es el caso que más importa.

- **[Riesgo]** El espejo puede quedar desactualizado si el hilo de
  refresco muere silenciosamente.
  → **Mitigación**: mismo patrón defensivo que `Sincronizador`
  (try/except amplio alrededor de cada ciclo, nunca deja morir el hilo);
  además, el fallback a BigQuery (Decisión 4) significa que aunque el
  hilo muriera, el catálogo seguiría funcionando, solo sin la mejora de
  velocidad.

- **[Riesgo]** Corrupción del archivo SQLite (apagón a media escritura).
  → **Mitigación**: el refresco reemplaza el contenido dentro de una
  transacción; SQLite es resistente a corrupción por corte de energía en
  el modo por defecto. Si aun así se corrompiera, es un archivo
  desechable: se borra y se reconstruye solo en el siguiente ciclo (igual
  fallback a BigQuery mientras tanto).

- **[Riesgo]** Duplicar la lógica de "insensible a mayúsculas/acentos"
  entre BigQuery (`NORMALIZE`) y SQLite (Python) es una fuente potencial
  de comportamiento distinto entre ambos caminos.
  → **Mitigación**: se cubre con tests que verifican el mismo conjunto de
  casos (acentos, mayúsculas, código de barras exacto) contra ambos
  repositorios, no solo contra el nuevo.

- **[Riesgo]** Este cambio no resuelve la pantalla de Ventas/reportes
  históricos (agregaciones), que sigue leyendo BigQuery directo y puede
  seguir sintiéndose lenta.
  → **Mitigación**: fuera de alcance a propósito (ver proposal de la
  sesión de exploración original) — este cambio ataca específicamente el
  catálogo, que es donde se reportó la molestia.

## Migration Plan

1. Desplegar el código. El primer arranque en cada PC no tiene espejo
   todavía: el fallback a BigQuery (Decisión 4) cubre ese primer minuto
   sin que nadie lo note salvo por la latencia habitual.
2. El hilo de refresco puebla el espejo en su primer ciclo (segundos
   después de arrancar). A partir de ahí, el catálogo responde del
   espejo.
3. Sin pasos manuales para el usuario del negocio — no hay `.env` nuevo,
   ni script que correr, ni tabla nueva en BigQuery.
4. Rollback: revertir el código. El archivo `.sqlite3` local se ignora
   automáticamente por el código viejo (no lo referencia); no requiere
   limpieza manual, aunque se puede borrar sin problema.

## Open Questions

- Ninguna bloqueante. Si más adelante el negocio agrega una segunda PC
  operando el catálogo a la vez, valdría la pena revisar si 30s de
  divergencia sigue siendo aceptable o si conviene bajar el intervalo —
  no es una decisión que haga falta tomar ahora.
