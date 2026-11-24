"""
Logica de la lista de faltantes sobre el journal local
(almacen_local/faltantes.py). Validaciones y permisos viven aqui; las vistas
solo traducen HTTP.

Reglas (spec lista-de-faltantes):
  - Cualquier usuario con sesion agrega y edita cantidad/nota.
  - Solo `dueno` cambia el estado (pendiente <-> comprado).
  - Elimina `dueno` o quien lo registro.
  - Un producto del catalogo no puede estar dos veces en pendientes (409).

Cada escritura valida y escribe bajo el lock del journal, para que la
revision de duplicados/existencia y la escritura sean atomicas.
"""

import datetime
import uuid
from decimal import Decimal, InvalidOperation

from almacen_local import faltantes as journal_faltantes

ROL_DUENO = "dueno"
PENDIENTE = "pendiente"
COMPRADO = "comprado"
ESTADOS = (PENDIENTE, COMPRADO)

MAX_NOMBRE = 120
MAX_NOTA = 200
MAX_CANTIDAD = 100000
DIAS_COMPRADOS = 30


class ErrorFaltantes(Exception):
    """Error de negocio con el status HTTP que le corresponde."""

    def __init__(self, mensaje: str, status: int = 400, campo: str | None = None, extra: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.campo = campo
        self.extra = extra or {}


# ------------------------------------------------------------ validaciones

def _normalizar(texto: str) -> str:
    return " ".join(str(texto).split())


def _nombre(datos: dict) -> str:
    valor = datos.get("nombre")
    if not isinstance(valor, str) or not _normalizar(valor):
        raise ErrorFaltantes("El nombre es obligatorio", campo="nombre")
    valor = _normalizar(valor)
    if len(valor) > MAX_NOMBRE:
        raise ErrorFaltantes(f"El nombre admite como maximo {MAX_NOMBRE} caracteres", campo="nombre")
    return valor


def _cantidad(datos: dict):
    valor = datos.get("cantidad")
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ErrorFaltantes("La cantidad debe ser un numero entero", campo="cantidad")
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        numero = None
    if numero is None or not numero.is_finite() or numero != numero.to_integral_value():
        raise ErrorFaltantes("La cantidad debe ser un numero entero", campo="cantidad")
    numero = int(numero)
    if numero < 1 or numero > MAX_CANTIDAD:
        raise ErrorFaltantes("La cantidad debe ser al menos 1", campo="cantidad")
    return numero


def _nota(datos: dict):
    valor = datos.get("nota")
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ErrorFaltantes("La nota debe ser texto", campo="nota")
    valor = _normalizar(valor)
    if len(valor) > MAX_NOTA:
        raise ErrorFaltantes(f"La nota admite como maximo {MAX_NOTA} caracteres", campo="nota")
    return valor or None


def _producto_id(datos: dict):
    valor = datos.get("producto_id")
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str):
        raise ErrorFaltantes("producto_id no es valido", campo="producto_id")
    return valor.strip() or None


# ------------------------------------------------------------ lectura

def _vigentes(carpeta=None) -> dict:
    return {f["faltante_id"]: f for f in journal_faltantes.faltantes_vigentes(carpeta)}


def _json(f: dict) -> dict:
    return {campo: f.get(campo) for campo in (
        "faltante_id", "producto_id", "nombre", "cantidad", "nota", "estado",
        "usuario_id", "registrado_por", "creado_en", "comprado_por", "comprado_en",
    )}


def estado(carpeta=None, ahora=None) -> dict:
    """Todo lo que muestra la pantalla, leido del journal local."""
    eventos = journal_faltantes.leer_eventos(carpeta)
    vigentes = journal_faltantes.faltantes_vigentes(eventos=eventos)

    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    limite = (ahora - datetime.timedelta(days=DIAS_COMPRADOS)).isoformat()

    pendientes = sorted(
        (f for f in vigentes if f["estado"] == PENDIENTE), key=lambda f: f["creado_en"]
    )
    comprados = sorted(
        (f for f in vigentes if f["estado"] == COMPRADO and (f.get("comprado_en") or "") >= limite),
        key=lambda f: f.get("comprado_en") or "",
        reverse=True,
    )
    return {
        "pendientes": [_json(f) for f in pendientes],
        "comprados": [_json(f) for f in comprados],
        "pendientes_de_subir": len(journal_faltantes.leer_pendientes(eventos=eventos)),
    }


