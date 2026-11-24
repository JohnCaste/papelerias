"""
Captura manual del resumen de ventas de un dia por categoria
(handoff "Ventas lapape.dc.html", pantalla de Ventas).

El `ModalVentaDia` del frontend es la AUTORIDAD del dia: los montos que
manda son el total del dia por categoria, no un ajuste. Este repositorio
reconcilia ese objetivo contra lo que ya hay en `venta`:

  1. `base[cat]`  -- lo que aportan al dia las ventas que NO son captura
     manual (POS + migracion), ya neteado.
  2. Se revierte toda captura manual vigente de esa fecha con una fila de
     reversion (`venta_original_id`), que `/api/agregaciones` netea sola.
  3. Se inserta UNA venta `origen = 'resumen_manual'` con una linea
     `tipo = 'categoria'` por cada categoria cuya diferencia
     `objetivo[cat] - base[cat]` no sea cero.

Resultado: el agregado del dia por categoria queda EXACTAMENTE en el
objetivo, sin duplicar (arregla el 200 -> 400). Escribe directo a
BigQuery por streaming: no es camino caliente, no necesita el journal
local (#14).

Marca: `origen = 'resumen_manual'` y `metodo_pago = 'resumen_manual'`.
Las lineas son `tipo = 'categoria'`, asi que el sincronizador no genera
`movimiento_inventario`.
"""

import datetime
import uuid

from acceso_datos.consultas import ejecutar_query
from acceso_datos.escrituras import insertar_filas
from acceso_datos.modelos_venta import construir_venta
from esquema.tablas import DATASET
from utilidades import categorias

TABLA_VENTA = f"{DATASET}.venta"
ZONA = "America/Mexico_City"

ORIGEN = "resumen_manual"
METODO_PAGO = "resumen_manual"
USUARIO_POR_DEFECTO = "sistema"

# Claves canonicas de la captura de resumen: las MISMAS que valida el POS
# (utilidades/categorias.py). Hasta esta version aqui vivia una lista
# recortada de 5 claves, asi que un dia capturado a mano no podia
# registrar sublimacion / limpieza / terramar / otros aunque el POS si
# las vendiera. El frontend ya no usa 'productos'.
CATEGORIAS = categorias.CLAVES

PLIEGUE_LEGADO = categorias.PLIEGUE_LEGADO

# Namespace fijo para ids deterministas (mismo patron que #26): un doble
# clic o un reintento produce los mismos ids y BigQuery los deduplica por
# row_id en vez de escribir dos veces.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "lapape.resumen_diario")

# Rango exacto y podable por particion: la fecha civil en la zona del
# negocio, igual que reportes/agregaciones.py.
_RANGO = (
    f"fecha_hora >= TIMESTAMP(@fecha, '{ZONA}') "
    f"AND fecha_hora < TIMESTAMP(DATE_ADD(@fecha, INTERVAL 1 DAY), '{ZONA}')"
)


def _instante(fecha: datetime.date) -> datetime.datetime:
    """
    18:00 UTC del dia pedido: en `America/Mexico_City` (UTC-6, sin horario
    de verano desde 2023; UTC-5 si alguna vez volviera) eso es mediodia o
    la una de la tarde -- el mismo dia civil con cualquiera de los dos
    offsets. Se evita depender de una base de zonas horarias en Windows.
    """
    return datetime.datetime(
        fecha.year, fecha.month, fecha.day, 18, 0, tzinfo=datetime.timezone.utc
    )


def _canonica(clave: str) -> str:
    return PLIEGUE_LEGADO.get(clave, clave)


def base_por_categoria(fecha: datetime.date) -> dict[str, float]:
    """
    Aporte del dia por categoria SIN contar la captura manual: suma
    `lineas.subtotal` de las lineas `tipo = 'categoria'` de las ventas de
    la fecha con `origen != 'resumen_manual'`. Las claves legadas se
    pliegan a las canonicas.
    """
    sql = f"""
        SELECT l.categoria AS clave, SUM(l.subtotal) AS monto
        FROM `{TABLA_VENTA}` v, UNNEST(v.lineas) l
        WHERE {_RANGO}
            AND l.tipo = 'categoria'
            AND v.origen != '{ORIGEN}'
        GROUP BY clave
    """
    base = {cat: 0.0 for cat in CATEGORIAS}
    for fila in ejecutar_query(sql, {"fecha": fecha}, {"fecha": "DATE"}):
        clave = _canonica((fila["clave"] or "").lower())
        if clave in base:
            base[clave] += float(fila["monto"] or 0)
    return base


