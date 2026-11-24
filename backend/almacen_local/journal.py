"""
Journal local de ventas (#14). Cada venta confirmada se escribe aqui
ANTES que a BigQuery -- esto es lo que hace que capturar una venta
tome milisegundos y siga funcionando sin internet (ver #55).

    Enter -> escribir_venta() -> ventas-2026-08-31.jsonl (fsync)
                                        |
                                        v (en segundo plano, #15)
                                   BigQuery

Formato: un archivo .jsonl por dia de calendario DEL NEGOCIO (zona
`America/Mexico_City`, ver utilidades/zona_negocio.py; rotacion por dia),
con dos tipos de linea -- el mismo patron append-only que ya usamos
para BigQuery en #8: nunca se reescribe una linea, se agrega una nueva
que la complementa.

    {"evento": "venta", ...datos de la venta (ver modelos_venta)...}
    {"evento": "confirmacion", "id": "...", "confirmado_en": "..."}

Una venta esta 'pendiente' si su evento 'venta' no tiene un
'confirmacion' que lo siga para el mismo id; 'enviada' en caso
contrario. Ese estado se CALCULA al leer, nunca se guarda como campo
mutable.

El archivo debe vivir en disco LOCAL, no en una unidad de red ni una
carpeta sincronizada por Drive/Dropbox -- fsync sobre una unidad de red
puede tardar segundos en vez de milisegundos, y una carpeta sincronizada
puede copiar el archivo a medio escribir (mismo riesgo que se documento
para SQLite en versiones anteriores del plan; aplica igual aqui).
"""

import datetime
import json
import os
import threading
from pathlib import Path

from acceso_datos.modelos_venta import construir_venta
from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real
from utilidades import zona_negocio

_CARPETA_REAL = Path(__file__).resolve().parent.parent / "datos_locales" / "journal"
CARPETA_POR_DEFECTO = _CARPETA_REAL

_lock = threading.Lock()


def resolver_carpeta(carpeta=None) -> Path:
    ruta = Path(carpeta) if carpeta else CARPETA_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _CARPETA_REAL, "journal")
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _archivo_dia(fecha: datetime.date, carpeta=None) -> Path:
    return resolver_carpeta(carpeta) / f"ventas-{fecha.isoformat()}.jsonl"


def _default_json(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    raise TypeError(f"No se sabe serializar {type(valor).__name__} en el journal")


def _escribir_linea(archivo: Path, evento: dict):
    linea = json.dumps(evento, default=_default_json, ensure_ascii=False)
    with _lock:
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def escribir_venta(datos: dict, carpeta=None) -> dict:
    """
    Confirma la venta: la escribe en el journal (con fsync) y devuelve
    la fila completa, ya con su id. Esto es lo unico que debe esperar
    el cajero -- BigQuery se entera despues, en segundo plano (#15).
    """
    fila = construir_venta(datos)
    # El archivo se elige por la fecha del NEGOCIO, no por la fecha UTC
    # de `fecha_hora`: con UTC-6, tomar `.date()` en crudo mandaba toda
    # venta de las 6pm en adelante al archivo del dia siguiente (ver
    # utilidades/zona_negocio.py).
    fecha = zona_negocio.fecha_de(fila["fecha_hora"])
    archivo = _archivo_dia(fecha, carpeta)
    _escribir_linea(archivo, {"evento": "venta", **fila})
    return fila


def marcar_confirmada(id_: str, fecha: datetime.date, carpeta=None):
    """
    Registra que BigQuery ya acepto esta venta -- la llama #15 despues
    de un insert exitoso. `fecha` es la fecha de la venta ORIGINAL (no
    la de hoy): decide en que archivo cae la confirmacion, para que
    quede junto al evento 'venta' que confirma.
    """
    archivo = _archivo_dia(fecha, carpeta)
    _escribir_linea(
        archivo,
        {
            "evento": "confirmacion",
            "id": id_,
            "confirmado_en": datetime.datetime.now(datetime.timezone.utc),
        },
    )


def leer_dia(fecha: datetime.date, carpeta=None) -> list:
    """
    Reconstruye el estado del dia leyendo el journal desde cero: cada
    venta con su 'estado_local' ('pendiente' o 'enviada'), calculado a
    partir de si le sigue un evento de confirmacion.

    Es la fuente de "ventas del dia en curso" que pide #55 -- no
    requiere BigQuery ni internet. Si el dia no tiene journal todavia
    (sin ventas capturadas), regresa una lista vacia, no un error.
    """
    archivo = _archivo_dia(fecha, carpeta)
    if not archivo.exists():
        return []

    ventas_por_id = {}
    confirmadas = set()

    with open(archivo, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            evento = json.loads(linea)
            if evento["evento"] == "venta":
                ventas_por_id[evento["id"]] = evento
            elif evento["evento"] == "confirmacion":
                confirmadas.add(evento["id"])

    resultado = []
    for id_, venta in ventas_por_id.items():
        venta = dict(venta)
        venta.pop("evento", None)
        venta["estado_local"] = "enviada" if id_ in confirmadas else "pendiente"
        resultado.append(venta)

    resultado.sort(key=lambda v: v["fecha_hora"])
    return resultado


def leer_pendientes(fecha: datetime.date, carpeta=None) -> list:
    """Solo las ventas que #15 todavia no confirmo contra BigQuery."""
    return [v for v in leer_dia(fecha, carpeta) if v["estado_local"] == "pendiente"]


def buscar_venta(id_: str, fecha: datetime.date, carpeta=None):
    """
    La venta con ese `id` en el journal de `fecha`, o `None` si no esta
    (o el dia no tiene journal). La cancelacion (#26) la usa para
    localizar la venta original: el journal esta particionado por dia y
    los ids son uuid4, asi que quien cancela pasa la fecha de la venta.
    """
    for venta in leer_dia(fecha, carpeta):
        if venta["id"] == id_:
            return venta
    return None


def reconstruir_desde(fecha_inicio: datetime.date, fecha_fin: datetime.date, carpeta=None) -> list:
    """
    Recorre varios dias de journal y regresa todas las ventas en el
    rango (ambos extremos incluidos) -- para reponer el backlog tras
    una caida larga de internet (#55), o para auditar/recuperar a mano.
    """
    resultado = []
    dia = fecha_inicio
    while dia <= fecha_fin:
        resultado.extend(leer_dia(dia, carpeta))
        dia += datetime.timedelta(days=1)
    return resultado
