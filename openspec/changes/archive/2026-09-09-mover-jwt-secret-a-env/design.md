## Context

`backend/main.py` fija `app.config["JWT_SECRET_KEY"] = "<secreto-viejo-ya-rotado>"`
directo en el código, con un comentario `# ver #5, sin tocar aqui` — quedó
pendiente desde el issue original. El resto de secretos del proyecto
(`GOOGLE_APPLICATION_CREDENTIALS`, `BUCKET_IMAGENES_PRODUCTO`) ya viven en
`backend/.env` (no versionado, cargado con `python-dotenv` desde
`autentificacion/serviciosCloud.py`), así que el patrón a seguir ya existe
en el proyecto — este cambio solo extiende ese mismo patrón al secreto de
JWT.

`main.py` construye `app = crear_app()` a nivel de módulo (línea final del
archivo) y los tests (`test_main.py`) importan ese módulo y llaman a
`crear_app()` directamente, sin pasar por un `.env` real. Cualquier validación
de arranque tiene que convivir con eso sin romper los tests.

## Goals / Non-Goals

**Goals:**
- El secreto de JWT deja de estar en el código fuente / historial de git
  hacia adelante.
- Un despliegue en producción sin la variable configurada falla de forma
  ruidosa y clara, no arranca "a medias" con un secreto débil.
- Desarrollo local y tests siguen funcionando sin fricción nueva (sin
  exigir un `.env` que hoy no tienen todos los entornos de test).

**Non-Goals:**
- No se implementa rotación automática de secretos ni un sistema de
  gestión de secretos (Vault, Secret Manager, etc.) — es una PC de
  negocio con un solo backend, un `.env` local es proporcional.
- No se invalidan sesiones activas ni se fuerza un logout masivo como
  parte del código de este cambio (ver Migration Plan: es un paso manual
  al desplegar, no una feature del sistema).
- No se generaliza a "validar TODOS los secretos configurables" — el
  alcance es `JWT_SECRET_KEY`, que es el único secreto sensible que hoy
  vive hardcodeado en el código (a diferencia de los de GCP, que ya están
  en `.env`).

## Decisions

### 1. Falla dura en producción, valor fijo en desarrollo/tests

`crear_app()` (o un helper que llama antes de construir la app) lee
`os.environ.get("JWT_SECRET_KEY")`:

- Si `ENTORNO == "desarrollo"` (o bajo pytest) y la variable no está
  definida: usa un valor fijo documentado como "solo para desarrollo/tests,
  nunca usar en producción" (p. ej. `"desarrollo-inseguro-no-usar-en-produccion"`).
  Mantiene `python main.py` con `ENTORNO=desarrollo` funcionando sin tocar
  nada, igual que hoy, y no pide `.env` a los tests.
- Si `ENTORNO != "desarrollo"` (producción, el default) y la variable NO
  está definida: `crear_app()` lanza `RuntimeError` con un mensaje que dice
  exactamente qué falta y en qué archivo agregarla — el proceso ni siquiera
  llega a escuchar en el puerto. Alternativa considerada: loguear una
  advertencia y arrancar de todos modos con un valor por defecto débil —
  se descarta porque es exactamente el problema actual (arrancar en
  silencio con un secreto conocido/débil); fallar es la opción segura por
  defecto, y coherente con el propio comentario de `ENTORNO` en `main.py`
  ("falla hacia el lado seguro si alguien corre esto sin pensar en la
  variable").

Esto reutiliza el criterio que main.py ya aplica a `ENTORNO` mismo
(default seguro, explícito para desarrollo) — no introduce un patrón nuevo.

### 2. Variable de entorno simple, no un archivo de secreto aparte

Se usa `JWT_SECRET_KEY` en `backend/.env`, igual que
`GOOGLE_APPLICATION_CREDENTIALS`. Alternativa considerada: generar el
secreto en un archivo aparte (`backend/secretos/jwt.key`) como se hace con
la llave de GCP. Se descarta: la llave de GCP es un archivo porque así la
entrega Google (JSON de cuenta de servicio); un secreto de JWT es solo una
cadena de texto, una variable de entorno es más simple y sigue el patrón
que `python-dotenv` ya resuelve en el proyecto.

### 3. Generación del valor real: manual, documentada en INSTALAR.md

No se automatiza la generación de un secreto aleatorio en el script de
instalación (`scripts/instalar.ps1`) en este cambio — mantenerlo simple:
`INSTALAR.md` da un comando de una línea (`python -c "import secrets;
print(secrets.token_hex(32))"`, ya disponible con el Python que el
proyecto ya exige) para que Jona lo genere una vez y lo pegue en `.env`,
igual que ya hace con la ruta de la llave de GCP.

## Risks / Trade-offs

- **[Riesgo]** Si se despliega este cambio sin agregar la variable al
  `.env` de la PC del negocio, el backend deja de arrancar en producción.
  → **Mitigación**: es intencional (falla dura, ver Decisión 1) y
  documentado en `INSTALAR.md` con el mensaje de error exacto que se va a
  ver, para que se reconozca de inmediato en vez de investigarse a ciegas.

- **[Riesgo]** Rotar el secreto invalida todos los tokens JWT ya emitidos
  (todos los usuarios con sesión activa quedan deslogueados a la vez).
  → **Mitigación**: aceptable — pasa una sola vez al desplegar este
  cambio, y un logout forzado de todos los usuarios es exactamente lo
  correcto dado que el secreto viejo quedó expuesto en el historial de
  git (cualquier token firmado con la llave vieja debe dejar de ser
  válido).

- **[Riesgo]** El secreto viejo (`"<secreto-viejo-ya-rotado>"`) sigue en el
  historial de git de este repo aunque se quite del código.
  → **Mitigación**: fuera de alcance de este cambio (purgar historial de
  git ya se hizo antes para las credenciales de GCP, ver memoria de
  sesión "GCP credenciales lapape" — es una operación disruptiva que
  requiere coordinarse aparte, no algo para incluir aquí sin que el
  usuario lo pida explícitamente). Lo que este cambio sí logra es que el
  secreto *vigente* deje de estar expuesto a partir de ahora.

## Migration Plan

1. Desplegar el código de este cambio.
2. Generar un secreto nuevo con el comando documentado en `INSTALAR.md`.
3. Agregar `JWT_SECRET_KEY=<el valor generado>` a `backend\.env` en la PC
   del negocio, **antes** de reiniciar el backend (si se reinicia sin la
   variable, no arranca — ver Decisión 1, es la señal de que falta este
   paso).
4. Reiniciar el backend. Todas las sesiones activas (con el secreto viejo)
   dejan de ser válidas — cada usuario tiene que volver a iniciar sesión
   una vez. Se documenta en `INSTALAR.md` como algo esperado, no un error.
5. Rollback: si algo sale mal, revertir el código a como estaba (secreto
   hardcodeado) es reversible sin pérdida de datos — no hay migración de
   esquema de por medio.

## Open Questions

Ninguna bloqueante.
