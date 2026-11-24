"""
Sucursal a la que pertenece esta instalacion (segunda papeleria).

Cada sucursal tiene su propio dataset de BigQuery, elegido en
`backend\\.env` con BQ_DATASET. Este modulo es la UNICA fuente de ese
nombre -- esquema/tablas.py lo lee de aqui, y de ahi todas las tablas.

Principio: ante la duda, no arrancar. Un dataset mal resuelto no truena
nada, simplemente escribe las ventas de una tienda en la base de la otra
sin que nadie se entere. Por eso:

  - En produccion BQ_DATASET es obligatoria (mismo criterio que
    JWT_SECRET_KEY en main.py). En desarrollo/tests se usa `lapape`.
  - `.env` se carga AQUI, no solo en serviciosCloud: tablas.py puede
    importarse antes que serviciosCloud, y entonces la variable todavia
    no existiria y se usaria el default sin aviso.
  - Candado: la PC anota en datos_locales/sucursal.json a que dataset
    pertenece; si despues el .env dice otro, no arranca (el diario local
    pendiente se subiria a la base equivocada).
"""

import datetime
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from almacen_local._seguridad_pruebas import bajo_pruebas

# Misma ruta absoluta que autentificacion/serviciosCloud.py. load_dotenv
# no pisa variables ya definidas, asi que cargarlo en los dos lados es
# inocuo.
RUTA_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(RUTA_ENV)

VARIABLE_DATASET = "BQ_DATASET"
VARIABLE_NOMBRE = "SUCURSAL_NOMBRE"

# El dataset de la tienda original. Tambien el default de desarrollo/tests.
DATASET_ORIGINAL = "lapape"

# Valor de `papeleria` en nuevas_tablas.login para la tienda original: es
# el que ya tienen todas las filas de antes de haber sucursales.
PAPELERIA_ORIGINAL = "1"

_PATRON_DATASET = re.compile(r"^[A-Za-z0-9_]{1,1024}$")

CARPETA_CANDADO = Path(__file__).resolve().parent.parent / "datos_locales"
ARCHIVO_CANDADO = "sucursal.json"


class ConfiguracionSucursalInvalida(RuntimeError):
    """BQ_DATASET falta (en produccion), es invalida, o no coincide con el candado."""


def _es_desarrollo() -> bool:
    return os.environ.get("ENTORNO", "produccion") == "desarrollo" or bajo_pruebas()


def resolver_dataset() -> str:
    valor = (os.environ.get(VARIABLE_DATASET) or "").strip()

    if not valor:
        if _es_desarrollo():
            return DATASET_ORIGINAL
        raise ConfiguracionSucursalInvalida(
            "Falta la variable BQ_DATASET en backend\\.env. Es el nombre de la "
            "base de datos de ESTA papeleria (por ejemplo BQ_DATASET=lapape en "
            "la tienda original). El programa no arranca sin ella a proposito: "
            "sin saber a que sucursal pertenece podria guardar las ventas en la "
            "base de otra tienda."
        )

    if not _PATRON_DATASET.match(valor):
        raise ConfiguracionSucursalInvalida(
            f"BQ_DATASET={valor!r} en backend\\.env no es un nombre de dataset "
            "valido: solo letras, numeros y guion bajo (por ejemplo "
            "lapape_sucursal2)."
        )
    return valor


def papeleria_login(dataset: str) -> str:
    """
    Valor de la columna `papeleria` de nuevas_tablas.login que le toca a
    esta sucursal. Derivado del dataset, no configurado aparte: una
    variable menos que pueda quedar mal puesta.
    """
    return PAPELERIA_ORIGINAL if dataset == DATASET_ORIGINAL else dataset


def nombre_sucursal(dataset: str) -> str:
    nombre = (os.environ.get(VARIABLE_NOMBRE) or "").strip()
    if nombre:
        return nombre
    return "Principal" if dataset == DATASET_ORIGINAL else dataset


def verificar_candado(dataset: str, carpeta: Path = CARPETA_CANDADO) -> None:
    """
    Primer arranque: anota el dataset. Siguientes: exige que sea el mismo.
    """
    ruta = Path(carpeta) / ARCHIVO_CANDADO

    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "registrado": datetime.datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return

    try:
        registrado = json.loads(ruta.read_text(encoding="utf-8")).get("dataset")
    except (ValueError, OSError) as error:
        raise ConfiguracionSucursalInvalida(
            f"No se pudo leer {ruta} ({error}). Si el archivo se dano, "
            "borralo y vuelve a abrir el programa."
        ) from error

    if registrado != dataset:
        raise ConfiguracionSucursalInvalida(
            f"Esta PC pertenece a la sucursal con base '{registrado}', pero "
            f"backend\\.env dice BQ_DATASET={dataset}. No se arranca para no "
            "mezclar las ventas de dos tiendas.\n"
            "  - Si fue un error, corrige BQ_DATASET en backend\\.env.\n"
            "  - Si de verdad esta PC cambia de sucursal: primero confirma que "
            "no quedan ventas sin subir, luego borra "
            f"{ruta} y vuelve a abrir el programa."
        )


def confirmar_destino(accion: str, si: bool = False, entrada=input) -> bool:
    """
    Para los scripts de esquema/: muestra a que base se va a escribir y
    pide confirmacion. `si=True` (bandera --si) salta la pregunta, para
    los instaladores.
    """
    dataset = resolver_dataset()
    print(f"Sucursal: {nombre_sucursal(dataset)}  |  dataset: {dataset}")
    print(f"Accion:   {accion}")
    if si:
        return True
    respuesta = entrada("Continuar? (s/N): ").strip().lower()
    return respuesta in ("s", "si", "sí", "y", "yes")
