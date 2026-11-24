# api_lapape

## Configuración (`backend/.env`)

Copia `backend/.env.example` a `backend/.env` y llena los valores. Ver
`autentificacion/serviciosCloud.py` para el detalle de las credenciales.

| Variable | Para qué |
| --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta a la llave `.json` de la cuenta de servicio de GCP (desarrollo local). Alternativa: `GCP_SERVICE_ACCOUNT_JSON` con el JSON completo en una línea. |
| `GCP_PROJECT_ID` | Opcional; si falta se toma del `project_id` de la llave. |
| `BUCKET_IMAGENES_PRODUCTO` | Nombre del bucket de Google Cloud Storage donde se guardan las imágenes de producto convertidas a `.webp` (ver `catalogos/imagenes.py`). |

### Bucket de imágenes de producto

1. Crear un bucket dedicado (p. ej. `lapape-imagenes-producto`).
2. Darle lectura pública para que las imágenes se muestren en el catálogo
   del navegador.
3. Conceder a la cuenta de servicio de `backend/.env` el rol
   `roles/storage.objectAdmin` **sobre ese bucket** (no sobre el proyecto).
4. Poner el nombre del bucket en `BUCKET_IMAGENES_PRODUCTO`.

`POST /api/catalogo/imagen` recibe la foto (cámara o archivo), la convierte
a `.webp`, la redimensiona (lado mayor ≤ 1024 px), la comprime y la sube al
bucket; devuelve `{ "url": "<url pública>" }` para guardarla en
`producto.imagen`.
