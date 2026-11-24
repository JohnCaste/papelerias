## ADDED Requirements

### Requirement: Logging a archivo con rotación

El backend SHALL escribir sus mensajes de log (de todos los módulos que usan
`logging.getLogger`) a un archivo en disco dentro de
`backend/datos_locales/logs/`, con rotación por tamaño, además de a consola
cuando corre en modo desarrollo. La configuración SHALL aplicarse una sola
vez, al arrancar el proceso, sin requerir cambios en los módulos que ya
registran logs (`almacen_local/sincronizador.py`,
`almacen_local/programador_cierre.py`).

- El handler de archivo SHALL usar `logging.handlers.RotatingFileHandler`
  con un tamaño máximo por archivo y una cantidad máxima de respaldos, de
  forma que el total en disco quede acotado sin intervención manual.
- El nivel de log SHALL ser INFO en producción (`ENTORNO` distinto de
  `"desarrollo"`) y DEBUG cuando `ENTORNO=desarrollo`.
- Cada línea SHALL incluir al menos fecha/hora, nivel, nombre del logger
  (módulo de origen) y el mensaje.
- La carpeta `backend/datos_locales/logs/` SHALL crearse automáticamente si
  no existe, igual que ya hacen `almacen_local/journal.py` y
  `almacen_local/cierres.py` con sus propias carpetas.

#### Scenario: Un mensaje del sincronizador queda en disco

- **WHEN** el backend arranca en modo producción (`ENTORNO` no es
  `"desarrollo"`)
- **AND** el sincronizador registra un mensaje de error al fallar la subida
  de un día pendiente a BigQuery
- **THEN** ese mensaje aparece en un archivo dentro de
  `backend/datos_locales/logs/`, con fecha/hora, nivel y el nombre del
  módulo que lo generó

#### Scenario: El log no crece sin control

- **WHEN** el archivo de log activo alcanza el tamaño máximo configurado
- **THEN** el sistema rota a un archivo nuevo y conserva solo la cantidad de
  respaldos configurada, sin intervención manual

#### Scenario: Modo desarrollo también muestra los logs en consola

- **WHEN** el backend arranca con `ENTORNO=desarrollo`
- **THEN** los mensajes de log aparecen tanto en el archivo como en la
  consola donde corre `python main.py`
- **AND** el nivel mínimo registrado es DEBUG

#### Scenario: La carpeta de logs no se sube a git

- **WHEN** se revisa `.gitignore` en la raíz del proyecto
- **THEN** la carpeta `backend/datos_locales/logs/` está excluida, igual
  que el resto de `datos_locales/`

### Requirement: Excepciones no capturadas quedan registradas

El sistema SHALL registrar con nivel ERROR y traceback completo cualquier
excepción no capturada que ocurra al atender una petición HTTP, antes de
devolver la respuesta de error al cliente.

#### Scenario: Un error interno queda en el log antes del 500

- **WHEN** una petición a cualquier endpoint de la API provoca una excepción
  no manejada dentro del código de la vista
- **THEN** el cliente recibe una respuesta con código 500
- **AND** el archivo de log contiene una entrada de nivel ERROR con el
  traceback de esa excepción
