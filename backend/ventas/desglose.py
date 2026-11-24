"""
Desglose de un conjunto de ventas por categoria y por metodo de pago.

Compartido entre el cierre de dia (almacen_local/cierres.py) y el
dashboard del dia (reportes/dashboard.py) para que las dos vistas
cuenten lo mismo.

Regla (la misma de #34): el desglose por categoria suma
`lineas.subtotal` de cada linea `tipo == 'categoria'`, NO el `total` de
la venta contra su primera linea -- ese atajo repartia mal una venta
con varias lineas de categoria.

El desglose por categoria devuelve SIEMPRE las categorias canonicas
completas (utilidades/categorias.py), en su orden, aunque ese dia no se
haya vendido nada de alguna: el negocio quiere ver la lista entera para
saber de un vistazo que quedo en cero, no que la fila desaparezca.
Cualquier clave que aparezca en los datos y no este en la lista (legado,
`sin_categoria`) se muestra al final, no se pierde.
"""

from utilidades import categorias as cat


def por_categoria(ventas: list) -> list:
    """[{clave, monto}] sumando el subtotal de las lineas de categoria."""
    totales: dict[str, float] = {clave: 0.0 for clave in cat.CLAVES}
    for venta in ventas:
        for linea in venta.get("lineas", []):
            if linea.get("tipo") != "categoria":
                continue
            clave = cat.canonica((linea.get("categoria") or "sin_categoria").lower())
            totales[clave] = totales.get(clave, 0.0) + float(linea["subtotal"])
    return [{"clave": clave, "monto": monto} for clave, monto in totales.items()]


def por_metodo_pago(ventas: list) -> list:
    """[{clave, monto}] sumando el total de cada venta por metodo de pago."""
    totales: dict[str, float] = {}
    for venta in ventas:
        clave = venta.get("metodo_pago") or "sin_metodo"
        totales[clave] = totales.get(clave, 0.0) + float(venta["total"])
    return [{"clave": clave, "monto": monto} for clave, monto in totales.items()]
