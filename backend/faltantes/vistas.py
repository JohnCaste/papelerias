"""
Vistas HTTP de la lista de faltantes. Solo traducen request/response; la
logica esta en faltantes/servicio.py y los datos en el journal local
(almacen_local/faltantes.py). Cualquier usuario con sesion entra; los
permisos finos (comprado, eliminar) los aplica el servicio con el claim
`rol` del JWT (sin consultar BigQuery: funciona sin internet).

    GET    /api/faltantes               -> pendientes, comprados, por subir
    POST   /api/faltantes               -> alta
    PUT    /api/faltantes/<id>          -> cantidad / nota
    PUT    /api/faltantes/<id>/estado   -> pendiente | comprado (solo dueno)
    DELETE /api/faltantes/<id>          -> eliminar (dueno o quien lo anoto)
"""

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from faltantes import servicio
from faltantes.servicio import ErrorFaltantes


def _datos() -> dict:
    datos = request.get_json(silent=True)
    return datos if isinstance(datos, dict) else {}


def _responder(funcion, status_ok=200):
    try:
        return jsonify(funcion()), status_ok
    except ErrorFaltantes as error:
        cuerpo = {"error": error.mensaje, **error.extra}
        if error.campo:
            cuerpo["campo"] = error.campo
        return jsonify(cuerpo), error.status


def listar():
    return _responder(servicio.estado)


def crear():
    nombre = get_jwt().get("nombre")
    return _responder(lambda: servicio.crear(_datos(), get_jwt_identity(), nombre), 201)


def editar(faltante_id: str):
    nombre = get_jwt().get("nombre")
    return _responder(lambda: servicio.editar(faltante_id, _datos(), get_jwt_identity(), nombre))


def cambiar_estado(faltante_id: str):
    claims = get_jwt()
    return _responder(lambda: servicio.cambiar_estado(
        faltante_id, _datos().get("estado"), claims.get("rol"), claims.get("nombre")
    ))


def eliminar(faltante_id: str):
    claims = get_jwt()
    return _responder(lambda: servicio.eliminar(
        faltante_id, get_jwt_identity(), claims.get("rol"), claims.get("nombre")
    ))
