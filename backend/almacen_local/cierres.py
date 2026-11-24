"""
Cierre de dia (#50): consolida el journal local (#14) en un acta
congelada.

Igual que las ventas, el cierre se genera y persiste LOCALMENTE primero
-- no requiere internet ni BigQuery. El sincronizador (#15) lo sube
despues, en segundo plano.

    generar_cierre_dia() -> cierre-2026-08-31.jsonl (fsync)
                                   |
                                   v (sincronizador, #15)
                              BigQuery (tabla `cierre`, #8)

Formato: mismo patron append-only del journal de ventas -- un archivo
por dia, eventos que nunca se reescriben.

    {"evento": "cierre", ...datos del cierre...}
    {"evento": "sincronizado", "sincronizado_en": "..."}

PRINCIPIO CENTRAL DE #50: el cierre NO es lo que salva los datos. Cada
venta ya esta en el journal desde que se oprime Enter (#22, #14). Esto
solo consolida y archiva un acta -- generar el cierre dos veces
(idempotente, ver `ya_cerrado`) o nunca generarlo no hace que se
pierda una sola venta.
"""

import datetime
import json
import os
import threading
import uuid
from pathlib import Path

from almacen_local import journal
from almacen_local._seguridad_pruebas import verificar_no_es_carpeta_real
from utilidades import zona_negocio
from ventas import desglose

_CARPETA_REAL = Path(__file__).resolve().parent.parent / "datos_locales" / "cierres"
CARPETA_POR_DEFECTO = _CARPETA_REAL

# Cuantos dias hacia atras revisa el disparador "perezoso" al arrancar
# -- acotado para no intentar cerrar historia arbitraria de antes de
# que el sistema empezara a usarse.
DIAS_HACIA_ATRAS_PEREZOSO = 7

# Hora a partir de la cual el dia se cierra solo (#50). La define
# utilidades/zona_negocio.py (misma fuente que el resto del sistema); se
# re-exporta aqui porque el programador y el calculo de `provisional`
# (#54) la importan desde este modulo.
HORA_CIERRE_POR_DEFECTO = zona_negocio.HORA_CIERRE

_lock = threading.Lock()


def _carpeta(carpeta=None) -> Path:
    ruta = Path(carpeta) if carpeta else CARPETA_POR_DEFECTO
    verificar_no_es_carpeta_real(ruta, _CARPETA_REAL, "cierres")
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _archivo_dia(fecha: datetime.date, carpeta=None) -> Path:
    return _carpeta(carpeta) / f"cierre-{fecha.isoformat()}.jsonl"


def _default_json(valor):
    if isinstance(valor, (datetime.datetime, datetime.date)):
        return valor.isoformat()
    raise TypeError(f"No se sabe serializar {type(valor).__name__} en el cierre local")


