"""
Endpoint de captura manual del resumen de ventas de un dia
(pantalla de Ventas -> ModalVentaDia).

    POST /api/ventas/resumen-dia
    body: { fecha: "YYYY-MM-DD",
            categorias: [ { clave, monto }, ... ],
            gasto: 0 (opcional) }

`clave` es una de las claves canonicas de utilidades/categorias.py
(papeleria, copias, dulces, helados, recargas, sublimacion, limpieza,
terramar, otros);
`monto` es el TOTAL del dia para esa categoria (el modal es la autoridad
del dia, no un ajuste). La reconciliacion contra lo ya registrado vive
en acceso_datos/repositorios/resumen_diario.py.

`gasto` (columna "Gastos" del modal) es un egreso, no una venta: se
guarda aparte (acceso_datos/repositorios/gasto_dia.py) y solo sirve para
calcular, EN EL MODAL, el total del dia con descuento sobre 'papeleria'.
No afecta ninguna categoria de venta ni ningun reporte agregado (#34).

Solo se aceptan fechas de dias YA CERRADOS: de ayer hacia atras, y no mas
alla del anio anterior. El dia EN CURSO se registra en vivo desde la
pantalla de Vender (dashboard del dia, que lee el journal local); dejar
que el modal tambien lo edite crearia dos fuentes de verdad para "hoy"
que no cuadran mientras el sincronizador trabaja. Misma regla para el
gasto: GET /api/ventas/gasto-dia sirve para precargar el campo al abrir
el modal de un dia ya cerrado.
"""

import datetime

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity

import acceso_datos.repositorios.gasto_dia as gasto_repo
import acceso_datos.repositorios.resumen_diario as repo
from utilidades import zona_negocio


def _hoy_negocio() -> datetime.date:
    return zona_negocio.hoy()


def _fecha_en_rango(fecha: datetime.date) -> bool:
    hoy = _hoy_negocio()
    return fecha < hoy and fecha.year >= hoy.year - 1


def _parsear_fecha(datos_o_args) -> tuple[datetime.date | None, tuple | None]:
    """Valida 'fecha' con las mismas reglas para el GET y el POST de este modulo."""
    try:
        fecha = datetime.date.fromisoformat(datos_o_args.get("fecha", ""))
    except (TypeError, ValueError):
        return None, (jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400)

    if fecha >= _hoy_negocio():
        return None, (
            jsonify(
                error="El dia en curso se registra desde Vender; el resumen es para dias ya cerrados"
            ),
            400,
        )
    if not _fecha_en_rango(fecha):
        return None, (
            jsonify(error="Solo se pueden editar dias del anio en curso o el anterior"),
            400,
        )
    return fecha, None


def _monto_no_negativo(valor, campo: str):
    """Devuelve (monto, error_response). `error_response` es None si es valido."""
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        return None, (jsonify(error=f"monto invalido para {campo!r}"), 400)
    if monto < 0:
        return None, (jsonify(error=f"el monto de {campo!r} no puede ser negativo"), 400)
    return monto, None


def guardar_resumen_dia():
    datos = request.get_json(silent=True) or {}

    fecha, error = _parsear_fecha(datos)
    if error:
        return error

    categorias_entrada = datos.get("categorias")
    if not isinstance(categorias_entrada, list):
        return jsonify(error="'categorias' debe ser una lista de {clave, monto}"), 400

    objetivo = {cat: 0.0 for cat in repo.CATEGORIAS}
    for item in categorias_entrada:
        if not isinstance(item, dict):
            return jsonify(error="cada categoria es un objeto {clave, monto}"), 400
        clave = repo.PLIEGUE_LEGADO.get(item.get("clave"), item.get("clave"))
        if clave not in objetivo:
            return jsonify(error=f"categoria invalida: {item.get('clave')!r}"), 400
        monto, error = _monto_no_negativo(item.get("monto"), clave)
        if error:
            return error
        objetivo[clave] += monto

    # El gasto se valida ANTES de escribir nada: si es invalido, la
    # peticion se rechaza completa (400) sin dejar el resumen de
    # categorias guardado a medias sin su gasto.
    gasto, error = _monto_no_negativo(datos.get("gasto", 0), "gasto")
    if error:
        return error

    usuario_id = get_jwt_identity()
    resumen = repo.guardar(fecha, objetivo, usuario_id)
    gasto_guardado = gasto_repo.guardar(fecha, gasto, usuario_id)

    resumen["gasto"] = gasto_guardado["monto"]
    return jsonify(resumen), 200


def obtener_gasto_dia():
    """GET /api/ventas/gasto-dia?fecha=YYYY-MM-DD -- precarga el campo Gastos del modal."""
    fecha, error = _parsear_fecha(request.args)
    if error:
        return error

    return jsonify(fecha=fecha.isoformat(), gasto=gasto_repo.obtener(fecha))
