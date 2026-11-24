"""
Control de rol en el backend a partir del claim `rol` del JWT.

El rol se lee del token y NO de usuario_roles.obtener(): esa consulta va a
BigQuery y fallaria sin internet (misma razon que compras/acceso.py).
Costo: un cambio de rol aplica al renovar el token.

Uso (despues de @jwt_required(), que ya valida el token):

    @app.route(...)
    @jwt_required()
    @requiere_dueno
    def vista(): ...
"""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt

ROL_DUENO = "dueno"


def requiere_dueno(vista):
    @wraps(vista)
    def envuelta(*args, **kwargs):
        if get_jwt().get("rol") != ROL_DUENO:
            return jsonify(error="Solo la duena puede hacer esta accion"), 403
        return vista(*args, **kwargs)

    return envuelta