def _escribir_linea(archivo: Path, evento: dict):
    linea = json.dumps(evento, default=_default_json, ensure_ascii=False)
    with _lock:
        with open(archivo, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def _leer_eventos(fecha: datetime.date, carpeta=None) -> list:
    archivo = _archivo_dia(fecha, carpeta)
    if not archivo.exists():
        return []
    eventos = []
    with open(archivo, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                eventos.append(json.loads(linea))
    return eventos


def ya_cerrado(fecha: datetime.date, carpeta=None) -> bool:
    return any(e.get("evento") == "cierre" for e in _leer_eventos(fecha, carpeta))


def es_antes_de_hora_cierre(ahora: datetime.datetime | None = None) -> bool:
    """
    True si todavia no se cruza la hora de cierre configurada hoy. Se
    compara contra el reloj de pared del NEGOCIO (ver
    utilidades/zona_negocio.py).
    """
    return zona_negocio.antes_de_hora_cierre(ahora)


def obtener_cierre_local(fecha: datetime.date, carpeta=None) -> dict | None:
    """
    El acta del dia (si existe), con su estado de sincronizacion
    calculado. El archivo puede tener varios eventos `cierre` (una por
    generacion o regeneracion, #54): se devuelve el ULTIMO, y
    `sincronizado` es True solo si hay un evento `sincronizado`
    posterior a ese ultimo `cierre`.
    """
    eventos = _leer_eventos(fecha, carpeta)
    indice_ultimo_cierre = None
    for i, evento in enumerate(eventos):
        if evento.get("evento") == "cierre":
            indice_ultimo_cierre = i
    if indice_ultimo_cierre is None:
        return None

    cierre = dict(eventos[indice_ultimo_cierre])
    cierre.pop("evento", None)
    cierre.setdefault("provisional", False)
    cierre["sincronizado"] = any(
        e.get("evento") == "sincronizado"
        for e in eventos[indice_ultimo_cierre + 1 :]
    )
    return cierre


def _construir_acta(
    fecha: datetime.date, generado_por: str, provisional: bool, carpeta_journal=None
) -> dict:
    """Consolida el journal del dia en un acta nueva (id y marca de tiempo frescos)."""
    ventas = journal.leer_dia(fecha, carpeta=carpeta_journal)
    total = sum(v["total"] for v in ventas)
    return {
        "id": str(uuid.uuid4()),
        "tipo": "dia",
        "fecha_inicio": fecha,
        "fecha_fin": fecha,
        "total": total,
        "num_ventas": len(ventas),
        "desglose_categoria": desglose.por_categoria(ventas),
        "desglose_metodo_pago": desglose.por_metodo_pago(ventas),
        "generado_en": datetime.datetime.now(datetime.timezone.utc),
        "generado_por": generado_por,
        "pdf_ruta": None,
        "estado": "cerrado",
        "provisional": provisional,
    }


def generar_cierre_dia(
    fecha: datetime.date, generado_por: str, carpeta_journal=None, carpeta_cierre=None
) -> dict:
    """
    Idempotente: si el dia ya esta cerrado localmente, regresa el
    cierre existente sin generar uno nuevo -- nunca duplica. Para
    rehacer un acta ya existente, ver `regenerar_cierre_dia`.

    `generado_por`: 'automatico' | 'perezoso' | 'manual' | 'regeneracion'.
    Un cierre 'manual' hecho ANTES de la hora de cierre queda marcado
    `provisional`: el programador (#50) lo finaliza a la hora de cierre.
    """
    existente = obtener_cierre_local(fecha, carpeta_cierre)
    if existente is not None:
        return existente

    # Solo el cierre forzado de HOY antes de la hora es provisional: un
    # cierre manual de un dia pasado ya no tiene un "despues" que
    # consolidar.
    provisional = (
        generado_por == "manual"
        and fecha == zona_negocio.hoy()
        and es_antes_de_hora_cierre()
    )
    cierre = _construir_acta(fecha, generado_por, provisional, carpeta_journal)

    archivo = _archivo_dia(fecha, carpeta_cierre)
    _escribir_linea(archivo, {"evento": "cierre", **cierre})

    resultado = dict(cierre)
    resultado["sincronizado"] = False
    return resultado


def regenerar_cierre_dia(
    fecha: datetime.date, generado_por: str, carpeta_journal=None, carpeta_cierre=None
) -> dict:
    """
    A diferencia de `generar_cierre_dia`, SIEMPRE append-ea un evento
    `cierre` nuevo con los valores actuales del journal -- no es
    idempotente. Se usa para rehacer el acta del dia en curso (#54)
    cuando entraron ventas despues del primer cierre.

    El evento nuevo queda con `provisional=False` y su propio id. Los
    lectores (`obtener_cierre_local`) toman el ultimo evento `cierre`;
    el sincronizador (#15) re-sube el acta porque el marcador
    `sincronizado` quedo antes de este evento.
    """
    cierre = _construir_acta(fecha, generado_por, False, carpeta_journal)

    archivo = _archivo_dia(fecha, carpeta_cierre)
    _escribir_linea(archivo, {"evento": "cierre", **cierre})

    resultado = dict(cierre)
    resultado["sincronizado"] = False
    return resultado


def marcar_sincronizado(fecha: datetime.date, carpeta_cierre=None):
    """Lo llama el sincronizador (#15) tras insertar el cierre en BigQuery."""
    archivo = _archivo_dia(fecha, carpeta_cierre)
    _escribir_linea(
        archivo,
        {
            "evento": "sincronizado",
            "sincronizado_en": datetime.datetime.now(datetime.timezone.utc),
        },
    )


def cerrar_dias_pendientes(
    generado_por: str = "perezoso",
    dias_hacia_atras: int = DIAS_HACIA_ATRAS_PEREZOSO,
    carpeta_journal=None,
    carpeta_cierre=None,
) -> list:
    """
    Disparador PEREZOSO de #50: revisa desde ayer hacia atras y cierra
    cualquier dia que no tenga cierre todavia -- incluidos dias sin
    ninguna venta (por ejemplo, un domingo que el negocio no abre).
    Nunca toca el dia de HOY -- ese sigue en curso.

    Se llama una vez al arrancar el sistema (#13/#50): cubre el caso de
    "se apago la PC antes de la hora de cierre y nadie cerro a mano".
    """
    cerrados = []
    hoy = zona_negocio.hoy()
    for delta in range(1, dias_hacia_atras + 1):
        fecha = hoy - datetime.timedelta(days=delta)
        acta = obtener_cierre_local(fecha, carpeta_cierre)
        if acta is None:
            cerrados.append(
                generar_cierre_dia(
                    fecha, generado_por, carpeta_journal=carpeta_journal, carpeta_cierre=carpeta_cierre
                )
            )
        elif acta.get("provisional"):
            # Se forzo el cierre antes de la hora de cierre y la PC se apago antes
            # de que el programador lo finalizara: lo finaliza ahora.
            cerrados.append(
                regenerar_cierre_dia(
                    fecha, generado_por, carpeta_journal=carpeta_journal, carpeta_cierre=carpeta_cierre
                )
            )
    return cerrados
