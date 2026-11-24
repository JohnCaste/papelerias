"""
Credenciales de la cuenta de servicio de GCP, leidas de variables de
entorno (#2) -- nunca hardcodeadas en el codigo fuente.

La llave que vivia aqui antes (pegada en texto plano) quedo expuesta en
el historial de git. #1 (revocarla en GCP IAM y emitir una nueva) y #2
(purgar el historial y forzar el push) ya se resolvieron el 2026-09-01;
este modulo lee la llave NUEVA del entorno.

Dos formas de dar la llave; si ambas estan presentes gana la primera:

  GOOGLE_APPLICATION_CREDENTIALS=ruta/al/archivo.json
      -- la variable estandar que usan las librerias de Google. Sirve
      para desarrollo local, apuntando a un archivo FUERA del repo
      (nunca dentro de una carpeta que git seguya).

  GCP_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
      -- el JSON completo de la llave como una sola linea de texto, para
      entornos sin filesystem persistente donde no conviene escribir un
      archivo (CI, algunos hosts administrados).

GCP_PROJECT_ID es opcional: si no se define, se toma del campo
'project_id' que ya trae la llave.

Ver .env.example (junto a este archivo) para la plantilla, sin valores.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account

# Ruta absoluta a backend/.env, NUNCA relativa al directorio de trabajo
# del proceso -- antes esto era `load_dotenv()` a secas, que busca hacia
# arriba desde el directorio de trabajo actual. Funcionaba porque
# siempre se corria `python main.py` desde dentro de `backend/`, pero un
# Servicio de Windows (#13/#servicio) no garantiza ese directorio de
# trabajo (el Administrador de control de servicios suele arrancarlo
# desde `C:\Windows\System32`). Mismo patron `__file__`-relativo que ya
# usan almacen_local/journal.py, almacen_local/cierres.py y
# almacen_local/espejo_catalogo_sqlite.py para sus propias rutas.
RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"

# No revienta si el archivo no existe -- en produccion las variables ya
# pueden venir puestas por el sistema, no por un archivo.
load_dotenv(RUTA_ENV)

_VARIABLE_RUTA = "GOOGLE_APPLICATION_CREDENTIALS"
_VARIABLE_JSON = "GCP_SERVICE_ACCOUNT_JSON"
_VARIABLE_PROJECT_ID = "GCP_PROJECT_ID"

_credenciales = None
_info_cacheada = None


class CredencialesNoConfiguradas(RuntimeError):
    """Ni GOOGLE_APPLICATION_CREDENTIALS ni GCP_SERVICE_ACCOUNT_JSON estan definidas."""


def _cargar_info() -> dict:
    global _info_cacheada
    if _info_cacheada is not None:
        return _info_cacheada

    ruta = os.environ.get(_VARIABLE_RUTA)
    if ruta:
        with open(ruta, "r", encoding="utf-8") as archivo:
            _info_cacheada = json.load(archivo)
        return _info_cacheada

    json_texto = os.environ.get(_VARIABLE_JSON)
    if json_texto:
        _info_cacheada = json.loads(json_texto)
        return _info_cacheada

    raise CredencialesNoConfiguradas(
        "Faltan las credenciales de GCP: define "
        f"{_VARIABLE_RUTA} (ruta a un archivo .json) o "
        f"{_VARIABLE_JSON} (el JSON completo como texto) en el entorno "
        "o en un archivo .env. Ver backend/.env.example."
    )


def get_credentials():
    """Devuelve las credenciales, construyendolas la primera vez."""
    global _credenciales
    if _credenciales is None:
        _credenciales = service_account.Credentials.from_service_account_info(_cargar_info())
    return _credenciales


def get_project_id() -> str:
    explicito = os.environ.get(_VARIABLE_PROJECT_ID)
    if explicito:
        return explicito
    return _cargar_info()["project_id"]


def resetear():
    """Solo para tests: fuerza que la siguiente llamada relea el entorno."""
    global _credenciales, _info_cacheada
    _credenciales = None
    _info_cacheada = None
