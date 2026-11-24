## 1. Backend — combinar buscar + contar en una sola consulta

- [x] 1.1 Agregar `buscar_con_total(...)` en
      `backend/acceso_datos/repositorios/productos.py`: reutiliza
      `_condiciones_busqueda(...)` y ejecuta una sola consulta con
      `COUNT(*) OVER() AS total_coincidencias`, devolviendo `(filas, total)`
      (`total = 0` si `filas` viene vacío).
- [x] 1.2 Actualizar `buscar_productos()` en
      `backend/catalogos/productos.py` para llamar a `buscar_con_total(...)`
      en vez de `buscar()` + `contar()` por separado.
- [x] 1.3 Confirmar que `contar()` sigue existiendo en el repositorio sin
      cambios (la sigue exponiendo el módulo por si algo más la usa).
- [x] 1.4 Actualizar/agregar pruebas en
      `backend/tests/test_endpoint_productos.py` (o `test_consultas.py`)
      cubriendo: total correcto con coincidencias, total 0 sin
      coincidencias, y que solo se ejecuta una consulta por búsqueda (mock
      de `ejecutar_query` con `assert_called_once` o equivalente).

## 2. Frontend — debounce del buscador

- [x] 2.1 En `frontend/src/pages/Catalogo.tsx`, separar el valor crudo del
      input (`q`) de un valor "debounced" (`qDebounced`) usando
      `useEffect` + `setTimeout(300ms)` con `clearTimeout` en el cleanup.
- [x] 2.2 Cambiar la dependencia del `useEffect` que llama a
      `buscarProductos(...)` para usar `qDebounced` en vez de `q`
      directamente; `categoria`, `marca`, `offset` y `recargar` siguen
      disparando de inmediato.
- [x] 2.3 Verificar que `useScannerGun` (que hace `setQ(codigo)` al leer un
      código de barras) sigue funcionando correctamente con el nuevo
      `qDebounced` — un escaneo también debe esperar los 300ms antes de
      buscar, no hay caso especial para saltarse el debounce.
- [x] 2.4 Revisar manualmente (o con test de componente si existe suite de
      frontend) que escribir varias letras seguidas dispara una sola
      petición de red, visible en las herramientas de desarrollador.
      **Nota**: no existe suite de tests de frontend en el proyecto. Se
      verificó con `tsc -b` y `eslint` (sin errores) y arrancando el
      preview de Vite (sin errores de consola). La verificación visual
      en el navegador con sesión real quedó pendiente para el usuario
      (no se usaron credenciales del negocio) — ver tarea 4.2.

## 3. Backend — logging a archivo con rotación

- [x] 3.1 Crear `backend/utilidades/registro.py` con
      `configurar_logging()`: crea `backend/datos_locales/logs/` si no
      existe, agrega `RotatingFileHandler` (tamaño máx. y `backupCount`
      razonables, p. ej. 5MB × 5 respaldos) y `StreamHandler` a consola,
      con formato que incluya fecha/hora, nivel, logger y mensaje.
- [x] 3.2 Nivel INFO por defecto; DEBUG cuando `ENTORNO=desarrollo` (misma
      variable que ya distingue el modo del servidor en `main.py`).
- [x] 3.3 Llamar a `configurar_logging()` en `backend/main.py`, antes de
      construir `Sincronizador()` y `ProgramadorCierre()`, para que su
      `logging.getLogger(__name__)` ya herede la configuración.
      **Nota**: la llamada se saltea bajo pytest (`bajo_pruebas()`) para
      no tocar `backend/datos_locales/logs/` real durante los tests,
      mismo criterio que `journal.py`/`cierres.py`.
- [x] 3.4 Agregar un `@app.errorhandler(Exception)` (o equivalente) en
      `crear_app()` que registre con `logger.error(..., exc_info=True)`
      cualquier excepción no capturada antes de devolver 500, sin romper
      el comportamiento actual de la respuesta de error.
- [x] 3.5 Agregar `backend/datos_locales/logs/` a `.gitignore`.
      **Nota**: ya estaba cubierta por la entrada existente
      `backend/datos_locales/` — no requirió cambios.
- [x] 3.6 Agregar prueba(s) en `backend/tests/` que verifiquen: se crea el
      archivo de log al llamar `configurar_logging()`, un mensaje de un
      logger de módulo (`logging.getLogger("almacen_local.sincronizador")`)
      queda escrito en el archivo, y una excepción no capturada en un
      endpoint de prueba queda registrada con nivel ERROR.
      (`backend/tests/test_registro.py`, 9 tests.)

## 4. Verificación end-to-end

- [x] 4.1 Correr `pytest` completo en `backend/` y confirmar que no se
      rompió ninguna prueba existente. **393/393 tests pasan.**
- [ ] 4.2 Levantar backend (`ENTORNO=desarrollo`) y frontend (`npm run
      dev`), probar el catálogo a mano: escribir un término, confirmar que
      la red solo muestra una petición tras dejar de teclear, y que los
      resultados y el total siguen siendo correctos.
      **Pendiente**: requiere sesión real (login contra BigQuery); no se
      usaron credenciales del negocio en esta sesión. Se agregó
      `.claude/launch.json` → `backend-dev` para poder levantar el
      backend real desde el preview cuando se quiera hacer esta prueba.
- [ ] 4.3 Confirmar en disco que `backend/datos_locales/logs/` se creó y
      contiene entradas legibles tras un uso normal de la app.
      **Pendiente**: depende de 4.2 (uso real de la app). Cubierto a
      nivel unitario por `test_registro.py` (el archivo y el contenido
      del log sí se verificaron ahí, con carpeta temporal).
- [x] 4.4 Actualizar `INSTALAR.md` o `README.md` si aplica, mencionando la
      nueva carpeta de logs como referencia para diagnosticar problemas
      (breve, sin detallar formato interno).
