# articulo-inexistente Specification

## Purpose
TBD - created by archiving change escaneo-inventario. Update Purpose after archive.
## Requirements
### Requirement: Modal reutilizable de artículo inexistente

El frontend SHALL ofrecer un componente `ModalArticuloInexistente` que se
muestra cuando un código escaneado no corresponde a ningún producto.

- El modal SHALL mostrar el texto `Artículo «<código>» inexistente`, con el
  código exactamente como se leyó.
- El modal SHALL ofrecer una acción "Cancelar" (o "Cerrar") que lo cierra sin
  ningún efecto secundario.
- El modal SHALL ofrecer una acción "Agregar" **solo cuando quien lo ve puede
  dar de alta productos**; al pulsarla, SHALL cerrarse y abrir el alta de
  producto con el código precargado.
- Cuando "Agregar" no está disponible (rol sin alta de productos), el modal
  SHALL mostrar únicamente la acción de cierre.

#### Scenario: Cancelar no hace nada

- **WHEN** el modal está abierto para el código "0000000000000" y el usuario pulsa "Cancelar"
- **THEN** el modal se cierra
- **AND** no se abre ningún otro modal ni se crea ningún producto

#### Scenario: Agregar abre el alta con el código

- **WHEN** el modal está abierto para el código "7501234567890" y el usuario con permiso de alta pulsa "Agregar"
- **THEN** el modal de artículo inexistente se cierra
- **AND** se abre el formulario de alta de producto con el campo Código de barras precargado con "7501234567890"

#### Scenario: Sin permiso de alta solo se puede cerrar

- **WHEN** un usuario con rol `vendedor` ve el modal para un código no encontrado
- **THEN** el modal muestra solo la acción de cierre, sin "Agregar"

### Requirement: Precarga del código en el alta de producto

El formulario de alta de producto (`AgregarProModal`) SHALL aceptar un valor
inicial opcional para el código de barras y usarlo como valor inicial del campo
`codigo_barras` cada vez que el modal se abre.

- Si no se pasa valor inicial, el campo SHALL arrancar vacío como hasta ahora.
- El valor precargado SHALL ser editable por el usuario antes de guardar.

#### Scenario: Alta abierta desde el flujo de escaneo

- **WHEN** se abre el alta de producto con código inicial "7501234567890"
- **THEN** el campo Código de barras muestra "7501234567890"
- **AND** el resto del formulario está vacío

#### Scenario: Alta abierta normalmente

- **WHEN** se abre el alta de producto sin código inicial (botón "Agregar producto")
- **THEN** el campo Código de barras está vacío

### Requirement: Escaneo en la pestaña Inventario

La pestaña **Inventario** de Administración SHALL reaccionar a la pistola de
código de barras mediante `useScannerGun`.

- Al leer un código, la tabla de Inventario SHALL filtrarse en cliente al
  producto cuyo `codigo_barras` es exactamente igual al código leído.
- Mientras el filtro por escaneo está activo, la pestaña SHALL mostrar un
  control para limpiarlo y volver a la lista completa.
- Si ningún producto cargado coincide con el código, la pestaña SHALL abrir
  `ModalArticuloInexistente` con ese código en lugar de mostrar una tabla
  vacía.
- Si desde ese modal se agrega el producto, la tabla SHALL recargarse para
  incluirlo.

#### Scenario: Escanear un producto existente filtra la tabla

- **WHEN** el inventario tiene un producto con `codigo_barras = "7501234567890"` y se lee ese código
- **THEN** la tabla muestra solo esa fila
- **AND** aparece un control para limpiar el filtro

#### Scenario: Limpiar el filtro de escaneo

- **WHEN** la tabla está filtrada por un escaneo y el usuario pulsa el control de limpiar
- **THEN** la tabla vuelve a mostrar todos los productos

#### Scenario: Escanear un código no cargado ofrece darlo de alta

- **WHEN** ningún producto del inventario tiene `codigo_barras = "0000000000000"` y se lee ese código
- **THEN** se abre `ModalArticuloInexistente` con «0000000000000»
- **AND** al pulsar "Agregar" se abre el alta con ese código precargado

#### Scenario: Alta desde el modal recarga la tabla

- **WHEN** el usuario agrega un producto con `codigo_barras = "0000000000000"` desde el flujo de artículo inexistente
- **THEN** la tabla de Inventario se recarga y el nuevo producto aparece

### Requirement: El Catálogo ofrece el alta cuando el escaneo no encuentra nada

El Catálogo SHALL mostrar `ModalArticuloInexistente` con el código escaneado
cuando el término de búsqueda proviene de un escaneo (no de escritura manual) y
la búsqueda server-side devuelve `total = 0`.

- El modal SHALL aparecer además del estado "sin resultados" ya existente (no
  lo reemplaza en el DOM; se superpone).
- Para el rol `admin`, el modal SHALL ofrecer "Agregar" (abre el alta con el
  código) y "Cancelar".
- Para el rol `vendedor`, el modal SHALL ofrecer solo la acción de cierre.
- Escribir un término a mano que no da resultados SHALL seguir mostrando solo
  el estado "sin resultados", sin abrir el modal.

#### Scenario: Admin escanea un código inexistente en el Catálogo

- **WHEN** un `admin` escanea "0000000000000" y la búsqueda devuelve `total = 0`
- **THEN** se abre `ModalArticuloInexistente` con «0000000000000» y botones "Agregar" y "Cancelar"

#### Scenario: Vendedor escanea un código inexistente en el Catálogo

- **WHEN** un `vendedor` escanea "0000000000000" y la búsqueda devuelve `total = 0`
- **THEN** se abre `ModalArticuloInexistente` con solo la acción de cierre

#### Scenario: Búsqueda manual sin resultados no abre el modal

- **WHEN** el usuario teclea "xyzxyz" en el buscador y la búsqueda devuelve `total = 0`
- **THEN** se muestra el estado "sin resultados" y NO se abre `ModalArticuloInexistente`

#### Scenario: Escaneo con resultado no abre el modal

- **WHEN** un `admin` escanea un código que sí existe
- **THEN** la grilla muestra ese producto y no se abre `ModalArticuloInexistente`

