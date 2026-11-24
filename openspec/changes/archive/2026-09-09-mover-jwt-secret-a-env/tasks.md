## 1. Backend — leer el secreto de la variable de entorno

- [x] 1.1 En `backend/main.py`, agregar una función (p. ej.
      `_resolver_jwt_secret_key()`) que: si `JWT_SECRET_KEY` está en el
      entorno, la devuelve; si no y `ENTORNO == "desarrollo"` o el proceso
      corre bajo pytest (`almacen_local._seguridad_pruebas.bajo_pruebas()`),
      devuelve el valor fijo de desarrollo/tests; si no (producción sin la
      variable), lanza `RuntimeError` con un mensaje claro mencionando
      `JWT_SECRET_KEY` y `backend\.env`.
- [x] 1.2 Reemplazar la línea
      `app.config["JWT_SECRET_KEY"] = "<secreto-viejo-ya-rotado>"` por una
      llamada a esa función dentro de `crear_app()`.
- [x] 1.3 Quitar el comentario `# ver #5, sin tocar aqui` (ya no aplica).

## 2. Configuración y documentación

- [x] 2.1 Agregar `JWT_SECRET_KEY=` a `backend/.env.example`, con un
      comentario breve explicando qué es y cómo generarlo.
- [x] 2.2 Actualizar `INSTALAR.md`: agregar el paso de generar y configurar
      `JWT_SECRET_KEY` en el Paso 3 (junto a `GOOGLE_APPLICATION_CREDENTIALS`
      y `BUCKET_IMAGENES_PRODUCTO`), con el comando de una línea para
      generarlo (`python -c "import secrets; print(secrets.token_hex(32))"`).
- [x] 2.3 Agregar una entrada a la sección "Si algo no arranca" de
      `INSTALAR.md`: el backend no arranca / error mencionando
      `JWT_SECRET_KEY` → falta configurar esa variable en `.env`.
- [x] 2.4 Agregar una nota en "Actualizar el código más adelante" (o en la
      sección de reparación de esta actualización) explicando que, tras
      actualizar a esta versión, hay que agregar `JWT_SECRET_KEY` al
      `.env` de la PC del negocio ANTES de reiniciar, y que todas las
      sesiones activas se cerrarán una vez (comportamiento esperado).

## 3. Tests

- [x] 3.1 Agregar tests en `backend/tests/test_main.py` (o un archivo
      nuevo) cubriendo: (a) con `JWT_SECRET_KEY` en el entorno,
      `crear_app()` la usa; (b) en desarrollo/tests sin la variable,
      `crear_app()` no falla y usa el valor por defecto documentado; (c)
      en producción (`ENTORNO` no `"desarrollo"`, fuera del contexto de
      pytest simulado) sin la variable, `crear_app()` lanza `RuntimeError`
      con un mensaje que menciona `JWT_SECRET_KEY`.
      (4 tests nuevos en `test_main.py`.)
- [x] 3.2 Confirmar que el resto de la suite (`pytest` completo en
      `backend/`) sigue pasando sin necesidad de un `.env` real.
      **397/397 pasan**, sin `.env` real.

## 4. Verificación

- [x] 4.1 Correr `pytest` completo en `backend/` y confirmar 0 fallos.
      **397/397 tests pasan.**
- [x] 4.2 Levantar el backend en modo producción localmente sin
      `JWT_SECRET_KEY` en el entorno y confirmar que falla al arrancar con
      el mensaje esperado (no llega a escuchar el puerto).
      **Confirmado**: `RuntimeError` mencionando `JWT_SECRET_KEY` y
      `backend\.env`, antes de construir la app.
- [x] 4.3 Levantar el backend en modo producción con `JWT_SECRET_KEY`
      configurada y confirmar que arranca normalmente y que el login sigue
      funcionando.
      **Confirmado**: arrancó en Waitress, `GET /` → 200,
      `POST /api/autentificacion/login` responde con su validación normal
      (no hubo credenciales reales de prueba a mano, pero el endpoint
      quedó operativo — no hay error relacionado al JWT).
