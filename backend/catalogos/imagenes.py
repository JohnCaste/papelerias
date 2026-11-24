"""
Pipeline de imagen de producto: convierte cualquier imagen recibida a
`.webp`, la redimensiona a un maximo acotado, la comprime y la sube a un
bucket de Google Cloud Storage. `producto.imagen` guarda la URL publica
resultante (sigue siendo un STRING en el esquema; ver esquema/tablas.py).

Requiere Pillow y google-cloud-storage (ver requirements.txt). Reusa la
credencial de la cuenta de servicio de backend/.env
(autentificacion/serviciosCloud.py) -- la misma que ya se usa para
BigQuery -- ampliando su rol a storage.objectAdmin sobre el bucket.
"""

import io
import os
import uuid

from PIL import Image, ImageOps

import autentificacion.serviciosCloud as serviciosCloud

_VARIABLE_BUCKET = "BUCKET_IMAGENES_PRODUCTO"

MAX_LADO = 1024          # lado mayor de la imagen final, en px (no amplia)
WEBP_QUALITY = 80        # calidad WebP: reduce peso conservando calidad visual
MAX_SUBIDA_MB = 10       # tope de tamano del archivo entrante

# Formatos de entrada aceptados. HEIC/HEIF es best-effort: solo si
# pillow-heif esta instalado y registrado.
_FORMATOS_VALIDOS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"}
try:  # pragma: no cover - depende del entorno
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _FORMATOS_VALIDOS.update({"HEIF", "HEIC"})
except Exception:  # pragma: no cover
    pass

_cliente_storage = None


class BucketNoConfigurado(RuntimeError):
    """No esta definida la variable de entorno del bucket de imagenes."""


def procesar_a_webp(datos: bytes, max_lado: int = MAX_LADO, calidad: int = WEBP_QUALITY) -> bytes:
    """Bytes de imagen -> bytes de un unico `.webp` optimizado.

    - Aplica la orientacion EXIF antes de redimensionar.
    - Reduce para que el lado mayor sea <= max_lado (no amplia).
    - Descarta EXIF en la salida.
    Lanza ValueError si `datos` no es una imagen que Pillow pueda abrir.
    """
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except Exception as error:  # noqa: BLE001 - se re-lanza como ValueError
        raise ValueError("El archivo no es una imagen valida") from error

    if imagen.format and imagen.format.upper() not in _FORMATOS_VALIDOS:
        raise ValueError(f"Formato de imagen no soportado: {imagen.format}")

    imagen = ImageOps.exif_transpose(imagen)
    imagen.thumbnail((max_lado, max_lado))  # in-place, mantiene proporcion, no amplia

    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGB")

    salida = io.BytesIO()
    imagen.save(salida, format="WEBP", quality=calidad, method=6)
    return salida.getvalue()


def _obtener_bucket():
    global _cliente_storage
    nombre = os.environ.get(_VARIABLE_BUCKET)
    if not nombre:
        raise BucketNoConfigurado(
            f"Falta configurar {_VARIABLE_BUCKET} en el entorno o en "
            "backend/.env (nombre del bucket de GCS para imagenes de "
            "producto). Ver backend/.env.example."
        )
    if _cliente_storage is None:
        from google.cloud import storage

        _cliente_storage = storage.Client(
            credentials=serviciosCloud.get_credentials(),
            project=serviciosCloud.get_project_id(),
        )
    return _cliente_storage.bucket(nombre)


def subir_a_gcs(datos_webp: bytes) -> str:
    """Sube el `.webp` con un nombre unico y devuelve su URL publica."""
    bucket = _obtener_bucket()
    blob = bucket.blob(f"{uuid.uuid4()}.webp")
    blob.upload_from_string(datos_webp, content_type="image/webp")
    return blob.public_url


def resetear_cliente():
    """Solo para tests: fuerza reconstruir el cliente de Storage."""
    global _cliente_storage
    _cliente_storage = None
