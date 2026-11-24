"""
Tests de autentificacion/credenciales.py. La parte que mas importa
verificar: una cadena de inyeccion en 'nombre' no debe autenticar a
nadie, y la contrasena nunca debe compararse dentro del SQL.
"""

import json

import bcrypt
import pytest
from flask import Flask

import autentificacion.credenciales as vista

HASH_DE_1234 = bcrypt.hashpw(b"1234", bcrypt.gensalt()).decode("utf-8")


@pytest.fixture
def app():
    app = Flask(__name__)
    app.testing = True
    app.config["JWT_SECRET_KEY"] = "clave-de-pruebas"
    from flask_jwt_extended import JWTManager

    JWTManager(app)
    return app


@pytest.fixture(autouse=True)
def _sin_rol(monkeypatch):
    """Por defecto el login no encuentra rol asignado (=> 'empleado').
    Un test que necesite otro rol sobreescribe `vista.usuario_roles.obtener`."""
    monkeypatch.setattr(vista.usuario_roles, "obtener", lambda usuario_id: None)


def test_sin_nombre_o_password_da_400(app):
    with app.test_request_context(
        "/api/autentificacion/login", method="POST", json={"nombre": "ana"}
    ):
        body, status = vista.crear_token()
    assert status == 400


def test_usuario_inexistente_da_401(app, monkeypatch):
    monkeypatch.setattr(vista, "ejecutar_uno", lambda sql, valores: None)

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "no-existe", "password": "x"},
    ):
        respuesta = vista.crear_token()

    assert respuesta.status_code == 401


def test_la_query_busca_solo_por_nombre_sin_password_en_el_where(app, monkeypatch):
    """
    El login viejo interpolaba nombre Y password en el WHERE. Ahora la
    consulta solo debe filtrar por nombre; la verificacion de password
    ocurre en Python.
    """
    capturado = {}

    def falso_ejecutar_uno(sql, valores):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return None

    monkeypatch.setattr(vista, "ejecutar_uno", falso_ejecutar_uno)

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "1234"},
    ):
        vista.crear_token()

    assert "password" not in capturado["sql"]
    assert capturado["valores"] == {"nombre": "ana", "papeleria": vista.PAPELERIA}


def test_el_login_solo_busca_usuarios_de_esta_sucursal(app, monkeypatch):
    """
    nuevas_tablas.login es compartida entre sucursales: un usuario de otra
    papeleria no debe poder entrar aunque su password sea correcta.
    """
    capturado = {}

    def falso_ejecutar_uno(sql, valores):
        capturado["sql"] = sql
        capturado["valores"] = valores
        return None

    monkeypatch.setattr(vista, "ejecutar_uno", falso_ejecutar_uno)
    monkeypatch.setattr(vista, "PAPELERIA", "lapape_sucursal2")

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "1234"},
    ):
        respuesta = vista.crear_token()

    assert "papeleria = @papeleria" in capturado["sql"]
    assert capturado["valores"]["papeleria"] == "lapape_sucursal2"
    assert respuesta.status_code == 401


def test_cadena_de_inyeccion_en_nombre_no_autentica(app, monkeypatch):
    """
    Antes: WHERE nombre = '' OR 1=1 --' AND password = '...' devolvia
    filas. Ahora el nombre va parametrizado -- se busca literal esa
    cadena como nombre de usuario, que no existe, y el repositorio
    (aqui, el fake) simplemente no encuentra nada.
    """
    inyeccion = "' OR 1=1 --"
    capturado = {}

    def falso_ejecutar_uno(sql, valores):
        capturado["valores"] = valores
        # simula una tabla real: nadie se llama literalmente eso
        return None

    monkeypatch.setattr(vista, "ejecutar_uno", falso_ejecutar_uno)

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": inyeccion, "password": "cualquiera"},
    ):
        respuesta = vista.crear_token()

    assert capturado["valores"]["nombre"] == inyeccion  # va tal cual, como dato
    assert respuesta.status_code == 401


def test_password_correcta_con_hash_bcrypt_autentica(app, monkeypatch):
    monkeypatch.setattr(
        vista,
        "ejecutar_uno",
        lambda sql, valores: {"id": "u1", "nombre": "ana", "password": HASH_DE_1234},
    )

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "1234"},
    ):
        respuesta = vista.crear_token()

    data = json.loads(respuesta.get_data(as_text=True))
    assert "token" in data
    assert data["user_id"] == "u1"
    # El nombre viaja en la respuesta y como claim del token, para que la
    # captura de venta pueda anotar "quien vendio" sin consultar BigQuery.
    assert data["nombre"] == "ana"
    # Sin fila en usuario_rol -> 'empleado' por defecto.
    assert data["rol"] == "empleado"


def test_password_incorrecta_con_hash_bcrypt_da_401(app, monkeypatch):
    monkeypatch.setattr(
        vista,
        "ejecutar_uno",
        lambda sql, valores: {"id": "u1", "nombre": "ana", "password": HASH_DE_1234},
    )

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "incorrecta"},
    ):
        respuesta = vista.crear_token()

    assert respuesta.status_code == 401


def test_password_en_texto_plano_correcta_autentica_y_rehashea(app, monkeypatch):
    monkeypatch.setattr(
        vista,
        "ejecutar_uno",
        lambda sql, valores: {"id": "u1", "nombre": "ana", "password": "1234"},
    )

    llamadas_update = []

    def falso_ejecutar_query(sql, valores=None):
        llamadas_update.append((sql, valores))

    monkeypatch.setattr(vista, "ejecutar_query", falso_ejecutar_query)

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "1234"},
    ):
        respuesta = vista.crear_token()

    data = json.loads(respuesta.get_data(as_text=True))
    assert "token" in data

    assert len(llamadas_update) == 1
    sql, valores = llamadas_update[0]
    assert "UPDATE" in sql
    assert valores["id"] == "u1"
    # lo guardado ahora es un hash de bcrypt, no el texto plano
    assert vista.es_hash_bcrypt(valores["password"])


def test_password_en_texto_plano_incorrecta_da_401_sin_rehashear(app, monkeypatch):
    monkeypatch.setattr(
        vista,
        "ejecutar_uno",
        lambda sql, valores: {"id": "u1", "nombre": "ana", "password": "1234"},
    )

    llamadas_update = []
    monkeypatch.setattr(
        vista, "ejecutar_query", lambda sql, valores=None: llamadas_update.append(1)
    )

    with app.test_request_context(
        "/api/autentificacion/login",
        method="POST",
        json={"nombre": "ana", "password": "no-es-esta"},
    ):
        respuesta = vista.crear_token()

    assert respuesta.status_code == 401
    assert llamadas_update == []


def test_usuario_sin_password_da_401():
    assert vista._verificar_password("x", {"password": None}) is False


def test_es_hash_bcrypt_reconoce_los_tres_prefijos():
    assert vista.es_hash_bcrypt("$2a$12$xxxx")
    assert vista.es_hash_bcrypt("$2b$12$xxxx")
    assert vista.es_hash_bcrypt("$2y$12$xxxx")
    assert not vista.es_hash_bcrypt("1234")
    assert not vista.es_hash_bcrypt(None)
