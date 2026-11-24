## Why

El catálogo tarda en responder porque cada tecla escrita en el buscador dispara
una búsqueda inmediata contra BigQuery (latencia de ~0.5-2s por consulta, sin
importar el volumen de datos) y cada búsqueda ejecuta tres llamadas
secuenciales (`buscar` + `contar` + `stock_de_varios`). Escribir una palabra de
8 letras genera hasta 24 llamadas a BigQuery. Esto ya era molesto y con
clientes esperando en el mostrador se volvió tedioso.

Por separado, el backend no escribe ningún log a disco: los hilos en segundo
plano (sincronizador, programador de cierre) y los errores del servidor solo
se ven si la ventana de la consola sigue abierta y visible. Esto es un
bloqueante para el plan de convertir el backend en una app de arranque
automático / servicio de Windows (sin ventana visible): hoy, si algo falla en
segundo plano, no queda ningún rastro para diagnosticarlo.

Este cambio es el primer paso de un proceso más grande explorado en sesión
(startup app/servicio de Windows, posible espejo local del catálogo, revisar
`JWT_SECRET_KEY` hardcodeado). Por ahora cubre solo debounce + logging: son
independientes entre sí, de bajo riesgo, y desbloquean el resto sin comprometer
al negocio con cambios de infraestructura mayores todavía.

## What Changes

- Agregar debounce de 300ms al buscador del Catálogo (`frontend/src/pages/Catalogo.tsx`):
  la búsqueda server-side solo se dispara cuando el usuario deja de teclear
  300ms, no en cada cambio de `q`. Los filtros de categoría, marca y el cambio
  de página siguen disparando la búsqueda de inmediato (no son texto libre).
- Colapsar `contar()` dentro de `buscar()` en el backend: `GET
  /api/catalogo/buscar` deja de requerir dos consultas (`buscar` + `contar`)
  y las combina en una sola función de repositorio, reduciendo de 3 a 2
  llamadas a BigQuery por búsqueda (la tercera, `stock_de_varios`, ya está
  colapsada en una sola llamada para toda la página y no cambia).
- Agregar logging a archivo con rotación en el backend: un logger raíz
  configurado en `main.py` (o módulo dedicado) que escribe a
  `backend/datos_locales/logs/` con rotación por tamaño, activo tanto en
  desarrollo como en producción. El sincronizador y el programador de cierre
  (que ya usan `logging.getLogger(__name__)`) empiezan a persistir sus
  mensajes sin cambiar su código. Se agrega manejo de errores no capturados
  de Flask para que un 500 también quede registrado.
- **BREAKING**: ninguno — ambos cambios son de implementación interna, no
  alteran contratos de API ni comportamiento visible salvo el retraso
  intencional de 300ms en la búsqueda por texto.

## Capabilities

### New Capabilities
- `registro-de-eventos-backend`: logging a archivo con rotación para los
  procesos en segundo plano y errores del servidor Flask, necesario para
  operar el backend sin una consola visible.

### Modified Capabilities
- `busqueda-de-catalogo`: el Catálogo deja de disparar una búsqueda por cada
  tecla (debounce de 300ms sobre el término de texto) y el endpoint
  `GET /api/catalogo/buscar` deja de hacer una consulta separada para el
  total, calculándolo junto con los resultados en una sola función de
  repositorio (el contrato de la respuesta `{ items, total }` no cambia).

## Impact

- **Frontend**: `frontend/src/pages/Catalogo.tsx` (debounce sobre `q`).
- **Backend**:
  - `backend/catalogos/productos.py` (`buscar_productos`, deja de llamar
    `contar()` por separado).
  - `backend/acceso_datos/repositorios/productos.py` (nueva función que
    devuelve resultados + total combinados; `contar()` se conserva si algo
    más la usa, si no se retira).
  - `backend/main.py` (configuración del logger raíz, handler de errores no
    capturados).
  - Nuevo módulo, p. ej. `backend/utilidades/registro.py` (configuración de
    `RotatingFileHandler`).
  - `backend/almacen_local/sincronizador.py` y
    `backend/almacen_local/programador_cierre.py` (sin cambios de código,
    solo empiezan a persistir sus logs existentes).
  - `.gitignore` (excluir la carpeta de logs, igual que `datos_locales/`).
- **Tests**: `backend/tests/test_endpoint_productos.py` y/o
  `test_consultas.py` (cubrir la función combinada buscar+contar);
  posible test nuevo para el logger.
- Sin cambios en esquema de BigQuery ni en contratos de API existentes.
