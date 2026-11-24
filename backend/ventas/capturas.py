"""
Captura de ventas para el punto de venta (#20).

La venta se confirma escribiendola en el journal local (#14) -- NUNCA
espera a BigQuery. Eso es lo que hace que "Enter" responda en
milisegundos y siga funcionando sin internet (#22, #55). La subida a
BigQuery ocurre despues, sola, en el sincronizador (#15).

Prioridad de este modulo: velocidad. La venta se anota DESPUES de que
el cliente ya pago (ver #20) -- la validacion es la minima necesaria
para no guardar basura, no un formulario estricto.
"""

import datetime

from flask import jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity

import acceso_datos.repositorios.movimientos_inventario as movimientos_repo
from almacen_local import cierres, journal
from utilidades import categorias, zona_negocio
from ventas import cancelaciones

# Lista canonica en utilidades/categorias.py (la misma que usa el resumen
# manual y que el frontend espeja en src/categorias.ts). Configurables
# desde un panel de administracion en #27.
CATEGORIAS_VALIDAS = categorias.CLAVES_VALIDAS
METODOS_PAGO_VALIDOS = {"efectivo", "transferencia", "tarjeta"}
TIPOS_LINEA_VALIDOS = {"categoria", "producto", "servicio", "recarga"}


def capturar_venta():
    datos = request.get_json(silent=True) or {}
    lineas_entrada = datos.get("lineas")

    if not lineas_entrada:
        return jsonify(error="La venta necesita al menos una linea"), 400

    metodo_pago = datos.get("metodo_pago", "efectivo")
    if metodo_pago not in METODOS_PAGO_VALIDOS:
        return jsonify(error=f"Metodo de pago invalido: {metodo_pago!r}"), 400

    lineas = []
    for indice, linea in enumerate(lineas_entrada):
        error = _validar_linea(linea)
        if error:
            return jsonify(error=f"Linea {indice + 1}: {error}"), 400
        lineas.append(_normalizar_entrada_linea(linea))

    total = sum(linea["subtotal"] for linea in lineas)
    detallada = any(linea["tipo"] == "producto" for linea in lineas)

    # Si el dia ya se cerro (automatico a la hora de cierre, o manual) y el
    # negocio sigue vendiendo, la venta NUNCA se rechaza -- eso violaria
    # el principio central de #22 (nunca detener una venta). Se marca
    # como extemporanea para que quede visible que paso despues del
    # cierre; reconciliar esos casos es #54, que todavia no existe.
    extemporanea = cierres.ya_cerrado(zona_negocio.hoy())

    advertencias = _advertencias_de_stock(lineas)

    fila = journal.escribir_venta(
        {
            "total": total,
            "metodo_pago": metodo_pago,
            "usuario_id": get_jwt_identity(),
            "vendedor": _nombre_vendedor(),
            "detallada": detallada,
            "origen": "pos",
            "extemporanea": extemporanea,
            "lineas": lineas,
        }
    )

    respuesta = _a_json(fila)
    if advertencias:
        respuesta["advertencias"] = advertencias
    return jsonify(respuesta), 201


def _nombre_vendedor():
    """
    Nombre de quien captura la venta. Viaja como claim del JWT (ver
    autentificacion/credenciales.py), asi no hace falta consultar a
    BigQuery -- el POS captura offline. `None` si el token no lo trae
    (tokens viejos) o si se llama fuera de una peticion con JWT.
    """
    try:
        return get_jwt().get("nombre")
    except RuntimeError:
        return None


