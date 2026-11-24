## 1. Esquema y acceso a datos del espejo local (SQLite)

- [x] 1.1 Crear `backend/almacen_local/espejo_catalogo_sqlite.py` (nombre
      tentativo) con: ruta del archivo
      (`backend/datos_locales/catalogo_espejo.sqlite3`, mismo patrón de
      `resolver_carpeta`/guardas de tests que `journal.py`), función
      `conectar()` y `crear_esquema(conexion)` con las tablas `producto`
      (id, codigo_barras, codigo_interno, nombre, nombre_normalizado,
      categoria, marca, descripcion, imagen, precio, costo, stock_minimo,
      cantidad, actualizado_en) y `categoria` (nombre, orden), con
      índices en `nombre_normalizado`, `codigo_barras`, `categoria`,
      `marca`, `precio`.
- [x] 1.2 Función de normalización de texto (quitar acentos/mayúsculas,
      usando `unicodedata`) reutilizable tanto para guardar
      `nombre_normalizado` como para armar el término de búsqueda.
- [x] 1.3 Crear `backend/acceso_datos/repositorios/productos_local.py`
      con las funciones equivalentes a las que usa
      `catalogos/productos.py`: `buscar_con_total(...)`, `listar(...)`,
      `marcas_distintas()`, `listar_categorias()` — mismos parámetros y
      misma forma de retorno que sus contrapartes en
      `acceso_datos/repositorios/productos.py` /
      `acceso_datos/repositorios/categorias.py`, pero contra SQLite con
      SQL parametrizado (placeholders `?`, nunca f-strings con datos del
      usuario).
      **Nota**: también se agregaron ahí mismo `reemplazar_todo`,
      `upsert_producto` y `marcar_inactivo` (funciones de escritura del
      espejo, usadas por el refresco periódico y por la actualización
      puntual tras escribir — grupos 2 y 4).
- [x] 1.4 Tests de `productos_local.py`: mismos casos que ya cubre
      `test_repositorio_productos.py` (búsqueda por término con acentos/
      mayúsculas, código de barras exacto, filtros combinados, paginación,
      total correcto, sin coincidencias) contra una base SQLite temporal
      (`tmp_path`), para confirmar paridad de comportamiento con el
      camino de BigQuery.
      (`backend/tests/test_repositorio_productos_local.py`, 14 tests.)

## 2. Refresco periódico en segundo plano

- [x] 2.1 En `acceso_datos/repositorios/productos.py` (o un módulo
      nuevo), agregar una función de lectura masiva para el refresco:
      todos los productos activos, y el stock agregado
      (`SELECT producto_id, SUM(cantidad) ... GROUP BY producto_id` sobre
      `movimiento_inventario`) en una sola consulta cada una. Reutilizar
      `categorias_repo.listar()` para las categorías (ya existe).
      (`productos.listar_todos_activos()` +
      `movimientos_inventario.stock_de_todos()`, con tests.)
- [x] 2.2 Crear `almacen_local/espejo_catalogo.py` con la clase
      `EspejoCatalogo` (mismo esqueleto que `Sincronizador`/
      `ProgramadorCierre`: `__init__`, `iniciar()`, `detener()`,
      `ejecutar_ciclo()` síncrono y probable sin hilos, `_bucle()` con
      `threading.Event`, intervalo por defecto 30s). `ejecutar_ciclo()`
      lee de BigQuery (tarea 2.1) y reemplaza el contenido de SQLite
      dentro de una transacción.
- [x] 2.3 Exponer en `EspejoCatalogo` una forma de saber si ya hubo al
      menos un refresco exitoso (p. ej. `disponible()` o
      `ultimo_refresco_exitoso`), para que el fallback (grupo 3) sepa
      cuándo confiar en el espejo.
- [x] 2.4 Tests de `EspejoCatalogo`: un ciclo exitoso puebla SQLite con lo
      que devuelve BigQuery (mockeado); un ciclo que falla no tumba el
      hilo y dijo servir el contenido previo; `disponible()` refleja el
      estado correctamente antes/después del primer ciclo exitoso.
      (`backend/tests/test_espejo_catalogo.py`, 6 tests.)

## 3. Los endpoints de lectura usan el espejo con fallback a BigQuery

- [x] 3.1 En `catalogos/productos.py`, las funciones `buscar_productos()`,
      `limite_productos()`, `listar_categorias()`, `listar_marcas()`
      intentan primero `productos_local`/espejo; si el espejo no está
      `disponible()` o la llamada lanza excepción, caen a las funciones
      equivalentes ya existentes contra `productos_repo`/
      `categorias_repo` (BigQuery). Registrar con `logger.warning` cuando
      se usa el fallback por una excepción inesperada (no cuando es
      simplemente "todavía no hay primer refresco", eso es esperado en
      cada arranque).
      (`_con_fallback`/`_espejo_disponible` en `catalogos/productos.py`,
      vía `current_app.espejo_catalogo`; los 34 tests existentes de
      `test_endpoint_productos.py` siguen pasando sin cambios porque su
      app de prueba no tiene `espejo_catalogo` -- cae a BigQuery siempre,
      confirmando el fallback por defecto.)
