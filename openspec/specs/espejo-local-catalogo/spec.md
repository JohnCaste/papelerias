# espejo-local-catalogo Specification

## Purpose

Espejo de solo lectura del catálogo (productos activos, categorías
activas y stock agregado) en SQLite dentro de `backend/datos_locales/`,
refrescado periódicamente desde BigQuery en segundo plano. Existe para
que las búsquedas del catálogo respondan en milisegundos en vez de pagar
la latencia de red de BigQuery en cada petición, sin comprometer a
BigQuery como fuente de verdad ni requerir una migración de motor de
base de datos. Es una proyección desechable: se puede borrar en
cualquier momento y se reconstruye sola.

## Requirements

### Requirement: Espejo local de solo lectura del catálogo

El sistema SHALL mantener una copia local en SQLite (dentro de
`backend/datos_locales/`) de los productos activos, las categorías
activas y el stock agregado por producto, refrescada periódicamente desde
BigQuery en segundo plano, sin bloquear ninguna petición HTTP mientras se
refresca.

- El refresco SHALL correr en un hilo separado del que atiende peticiones
  HTTP, con un intervalo por defecto de 30 segundos.
- Cada ciclo de refresco SHALL reemplazar el contenido local completo
  (nunca dejar un estado a medias visible a una lectura concurrente).
- Una excepción durante un ciclo de refresco (sin internet, error de
  BigQuery, lo que sea) SHALL registrarse y NO SHALL detener el hilo: el
  siguiente ciclo reintenta.

#### Scenario: El espejo se puebla solo al arrancar

- **WHEN** el backend arranca y no existe ningún archivo de espejo previo
- **THEN** dentro del intervalo de refresco configurado, el espejo local
  contiene los productos y categorías activos que hay en BigQuery en ese
  momento

#### Scenario: Un fallo de red no detiene el refresco futuro

- **WHEN** un ciclo de refresco falla porque no hay conexión a internet
- **THEN** el hilo de refresco sigue vivo y lo vuelve a intentar en el
  siguiente ciclo
- **AND** el espejo conserva el contenido del último refresco exitoso
  mientras tanto

#### Scenario: El paginador simple también lee del espejo

- **WHEN** el espejo local completó al menos un refresco exitoso
- **AND** se llama `GET /api/catalogo/paginador?limit=12&offset=0`
- **THEN** la respuesta se resuelve sin ejecutar ninguna consulta a
  BigQuery, con el mismo formato de producto que devuelve hoy

### Requirement: El catálogo sigue funcionando si el espejo no está disponible

El sistema SHALL responder la petición consultando BigQuery directamente
si el espejo local no existe todavía, o si una lectura sobre él falla por
cualquier motivo, sin devolver error al cliente por esa causa.

#### Scenario: Primer arranque en una PC nueva

- **WHEN** el backend acaba de arrancar y el hilo de refresco todavía no
  completó su primer ciclo
- **AND** se recibe `GET /api/catalogo/buscar`
- **THEN** la respuesta llega con los datos vigentes en BigQuery (no un
  catálogo vacío ni un error)

#### Scenario: El archivo del espejo se borra en caliente

- **WHEN** alguien borra `backend/datos_locales/catalogo_espejo.sqlite3`
  mientras el backend está corriendo
- **AND** se recibe una petición de catálogo antes del siguiente ciclo de
  refresco
- **THEN** la respuesta llega igual, resuelta contra BigQuery
- **AND** el siguiente ciclo de refresco recrea el archivo del espejo sin
  intervención manual

### Requirement: Una escritura de catálogo actualiza el espejo de inmediato

El sistema SHALL reflejar en el espejo local, antes de que ocurra el
siguiente ciclo de refresco periódico, cualquier alta, edición o baja de
producto que ya se haya confirmado en BigQuery, para que el mismo usuario
no vea datos obsoletos justo después de escribir.

- Si la actualización puntual del espejo falla, el sistema SHALL
  registrar el fallo y SHALL devolver éxito de todos modos si la
  escritura en BigQuery se confirmó (el espejo no es la fuente de verdad;
  el siguiente refresco periódico lo corrige).

#### Scenario: Editar un producto se ve reflejado sin esperar el refresco

- **WHEN** se edita el precio de un producto vía `PATCH /api/catalogo`
- **AND** la respuesta de esa edición es exitosa
- **THEN** una búsqueda inmediata de ese producto (antes de que pase el
  intervalo de refresco) devuelve el precio nuevo

#### Scenario: Un fallo al actualizar el espejo no rompe la escritura real

- **WHEN** se edita un producto y BigQuery confirma el cambio
- **AND** la actualización puntual del espejo local lanza una excepción
- **THEN** la petición de edición sigue devolviendo éxito al cliente
- **AND** el fallo queda registrado en el log
