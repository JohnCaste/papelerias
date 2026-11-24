# configuracion-de-secretos-backend Specification

## Purpose

El backend valida en el arranque que los secretos sensibles (por ahora,
`JWT_SECRET_KEY`) vengan de variables de entorno y no de un valor fijo en
el código, fallando de forma clara en producción si falta.

## Requirements

### Requirement: JWT_SECRET_KEY viene de variable de entorno

El sistema SHALL leer la llave de firma de JWT (`JWT_SECRET_KEY`) desde la
variable de entorno `JWT_SECRET_KEY` (vía `backend/.env`), nunca desde un
valor fijo en el código fuente.

#### Scenario: La app arranca con el valor de la variable de entorno

- **WHEN** `JWT_SECRET_KEY` está definida en el entorno del proceso (por
  `.env` o de cualquier otra forma)
- **AND** se construye la app con `crear_app()`
- **THEN** `app.config["JWT_SECRET_KEY"]` es exactamente el valor de esa
  variable de entorno

### Requirement: Falla dura en producción si falta el secreto

El sistema SHALL rehusarse a construir la aplicación si `ENTORNO` es
distinto de "desarrollo" (modo producción, el default) y `JWT_SECRET_KEY`
no está definida en el entorno, lanzando un error con un mensaje que
indique claramente qué variable falta y en qué archivo configurarla.

#### Scenario: Producción sin la variable no arranca

- **WHEN** `ENTORNO` no está definida (o es distinta de "desarrollo")
- **AND** `JWT_SECRET_KEY` no está definida en el entorno
- **AND** se intenta construir la app con `crear_app()`
- **THEN** se lanza una excepción antes de que el servidor quede
  escuchando en ningún puerto
- **AND** el mensaje de la excepción menciona `JWT_SECRET_KEY` y
  `backend\.env`

### Requirement: Valor de desarrollo/tests sin configuración adicional

El sistema SHALL usar un valor fijo documentado como exclusivo de
desarrollo/tests si `ENTORNO` es igual a "desarrollo" (o el proceso corre
bajo pytest) y `JWT_SECRET_KEY` no está definida, sin requerir que cada
entorno de desarrollo o de pruebas tenga su propio `.env` con esa variable.

#### Scenario: Desarrollo arranca sin .env adicional

- **WHEN** `ENTORNO=desarrollo`
- **AND** `JWT_SECRET_KEY` no está definida en el entorno
- **AND** se construye la app con `crear_app()`
- **THEN** la app arranca sin error
- **AND** `app.config["JWT_SECRET_KEY"]` tiene un valor no vacío

#### Scenario: Los tests construyen la app sin .env

- **WHEN** un test llama a `crear_app()` sin que `JWT_SECRET_KEY` esté
  definida y sin que `ENTORNO=desarrollo` esté forzado explícitamente
- **THEN** la construcción de la app no falla por falta de esa variable
  (los tests corren bajo el mismo criterio que desarrollo, o un criterio
  equivalente que los identifique como entorno de pruebas)
