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

### Requirement: El Catálogo consume la búsqueda server-side

La página de Catálogo SHALL obtener sus resultados de `GET /api/catalogo/buscar`
pasando el término del navbar y los filtros de categoría, marca y orden, y SHALL
paginar usando el `total` de la respuesta en vez de la heurística
"trajo menos de `limit`".

El término de texto del buscador SHALL aplicar un debounce de 300ms: la
búsqueda solo se dispara cuando el usuario deja de escribir por ese tiempo,
para no ejecutar una petición por cada tecla. Los cambios de categoría, marca
y de página (offset) NO SHALL tener debounce: disparan la búsqueda de
inmediato, igual que hoy.

#### Scenario: Escribir en el buscador filtra todo el catálogo

- **WHEN** el usuario escribe "regla" en el buscador estando en la página 1
- **THEN** la grilla muestra todas las coincidencias del catálogo completo, no solo las de la página cargada
- **AND** el contador de paginación se calcula a partir de `total`

#### Scenario: Teclear varias letras seguidas dispara una sola búsqueda

- **WHEN** el usuario escribe "regla" letra por letra, con menos de 300ms
  entre cada tecla
- **THEN** el sistema espera a que pasen 300ms sin nuevas teclas antes de
  llamar a `GET /api/catalogo/buscar`
- **AND** se ejecuta una sola búsqueda con `q=regla`, no una por cada letra

#### Scenario: Dejar de escribir dispara la búsqueda tras el retraso

- **WHEN** el usuario escribe "regla" y no vuelve a tocar el buscador
- **THEN** la búsqueda se ejecuta 300ms después de la última tecla, sin
  necesidad de una acción adicional del usuario

#### Scenario: Filtro por marca

- **WHEN** el usuario elige la marca "BIC" en el nuevo selector de marca
- **THEN** la grilla muestra solo productos de marca "BIC"
- **AND** el filtro se combina con el término de búsqueda y la categoría activos

#### Scenario: Cambiar de categoría o marca no espera el debounce

- **WHEN** el usuario selecciona una categoría o una marca del selector
- **THEN** la búsqueda se ejecuta de inmediato, sin el retraso de 300ms que
  aplica al término de texto

#### Scenario: Limpiar filtros

- **WHEN** el usuario pulsa "Limpiar filtros"
- **THEN** se restablecen término, categoría, marca y orden a sus valores por defecto
- **AND** la grilla vuelve a la primera página del catálogo completo
