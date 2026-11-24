# carga-de-imagenes-de-producto Specification

## Purpose

Subida de la imagen de un producto desde la cámara o desde un archivo. El
backend convierte toda imagen recibida a `.webp`, la redimensiona (lado mayor
≤ 1024 px, sin ampliar), la comprime y la sube a un bucket de Google Cloud
Storage; `producto.imagen` guarda la URL pública resultante. El formulario
muestra el campo de imagen al final y previsualiza el `.webp` antes de guardar.

## Requirements

### Requirement: Subida de imagen de producto por cámara o archivo

El sistema SHALL exponer `POST /api/catalogo/imagen` que reciba una imagen
—capturada con la cámara o subida desde el dispositivo— como `multipart/form-data`
y devuelva la URL pública de la imagen ya procesada.

- El endpoint SHALL aceptar los tipos de entrada comunes de imagen
  (JPEG, PNG, WebP, HEIC si el entorno lo soporta).
- El endpoint SHALL rechazar con 400 los archivos que no sean imágenes válidas
  o que superen el tamaño máximo de subida configurado.
- La respuesta exitosa SHALL tener la forma `{ "url": "<url pública .webp>" }`.
- El endpoint SHALL requerir autenticación de administrador, igual que el resto
  de escrituras de catálogo.

#### Scenario: Subida de una foto tomada con la cámara

- **WHEN** el administrador toma una foto en el formulario de producto y se envía a `POST /api/catalogo/imagen`
- **THEN** la respuesta es 200 con `{ "url": "https://.../<id>.webp" }`
- **AND** la URL apunta a un objeto existente en el bucket de imágenes de producto

#### Scenario: Archivo que no es imagen

- **WHEN** se envía un PDF a `POST /api/catalogo/imagen`
- **THEN** la respuesta es 400 con un mensaje que indica que el archivo no es una imagen válida

### Requirement: Conversión, redimensionado y optimización a WebP

Antes de almacenarla, el sistema SHALL transformar toda imagen recibida a
formato `.webp`, redimensionarla para que su lado mayor no exceda un máximo
configurado (por defecto 1024 px, sin ampliar imágenes más pequeñas) y
comprimirla con una calidad que reduzca el peso conservando una calidad visual
aceptable.

- La orientación EXIF SHALL aplicarse antes de redimensionar.
- Los metadatos EXIF SHALL descartarse en la imagen final.
- El resultado SHALL ser un único archivo `.webp`.

#### Scenario: Imagen grande se reduce

- **WHEN** se sube una foto de 4000×3000 px y 5 MB
- **THEN** la imagen almacenada es `.webp`, con lado mayor de 1024 px
- **AND** su peso es sensiblemente menor al original

#### Scenario: Imagen pequeña no se amplía

- **WHEN** se sube una imagen de 300×300 px
- **THEN** la imagen almacenada mantiene 300×300 px y se guarda como `.webp`

#### Scenario: Foto de teléfono con rotación EXIF

- **WHEN** se sube una foto tomada en vertical con rotación EXIF
- **THEN** la imagen almacenada se ve en la orientación correcta sin depender de EXIF

### Requirement: Almacenamiento en Google Cloud Storage

El sistema SHALL subir la imagen `.webp` resultante a un bucket de Google Cloud
Storage dedicado a imágenes de producto y SHALL guardar en `producto.imagen`
la URL pública de ese objeto.

- El nombre del bucket SHALL leerse de una variable de entorno
  (p. ej. `BUCKET_IMAGENES_PRODUCTO`).
- El nombre del objeto SHALL ser único (p. ej. UUID + `.webp`) para no
  sobrescribir imágenes existentes.
- La escritura SHALL usar la cuenta de servicio ya configurada en `backend/.env`.
- Si falta la configuración del bucket, el endpoint SHALL responder 500 con un
  mensaje claro y no SHALL intentar guardar rutas locales.

#### Scenario: La URL devuelta se persiste en el producto

- **WHEN** se sube una imagen y luego se crea o edita un producto con esa `url`
- **THEN** `producto.imagen` contiene la URL pública del objeto en GCS
- **AND** la imagen es accesible públicamente desde esa URL

#### Scenario: Bucket no configurado

- **WHEN** la variable de entorno del bucket no está definida
- **AND** se llama `POST /api/catalogo/imagen`
- **THEN** la respuesta es 500 con un mensaje que indica que falta configurar el bucket

### Requirement: Previsualización de la imagen procesada en el formulario

El formulario de producto SHALL mostrar el campo de imagen al final, con dos
acciones ("Tomar foto" y "Subir foto"), y tras una subida exitosa SHALL mostrar
la imagen `.webp` devuelta como previsualización antes de guardar el producto.

#### Scenario: Previsualización tras subir

- **WHEN** el administrador sube una imagen y el endpoint responde con la URL
- **THEN** el formulario muestra esa imagen como previsualización
- **AND** al guardar el producto se envía esa URL en el campo `imagen`

#### Scenario: Reemplazar la imagen antes de guardar

- **WHEN** el administrador sube una imagen y luego sube otra distinta
- **THEN** la previsualización muestra la última imagen subida
- **AND** solo la última URL se envía al guardar
