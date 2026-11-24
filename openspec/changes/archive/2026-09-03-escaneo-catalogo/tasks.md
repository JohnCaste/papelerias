## 1. Backend · búsqueda por código de barras

- [x] 1.1 En `backend/acceso_datos/repositorios/productos.py::_condiciones_busqueda`,
  cuando hay `termino`, la condición de nombre pasa a
  `(LOWER(NORMALIZE(nombre, NFD)) LIKE LOWER(NORMALIZE(@termino, NFD)) OR codigo_barras = @codigo_barras_exacto)`.
  Se mantiene `@termino` para el LIKE (no romper el test existente) y se agrega
  `valores["codigo_barras_exacto"] = termino`. Docstring actualizado.
- [x] 1.2 `contar` y `buscar` ya delegan en `_condiciones_busqueda` y desempacan
  `condiciones, valores, tipos`; el nuevo parámetro entra por `valores` en ambos,
  sin cambios extra. `total` coherente.
- [x] 1.3 Tests en `backend/tests/test_repositorio_productos.py`:
  `test_buscar_por_termino_tambien_matchea_codigo_de_barras_exacto` (el término
  entra como LIKE por nombre y como igualdad exacta por `codigo_barras`, sin `%`)
  y `test_contar_usa_las_mismas_condiciones_que_buscar`.

## 2. Backend · unicidad de codigo_barras en alta/edición

- [x] 2.1 `backend/catalogos/productos.py`: helper `_normalizar_codigo_barras(datos)`
  (recorta; `""`/espacios/no-str → `None`) y `_codigo_barras_en_conflicto(codigo,
  id_propio=None)` (usa `obtener_por_codigo_barras`, exime al propio producto).
- [x] 2.2 `agregar_productos`: normaliza y fija `datos["codigo_barras"]`; si no es
  `None` y está en conflicto → `400 {"error": "El codigo de barras ya esta en uso"}`
  sin llamar a `crear`.
- [x] 2.3 `actualizar_productos`: solo valida si el `PATCH` trae `codigo_barras`;
  normaliza, y si choca con OTRO producto → `400` antes de `actualizar`. Conservar
  el propio código es válido.
- [x] 2.4 Tests en `backend/tests/test_endpoint_productos.py`: alta con código
  nuevo OK, alta con `"   "` guarda `None`, alta duplicada → `400` sin crear,
  edición conservando el propio código → `200`, edición con código de otro → `400`
  sin `actualizar`.

## 3. Frontend · hook useScannerGun

- [x] 3.1 Creado `frontend/src/hooks/useScannerGun.ts` con
  `useScannerGun(alLeer, { umbralMs?, minLargo? })`.
- [x] 3.2 Listener único `keydown` en `document` dentro de `useEffect`; se
  remueve en el cleanup. Estado `{ buffer, ultimaTeclaMs }` local al efecto.
  `alLeer` en un ref para no re-suscribir por render.
- [x] 3.3 Función pura `acumularTecla(estado, char, ahoraMs, umbralMs)`: si
  `ahoraMs - ultimaTeclaMs > umbralMs` (def. 50) reinicia el buffer antes de
  agregar. Solo teclas `key.length === 1` y sin `ctrl/alt/meta`.
- [x] 3.4 Cierre con `Enter` **o** `Tab`: si `buffer.length >= minLargo` (def. 3)
  y la última tecla llegó dentro del umbral → `preventDefault()` + `alLeer(buffer)`;
  siempre reinicia después.
- [x] 3.5 `window.setTimeout(reiniciar, umbralMs * 2)` reprogramado en cada
  carácter y cancelado en el cleanup.
- [x] 3.6 `focoEnCampoEditableAjeno()`: ignora el evento si el foco está en
  `INPUT`/`TEXTAREA`/`contentEditable` que **no** lleve `data-scanner-passthrough`.
- [x] 3.7 (Sin infra de tests en el frontend.) La lógica de acumulación quedó en
  `acumularTecla`, función pura exportada; la cobertura real es la verificación de
  preview (6.3–6.6).

## 4. Frontend · Catálogo usa el hook

- [x] 4.1 `Catalogo.tsx`: `useScannerGun((codigo) => setQ(codigo))` junto al
  `useEffect` que sincroniza `q` con el prop `filtro`.
- [x] 4.2 `data-scanner-passthrough` añadido al `<input>` del buscador;
  placeholder actualizado a "Buscar por nombre o código de barras".
- [x] 4.3 El `useEffect` de filtros ya reinicia `offset` a 0; el botón de limpiar
  ya vacía `q`; el estado "sin resultados" ya muestra el término. Sin cambios.
  (Verificación visual pendiente en 6.3–6.4.)

## 5. Frontend · campo Código de barras en los formularios

- [x] 5.1 `AgregarProModal.tsx`: campo "Código de barras (opcional)" en
  `FORM_VACIO` y en el `<Form>`, tras Marca. Se envía dentro de `form` a
  `agregarProducto`; el backend normaliza `""` → `null`.
- [x] 5.2 `ActualizarProModal.tsx`: mismo campo, `codigo_barras` en `formData` y
  precargado con `producto.codigo_barras ?? ""`. Se envía en el `PATCH` vía el
  spread `{...producto, ...formData}`. Interface `Producto` amplía con
  `codigo_barras?: string | null`.
- [x] 5.3 El error `400` del backend ya se muestra: ambos modales renderizan
  `err.message`, y `_mensajeError` en el servicio extrae `{ error }`.
- [x] 5.4 `services/catalogo.ts`: comentario en `agregarProducto` y
  `actualizarProducto` describiendo la regla de `codigo_barras` (sin cambio de
  firma).

## 6. Verificación end-to-end

- [x] 6.1 `pytest` en `backend/` → 393 passed (incluye los tests nuevos de
  repositorio y endpoint).
- [x] 6.2 `npm run build` en verde (`tsc -b` + vite). `npm run lint`: sin
  problemas en los archivos tocados; los 5 errores restantes son preexistentes
  en `Dashboard.tsx`, ajenos a este cambio.
- [ ] 6.3 En preview (requiere frontend + backend + BigQuery): crear un producto
  con `codigo_barras`; en Catálogo simular la lectura y comprobar que la grilla
  queda con ese producto y la paginación en página 1. **Pendiente: hacerlo en la
  máquina con acceso a BigQuery para no insertar datos de prueba desde aquí.**
- [ ] 6.4 En preview: leer un código inexistente → estado "Sin resultados para …".
  **Pendiente (mismo motivo).**
- [ ] 6.5 En preview: intentar guardar dos productos con el mismo código → el
  segundo muestra el aviso de código en uso. **Pendiente (mismo motivo).**
- [ ] 6.6 Con la pistola real: confirmar el carácter de cierre (`Enter`/`Tab`) y,
  si hace falta, ajustar `umbralMs`; anotar el valor final en `design.md`.
  **Pendiente: necesita el hardware.**

## 7. Cierre

- [x] 7.1 `openspec validate escaneo-catalogo --changes` → en verde.
- [ ] 7.2 `openspec archive escaneo-catalogo` cuando la verificación de preview
  (6.3–6.6) esté hecha en la máquina de la papelería.
