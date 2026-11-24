"""
Tests de autentificacion/serviciosCloud.py -- las credenciales de GCP
deben salir del entorno (#2), nunca de un valor hardcodeado. Ningun test
aqui toca el filesystem real ni una llave real.
"""

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

import autentificacion.serviciosCloud as servicios_cloud

# Llave RSA generada solo para este test (nunca se uso contra GCP, no
# esta ligada a ninguna cuenta real) -- google-auth valida el formato
# PEM al construir las credenciales, un string cualquiera no le basta.
_LLAVE_DE_PRUEBA = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCz94gy56LEtHsY\n"
    "zc/KM8HgHspX2eMFyICQjqdyLxmKBAFEBFDZ/ug7y8urD+hpj7uf/DZzRGDJSAvv\n"
    "Gw4j6yb8I14TrlFZfHvF9rjeankC+2YAR8dAWWoMVs6g1R44m5arot6klmAJD43Z\n"
    "DcCVbzmFnaByONltU4qDNf6rRYELnKa68n/uKV34DAJ/8ocKrIyBHsZbtE06hKBf\n"
    "5WQ1N2r6DD3f0YOZMxZWOmXVVntBf9sT43C/5B00bqYn46AUOWwpdueV44u2Uvlf\n"
    "rmYrIfzcrRYv3Z3VbAvzhsVMs3kbJLK5G+a9wQ1sbR76yfq9AJBnufFBDEZ5Yu4/\n"
    "xDa3Wc+XAgMBAAECggEABgdnWSk4YzWWoByY9vGn742ogqvqdpGiePVGd8VLKjv7\n"
    "HN+2I69t8T7hClCEnTCy/OeSnWbvhR60Q6TY4uwoSK8YojknQYOxk86xn8XaWva4\n"
    "Eo9VBftY2aP41Rt+oS/ZKtPQeJwPCI6sVlanGnp451iB/QGZixeO3tlquCsiaRSe\n"
    "doYeH09lJ5rkuN/dpZxwhet7eiZuZ9q0QV6Mx+2tID/cOpkO0YoLNRZdAeh0RgsE\n"
    "ycgchaQ7M1VnV0LeDAuIvRO/jHi1tTiLsWlB0udXQxLw/Mk0isGBT3N9r93ZdBNo\n"
    "IWsWRne/n01DPnC5d9bbC97W9Iy56aCF0d241QFOjQKBgQDoABlneYmpJ34SAQgR\n"
    "wRI0aYbCCwLeJjJ7aHC5nRQCO7tqxL2+3rUPWbf/XrLvZ/szDpdxEUgdimjmf0Y3\n"
    "7X9NUVTW5kR5Tx/c0yu7BLbhEJbRJG0cqRC07iYqcQucTiF8lWaD8po7KIWI22Mf\n"
    "CrSqrUvHZpQSe+HiJFp1pKhNKwKBgQDGlXe3N8Fojo1Rej3TgTZIqKVwKCBQ54ho\n"
    "7+Y4Jt1EQW+6Cotpedo7F5xzJDSi7+4Vl3gn0m9bxbQMbAQKAVi5gQhl5YUMdulP\n"
    "+bbSE5FkoAvEspDwpkJDQxVDiiWFtS8Horig0cuR1jIIE9yjFCVul8Elb3dGUFuB\n"
    "8k5UX5OJRQKBgBnGUQw2631YfuAfLzdRvOUHyEnskT/+/GLLgqKMefmZi0PcYbw/\n"
    "39u5uwBrE/QXGEhe2aJdKibmBqt8/l8eSqNbYtKROJBFoyOUbmpTpsGwZyELK/gg\n"
    "LFP9lU3ny0NtRrkhnAcSv+HMqbE/tm5vcQz5Pc8EbXT0QG8wXMBvL6eLAoGAE+VJ\n"
    "tzuIzxbpJa6fnx8k9yaeXJxIkJKB4jGW2S1bockEjpkb2pdwu9bjv81y0JhFPDiO\n"
    "uz6kFYe7QDtaND5qSzuYQc07BUKsoWydWnLHcFNwmmZhixq9LMv9x2SB2eGLMrKk\n"
    "2MfsI1JYdOK4ikYsceYWXc/LHWpToLNMEbv5phkCgYEA1NJO0Mkj3GWD+GDgEDNz\n"
    "FdaIoHFfihWEIuEkUsB04BaKERnHpM+wB6SFQjpUazBA7dehNplH5CMU8WYQ6uSv\n"
    "UDTtmz/SxESAv8pV4f2ELmzk4SYtpiID7DuLlm7p6cg7RHTd68N1PznZ5MbvbgHy\n"
    "AfHtd9167vtoYzS8ILyApJ8=\n"
    "-----END PRIVATE KEY-----\n"
)