# ------------------------------------------------------------ escritura

def _buscar(vigentes: dict, faltante_id: str) -> dict:
    actual = vigentes.get(faltante_id)
    if actual is None:
        raise ErrorFaltantes("El faltante no existe o fue eliminado", status=404)
    return actual


def _nueva_version(actual: dict, cambios: dict, modificado_por, carpeta) -> dict:
    datos = {campo: actual.get(campo) for campo in journal_faltantes.CAMPOS_FALTANTE}
    datos.update(cambios)
    datos["modificado_por"] = modificado_por
    return journal_faltantes.escribir_faltante(datos, carpeta)


def crear(datos: dict, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    nombre = _nombre(datos)
    cantidad = _cantidad(datos)
    nota = _nota(datos)
    producto_id = _producto_id(datos)

    with journal_faltantes.lock:
        if producto_id:
            repetido = next(
                (f for f in _vigentes(carpeta).values()
                 if f["estado"] == PENDIENTE and f.get("producto_id") == producto_id),
                None,
            )
            if repetido:
                raise ErrorFaltantes(
                    f"«{repetido['nombre']}» ya esta en la lista de pendientes",
                    status=409,
                    extra={"faltante_id": repetido["faltante_id"]},
                )
        fila = journal_faltantes.escribir_faltante(
            {
                "faltante_id": str(uuid.uuid4()),
                "producto_id": producto_id,
                "nombre": nombre,
                "cantidad": cantidad,
                "nota": nota,
                "estado": PENDIENTE,
                "usuario_id": usuario_id,
                "registrado_por": registrado_por,
                "creado_en": journal_faltantes.ahora(),
                "modificado_por": registrado_por,
            },
            carpeta,
        )
        return _json(fila)


def editar(faltante_id: str, datos: dict, usuario_id: str, registrado_por=None, carpeta=None) -> dict:
    cambios = {}
    if "cantidad" in datos:
        cambios["cantidad"] = _cantidad(datos)
    if "nota" in datos:
        cambios["nota"] = _nota(datos)
    with journal_faltantes.lock:
        actual = _buscar(_vigentes(carpeta), faltante_id)
        return _json(_nueva_version(actual, cambios, registrado_por, carpeta))


def cambiar_estado(faltante_id: str, nuevo: str, rol: str, registrado_por=None, carpeta=None) -> dict:
    if rol != ROL_DUENO:
        raise ErrorFaltantes("Solo la duena puede marcar faltantes como comprados", status=403)
    if nuevo not in ESTADOS:
        raise ErrorFaltantes("El estado debe ser 'pendiente' o 'comprado'", campo="estado")
    with journal_faltantes.lock:
        actual = _buscar(_vigentes(carpeta), faltante_id)
        if nuevo == COMPRADO:
            cambios = {"estado": COMPRADO, "comprado_por": registrado_por,
                       "comprado_en": journal_faltantes.ahora()}
        else:
            cambios = {"estado": PENDIENTE, "comprado_por": None, "comprado_en": None}
        return _json(_nueva_version(actual, cambios, registrado_por, carpeta))


def eliminar(faltante_id: str, usuario_id: str, rol: str, registrado_por=None, carpeta=None) -> dict:
    with journal_faltantes.lock:
        actual = _buscar(_vigentes(carpeta), faltante_id)
        if rol != ROL_DUENO and actual.get("usuario_id") != usuario_id:
            raise ErrorFaltantes("Solo quien lo anoto o la duena pueden eliminarlo", status=403)
        _nueva_version(actual, {"eliminado": True}, registrado_por, carpeta)
        return {"faltante_id": faltante_id, "eliminado": True}
