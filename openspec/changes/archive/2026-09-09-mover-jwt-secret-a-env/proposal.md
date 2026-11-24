## Why

El `JWT_SECRET_KEY` que firma la sesión de todos los usuarios está escrito en
texto plano en `backend/main.py` (`"<secreto-viejo-ya-rotado>"`), commiteado y
presente en el historial de git. Mientras el backend solo corría cuando
alguien lo encendía a mano, era un descuido pendiente; con el plan de
convertirlo en app de arranque automático / servicio de Windows (corriendo
24/7 y expuesto en la red local vía Waitress en `0.0.0.0`), pasa a ser un
riesgo activo: cualquiera con acceso al repositorio (o a una copia del
código en una USB, como ya contempla `INSTALAR.md`) puede forjar un token
válido y entrar como cualquier usuario, incluido el dueño.

## What Changes

- El secreto deja de vivir en el código fuente: `main.py` lo lee de la
  variable de entorno `JWT_SECRET_KEY` (vía `backend/.env`, igual que ya se
  hace con `GOOGLE_APPLICATION_CREDENTIALS` y `BUCKET_IMAGENES_PRODUCTO`).
- En **producción** (`ENTORNO` distinto de `"desarrollo"`), si la variable
  no está definida el proceso **SHALL** rehusarse a arrancar con un error
  claro, en vez de arrancar silenciosamente con un secreto adivinable o
  vacío.
- En **desarrollo/tests**, si la variable no está definida se usa un valor
  fijo de solo-desarrollo (documentado como tal), para no romper el flujo
  de `python main.py` con `ENTORNO=desarrollo` a cada rato ni los tests que
  construyen la app sin `.env`.
- `backend/.env.example` documenta la nueva variable.
- **No** se invalidan las sesiones existentes automáticamente como parte de
  este cambio (el secreto rotará una sola vez, al desplegar); ver
  Impact/Migration en design.md para el paso manual de rotación real de la
  llave usada hasta hoy.
- **BREAKING** (operacional, no de API): al desplegar este cambio, quien
  actualice la PC del negocio debe agregar `JWT_SECRET_KEY` a su
  `backend\.env` — si no lo hace, el backend en producción no arranca (a
  propósito, ver arriba). Se documenta en `INSTALAR.md`.

## Capabilities

### New Capabilities
- `configuracion-de-secretos-backend`: el backend valida en el arranque que
  los secretos sensibles (por ahora, `JWT_SECRET_KEY`) vengan de variables
  de entorno y no de un valor fijo en el código, fallando de forma clara en
  producción si falta.

### Modified Capabilities
(ninguna — no hay spec existente para autenticación/JWT; el contrato de los
endpoints `/api/autentificacion/*` no cambia, solo de dónde sale la llave
con la que se firman los tokens.)

## Impact

- **Backend**: `backend/main.py` (lectura de `JWT_SECRET_KEY`, validación
  de arranque).
- **Config**: `backend/.env.example` (nueva variable documentada);
  `backend/.env` de cada PC (Jona debe agregar la línea a mano, como ya
  pasa con las otras variables).
- **Docs**: `INSTALAR.md` (paso 3, configuración de `.env`) y la sección de
  actualización, para que quien actualice el código sepa que debe agregar
  la variable antes de reiniciar.
- **Tests**: `backend/tests/test_main.py` y cualquier test que construya
  `crear_app()` sin `.env` — deben seguir pasando con el valor de
  desarrollo/tests por defecto.
- Sin cambios en el contrato de los endpoints `/api/autentificacion/*` ni
  en el frontend.