def _advertencias_de_stock(lineas: list) -> list:
    """
    Aviso -- nunca un bloqueo -- si una linea de producto (#21) se vende
    con stock en cero o insuficiente. "El stock real manda, no el
    sistema": esta consulta es best-effort, se hace ANTES de escribir el
    journal (si el stock esta claramente al descubierto se prefiere que
    el cajero lo sepa de una vez) pero cualquier falla -- tipicamente sin
    internet, el caso normal de este POS -- se traga en silencio y la
    venta sigue su curso sin advertencias, nunca con un error.
    """
    producto_ids = [l["producto_id"] for l in lineas if l["tipo"] == "producto"]
    if not producto_ids:
        return []

    try:
        stock_por_id = movimientos_repo.stock_de_varios(producto_ids)
    except Exception:  # noqa: BLE001 -- cualquier falla de red/API cuenta
        return []

    advertencias = []
    for linea in lineas:
        if linea["tipo"] != "producto":
            continue
        # SUM() de una columna NUMERIC llega como Decimal; restarle un
        # float truena, asi que se normaliza antes de comparar.
        stock = float(stock_por_id.get(linea["producto_id"], 0))
        if stock - linea["cantidad"] < 0:
            advertencias.append(
                f"Producto {linea['producto_id']}: stock actual ({stock}) "
                f"menor a la cantidad vendida ({linea['cantidad']})"
            )
    return advertencias


def _validar_linea(linea: dict):
    if not isinstance(linea, dict):
        return "formato invalido"

    tipo = linea.get("tipo", "categoria")
    if tipo not in TIPOS_LINEA_VALIDOS:
        return f"tipo invalido: {tipo!r}"

    if tipo == "categoria" and linea.get("categoria") not in CATEGORIAS_VALIDAS:
        return f"categoria invalida: {linea.get('categoria')!r}"
    if tipo == "producto" and not linea.get("producto_id"):
        return "falta producto_id"
    if tipo == "servicio" and not linea.get("servicio_id"):
        return "falta servicio_id"
    if tipo == "recarga" and linea.get("monto_comision") is None:
        return "una recarga necesita monto_comision"

    try:
        monto = float(linea.get("monto", linea.get("subtotal", 0)))
    except (TypeError, ValueError):
        return "monto invalido"
    if monto <= 0:
        return "el monto debe ser mayor a cero"

    return None


def _normalizar_entrada_linea(linea: dict) -> dict:
    monto = float(linea.get("monto", linea.get("subtotal", 0)))
    return {
        "tipo": linea.get("tipo", "categoria"),
        "categoria": linea.get("categoria"),
        "producto_id": linea.get("producto_id"),
        "servicio_id": linea.get("servicio_id"),
        "descripcion": linea.get("descripcion"),
        "cantidad": float(linea.get("cantidad", 1)),
        "precio_unitario": monto,
        "costo_unitario": None,
        "subtotal": monto,
        "monto_comision": (
            float(linea["monto_comision"]) if linea.get("monto_comision") is not None else None
        ),
    }


def listar_ventas_del_dia():
    fecha_texto = request.args.get("fecha")
    if fecha_texto:
        try:
            fecha = datetime.date.fromisoformat(fecha_texto)
        except ValueError:
            return jsonify(error="'fecha' debe tener formato YYYY-MM-DD"), 400
    else:
        fecha = zona_negocio.hoy()

    ventas = journal.leer_dia(fecha)
    # El total suma TODAS las filas (ventas + reversiones de #26 + filas de
    # edicion de monto): los ajustes restan/suman por neteo. La lista, en
    # cambio, solo muestra las ventas reales, cada una marcada si esta
    # cancelada o editada. `cancelada` tiene precedencia sobre `editada`.
    total = sum(v["total"] for v in ventas)
    reales, canceladas_ids, editadas = cancelaciones.clasificar_ventas(ventas)
    for venta in reales:
        venta["cancelada"] = venta["id"] in canceladas_ids
        venta["editada"] = venta["id"] in editadas and not venta["cancelada"]
        if venta["editada"]:
            # El monto vigente manda: la venta se muestra con el ultimo valor.
            venta["total"] = editadas[venta["id"]]

    return jsonify(fecha=fecha.isoformat(), total=total, num_ventas=len(reales), ventas=reales)


def _a_json(fila: dict) -> dict:
    """
    fecha_hora/creado_en llegan como datetime real (no como texto) --
    journal.escribir_venta() los deja asi, journal.leer_dia() en cambio
    ya los regresa como texto ISO (los releyo de disco). Se normalizan
    aqui para que las dos rutas del API respondan en el mismo formato.
    """
    salida = dict(fila)
    for campo in ("fecha_hora", "creado_en"):
        valor = salida.get(campo)
        if isinstance(valor, (datetime.datetime, datetime.date)):
            salida[campo] = valor.isoformat()
    return salida
