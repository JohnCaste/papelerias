"""
Journal local de la lista de faltantes. Mismo principio que el de compras
de trabajadores (almacen_local/compras.py): cada operacion se confirma
escribiendola aqui con fsync, ANTES y SIN depender de BigQuery. El
Sincronizador la sube despues (sincronizar_faltantes_una_vez).

    alta / edicion / comprado / eliminacion
        -> faltantes.jsonl (fsync)        <- la pantalla lee SIEMPRE de aqui
              |
              v (en segundo plano)
        BigQuery: faltante   (respaldo)

Dos tipos de linea, append-only (nunca se reescribe ni se borra una):

    {"evento": "faltante", "id": <evento>, "faltante_id": ..., ...instantanea}
    {"evento": "confirmacion", "id": <evento>, "confirmado_en": ...}

Cada operacion es OTRA linea con la instantanea completa (eliminar =
`eliminado` true). La version vigente es la ULTIMA linea por faltante_id en
orden de archivo -- el lock serializa la escritura, asi que no se depende
del reloj de la PC.
"""

import datetime
import json
import os
import threading
import uuid
from pathlib import Path

from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real

_CARPETA_REAL = Path(__file__).resolve().parent.parent / "datos_locales" / "faltantes"
CARPETA_POR_DEFECTO = _CARPETA_REAL
NOMBRE_ARCHIVO = "faltantes.jsonl"

# Reentrante: el servicio lo toma para validar y escribir de forma atomica.
lock = threading.RLock()

CAMPOS_FALTANTE = (
    "faltante_id", "producto_id", "nombre", "cantidad", "nota", "estado",
    "eliminado", "usuario_id", "registrado_por", "creado_en", "comprado_por",
    "comprado_en", "modificado_por", "generado_en",
)


def resolver_carpeta(carpeta=None, crear=False) -> Path:
    ruta = Path(carpeta) if carpeta else CARPETA_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _CARPETA_REAL, "faltantes")
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_archivo(carpeta=None) -> Path:
    return resolver_carpeta(carpeta) / NOMBRE_ARCHIVO


def _default_json(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    raise TypeError(f"No se sabe serializar {type(valor).__name__} en el journal de faltantes")


def _escribir_linea(evento: dict, carpeta=None):
    archivo = resolver_carpeta(carpeta, crear=True) / NOMBRE_ARCHIVO
    linea = json.dumps(evento, default=_default_json, ensure_ascii=False)
    with lock:
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def ahora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def escribir_faltante(datos: dict, carpeta=None) -> dict:
    """
    Escribe una version del faltante. `datos` trae la instantanea completa;
    aqui se agregan `id` del evento y `generado_en`. Devuelve el evento tal
    como quedo en disco (sin 'evento').
    """
    fila = {campo: datos.get(campo) for campo in CAMPOS_FALTANTE}
    fila["id"] = str(uuid.uuid4())
    fila["eliminado"] = bool(fila.get("eliminado"))
    fila["generado_en"] = ahora()
    _escribir_linea({"evento": "faltante", **fila}, carpeta)
    return fila


def marcar_confirmados(ids, carpeta=None):
    """Registra que BigQuery ya acepto estos eventos (lo llama el Sincronizador)."""
    for id_ in ids:
        _escribir_linea({"evento": "confirmacion", "id": id_, "confirmado_en": ahora()}, carpeta)


def escribir_confirmado(evento: dict, carpeta=None):
    """Reconstruccion desde BigQuery: el evento tal cual + su confirmacion."""
    _escribir_linea(evento, carpeta)
    _escribir_linea({"evento": "confirmacion", "id": evento["id"], "confirmado_en": ahora()}, carpeta)


def leer_eventos(carpeta=None) -> list:
    """Todas las lineas del journal en orden de archivo ([] si no existe)."""
    archivo = ruta_archivo(carpeta)
    if not archivo.exists():
        return []
    eventos = []
    with lock:
        with open(archivo, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if linea:
                    eventos.append(json.loads(linea))
    return eventos


def faltantes_vigentes(carpeta=None, eventos=None) -> list:
    """Ultima version por faltante_id, sin los eliminados."""
    eventos = leer_eventos(carpeta) if eventos is None else eventos
    ultimos = {}
    for evento in eventos:
        if evento.get("evento") == "faltante":
            ultimos.pop(evento["faltante_id"], None)
            ultimos[evento["faltante_id"]] = evento
    resultado = []
    for evento in ultimos.values():
        if evento.get("eliminado"):
            continue
        fila = dict(evento)
        fila.pop("evento", None)
        resultado.append(fila)
    return resultado


def leer_pendientes(carpeta=None, eventos=None) -> list:
    """Eventos 'faltante' sin linea de confirmacion, en orden de archivo."""
    eventos = leer_eventos(carpeta) if eventos is None else eventos
    confirmados = {e["id"] for e in eventos if e.get("evento") == "confirmacion"}
    return [e for e in eventos if e.get("evento") == "faltante" and e["id"] not in confirmados]
