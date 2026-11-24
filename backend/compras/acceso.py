"""
Candado del apartado de compras de trabajadores: solo existe en la sucursal
original (dataset `lapape`) y solo lo usa la duena (rol `dueno`).

  - Otra sucursal  -> 404: para esa instalacion el apartado "no existe".
  - Rol != dueno   -> 403.

El rol sale del claim `rol` del JWT y NO de usuario_roles.obtener(): esa
consulta va a BigQuery y fallaria sin internet, y el apartado debe
funcionar sin conexion. Costo: un cambio de rol aplica al vencer el token.
"""

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt

from esquema import tablas
from utilidades import sucursal

ROL_DUENO = "dueno"


def disponible_en_esta_sucursal() -> bool:
    return tablas.DATASET == sucursal.DATASET_ORIGINAL


def requiere_duena_lapape(vista):
    @wraps(vista)
    def envuelta(*args, **kwargs):
        if not disponible_en_esta_sucursal():
            return jsonify(error="No encontrado"), 404
        if get_jwt().get("rol") != ROL_DUENO:
            return jsonify(error="Solo la duena puede ver las compras de trabajadores"), 403
        return vista(*args, **kwargs)

    return envuelta