def capturas_manuales(fecha: datetime.date) -> list[dict]:
    """
    Filas `origen = 'resumen_manual'` de la fecha (ventas y reversiones),
    tal cual estan en `venta`. Quien llama decide cuales revertir.
    """
    sql = f"""
        SELECT id, total, venta_original_id, lineas
        FROM `{TABLA_VENTA}`
        WHERE {_RANGO} AND origen = '{ORIGEN}'
        ORDER BY creado_en
    """
    return ejecutar_query(sql, {"fecha": fecha}, {"fecha": "DATE"})


def _linea(categoria: str, subtotal: float) -> dict:
    return {
        "tipo": "categoria",
        "categoria": categoria,
        "cantidad": 1,
        "precio_unitario": subtotal,
        "subtotal": subtotal,
    }


def _reversion(
    original: dict,
    usuario_id: str,
    instante: datetime.datetime,
    ahora: datetime.datetime,
) -> dict:
    # `fecha_hora` = `instante` (el mismo dia civil que la captura que se
    # revierte): las agregaciones agrupan por DATE(fecha_hora, zona), asi
    # que fecharla en `ahora` meteria el neto negativo en el dia de HOY y
    # descuadraria tanto el dia editado como el dia en curso. `cancelada_en`
    # si es `ahora`: es metadato de auditoria (cuando se hizo la edicion).
    lineas = [
        {**l, "cantidad": -float(l["cantidad"]), "subtotal": -float(l["subtotal"])}
        for l in (original.get("lineas") or [])
    ]
    return construir_venta(
        {
            "id": str(uuid.uuid5(_NAMESPACE, f"{original['id']}:reversion")),
            "fecha_hora": instante,
            "total": -float(original["total"]),
            "metodo_pago": METODO_PAGO,
            "usuario_id": usuario_id,
            "estado": "cancelada",
            "origen": ORIGEN,
            "venta_original_id": original["id"],
            "motivo_cancelacion": "reemplazo de resumen diario",
            "cancelada_por": usuario_id,
            "cancelada_en": ahora,
            "lineas": lineas,
        }
    )


def guardar(fecha: datetime.date, objetivo: dict[str, float], usuario_id: str | None = None) -> dict:
    """
    Reconcilia el dia contra `objetivo` (dict categoria -> monto, se
    asume ya validado y con las claves canonicas). Devuelve un resumen
    del dia tras la operacion: {fecha, total, categorias: [{clave, monto}]}.
    """
    usuario_id = usuario_id or USUARIO_POR_DEFECTO
    base = base_por_categoria(fecha)
    manuales = capturas_manuales(fecha)

    revertidos_ya = {
        m["venta_original_id"] for m in manuales if m.get("venta_original_id")
    }
    vigentes = [
        m
        for m in manuales
        if not m.get("venta_original_id") and m["id"] not in revertidos_ya
    ]
    # `n` para el id determinista: cuantas ventas manuales (no reversiones)
    # hubo ya en la fecha, revertidas o no.
    n = sum(1 for m in manuales if not m.get("venta_original_id"))

    ahora = datetime.datetime.now(datetime.timezone.utc)
    instante = _instante(fecha)

    filas = [_reversion(m, usuario_id, instante, ahora) for m in vigentes]

    lineas_nuevas = [
        _linea(cat, round(objetivo[cat] - base[cat], 2))
        for cat in CATEGORIAS
        if round(objetivo[cat] - base[cat], 2) != 0
    ]
    if lineas_nuevas:
        filas.append(
            construir_venta(
                {
                    "id": str(uuid.uuid5(_NAMESPACE, f"resumen-diario:{fecha.isoformat()}:{n}")),
                    "fecha_hora": instante,
                    "total": sum(l["subtotal"] for l in lineas_nuevas),
                    "metodo_pago": METODO_PAGO,
                    "usuario_id": usuario_id,
                    "estado": "activa",
                    "origen": ORIGEN,
                    "lineas": lineas_nuevas,
                }
            )
        )

    if filas:
        insertar_filas(TABLA_VENTA, filas)

    categorias = [{"clave": cat, "monto": round(objetivo[cat], 2)} for cat in CATEGORIAS]
    return {
        "fecha": fecha.isoformat(),
        "total": round(sum(objetivo[cat] for cat in CATEGORIAS), 2),
        "categorias": categorias,
    }
