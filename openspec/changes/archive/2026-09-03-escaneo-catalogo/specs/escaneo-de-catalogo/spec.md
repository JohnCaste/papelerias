## ADDED Requirements

### Requirement: Hook de lectura de pistola de código de barras

El frontend SHALL ofrecer un hook `useScannerGun(alLeer)` que detecte las
lecturas de una pistola de código de barras USB (que emite las teclas como un
teclado) y entregue el código leído a la función `alLeer`.

- El hook SHALL escuchar `keydown` a nivel `document` y acumular los caracteres
  imprimibles en un buffer.
- El hook SHALL considerar la secuencia una lectura de pistola solo cuando el
  tiempo entre pulsaciones es menor o igual a un umbral corto (por defecto
  50 ms) y la secuencia termina con `Enter`.
- Al recibir `Enter` con un buffer válido (longitud mínima configurable, por
  defecto 3 caracteres) SHALL invocar `alLeer(codigo)` con el buffer acumulado y
  luego vaciar el buffer.
- Si entre dos pulsaciones pasa más que el umbral, el buffer SHALL reiniciarse:
  la escritura humana normal nunca dispara `alLeer`.
- El hook SHALL ignorar la secuencia cuando el foco está en un `<input>`,
  `<textarea>` o elemento editable **distinto** del buscador del catálogo, para
  no robar la escritura de otros formularios.
- El hook SHALL limpiar su listener al desmontarse.

#### Scenario: Lectura de pistola dispara el callback

- **WHEN** el componente monta `useScannerGun(alLeer)` y llegan las teclas `7`,`5`,`0`,`1`,`2`,`3`,`4` con menos de 50 ms entre cada una y luego `Enter`
- **THEN** `alLeer` se llama una vez con `"7501234"`
- **AND** el buffer queda vacío para la siguiente lectura

#### Scenario: Escritura humana no dispara el callback

- **WHEN** un usuario teclea `c`,`u`,`a` con pausas de más de 50 ms entre teclas y pulsa `Enter`
- **THEN** `alLeer` no se llama
- **AND** el buffer se reinició en cada pausa

#### Scenario: Foco en otro campo de texto no intercepta la lectura

- **WHEN** el foco está en el `<input>` de precio de un formulario y llega una ráfaga de teclas con `Enter`
- **THEN** `alLeer` no se llama y las teclas quedan en ese campo

#### Scenario: El hook se limpia al desmontar

- **WHEN** el componente que usa `useScannerGun` se desmonta
- **THEN** el listener de `keydown` en `document` queda removido

### Requirement: El Catálogo muestra el producto al escanear

La página de Catálogo SHALL usar `useScannerGun` de modo que, al leer un código,
coloque ese código como término de búsqueda del catálogo y muestre el resultado
en la grilla existente, sin abrir pantallas nuevas.

- Al recibir una lectura, el Catálogo SHALL fijar el término de búsqueda (`q`)
  al código leído, lo que dispara la búsqueda server-side ya existente
  (`GET /api/catalogo/buscar`) y reinicia la paginación a la primera página.
- El código leído SHALL mostrarse en el campo del buscador, de modo que el
  usuario vea qué se buscó y pueda limpiarlo con el control de limpiar ya
  presente.
- Si el código no coincide con ningún producto, el Catálogo SHALL mostrar el
  estado "sin resultados" actual, incluyendo el término buscado.
- El escaneo SHALL funcionar tanto para el rol `admin` como para `vendedor`.

#### Scenario: Escanear un producto existente lo muestra

- **WHEN** existe un producto activo con `codigo_barras = "7501234567890"` y el usuario está en la página de Catálogo
- **AND** la pistola lee `7501234567890`
- **THEN** el buscador muestra `7501234567890`
- **AND** la grilla muestra ese producto y la paginación vuelve a la página 1

#### Scenario: Escanear un código sin producto muestra sin resultados

- **WHEN** ningún producto activo tiene `codigo_barras = "0000000000000"`
- **AND** la pistola lee `0000000000000`
- **THEN** la grilla muestra el estado "Sin resultados para '0000000000000'"

#### Scenario: Limpiar la búsqueda tras un escaneo

- **WHEN** el buscador quedó con un código escaneado y el usuario pulsa el control de limpiar del buscador
- **THEN** el término se vacía y la grilla vuelve al catálogo completo
