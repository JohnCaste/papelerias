"""
Vistas HTTP de compras de trabajadores. Solo traducen request/response; la
logica esta en compras/servicio.py y los datos en el journal local
(almacen_local/compras.py). El candado de acceso lo pone main.py con
compras.acceso.requiere_duena_lapape.

    GET    /api/compras                     -> estado completo de la pantalla
    POST   /api/compras                     -> alta (+ abono inicial opcional)
    PUT    /api/compras/<id>                -> edicion
    DELETE /api/compras/<id>                -> eliminacion
    GET    /api/compras/abonos              -> historial de abonos
    POST   /api/compras/<id>/abonos         -> nuevo abono
    DELETE /api/compras/abonos/<abono_id>   -> eliminar abono
"""

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

from compras import servicio
from compras.servicio import ErrorCompras


def _quien():
    return get_jwt_identity(), get_jwt().get("nombre")


def _datos() -> dict:
    datos = request.get_json(silent=True)
    return datos if isinstance(datos, dict) else {}


def _responder(funcion, status_ok=200):
    try:
        return jsonify(funcion()), status_ok
    except ErrorCompras as error:
        cuerpo = {"error": error.mensaje}
        if error.campo:
            cuerpo["campo"] = error.campo
        return jsonify(cuerpo), error.status


def listar():
    return _responder(servicio.estado)


def listar_abonos():
    return _responder(lambda: servicio.estado()["abonos"])


def crear():
    usuario_id, nombre = _quien()
    return _responder(lambda: servicio.crear_compra(_datos(), usuario_id, nombre), 201)


def editar(compra_id: str):
    usuario_id, nombre = _quien()
    return _responder(lambda: servicio.editar_compra(compra_id, _datos(), usuario_id, nombre))


def eliminar(compra_id: str):
    usuario_id, nombre = _quien()
    return _responder(lambda: servicio.eliminar_compra(compra_id, usuario_id, nombre))


def abonar(compra_id: str):
    usuario_id, nombre = _quien()
    return _responder(lambda: servicio.abonar(compra_id, _datos(), usuario_id, nombre), 201)


def eliminar_abono(abono_id: str):
    usuario_id, nombre = _quien()
    return _responder(lambda: servicio.eliminar_abono(abono_id, usuario_id, nombre))
