## Context

Este cambio toca dos capas independientes que comparten un mismo motivo:
preparar el sistema para operar sin que alguien esté mirando la pantalla del
backend en todo momento (paso previo al plan de convertirlo en servicio de
Windows) y reducir la latencia percibida en el catálogo, que hoy depende de
BigQuery (latencia fija de red por consulta, sin importar el volumen).

Estado actual relevante:
- `frontend/src/pages/Catalogo.tsx`: el `useEffect` que llama a
  `buscarProductos()` depende directamente de `q`, sin ningún retraso — cada
  `onChange` del input dispara una petición.
- `backend/catalogos/productos.py::buscar_productos()` llama primero a
  `productos_repo.buscar(...)` y luego, por separado, a
  `productos_repo.contar(...)` — dos round-trips a BigQuery en vez de uno.
- No existe ningún `logging.basicConfig` ni handler de archivo en todo el
  backend. `sincronizador.py` y `programador_cierre.py` ya llaman a
  `logging.getLogger(__name__)` y emiten mensajes, pero sin handler
  configurado esos mensajes se van a la nada (o a stderr si hay consola).
- El sincronizador corre como hilo daemon dentro del mismo proceso — un
  logger raíz configurado una vez en el arranque del proceso cubre también
  esos hilos sin tocarlos.

## Goals / Non-Goals

**Goals:**
- Reducir a una fracción las llamadas a BigQuery que dispara escribir en el
  buscador del catálogo, sin cambiar el contrato de la respuesta
  (`{ items, total }`) ni el comportamiento de filtros no-texto.
- Que cualquier excepción o mensaje de log del backend (incluidos los hilos
  de fondo) quede en disco, con rotación, para poder diagnosticar sin
  consola visible.
- Mantener el cambio acotado: no tocar el esquema de BigQuery, no introducir
  dependencias nuevas si la librería estándar alcanza.

**Non-Goals:**
- No se implementa aquí el servicio de Windows, el espejo local del
  catálogo (SQLite), ni el reemplazo del `JWT_SECRET_KEY` hardcodeado —
  quedan para cambios futuros ya identificados en la sesión de exploración.
- No se optimiza la pantalla de Ventas/agregaciones históricas (fuera de
  alcance de esta propuesta).
- No se agrega un servicio de logging centralizado ni telemetría remota;
  solo archivo local con rotación, consistente con el resto del proyecto
  (`datos_locales/` ya es la convención para estado local en disco).

## Decisions

### 1. Debounce en el cliente (no en el servidor)

Se implementa el retraso de 300ms en React (`useEffect` + `setTimeout`/
`clearTimeout`, o el hook `useDebouncedValue` si se opta por extraerlo),
no en el backend. Alternativa considerada: throttling del lado del
servidor (rate-limit por sesión). Se descarta porque no resuelve el
problema real (peticiones desperdiciadas que de todos modos viajan por la
red) y añade complejidad de estado en un backend que hoy es stateless por
petición.

El debounce aplica **solo al término de texto `q`**. Los cambios de
`categoria`, `marca` y `offset` (paginación) siguen disparando la búsqueda
de inmediato: son eventos discretos (clic), no tecleo continuo, y
retrasarlos sin necesidad empeoraría la percepción de velocidad ahí donde
hoy ya es instantáneo.

300ms se elige como valor conservador y estándar para búsquedas tipo
"live search" (suficiente para cubrir la cadencia de tecleo normal, sin
sentirse tardío). No se hace configurable: no hay necesidad identificada.

### 2. Combinar `buscar` + `contar` en una función de repositorio

Se agrega una función en `acceso_datos/repositorios/productos.py` (p. ej.
`buscar_con_total(...)`) que arma las mismas condiciones vía
`_condiciones_busqueda(...)` (ya existente, se reutiliza sin cambios) y
ejecuta **una sola consulta** que devuelve tanto las filas de la página
como el total, usando una window function
(`COUNT(*) OVER() AS total_coincidencias`) en vez de dos SELECT
separados. Alternativa considerada: un solo `ejecutar_query` con dos
sentencias (`;`-separadas) — BigQuery las trata como dos jobs igual, no
ahorra nada; se descarta.

`contar()` se conserva tal cual en el repositorio (la sigue usando quien
la necesite fuera de la búsqueda combinada, si aplica) — este cambio no
la elimina, solo deja de invocarla desde `buscar_productos()`.

