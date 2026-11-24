## MODIFIED Requirements

### Requirement: Búsqueda server-side sobre todo el catálogo

El sistema SHALL exponer un endpoint `GET /api/catalogo/buscar` que consulte
todos los productos activos (no solo la página visible) filtrando por término
de texto, categoría, marca y rango de precio, y devuelva la página pedida junto
con el total de coincidencias.

- El endpoint SHALL aceptar los parámetros de query `q`, `categoria`, `marca`,
  `precio_min`, `precio_max`, `limit` (defecto 12, máx 200) y `offset`
  (defecto 0).
- El término `q` SHALL comparar de forma insensible a mayúsculas y acentos
  contra el nombre del producto, Y ADEMÁS SHALL coincidir cuando `q` (tras
  `strip()`) es exactamente igual al `codigo_barras` de un producto activo. Un
  `q` que coincide con un código de barras SHALL devolver ese producto aunque no
  coincida con ningún nombre; la coincidencia por código es exacta, no por
  subcadena.
- La respuesta SHALL tener la forma `{ "items": [...], "total": <int> }`, donde
  `items` conserva el formato de producto actual (incluido `cantidad` como
  stock calculado y los campos numéricos como number).
- Los parámetros ausentes o inválidos SHALL tratarse como "sin filtro" sin
  devolver error.
- Los resultados de la página y el `total` de coincidencias SHALL obtenerse
  con una sola consulta a la base de datos (no una consulta para las filas y
  otra separada para el conteo), para reducir la cantidad de llamadas por
  búsqueda.
- El endpoint SHALL resolverse contra el espejo local del catálogo (ver
  capability `espejo-local-catalogo`) cuando esté disponible, y contra
  BigQuery directamente si el espejo no está disponible, sin que el
  contrato de la respuesta cambie según cuál de los dos haya respondido.

#### Scenario: Búsqueda por término encuentra productos fuera de la página actual

- **WHEN** existen 40 productos activos y solo uno llamado "Cuaderno profesional" está en la página 3
- **AND** se llama `GET /api/catalogo/buscar?q=cuaderno%20profesional&limit=12&offset=0`
- **THEN** la respuesta incluye ese producto en `items`
- **AND** `total` refleja la cantidad de coincidencias en todo el catálogo

#### Scenario: Búsqueda por código de barras exacto

- **WHEN** existe un producto activo "Cuaderno profesional" con `codigo_barras = "7501234567890"` y su nombre no contiene ese número
- **AND** se llama `GET /api/catalogo/buscar?q=7501234567890`
- **THEN** `items` incluye ese producto
- **AND** `total` es 1

#### Scenario: Código de barras parcial no coincide

- **WHEN** un producto activo tiene `codigo_barras = "7501234567890"`
- **AND** se llama `GET /api/catalogo/buscar?q=750123`
- **THEN** ese producto no aparece por coincidencia de código (solo aparecería si su nombre contuviera "750123")

#### Scenario: Filtro combinado categoría + marca + precio

- **WHEN** se llama `GET /api/catalogo/buscar?categoria=Escritura&marca=BIC&precio_max=50`
- **THEN** `items` solo contiene productos activos de categoría "Escritura", marca "BIC" (insensible a mayúsculas) y `precio <= 50`
- **AND** `total` es la cantidad de productos que cumplen los tres filtros

#### Scenario: Paginación devuelve total estable

- **WHEN** hay 25 coincidencias y se pide `limit=12&offset=12`
- **THEN** `items` trae las coincidencias 13 a 24
- **AND** `total` es 25 independientemente del `offset`

#### Scenario: Parámetros inválidos se ignoran

- **WHEN** se llama `GET /api/catalogo/buscar?precio_min=abc&limit=-5`
- **THEN** la respuesta es 200
- **AND** el filtro de precio mínimo no se aplica y `limit` cae al valor por defecto

#### Scenario: Sin coincidencias, el total es cero en una sola consulta

- **WHEN** ningún producto activo cumple los filtros pedidos
- **THEN** la respuesta es `{ "items": [], "total": 0 }`
- **AND** el sistema no ejecuta una consulta adicional para calcular ese total

#### Scenario: Responde del espejo local cuando está disponible

- **WHEN** el espejo local del catálogo completó al menos un refresco exitoso
- **AND** se llama `GET /api/catalogo/buscar`
- **THEN** la respuesta se resuelve sin ejecutar ninguna consulta a BigQuery

#### Scenario: Cae a BigQuery si el espejo no está disponible

- **WHEN** el espejo local no existe o su lectura lanza una excepción
- **AND** se llama `GET /api/catalogo/buscar`
- **THEN** la respuesta se resuelve consultando BigQuery directamente
- **AND** el cliente recibe la misma forma de respuesta `{ items, total }`

### Requirement: Listado de categorías canónicas

El sistema SHALL exponer `GET /api/catalogo/categorias` que devuelva la lista
canónica de categorías de producto leída de la tabla fija `categoria`
(no de `SELECT DISTINCT` sobre `producto`), incluyendo solo las activas y
en el orden con el que fueron sembradas (columna `orden`). Esta lista
puebla el selector de los formularios de alta/edición y el filtro de
categoría del catálogo.

El endpoint SHALL resolverse contra el espejo local del catálogo cuando
esté disponible, y contra BigQuery directamente si no lo está.

#### Scenario: Devuelve la lista sembrada en su orden

- **WHEN** la tabla `categoria` fue sembrada con "Lapiceros" (orden 0), "Lápices" (orden 1), "Cuadernos" (orden 5)
- **AND** se llama `GET /api/catalogo/categorias`
- **THEN** la respuesta es `["Lapiceros", "Lápices", "Cuadernos"]` en ese orden

#### Scenario: No depende de las categorías guardadas en los productos

- **WHEN** todos los productos tienen `categoria = "Escolar"`
- **AND** la tabla `categoria` tiene las 32 categorías canónicas
- **THEN** `GET /api/catalogo/categorias` devuelve las 32, no solo "Escolar"

#### Scenario: Ignora categorías inactivas

- **WHEN** una fila de `categoria` tiene `activo = FALSE`
- **THEN** su nombre no aparece en la respuesta

### Requirement: Listado de marcas existentes

El sistema SHALL exponer `GET /api/catalogo/marcas` que devuelva la lista de
marcas distintas de productos activos (excluyendo nulos y vacíos), ordenada
alfabéticamente, para poblar el filtro por marca.

El endpoint SHALL resolverse contra el espejo local del catálogo cuando
esté disponible, y contra BigQuery directamente si no lo está.

#### Scenario: Devuelve marcas únicas y ordenadas

- **WHEN** hay productos activos con marcas "BIC", "Faber-Castell", "BIC", y uno sin marca
- **AND** se llama `GET /api/catalogo/marcas`
- **THEN** la respuesta es `["BIC", "Faber-Castell"]`