_INFO_FALSA = {
    "type": "service_account",
    "project_id": "proyecto-de-prueba",
    "private_key": _LLAVE_DE_PRUEBA,
    "client_email": "falso@proyecto-de-prueba.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}


@pytest.fixture(autouse=True)
def _limpiar_entorno_y_cache(monkeypatch):
    """Cada test arranca sin ninguna de las variables puestas y sin cache."""
    monkeypatch.delenv(servicios_cloud._VARIABLE_RUTA, raising=False)
    monkeypatch.delenv(servicios_cloud._VARIABLE_JSON, raising=False)
    monkeypatch.delenv(servicios_cloud._VARIABLE_PROJECT_ID, raising=False)
    servicios_cloud.resetear()
    yield
    servicios_cloud.resetear()


def test_sin_ninguna_variable_lanza_error_claro():
    with pytest.raises(servicios_cloud.CredencialesNoConfiguradas) as excepcion:
        servicios_cloud.get_project_id()
    assert "GOOGLE_APPLICATION_CREDENTIALS" in str(excepcion.value)
    assert "GCP_SERVICE_ACCOUNT_JSON" in str(excepcion.value)


def test_lee_project_id_desde_archivo_json(tmp_path, monkeypatch):
    archivo = tmp_path / "llave.json"
    archivo.write_text(json.dumps(_INFO_FALSA), encoding="utf-8")
    monkeypatch.setenv(servicios_cloud._VARIABLE_RUTA, str(archivo))

    assert servicios_cloud.get_project_id() == "proyecto-de-prueba"


def test_lee_project_id_desde_json_inline(monkeypatch):
    monkeypatch.setenv(servicios_cloud._VARIABLE_JSON, json.dumps(_INFO_FALSA))

    assert servicios_cloud.get_project_id() == "proyecto-de-prueba"


def test_variable_ruta_gana_si_ambas_estan_presentes(tmp_path, monkeypatch):
    archivo = tmp_path / "llave.json"
    archivo.write_text(json.dumps({**_INFO_FALSA, "project_id": "del-archivo"}), encoding="utf-8")
    monkeypatch.setenv(servicios_cloud._VARIABLE_RUTA, str(archivo))
    monkeypatch.setenv(
        servicios_cloud._VARIABLE_JSON, json.dumps({**_INFO_FALSA, "project_id": "del-json-inline"})
    )

    assert servicios_cloud.get_project_id() == "del-archivo"


def test_gcp_project_id_explicito_no_requiere_leer_la_llave(monkeypatch):
    monkeypatch.setenv(servicios_cloud._VARIABLE_PROJECT_ID, "otro-proyecto")
    # Ninguna de las dos variables de la llave esta puesta -- si
    # get_project_id() intentara leerla, esto reventaria.
    assert servicios_cloud.get_project_id() == "otro-proyecto"


def test_get_credentials_construye_credenciales_de_service_account(monkeypatch):
    monkeypatch.setenv(servicios_cloud._VARIABLE_JSON, json.dumps(_INFO_FALSA))

    credenciales = servicios_cloud.get_credentials()

    assert credenciales.service_account_email == _INFO_FALSA["client_email"]


def test_get_credentials_cachea_entre_llamadas(monkeypatch):
    monkeypatch.setenv(servicios_cloud._VARIABLE_JSON, json.dumps(_INFO_FALSA))

    primera = servicios_cloud.get_credentials()
    segunda = servicios_cloud.get_credentials()

    assert primera is segunda


# --------------------------------------------------------------------------
# .env se carga por ruta absoluta, no depende del directorio de trabajo
# del proceso (#servicio -- un Servicio de Windows no garantiza
# backend/ como CWD, ver docstring del modulo).
# --------------------------------------------------------------------------


def test_ruta_env_es_absoluta_y_no_depende_del_cwd(tmp_path, monkeypatch):
    """RUTA_ENV se calcula una vez, a partir de __file__ -- cambiar el
    directorio de trabajo del proceso despues no debe alterarla."""
    monkeypatch.chdir(tmp_path)

    assert servicios_cloud.RUTA_ENV.is_absolute()
    assert servicios_cloud.RUTA_ENV.name == ".env"
    assert servicios_cloud.RUTA_ENV.parent.name == "backend"


def test_load_dotenv_con_ruta_absoluta_funciona_sin_importar_el_cwd(tmp_path, monkeypatch):
    """
    Prueba el mecanismo real del que depende el fix: pasarle una ruta
    absoluta a load_dotenv() (en vez de dejar que busque hacia arriba
    desde el CWD, que es lo que hacia el codigo viejo) funciona sin
    importar desde donde se lanzo el proceso -- justo lo que necesita un
    Servicio de Windows, que no garantiza backend/ como directorio de
    trabajo.
    """
    archivo_env = tmp_path / "backend_simulado" / ".env"
    archivo_env.parent.mkdir()
    archivo_env.write_text("VARIABLE_DE_PRUEBA_SERVICIO=valor-de-prueba\n", encoding="utf-8")

    # Directorio de trabajo distinto de donde vive el .env -- si
    # load_dotenv() buscara hacia arriba desde el CWD (comportamiento
    # viejo), NO encontraria este archivo.
    otro_directorio = tmp_path / "otro_directorio_de_trabajo"
    otro_directorio.mkdir()
    monkeypatch.chdir(otro_directorio)
    monkeypatch.delenv("VARIABLE_DE_PRUEBA_SERVICIO", raising=False)

    load_dotenv(archivo_env)

    import os

    assert os.environ["VARIABLE_DE_PRUEBA_SERVICIO"] == "valor-de-prueba"


def test_resetear_fuerza_releer_el_entorno(monkeypatch):
    monkeypatch.setenv(servicios_cloud._VARIABLE_JSON, json.dumps(_INFO_FALSA))
    assert servicios_cloud.get_project_id() == "proyecto-de-prueba"

    monkeypatch.setenv(
        servicios_cloud._VARIABLE_JSON, json.dumps({**_INFO_FALSA, "project_id": "otro-proyecto"})
    )
    # Sin resetear(), seguiria devolviendo el valor cacheado.
    assert servicios_cloud.get_project_id() == "proyecto-de-prueba"

    servicios_cloud.resetear()
    assert servicios_cloud.get_project_id() == "otro-proyecto"
