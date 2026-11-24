"""
Endpoints de usuarios para la pestana Configuracion de Administracion.

    GET  /api/usuarios              -> lista (nombre + foto de perfil + rol)
    POST /api/usuarios/foto         -> sube/actualiza la foto del usuario LOGUEADO
    POST /api/usuarios/<id>/rol     -> cambia el rol de un usuario (solo 'dueno')

La contrasena NUNCA se expone: la lista solo trae id, nombre y rol. La
foto se guarda en `lapape.usuario_foto` y el rol en `lapape.usuario_rol`
(tablas aparte del legado, ver esquema/tablas.py); la imagen se procesa y
sube igual que la de producto (catalogos/imagenes.py: -> .webp -> GCS).

"Editar solo la foto del usuario logueado" no es una comprobacion de rol:
el endpoint no recibe a quien editar, siempre usa get_jwt_identity().
Cambiar rol SI la tiene: solo un 'dueno' puede reasignar roles, para que
nadie se promueva a si mismo.
"""

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

import acceso_datos.repositorios.usuario_fotos as fotos_repo
import acceso_datos.repositorios.usuario_roles as roles_repo
import catalogos.imagenes as imagenes
from acceso_datos.consultas import ejecutar_query
from autentificacion.credenciales import PAPELERIA, TABLA_LOGIN_LEGADO


def listar_usuarios():
    # Solo los de esta sucursal (ver credenciales.PAPELERIA).
    usuarios = ejecutar_query(
        f"SELECT id, nombre FROM `{TABLA_LOGIN_LEGADO}` "
        "WHERE papeleria = @papeleria ORDER BY nombre",
        {"papeleria": PAPELERIA},
    )
    fotos = fotos_repo.listar()
    roles = roles_repo.listar()
    return jsonify(
        [
            {
                "id": u["id"],
                "nombre": u["nombre"],
                "foto_url": fotos.get(u["id"]),
                "rol": roles.get(u["id"], roles_repo.ROL_EMPLEADO),
            }
            for u in usuarios
        ]
    )


def subir_foto_perfil():
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify(error="Falta el archivo de imagen ('archivo')"), 400

    datos = archivo.read()
    if len(datos) > imagenes.MAX_SUBIDA_MB * 1024 * 1024:
        return jsonify(
            error=f"La imagen supera el maximo de {imagenes.MAX_SUBIDA_MB} MB"
        ), 400

    try:
        webp = imagenes.procesar_a_webp(datos)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    try:
        url = imagenes.subir_a_gcs(webp)
    except imagenes.BucketNoConfigurado as error:
        return jsonify(error=str(error)), 500

    fotos_repo.guardar(get_jwt_identity(), url)
    return jsonify({"foto_url": url})


def cambiar_rol(usuario_id: str):
    if roles_repo.obtener(get_jwt_identity()) != roles_repo.ROL_DUENO:
        return jsonify(error="Solo un dueno puede cambiar roles"), 403

    datos = request.get_json(silent=True) or {}
    rol = datos.get("rol")
    if rol not in roles_repo.ROLES_VALIDOS:
        return jsonify(
            error=f"Rol invalido: {rol!r}. Usa {sorted(roles_repo.ROLES_VALIDOS)}"
        ), 400

    roles_repo.guardar(usuario_id, rol)
    return jsonify({"id": usuario_id, "rol": rol})
