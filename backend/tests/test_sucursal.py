"""
Tests de utilidades/sucursal.py -- dataset por sucursal, candado y
confirmacion de los scripts de esquema (segunda sucursal).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import main as modulo_main
from utilidades import sucursal

BACKEND = Path(__file__).resolve().parent.parent


# ------------------------------------------------------ resolver_dataset


def test_usa_bq_dataset_del_entorno(monkeypatch):
    monkeypatch.setenv("BQ_DATASET", "lapape_sucursal2")
    assert sucursal.resolver_dataset() == "lapape_sucursal2"


def test_bajo_pruebas_sin_variable_usa_lapape(monkeypatch):
    monkeypatch.delenv("BQ_DATASET", raising=False)
    assert sucursal.resolver_dataset() == "lapape"


def test_desarrollo_sin_variable_usa_lapape(monkeypatch):
    monkeypatch.delenv("BQ_DATASET", raising=False)
    monkeypatch.setenv("ENTORNO", "desarrollo")
    monkeypatch.setattr(sucursal, "bajo_pruebas", lambda: False)
    assert sucursal.resolver_dataset() == "lapape"


def test_produccion_sin_variable_no_arranca(monkeypatch):
    monkeypatch.delenv("BQ_DATASET", raising=False)
    monkeypatch.delenv("ENTORNO", raising=False)
    monkeypatch.setattr(sucursal, "bajo_pruebas", lambda: False)
    with pytest.raises(sucursal.ConfiguracionSucursalInvalida, match=r"BQ_DATASET.*backend\\\.env"):
        sucursal.resolver_dataset()


@pytest.mark.parametrize("valor", ["lapape.venta", "lapape;DROP", "con espacio", "tienda-2"])
def test_valor_invalido_se_rechaza(monkeypatch, valor):
    monkeypatch.setenv("BQ_DATASET", valor)
    with pytest.raises(sucursal.ConfiguracionSucursalInvalida, match="BQ_DATASET"):
        sucursal.resolver_dataset()


def test_tablas_toma_el_dataset_del_env_sin_importar_servicios_cloud(tmp_path):
    """
    En un proceso limpio, importar esquema.tablas SIN haber importado
    antes autentificacion.serviciosCloud debe ver BQ_DATASET del .env.
    Se apunta RUTA_ENV a un .env temporal parcheando dotenv antes de
    importar, para no depender del .env real de esta PC.
    """
    env = tmp_path / ".env"
    env.write_text("BQ_DATASET=lapape_desde_env\n", encoding="utf-8")
    codigo = (
        "import os, dotenv\n"
        "original = dotenv.load_dotenv\n"
        f"dotenv.load_dotenv = lambda *a, **k: original({str(env)!r})\n"
        "os.environ.pop('BQ_DATASET', None)\n"
        "import esquema.tablas as t\n"
        "import sys\n"
        "assert 'autentificacion.serviciosCloud' not in sys.modules\n"
        "print(t.DATASET)\n"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={"LAPAPE_ENTORNO_PRUEBAS": "1", "SYSTEMROOT": "C:\\Windows", "PATH": ""},
    )
    assert salida.returncode == 0, salida.stderr
    assert salida.stdout.strip() == "lapape_desde_env"


# ------------------------------------------------ papeleria / nombre


def test_papeleria_de_la_tienda_original_es_1():
    assert sucursal.papeleria_login("lapape") == "1"


def test_papeleria_de_otra_sucursal_es_su_dataset():
    assert sucursal.papeleria_login("lapape_sucursal2") == "lapape_sucursal2"


def test_nombre_configurado(monkeypatch):
    monkeypatch.setenv("SUCURSAL_NOMBRE", "Querétaro")
    assert sucursal.nombre_sucursal("lapape_queretaro") == "Querétaro"


def test_nombre_por_defecto(monkeypatch):
    monkeypatch.delenv("SUCURSAL_NOMBRE", raising=False)
    assert sucursal.nombre_sucursal("lapape") == "Principal"
    assert sucursal.nombre_sucursal("lapape_sucursal2") == "lapape_sucursal2"


# ------------------------------------------------------------- candado


def test_primer_arranque_registra_el_dataset(tmp_path):
    sucursal.verificar_candado("lapape_sucursal2", carpeta=tmp_path)
    datos = json.loads((tmp_path / "sucursal.json").read_text(encoding="utf-8"))
    assert datos["dataset"] == "lapape_sucursal2"


def test_mismo_dataset_arranca_normal(tmp_path):
    sucursal.verificar_candado("lapape", carpeta=tmp_path)
    sucursal.verificar_candado("lapape", carpeta=tmp_path)


def test_dataset_distinto_bloquea_el_arranque(tmp_path):
    sucursal.verificar_candado("lapape", carpeta=tmp_path)
    with pytest.raises(sucursal.ConfiguracionSucursalInvalida) as error:
        sucursal.verificar_candado("lapape_sucursal2", carpeta=tmp_path)
    assert "lapape" in str(error.value)
    assert "lapape_sucursal2" in str(error.value)


def test_crear_app_bajo_pruebas_no_toca_el_candado_real(tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(modulo_main.sucursal, "verificar_candado", lambda *a, **k: llamadas.append(a))
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    assert llamadas == []


def test_crear_app_fuera_de_pruebas_verifica_el_candado(tmp_path, monkeypatch):
    llamadas = []
    monkeypatch.setattr(modulo_main.sucursal, "verificar_candado", lambda *a, **k: llamadas.append(a))
    monkeypatch.setattr(modulo_main, "bajo_pruebas", lambda: False)
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    modulo_main.crear_app(carpeta_frontend=str(tmp_path))
    assert llamadas == [(modulo_main.DATASET,)]


def test_candado_distinto_impide_construir_la_app(tmp_path, monkeypatch):
    def candado_roto(dataset):
        raise sucursal.ConfiguracionSucursalInvalida("otra sucursal")

    monkeypatch.setattr(modulo_main.sucursal, "verificar_candado", candado_roto)
    monkeypatch.setattr(modulo_main, "bajo_pruebas", lambda: False)
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    with pytest.raises(sucursal.ConfiguracionSucursalInvalida):
        modulo_main.crear_app(carpeta_frontend=str(tmp_path))


# ---------------------------------------------------- /api/sucursal


def test_endpoint_sucursal_es_publico_y_devuelve_nombre(tmp_path, monkeypatch):
    monkeypatch.setenv("SUCURSAL_NOMBRE", "Querétaro")
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    cliente = modulo_main.crear_app(carpeta_frontend=str(tmp_path)).test_client()
    respuesta = cliente.get("/api/sucursal")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"nombre": "Querétaro", "dataset": modulo_main.DATASET}


# -------------------------------------------------- confirmar_destino


def test_confirmacion_rechazada(monkeypatch):
    assert sucursal.confirmar_destino("algo", entrada=lambda _: "n") is False
    assert sucursal.confirmar_destino("algo", entrada=lambda _: "") is False


def test_confirmacion_aceptada():
    assert sucursal.confirmar_destino("algo", entrada=lambda _: "s") is True


def test_modo_desatendido_no_pregunta():
    def no_deberia_preguntar(_):
        raise AssertionError("pregunto con --si")

    assert sucursal.confirmar_destino("algo", si=True, entrada=no_deberia_preguntar) is True


# ------------------------------------- los scripts de esquema importan


@pytest.mark.parametrize(
    "modulo",
    [
        "esquema.crear_dataset",
        "esquema.crear_usuario",
        "esquema.migrar_catalogo",
        "esquema.migrar_cuentas",
        "esquema.migrar_vendedor",
        "esquema.sembrar_categorias",
    ],
)
def test_script_de_esquema_se_puede_importar(modulo):
    """Los instaladores corren estos scripts con `python -m`: un import
    roto solo se descubria en la PC de la sucursal, a media instalacion."""
    import importlib

    importlib.import_module(modulo)