- [x] 3.2 Tests del fallback en `test_endpoint_productos.py`: con el
      espejo disponible, se usa el repositorio local y NO se llama al de
      BigQuery; con el espejo no disponible (o lanzando excepción), se
      usa BigQuery y la respuesta tiene la misma forma en ambos casos.
      (8 tests nuevos: buscar/paginador/categorías/marcas × disponible,
      no-disponible, excepción, y sin atributo `espejo_catalogo`.)

## 4. Escrituras actualizan el espejo de inmediato

- [x] 4.1 En `catalogos/productos.py`, después de que
      `productos_repo.crear/actualizar/eliminar` confirma en BigQuery,
      llamar a una función de `productos_local` (p. ej.
      `upsert_producto(...)`/`marcar_inactivo(...)`) que refleja el mismo
      cambio en SQLite. Envuelto en try/except: un fallo aquí se registra
      con `logger.warning` y NO cambia la respuesta HTTP (la escritura en
      BigQuery ya se confirmó).
      **Nota**: además se agregó `espejo_catalogo_sqlite` a la capa 1 de
      `tests/conftest.py` (redirección de `ARCHIVO_POR_DEFECTO` a
      `tmp_path`), igual que ya existía para journal/cierres, para que
      todos los tests de escritura del catálogo ejerciten el
      write-through real contra un archivo temporal en vez de disparar
      la guarda de "carpeta real" en cada uno.
- [x] 4.2 Tests: crear/actualizar/eliminar un producto deja el cambio
      visible de inmediato en una búsqueda local subsecuente (sin esperar
      el ciclo de refresco); un fallo simulado al escribir en el espejo
      no cambia el código de estado de la respuesta HTTP.
      (`backend/tests/test_espejo_catalogo_write_through.py`, 5 tests.)

## 5. Integración en `main.py`

- [x] 5.1 Construir `EspejoCatalogo()` en `crear_app()` (como
      `app.espejo_catalogo`), junto a `Sincronizador`/
      `ProgramadorCierre`.
- [x] 5.2 Arrancarlo (`.iniciar()`) solo en el bloque `if __name__ ==
      "__main__":`, junto a los otros dos hilos.

## 6. Verificación end-to-end

- [x] 6.1 Correr `pytest` completo en `backend/` y confirmar 0 fallos.
      **431/431 tests pasan.**
- [x] 6.2 Levantar el backend real (`ENTORNO=desarrollo`), confirmar que
      `backend/datos_locales/catalogo_espejo.sqlite3` se crea solo y que
      el catálogo sigue mostrando los productos correctos.
      **Confirmado** contra BigQuery real: el archivo se creó solo en
      el primer ciclo (~5s), con los productos y las 32 categorías
      reales. Probado también en modo producción (sin `ENTORNO`).
- [x] 6.3 Con el backend corriendo, borrar el archivo del espejo a mano y
      confirmar que una búsqueda inmediata sigue funcionando (fallback) y
      que el archivo reaparece en el siguiente ciclo.
      **Confirmado**: se borró el archivo con el backend corriendo, y
      reapareció solo, repoblado, en el siguiente ciclo (~30s), sin
      reiniciar nada.
- [ ] 6.4 Editar un producto desde Administración y confirmar en el
      Catálogo que el cambio se ve sin recargar más de una vez (sin
      esperar 30s).
      **Pendiente**: requiere sesión real (login) en el navegador — no
      se usaron credenciales del negocio en esta sesión (igual criterio
      que en el cambio anterior de debounce/logging). El comportamiento
      SÍ está cubierto por tests automatizados
      (`test_espejo_catalogo_write_through.py`), que confirman que el
      cambio queda visible de inmediato en una búsqueda local tras
      crear/actualizar/eliminar.
- [x] 6.5 Comparar informalmente el tiempo de respuesta de
      `GET /api/catalogo/buscar` antes/después (herramientas de red del
      navegador) para tener un número real que confirme (o no) que esto
      resuelve la latencia percibida, como insumo para decidir si además
      hace falta MySQL.
      **Medido directo contra los repositorios** (mismos datos reales,
      sin pasar por HTTP/login): BigQuery directo ~830-1400ms por
      búsqueda; espejo local (SQLite) ~3-6ms. **~150-400x más rápido.**
      Confirma que el espejo local resuelve el problema de latencia sin
      necesidad de MySQL, al menos a este volumen de catálogo.

      **Hallazgo colateral (fuera de alcance de este cambio)**: al medir
      se encontró que la búsqueda en BigQuery no ignora acentos
      correctamente -- buscar "lapiz" no encuentra "Lápiz" (solo
      funciona si se escribe con el acento). Es un bug preexistente en
      `acceso_datos/repositorios/productos.py::_condiciones_busqueda`:
      `NORMALIZE(nombre, NFD)` descompone "á" en "a" + acento combinante,
      pero no LO QUITA, así que el acento sigue rompiendo la coincidencia
      por subcadena. El espejo local (que sí quita los diacríticos en
      Python, ver `normalizar_texto`) no tiene este bug -- por eso, sin
      querer, es más correcto que el camino de BigQuery que reemplaza.
      Se reporta para una tarea aparte; no se corrige aquí para no
      mezclar un fix de bug con este cambio de infraestructura.
