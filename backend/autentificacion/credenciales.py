"""
Login. Reescrito por #3/#4.

Sigue leyendo la tabla LEGADA `nuevas_tablas.login` (no `usuario` del
esquema nuevo en esquema/tablas.py) -- mismo motivo que en
registros/valores.py (#11): es donde viven las credenciales reales hoy.
El dataset `lapape` ya existe y su catalogo ya se migro (#9), pero los
usuarios todavia no. Cuando se migren a `lapape.usuario`, este archivo
pasa a usar acceso_datos.repositorios.usuarios en vez de la query
directa de abajo -- igual que se hizo con el catalogo (#9); falta el
equivalente para usuarios y para las ventas historicas (#10), y no
existe todavia un issue para el de usuarios.

Cambios de esta pasada:
  - La consulta ya NO interpola nombre ni password en el SQL. La fila se
    busca solo por nombre (parametrizado); la contraseña se verifica en
    Python con bcrypt, nunca dentro de la query -- asi una cadena de
    inyeccion en 'nombre' simplemente no encuentra ninguna fila, en vez
    de alterar el WHERE.
  - Las contraseñas en texto plano (como estan guardadas hoy) ya no se
    comparan como si fueran seguras. Se detectan por NO tener el
    prefijo de un hash de bcrypt y, si coinciden, se re-hashean en ese
    mismo login (ver `_verificar_password`). Esto evita que el sistema
    se quede sin que nadie pueda entrar mientras el script de rehasheo
    (`rehashear_passwords.py`) no se haya corrido contra el proyecto
    real -- que sigue pendiente (#3).

Pendiente, fuera de esta pasada: "forzar cambio de password en el
primer login" (tarea de #3) requiere una columna nueva en una tabla que
no he inspeccionado en vivo y un endpoint de cambio de password que no
existe en el backend todavia. No se adivino el esquema real de
`login` para no arriesgar un ALTER TABLE a ciegas -- ver el hilo de #3.
"""

import bcrypt
from flask import Response, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
)

from acceso_datos.consultas import ejecutar_query, ejecutar_uno
from acceso_datos.repositorios import usuario_roles
from esquema.tablas import DATASET
from utilidades import sucursal

TABLA_LOGIN_LEGADO = "nuevas_tablas.login"  # ver docstring del modulo

# La tabla legada es compartida por todas las sucursales: cada una solo ve
# sus filas, por la columna `papeleria` ("1" = tienda original). Ver
# utilidades/sucursal.py::papeleria_login.
PAPELERIA = sucursal.papeleria_login(DATASET)

_PREFIJOS_BCRYPT = ("$2a$", "$2b$", "$2y$")


def crear_token():
    datos = request.get_json(silent=True) or {}
    nombre = datos.get("nombre")
    password = datos.get("password")
    if not nombre or not password:
        return jsonify(error="Faltan 'nombre' o 'password'"), 400

    sql = (
        f"SELECT * FROM `{TABLA_LOGIN_LEGADO}` "
        "WHERE nombre = @nombre AND papeleria = @papeleria LIMIT 1"
    )
    usuario = ejecutar_uno(sql, {"nombre": nombre, "papeleria": PAPELERIA})

    if usuario is None or not _verificar_password(password, usuario):
        return Response(response="Unauthorized", status=401)

    # 'nombre' viaja como claim para que la captura de venta (#20) anote
    # "quien vendio" sin consultar BigQuery (el POS trabaja offline).
    # 'rol' viaja para que el frontend muestre/oculte Ventas y Corte.
    rol = usuario_roles.obtener(usuario["id"]) or usuario_roles.ROL_EMPLEADO
    claims = {"nombre": usuario.get("nombre"), "rol": rol}
    access_token = create_access_token(identity=usuario["id"], additional_claims=claims)
    refresh_token = create_refresh_token(identity=usuario["id"], additional_claims=claims)
    return jsonify(
        token=access_token,
        user_id=usuario["id"],
        nombre=usuario.get("nombre"),
        rol=rol,
        refresh_token=refresh_token,
    )


def refresh():
    identity = get_jwt_identity()
    # Conserva los claims 'nombre' y 'rol' del refresh token al emitir el
    # nuevo access token.
    claims_previos = get_jwt()
    access_token = create_access_token(
        identity=identity,
        additional_claims={
            "nombre": claims_previos.get("nombre"),
            "rol": claims_previos.get("rol"),
        },
    )
    return jsonify(token=access_token)


def es_hash_bcrypt(valor) -> bool:
    return isinstance(valor, str) and valor.startswith(_PREFIJOS_BCRYPT)


def _verificar_password(password_recibido: str, usuario: dict) -> bool:
    password_guardado = usuario.get("password")
    if password_guardado is None:
        return False

    if es_hash_bcrypt(password_guardado):
        return bcrypt.checkpw(
            password_recibido.encode("utf-8"), password_guardado.encode("utf-8")
        )

    # Contraseña todavia en texto plano -- transicion mientras corre
    # rehashear_passwords.py. Se compara tal cual y, si coincide, se
    # re-hashea de una vez: no depende de que alguien se acuerde de
    # correr el script para que el sistema deje de aceptar texto plano.
    if password_recibido != password_guardado:
        return False

    _rehashear_en_login(usuario["id"], password_recibido)
    return True


def _rehashear_en_login(usuario_id: str, password_texto_plano: str):
    nuevo_hash = bcrypt.hashpw(
        password_texto_plano.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    sql = f"UPDATE `{TABLA_LOGIN_LEGADO}` SET password = @password WHERE id = @id"
    ejecutar_query(sql, {"password": nuevo_hash, "id": usuario_id})
