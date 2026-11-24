## Context

La papelería usa una pistola lectora de código de barras USB. Estos lectores se
presentan al sistema operativo como un teclado HID: al leer una etiqueta,
"teclean" los dígitos a gran velocidad y cierran con `Enter` (o `Tab`). No hace
falta ninguna API de dispositivo ni permisos del navegador.

Estado actual relevante:

- `esquema/tablas.py` ya define `producto.codigo_barras STRING NULLABLE`, con la
  nota de que debería ser único cuando no es nulo y que la unicidad "se valida
  en el código" (hoy no hay tal validación).
- `acceso_datos/repositorios/productos.py` ya tiene
  `obtener_por_codigo_barras(codigo)`, `crear`/`actualizar` que aceptan
  `codigo_barras`, y `_CAMPOS_EDITABLES` lo incluye. Nadie lo llama todavía.
- `_condiciones_busqueda` arma el `WHERE` de `buscar`/`contar`; el término `q`
  solo compara contra `nombre` con `LOWER(NORMALIZE(...))` y `LIKE %q%`.
- `Catalogo.tsx` ya tiene un estado `q`, un `useEffect` que llama
  `buscarProductos` cuando cambian `q`/`categoria`/`marca`/`offset`, y otro que
  reinicia `offset` a 0 cuando cambian los filtros. `q` arranca del prop
  `filtro` (buscador del navbar) y hay un botón de limpiar.
- Los modales `AgregarProModal.tsx` y `ActualizarProModal.tsx` NO tienen campo de
  código de barras.

## Goals / Non-Goals

**Goals:**

- Que al escanear en la página de Catálogo aparezca el producto correspondiente,
  reutilizando la grilla y la paginación actuales.
- Un hook `useScannerGun` reutilizable y con heurística de tiempo, para no
  confundir escritura humana con lecturas de pistola.
- Poder cargar el `codigo_barras` desde los formularios de alta/edición, con
  unicidad garantizada.

**Non-Goals:**

