# formulario-de-producto Specification

## Purpose

Reglas de los formularios de alta y edición de producto (modales de
Administración): la categoría se elige de un `<select>` cerrado poblado con la
lista canónica de la tabla `categoria` (sin texto libre), el precio no puede ser
negativo (validado en backend y en el formulario), y el campo de imagen va al
final con las acciones "Tomar foto" / "Subir foto" y previsualización.
## Requirements
### Requirement: Selector cerrado de categoría desde la lista canónica

Los formularios de alta y de edición de producto SHALL ofrecer la categoría
como un `<select>` cerrado poblado con la lista canónica de
`GET /api/catalogo/categorias` (tabla `categoria`). No SHALL admitir texto
libre ni la creación de categorías nuevas desde el formulario.

- El `<select>` SHALL mostrar las opciones en el orden que devuelve el
  endpoint, más una opción vacía inicial ("Seleccioná una categoría").
- El formulario de edición SHALL preseleccionar la categoría actual del
  producto. Si esa categoría ya no está en la lista canónica, SHALL
  mostrarla igualmente como opción marcada "(actual)" para no perderla al
  guardar sin querer.

#### Scenario: Elegir una categoría de la lista

- **WHEN** el administrador abre "Nuevo producto"
- **THEN** el selector de categoría muestra exactamente las categorías de la lista canónica, en su orden, y no acepta texto libre

#### Scenario: Editar un producto cuya categoría sigue en la lista

- **WHEN** se edita un producto con `categoria = "Escolar"` y "Escolar" está en la lista canónica
- **THEN** el selector aparece con "Escolar" preseleccionado

#### Scenario: Editar un producto con categoría fuera de la lista

- **WHEN** se edita un producto con `categoria = "papeleria"` y "papeleria" no está en la lista canónica
- **THEN** el selector incluye una opción "papeleria (actual)" preseleccionada, además de las categorías canónicas

### Requirement: El precio no puede ser negativo

El sistema SHALL rechazar la creación o edición de un producto cuyo `precio`
sea menor que 0.

- El backend (`agregar_productos` y `actualizar_productos`) SHALL responder 400
  con un mensaje claro cuando `precio < 0`.
- Los formularios SHALL impedir el envío con `precio < 0` (input con `min=0` y
  validación antes de llamar a la API).
- Un `precio` igual a 0 SHALL seguir siendo válido.

#### Scenario: Alta con precio negativo rechazada en backend

- **WHEN** se llama `POST /api/catalogo` con `precio = -10`
- **THEN** la respuesta es 400 con un mensaje que indica que el precio no puede ser negativo
- **AND** no se crea ningún producto

#### Scenario: Edición con precio negativo rechazada en backend

- **WHEN** se llama `PATCH /api/catalogo` con `precio = -1` para un producto existente
- **THEN** la respuesta es 400 y el producto conserva su precio anterior

#### Scenario: El formulario bloquea el envío

- **WHEN** el administrador escribe `-5` en el campo de precio
- **THEN** el botón de guardar no envía la petición y se muestra un mensaje de validación

#### Scenario: Precio cero permitido

- **WHEN** se crea un producto con `precio = 0`
- **THEN** el producto se crea correctamente

### Requirement: El campo de imagen va al final del formulario

Ambos formularios (alta y edición) SHALL ubicar el campo de imagen como último
elemento del formulario, con las acciones "Tomar foto" y "Subir foto" y la
previsualización de la imagen procesada.

#### Scenario: Orden del formulario

- **WHEN** el administrador abre el formulario de producto
- **THEN** el campo de imagen aparece después de los campos de datos (nombre, categoría, marca, precio, cantidad, descripción)

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

