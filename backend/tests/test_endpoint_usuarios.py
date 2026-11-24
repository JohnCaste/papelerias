"""
Tests de usuarios/vistas.py -- vistas de Flask con los repositorios y el
pipeline de imagen falseados. No pasan por JWT/CORS (eso es main.py).
"""

import io
import json

import pytest
from flask import Flask
from PIL import Image

import usuarios.vistas as vista


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    return app


def _png_en_memoria(tamano=(40, 40), color=(10, 120, 200)):
    buf = io.BytesIO()
    Image.new("RGB", tamano, color).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------- listar

def test_listar_usuarios_no_expone_la_contrasena(app, monkeypatch):
    consultado = {}

    def falso_ejecutar_query(sql, *a, **k):
        consultado["sql"] = sql
        return [{"id": "u1", "nombre": "Ana"}, {"id": "u2", "nombre": "Beto"}]

    monkeypatch.setattr(vista, "ejecutar_query", falso_ejecutar_query)
    monkeypatch.setattr(vista.fotos_repo, "listar", lambda: {"u1": "https://cdn/ana.webp"})
    monkeypatch.setattr(vista.roles_repo, "listar", lambda: {"u1": "dueno"})

    with app.test_request_context("/api/usuarios"):
        cuerpo = json.loads(vista.listar_usuarios().get_data(as_text=True))

    assert "password" not in consultado["sql"].lower()
    assert cuerpo == [
        {"id": "u1", "nombre": "Ana", "foto_url": "https://cdn/ana.webp", "rol": "dueno"},
        # sin fila en usuario_rol -> 'empleado' por defecto
        {"id": "u2", "nombre": "Beto", "foto_url": None, "rol": "empleado"},
    ]


# --------------------------------------------------------------- cambiar rol

def _ctx_rol(app, usuario_id, body):
    return app.test_request_context(
        f"/api/usuarios/{usuario_id}/rol", method="POST", json=body
    )


def test_cambiar_rol_lo_hace_un_dueno(app, monkeypatch):
    guardado = {}
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "jefe")
    monkeypatch.setattr(
        vista.roles_repo, "obtener", lambda uid: "dueno" if uid == "jefe" else None
    )
    monkeypatch.setattr(
        vista.roles_repo,
        "guardar",
        lambda uid, rol: guardado.update(uid=uid, rol=rol) or rol,
    )

    with _ctx_rol(app, "u2", {"rol": "dueno"}):
        cuerpo = json.loads(vista.cambiar_rol("u2").get_data(as_text=True))

    assert cuerpo == {"id": "u2", "rol": "dueno"}
    assert guardado == {"uid": "u2", "rol": "dueno"}


def test_cambiar_rol_lo_rechaza_a_un_empleado(app, monkeypatch):
    llamado = []
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "raso")
    monkeypatch.setattr(vista.roles_repo, "obtener", lambda uid: "empleado")
    monkeypatch.setattr(vista.roles_repo, "guardar", lambda *a: llamado.append(a))

    with _ctx_rol(app, "u2", {"rol": "dueno"}):
        body, status = vista.cambiar_rol("u2")

    assert status == 403
    assert llamado == []


def test_cambiar_rol_valida_el_valor(app, monkeypatch):
    llamado = []
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "jefe")
    monkeypatch.setattr(vista.roles_repo, "obtener", lambda uid: "dueno")
    monkeypatch.setattr(vista.roles_repo, "guardar", lambda *a: llamado.append(a))

    with _ctx_rol(app, "u2", {"rol": "superadmin"}):
        body, status = vista.cambiar_rol("u2")

    assert status == 400
    assert llamado == []


# ----------------------------------------------------------- subir foto

def test_subir_foto_guarda_para_el_usuario_logueado(app, monkeypatch):
    guardado = {}
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    monkeypatch.setattr(vista.imagenes, "subir_a_gcs", lambda datos: "https://cdn/x.webp")
    monkeypatch.setattr(
        vista.fotos_repo,
        "guardar",
        lambda usuario_id, url: guardado.update(usuario_id=usuario_id, url=url) or url,
    )

    data = {"archivo": (io.BytesIO(_png_en_memoria()), "yo.png")}
    with app.test_request_context(
        "/api/usuarios/foto", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        cuerpo = json.loads(vista.subir_foto_perfil().get_data(as_text=True))

    assert cuerpo == {"foto_url": "https://cdn/x.webp"}
    assert guardado == {"usuario_id": "u1", "url": "https://cdn/x.webp"}


def test_subir_foto_sin_archivo_da_400(app, monkeypatch):
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    with app.test_request_context("/api/usuarios/foto", method="POST"):
        body, status = vista.subir_foto_perfil()
    assert status == 400


def test_subir_foto_archivo_no_imagen_da_400(app, monkeypatch):
    monkeypatch.setattr(vista, "get_jwt_identity", lambda: "u1")
    llamado = []
    monkeypatch.setattr(vista.fotos_repo, "guardar", lambda *a: llamado.append(a))

    data = {"archivo": (io.BytesIO(b"no soy imagen"), "x.pdf")}
    with app.test_request_context(
        "/api/usuarios/foto", method="POST", data=data,
        content_type="multipart/form-data",
    ):
        body, status = vista.subir_foto_perfil()

    assert status == 400
    assert llamado == []  # no se guarda nada si la imagen es invalida


def test_listar_usuarios_filtra_por_la_papeleria_de_la_sucursal(app, monkeypatch):
    capturado = {}

    def falso_ejecutar_query(sql, parametros=None, *a, **k):
        capturado["sql"] = sql
        capturado["parametros"] = parametros
        return []

    monkeypatch.setattr(vista, "ejecutar_query", falso_ejecutar_query)
    monkeypatch.setattr(vista, "PAPELERIA", "lapape_sucursal2")
    monkeypatch.setattr(vista.fotos_repo, "listar", lambda: {})
    monkeypatch.setattr(vista.roles_repo, "listar", lambda: {})

    with app.test_request_context("/api/usuarios"):
        vista.listar_usuarios()

    assert "papeleria = @papeleria" in capturado["sql"]
    assert capturado["parametros"] == {"papeleria": "lapape_sucursal2"}