- Escaneo en el punto de venta (Vender) — es un flujo aparte (#39) y queda para
  otra propuesta.
- Alta rápida de producto "sobre la marcha" cuando el código no existe.
- Autoenfoque de un campo dedicado o modo "escáner" con indicador visual.
- Soporte de lectores en modo puerto serie (COM); se asume modo teclado HID.
- Validar el dígito verificador EAN/UPC o el formato del código.

## Decisions

### 1. Detección por heurística de tiempo entre teclas, a nivel `document`

`useScannerGun(alLeer, opciones?)` registra un único listener `keydown` en
`document`. Mantiene un buffer de caracteres y el timestamp de la última tecla:

- Tecla imprimible de largo 1 y sin `Ctrl/Alt/Meta`: si pasaron más de
  `umbralMs` (def. 50) desde la anterior, se reinicia el buffer; luego se
  agrega el carácter.
- `Enter`: si el buffer tiene al menos `minLargo` (def. 3) caracteres y la
  cadencia se mantuvo bajo el umbral, se llama `alLeer(buffer)` y se limpia el
  buffer. Si no, se descarta.
- Un `setTimeout` de `umbralMs * 2` limpia el buffer tras la inactividad, para
  no arrastrar teclas sueltas.

**Por qué:** es el patrón estándar y probado para lectores HID; no necesita
prefijo/sufijo configurable en la pistola ni foco en un campo. Alternativas
descartadas: (a) campo `<input>` oculto siempre enfocado — frágil, pelea con el
foco real de la página; (b) API `keydown` con `event.repeat`/`isTrusted`
únicamente — no distingue velocidad; (c) librería externa
(`onscan.js`, `react-barcode-reader`) — dependencia nueva para ~40 líneas.

### 2. El Catálogo enruta la lectura al término de búsqueda existente

El callback en `Catalogo.tsx` es `setQ(codigo)`. Esto aprovecha toda la
maquinaria ya presente: el `useEffect` de búsqueda se dispara, `offset` se
reinicia a 0, el buscador muestra el código, el botón de limpiar ya funciona, y
el estado "sin resultados" ya incluye el término. No se agrega ningún
componente ni endpoint nuevo en el frontend.

**Por qué no un modal de detalle:** el pedido es "mostrar el producto"; la
grilla filtrada a un resultado ya lo hace, y mantiene una sola forma de navegar
el catálogo. Un modal implicaría un endpoint "producto por código" y una vista
nueva. Si más adelante se quiere, el hook no cambia: solo el callback.

### 3. Coincidencia por `codigo_barras` dentro del mismo `q`, exacta

En `_condiciones_busqueda`, cuando hay `termino`, la condición pasa de:

```
LOWER(NORMALIZE(nombre, NFD)) LIKE LOWER(NORMALIZE(@termino, NFD))
```

a:

```
(LOWER(NORMALIZE(nombre, NFD)) LIKE LOWER(NORMALIZE(@termino_like, NFD))
 OR codigo_barras = @termino_exacto)
```

con `valores["termino_like"] = f"%{termino}%"` y
`valores["termino_exacto"] = termino`. `contar` usa la misma función, así que el
`total` queda coherente sin tocar nada más.

**Por qué reusar `q` en vez de un parámetro `codigo` nuevo:** el frontend ya
manda todo por `q`; el usuario podría además teclear un código a mano y esperar
el mismo resultado. Un parámetro aparte obligaría a que el cliente supiera de
antemano si lo que tiene es un código o un nombre. La coincidencia exacta
(no `LIKE %código%`) evita que teclear "750" traiga decenas de productos por
prefijo de código.

### 4. Unicidad de `codigo_barras` validada en el endpoint

En `agregar_productos` y `actualizar_productos`, si llega `codigo_barras` no
vacío, se consulta `obtener_por_codigo_barras`; si devuelve otro producto
(id distinto en el caso de edición), se responde `400`
`{"error": "El código de barras ya está en uso"}`. Cadena vacía / espacios →
se normaliza a `None`.

**Por qué en el endpoint y no en un índice de BigQuery:** BigQuery no impone
UNIQUE; el esquema ya delega esta invariante al código. La carrera entre dos
altas simultáneas del mismo código es tolerable para el volumen de esta
papelería (una caja), y de todos modos la búsqueda por código seguiría
funcionando (devolvería 2 filas; se toma la primera).

## Risks / Trade-offs

- **La ráfaga de la pistola coincide con teclas mientras el usuario escribe en
  el buscador** → el hook ignora el evento cuando el foco está en un campo
  editable que no sea el buscador; para el buscador mismo, escribir un código a
  mano y pulsar Enter produce el mismo resultado que escanear, así que no hay
  daño.
- **Lectores configurados con sufijo `Tab` en vez de `Enter`** → se acepta
  también `Tab` como cierre de secuencia si el buffer es válido; documentado en
  tasks para verificar con la pistola real.
- **Umbral de 50 ms demasiado estricto para una pistola lenta o un equipo
  cargado** → `umbralMs` es una opción del hook; si en la PC de la papelería
  hace falta, se sube a 80–100 ms sin cambiar la API.
- **Códigos con ceros a la izquierda** → se tratan como string en todo el
  camino (columna `STRING`, parámetro string); no se convierten a número en
  ningún punto.
- **Producto inactivo con el código** → `obtener_por_codigo_barras` y la
  búsqueda filtran `activo = TRUE`; un código "liberado" por baja lógica puede
  reasignarse.

## Migration Plan

- Sin cambios de datos ni de esquema: `producto.codigo_barras` ya existe en
  todos los entornos.
- Desপliegue estándar (frontend build + backend restart). Sin orden especial
  entre front y back: si el backend nuevo llega primero, el `q` por código
  simplemente aún no se dispara desde el front; si el frontend llega primero,
  escanear busca por nombre y no encuentra — sin error.
- Rollback: revertir el commit. No quedan datos con formato nuevo.

## Open Questions

- ¿La pistola de la papelería cierra con `Enter` o con `Tab`? (verificar en
  hardware real; el hook soporta ambos).
- ¿Interesa un aviso corto tipo toast "Producto encontrado / No hay producto con
  ese código" además del estado de la grilla? Fuera de alcance salvo que se pida.