`_con_stock()` no cambia: ya hace una sola llamada a
`movimientos_repo.stock_de_varios(ids)` para toda la página.

Resultado: de 3 llamadas a BigQuery por búsqueda (`buscar` + `contar` +
`stock_de_varios`) se pasa a 2 (`buscar_con_total` + `stock_de_varios`).

### 3. Logging: `RotatingFileHandler` configurado una vez en `main.py`

Se crea `backend/utilidades/registro.py` con una función
`configurar_logging()` que:
- Crea `backend/datos_locales/logs/` si no existe (mismo patrón que
  `journal.py` y `almacen_local/cierres.py` usan para sus carpetas).
- Configura el logger raíz con un `RotatingFileHandler`
  (`maxBytes` ~5MB, `backupCount` ~5 — suficiente para semanas de
  operación de un negocio de este volumen sin crecer sin control) más un
  `StreamHandler` a consola (para que `ENTORNO=desarrollo` siga viendo
  logs en la terminal de Vite/Flask como hoy).
- Se llama una sola vez, al importar `main.py` (junto a `crear_app()`),
  antes de construir `Sincronizador`/`ProgramadorCierre` — así sus
  `logging.getLogger(__name__)` ya heredan la configuración del logger
  raíz sin que esos módulos cambien.

Se agrega un `app.errorhandler(Exception)` (o
`app.log_exception`/hook equivalente) que registra cualquier excepción no
capturada con nivel ERROR y traceback completo antes de devolver 500 —
hoy Flask/Waitress no deja rastro en disco de esos casos.

Alternativa considerada: usar `logging.handlers.TimedRotatingFileHandler`
(rotación diaria). Se descarta `RotatingFileHandler` por tamaño en vez de
por tiempo porque el volumen de logs es impredecible (un ciclo de
reintentos del sincronizador sin internet puede generar muchas líneas en
poco tiempo) y rotar por tamaño acota mejor el disco.

Nivel por defecto: INFO en producción, DEBUG si `ENTORNO=desarrollo` —
reutiliza la misma variable de entorno que ya distingue el modo del
servidor, sin agregar una variable nueva.

## Risks / Trade-offs

- **[Riesgo]** El debounce introduce un retraso perceptible (300ms) entre
  teclear y ver resultados, lo que podría sentirse "lento" para quien
  compara contra el comportamiento actual (instantáneo pero costoso).
  → **Mitigación**: 300ms está por debajo del umbral típico de percepción
  de lag en UIs de búsqueda: es net positive porque el resultado final
  llega antes al reducirse los mensajes en cola.

- **[Riesgo]** La window function `COUNT(*) OVER()` repite el cálculo del
  total en cada fila devuelta — para una página de 20 filas es
  insignificante, pero si `limit` creciera mucho podría no serlo.
  → **Mitigación**: `limite` ya está acotado a `_LIMITE_MAXIMO = 200` en
  el repositorio; no representa un costo relevante a esa escala.

- **[Riesgo]** Logs sin rotación de espacio en disco agresiva podrían
  llenar la PC del negocio si algo entra en un bucle de error.
  → **Mitigación**: `RotatingFileHandler` con `maxBytes`/`backupCount`
  acota el total (~25MB) sin intervención manual.

- **[Riesgo]** Si `datos_locales/logs/` no se excluye en `.gitignore`,
  logs con datos operativos (nombres de usuario, IDs de venta en
  tracebacks) podrían terminar commiteados.
  → **Mitigación**: se agrega la carpeta a `.gitignore` en la misma tarea,
  siguiendo el patrón ya usado para `datos_locales/journal` y
  `datos_locales/cierres`.

## Migration Plan

- Sin migración de datos: son cambios de código puro.
- Despliegue normal vía `git pull` + `scripts/instalar.ps1` (recompila
  frontend, reinstala deps del backend si `requirements.txt` cambiara —
  no cambia aquí, se usa solo `logging` de la librería estándar).
- Rollback: revertir el commit; no hay estado persistente incompatible
  hacia atrás (los logs son solo de lectura/diagnóstico, no se leen desde
  otro código).
- No requiere detener el servicio en producción más allá del reinicio
  normal del proceso tras actualizar código (ya documentado en README).

## Open Questions

- Ninguna bloqueante. Queda abierto para una iteración futura si conviene
  exponer un endpoint de solo-lectura para ver el log reciente desde la
  pantalla de Admin, en vez de tener que abrir el archivo a mano en la PC
  del negocio — no se incluye en este cambio por mantenerlo acotado.
