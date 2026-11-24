# tarjeta-de-catalogo Specification

## Purpose

Comportamiento y presentación de la tarjeta de producto (`ProductoCard`) en la
vista de Catálogo: es de solo lectura, con una única acción "Ver" a ancho
completo que navega a `/admin` y abre el modal de edición del producto. Editar y
eliminar viven solo en Administración. Las imágenes de todas las tarjetas se
muestran a una altura fija común con `object-fit: cover`.

## Requirements

### Requirement: La tarjeta del Catálogo no ofrece Editar ni Eliminar

En la vista de Catálogo, `ProductoCard` SHALL mostrar únicamente la acción
"Ver". Los controles de Editar (lápiz) y "más acciones" (que abre Eliminar)
SHALL retirarse de esta vista, porque editar y eliminar solo se hacen desde
Administración.

#### Scenario: Tarjeta de administrador en el Catálogo

- **WHEN** un administrador ve el Catálogo
- **THEN** cada tarjeta muestra un único botón "Ver" y ningún botón de editar o de menú

#### Scenario: Administración conserva sus acciones

- **WHEN** el administrador está en la página de Administración
- **THEN** las acciones de editar y eliminar producto siguen disponibles allí

### Requirement: El botón "Ver" ocupa todo el ancho de la fila de acciones

`ProductoCard` SHALL renderizar el botón "Ver" ocupando el 100 % del ancho de
la zona de acciones de la tarjeta.

#### Scenario: Ancho completo

- **WHEN** se muestra una tarjeta de producto en el Catálogo
- **THEN** el botón "Ver" abarca todo el ancho disponible de la fila de acciones, sin espacio reservado para otros botones

### Requirement: "Ver" abre el modal de edición en Administración

Al hacer click en "Ver" desde el Catálogo, el sistema SHALL navegar a `/admin`
y abrir automáticamente el modal de edición del producto seleccionado.

- La navegación SHALL transportar el identificador del producto (vía estado de
  navegación de React Router o query param).
- La página de Administración SHALL detectar ese identificador al montar y abrir
  el modal de edición con los datos de ese producto.
- Si el producto no se encuentra, Administración SHALL cargarse normalmente sin
  abrir el modal.

#### Scenario: Ver un producto desde el Catálogo

- **WHEN** el administrador pulsa "Ver" en la tarjeta de un producto
- **THEN** la aplicación navega a `/admin`
- **AND** el modal de edición de ese producto se abre con sus datos cargados

#### Scenario: Identificador desconocido

- **WHEN** se llega a `/admin` con un identificador de producto que no existe
- **THEN** Administración se muestra normalmente y ningún modal se abre

### Requirement: Imágenes de tarjeta a altura uniforme

Las imágenes de las tarjetas del Catálogo SHALL mostrarse con una altura fija
común y `object-fit: cover`, de modo que la zona de imagen tenga el mismo alto
en todas las tarjetas independientemente de las proporciones del archivo.

#### Scenario: Imágenes de distinta proporción

- **WHEN** el Catálogo muestra un producto con imagen apaisada y otro con imagen vertical
- **THEN** ambas tarjetas tienen la zona de imagen del mismo alto
- **AND** ninguna imagen desborda ni deja franjas vacías (se recorta con `cover`)

#### Scenario: Producto sin imagen

- **WHEN** un producto no tiene imagen
- **THEN** su tarjeta muestra el marcador de "sin imagen" ocupando esa misma altura fija
