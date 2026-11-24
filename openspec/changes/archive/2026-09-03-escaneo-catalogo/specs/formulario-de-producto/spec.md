## ADDED Requirements

### Requirement: Campo opcional de código de barras

Los formularios de alta y de edición de producto SHALL ofrecer un campo de texto
opcional **Código de barras** que se envía como `codigo_barras` en
`POST /api/catalogo` y `PATCH /api/catalogo`.

- El campo SHALL ser opcional: un producto sin código de barras SHALL crearse y
  editarse igual que hoy.
- El formulario de edición SHALL precargar el `codigo_barras` actual del
  producto.
- El valor SHALL enviarse recortado (`trim`); un campo vacío SHALL enviarse como
  `null` (o ausente), no como cadena vacía.
- El backend SHALL rechazar con `400` un `codigo_barras` no vacío que ya use
  otro producto activo (unicidad ya declarada como invariante del esquema). Al
  editar, conservar el mismo código del propio producto SHALL ser válido.

#### Scenario: Alta de producto con código de barras

- **WHEN** el administrador crea un producto con `codigo_barras = "7501234567890"` no usado por otro producto
- **THEN** el producto se crea con ese código
- **AND** `GET /api/catalogo/buscar?q=7501234567890` lo devuelve

#### Scenario: Alta sin código de barras

- **WHEN** el administrador crea un producto dejando vacío el campo Código de barras
- **THEN** el producto se crea con `codigo_barras = null` y sin error

#### Scenario: Código de barras duplicado rechazado

- **WHEN** ya existe un producto activo con `codigo_barras = "7501234567890"`
- **AND** se llama `POST /api/catalogo` con ese mismo `codigo_barras`
- **THEN** la respuesta es `400` con un mensaje que indica que el código ya está en uso
- **AND** no se crea ningún producto

#### Scenario: Editar un producto conservando su propio código

- **WHEN** se llama `PATCH /api/catalogo` para un producto que ya tiene `codigo_barras = "7501234567890"` y se envía ese mismo valor
- **THEN** la edición se acepta (no cuenta como duplicado consigo mismo)

#### Scenario: Edición asigna un código ya usado por otro producto

- **WHEN** el producto A tiene `codigo_barras = "111"` y se llama `PATCH /api/catalogo` para el producto B con `codigo_barras = "111"`
- **THEN** la respuesta es `400` y el producto B conserva su código anterior
