## Why

La papelería tiene una pistola lectora de código de barras USB, pero hoy el
catálogo solo se puede consultar escribiendo el nombre a mano. La pistola se
comporta como un teclado (teclea los dígitos muy rápido y cierra con Enter), así
que basta con leerla desde el frontend y resolver el código contra el catálogo
para que el operario encuentre un producto sin escribir. El esquema ya tiene la
columna `producto.codigo_barras` y el repositorio ya expone
`obtener_por_codigo_barras`, pero nada del flujo de catálogo la usa todavía.

## What Changes

- La búsqueda del catálogo (`GET /api/catalogo/buscar`) resuelve el término `q`
  también contra `codigo_barras` por coincidencia **exacta**, además de la
  búsqueda por nombre actual (insensible a mayúsculas/acentos). Un `q` que
  coincide con un código de barras devuelve ese producto aunque no coincida con
  ningún nombre.
- Nuevo hook de frontend `useScannerGun`: escucha `keydown` a nivel documento,
  detecta la ráfaga característica de la pistola (varias teclas en pocos
  milisegundos que terminan en Enter) y entrega el código leído a un callback.
  Ignora la escritura humana normal y no interfiere cuando el foco está en un
  campo de texto que no sea el buscador.
- La página de Catálogo usa ese hook: al recibir una lectura, coloca el código
  en el término de búsqueda existente y deja que la grilla y la paginación
  actuales muestren el resultado. Sin pantallas ni componentes nuevos.
- Los formularios de alta y edición de producto incorporan un campo
  **Código de barras** (opcional), para que los productos escaneables tengan el
  código cargado. El backend valida que el código no se repita entre productos
  activos (ya documentado como invariante del esquema, hoy sin implementar).

## Capabilities

### New Capabilities

- `escaneo-de-catalogo`: lectura de la pistola de código de barras en la página
  de Catálogo — detección de la ráfaga de teclado vía `useScannerGun` y
  resolución del código contra la búsqueda del catálogo para mostrar el
  producto. No cubre el punto de venta.

### Modified Capabilities

- `busqueda-de-catalogo`: el término `q` de `GET /api/catalogo/buscar` pasa a
  coincidir también con `codigo_barras` exacto, no solo con el nombre.
- `formulario-de-producto`: los formularios de alta y edición añaden el campo
  opcional `codigo_barras`, y el backend rechaza (`400`) un código duplicado
  entre productos activos.

## Impact

- Backend:
  - `backend/acceso_datos/repositorios/productos.py` — `_condiciones_busqueda`
    (rama nueva para `codigo_barras`); helper para detectar código duplicado.
  - `backend/catalogos/productos.py` — `agregar_productos` y
    `actualizar_productos` validan unicidad de `codigo_barras`.
  - `backend/tests/` — `test_repositorio_productos.py`,
    `test_endpoint_*catalogo*` (búsqueda por código, alta/edición con código
    duplicado).
- Frontend:
  - `frontend/src/hooks/useScannerGun.ts` — nuevo.
  - `frontend/src/pages/Catalogo.tsx` — cablea el hook al término de búsqueda.
  - `frontend/src/components/AgregarProModal.tsx` y `ActualizarProModal.tsx` —
    campo Código de barras.
  - `frontend/src/services/catalogo.ts` — sin cambios de firma (los modales ya
    envían un objeto libre); se documenta el campo.
- Datos: ninguno. La columna `producto.codigo_barras` ya existe en `esquema/tablas.py`.
- Sin cambios en punto de venta, dashboard, cierres ni agregaciones.
