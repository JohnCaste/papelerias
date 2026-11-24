"""
Journal local de compras de trabajadores. Mismo principio que el journal de
ventas (almacen_local/journal.py): cada operacion se confirma escribiendola
aqui con fsync, ANTES y SIN depender de BigQuery -- asi el apartado funciona
sin internet. El Sincronizador lo sube despues (sincronizar_compras_una_vez).

    alta / abono / edicion / eliminacion
        -> compras.jsonl (fsync)          <- la pantalla lee SIEMPRE de aqui
              |
              v (en segundo plano)
        BigQuery: compra_trabajador / abono_compra   (respaldo)

Un solo archivo, no uno por dia: una compra puede seguir abierta meses y sus
abonos llegan despues. El volumen es minimo (cientos de lineas al anio).

Tres tipos de linea, append-only (nunca se reescribe ni se borra una):

    {"evento": "compra", "id": <evento>, "compra_id": ..., ...instantanea}
    {"evento": "abono",  "id": <evento>, "abono_id": ..., "compra_id": ...}
    {"evento": "confirmacion", "id": <evento>, "confirmado_en": ...}

Editar o eliminar es OTRA linea con la instantanea completa (eliminar =
`eliminada`/`eliminado` true). La version vigente es la ULTIMA linea por
compra_id / abono_id en orden de archivo -- el lock serializa la escritura,
asi que no se depende del reloj de la PC.
"""

import datetime
import json
import os
import threading
import uuid
from pathlib import Path

from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real

_CARPETA_REAL = Path(__file__).resolve().parent.parent / "datos_locales" / "compras"
CARPETA_POR_DEFECTO = _CARPETA_REAL
NOMBRE_ARCHIVO = "compras.jsonl"

# Reentrante: el servicio lo toma para validar contra el saldo y escribir
# de forma atomica, y dentro de esa seccion vuelve a pasar por aqui.
lock = threading.RLock()

CAMPOS_COMPRA = (
    "compra_id", "nombre", "producto", "cantidad", "precio", "fecha",
    "eliminada", "usuario_id", "registrado_por", "generado_en",
)
CAMPOS_ABONO = (
    "abono_id", "compra_id", "monto", "fecha", "eliminado",
    "usuario_id", "registrado_por", "generado_en",
)


def resolver_carpeta(carpeta=None, crear=False) -> Path:
    ruta = Path(carpeta) if carpeta else CARPETA_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _CARPETA_REAL, "compras")
    if crear:
        ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_archivo(carpeta=None) -> Path:
    return resolver_carpeta(carpeta) / NOMBRE_ARCHIVO


def _default_json(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    raise TypeError(f"No se sabe serializar {type(valor).__name__} en el journal de compras")


def _escribir_linea(evento: dict, carpeta=None):
    archivo = resolver_carpeta(carpeta, crear=True) / NOMBRE_ARCHIVO
    linea = json.dumps(evento, default=_default_json, ensure_ascii=False)
    with lock:
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def _ahora() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def escribir_compra(datos: dict, carpeta=None) -> dict:
    """
    Escribe una version de la compra (alta, edicion o eliminacion). `datos`
    trae la instantanea completa; aqui se agregan `id` del evento y
    `generado_en`. Devuelve el evento tal como quedo en disco (sin 'evento').
    """
    fila = {campo: datos.get(campo) for campo in CAMPOS_COMPRA}
    fila["id"] = str(uuid.uuid4())
    fila["eliminada"] = bool(fila.get("eliminada"))
    fila["generado_en"] = _ahora()
    _escribir_linea({"evento": "compra", **fila}, carpeta)
    return fila


def escribir_abono(datos: dict, carpeta=None) -> dict:
    """Igual que escribir_compra, para un abono (alta o eliminacion)."""
    fila = {campo: datos.get(campo) for campo in CAMPOS_ABONO}
    fila["id"] = str(uuid.uuid4())
    fila["eliminado"] = bool(fila.get("eliminado"))
    fila["generado_en"] = _ahora()
    _escribir_linea({"evento": "abono", **fila}, carpeta)
    return fila


def marcar_confirmados(ids, carpeta=None):
    """Registra que BigQuery ya acepto estos eventos (lo llama el Sincronizador)."""
    for id_ in ids:
        _escribir_linea(
            {"evento": "confirmacion", "id": id_, "confirmado_en": _ahora()}, carpeta
        )


def escribir_confirmado(evento: dict, carpeta=None):
    """
    Para la reconstruccion desde BigQuery: escribe el evento tal cual (con su
    `id` y `generado_en` originales) seguido de su confirmacion.
    """
    _escribir_linea(evento, carpeta)
    _escribir_linea(
        {"evento": "confirmacion", "id": evento["id"], "confirmado_en": _ahora()}, carpeta
    )


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


def _vigentes(eventos, tipo, clave, campo_eliminado) -> list:
    ultimos = {}
    for evento in eventos:
        if evento.get("evento") == tipo:
            # Reinsertar mueve la clave al final: el dict queda en el orden de
            # la ultima version, y la ultima linea gana.
            ultimos.pop(evento[clave], None)
            ultimos[evento[clave]] = evento
    resultado = []
    for evento in ultimos.values():
        if evento.get(campo_eliminado):
            continue
        fila = dict(evento)
        fila.pop("evento", None)
        resultado.append(fila)
    return resultado


def compras_vigentes(carpeta=None, eventos=None) -> list:
    eventos = leer_eventos(carpeta) if eventos is None else eventos
    return _vigentes(eventos, "compra", "compra_id", "eliminada")


def abonos_vigentes(carpeta=None, eventos=None) -> list:
    """Abonos no eliminados. OJO: incluye los de compras eliminadas; filtra quien llama."""
    eventos = leer_eventos(carpeta) if eventos is None else eventos
    return _vigentes(eventos, "abono", "abono_id", "eliminado")


def leer_pendientes(carpeta=None, eventos=None) -> list:
    """Eventos compra/abono sin linea de confirmacion, en orden de archivo."""
    eventos = leer_eventos(carpeta) if eventos is None else eventos
    confirmados = {e["id"] for e in eventos if e.get("evento") == "confirmacion"}
    return [
        e for e in eventos
        if e.get("evento") in ("compra", "abono") and e["id"] not in confirmados
    ]
