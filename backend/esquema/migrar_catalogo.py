"""
Migracion #9: catalogo legado -> esquema nuevo.

Copia `nuevas_tablas.catalogos` (19 productos, esquema viejo) a
`lapape.producto`, y convierte la columna `cantidad` -- que en el esquema
nuevo YA NO existe (#8: el stock es SUM(movimiento_inventario)) -- en un
movimiento de tipo 'inventario_inicial' por producto.

Lee del legado, nunca lo modifica. El dataset `nuevas_tablas` se conserva
intacto hasta que #9 y #10 esten validadas (ver esquema/tablas.py).

Mapeo de columnas (catalogos -> producto):
    id           -> id            (se conserva el UUID viejo, para trazar)
    nombre       -> nombre
    categoria    -> categoria
    marca        -> marca
    descripcion  -> descripcion
    imagen       -> imagen
    precio       -> precio        (FLOAT -> NUMERIC)
    codigoBarras -> codigo_barras
    cantidad     -> movimiento_inventario 'inventario_inicial' (no columna)
    papeleria    -> se descarta   (texto libre sin semantica; ver #11 y
                                   el docstring de catalogos/productos.py)
    categoriaVenta -> se descarta (NULL en las 19 filas)

Sin equivalente en el legado, se llenan por defecto:
    codigo_interno, costo, stock_minimo -> NULL
    activo -> TRUE
    creado_en / actualizado_en -> ahora (UTC)

Idempotencia: aborta si `lapape.producto` ya tiene filas, salvo --forzar.
No usa deduplicacion por id, asi que correrlo dos veces duplica.

Uso:
    cd backend
    python -m esquema.migrar_catalogo            # migra si producto esta vacio
    python -m esquema.migrar_catalogo --dry-run  # solo reporta, no escribe
    python -m esquema.migrar_catalogo --forzar   # migra aunque ya haya filas
"""

import argparse
import datetime
import decimal
import uuid

from acceso_datos.cliente import obtener_cliente
from acceso_datos.consultas import ejecutar_query
from acceso_datos.escrituras import insertar_filas
from esquema.tablas import DATASET
from utilidades import sucursal

TABLA_LEGADA = "nuevas_tablas.catalogos"
TABLA_PRODUCTO = f"{DATASET}.producto"
TABLA_MOVIMIENTO = f"{DATASET}.movimiento_inventario"

USUARIO_MIGRACION = "sistema"


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc)


def _numeric(valor):
    """FLOAT del legado -> Decimal, para no arrastrar ruido binario a NUMERIC."""
    if valor is None:
        return None
    return decimal.Decimal(str(valor))


def _leer_legado():
    proyecto = obtener_cliente().project
    return ejecutar_query(f"SELECT * FROM `{proyecto}.{TABLA_LEGADA}`")


def _contar_productos():
    return ejecutar_query(f"SELECT COUNT(*) AS n FROM `{TABLA_PRODUCTO}`")[0]["n"]


def _fila_producto(legado: dict, ahora):
    return {
        "id": legado["id"],
        "codigo_barras": legado.get("codigoBarras"),
        "codigo_interno": None,
        "nombre": legado["nombre"],
        "categoria": legado["categoria"],
        "marca": legado.get("marca"),
        "descripcion": legado.get("descripcion"),
        "imagen": legado.get("imagen"),
        "precio": _numeric(legado["precio"]),
        "costo": None,
        "stock_minimo": None,
        "activo": True,
        "creado_en": ahora,
        "actualizado_en": ahora,
    }


def _fila_movimiento(producto_id: str, cantidad, ahora):
    return {
        "id": str(uuid.uuid4()),
        "producto_id": producto_id,
        "tipo": "inventario_inicial",
        "cantidad": _numeric(cantidad),
        "costo_unitario": None,
        "referencia_id": None,
        "fecha": ahora,
        "usuario_id": USUARIO_MIGRACION,
    }


def migrar(dry_run: bool = False, forzar: bool = False):
    existentes = _contar_productos()
    if existentes and not forzar:
        raise SystemExit(
            f"`{TABLA_PRODUCTO}` ya tiene {existentes} fila(s). La migracion "
            "no es idempotente: correrla de nuevo duplicaria. Usa --forzar "
            "solo si sabes lo que haces (y limpiaste antes)."
        )

    legado = _leer_legado()
    ahora = _ahora()

    productos = [_fila_producto(fila, ahora) for fila in legado]

    movimientos = []
    sin_stock = []
    for fila in legado:
        cantidad = fila.get("cantidad")
        if cantidad is None or cantidad <= 0:
            sin_stock.append(fila["nombre"])
            continue
        movimientos.append(_fila_movimiento(fila["id"], cantidad, ahora))

    print(f"Leidas del legado: {len(legado)} filas de {TABLA_LEGADA}")
    print(f"  producto:               {len(productos)} filas a insertar")
    print(f"  movimiento_inventario:  {len(movimientos)} 'inventario_inicial'")
    if sin_stock:
        print(f"  sin movimiento (cantidad <= 0): {', '.join(sin_stock)}")

    if dry_run:
        print("\n--dry-run: no se escribio nada.")
        return

    insertar_filas(TABLA_PRODUCTO, productos)
    insertar_filas(TABLA_MOVIMIENTO, movimientos)
    print("\nMigracion completa.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migracion #9: catalogo legado.")
    parser.add_argument("--dry-run", action="store_true", help="Reporta, no escribe.")
    parser.add_argument(
        "--forzar", action="store_true", help="Migra aunque `producto` no este vacio."
    )
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion.")
    args = parser.parse_args()
    if not args.dry_run and not sucursal.confirmar_destino('migrar el catalogo legado a producto', si=args.si):
        print("Cancelado. No se escribio nada.")
        raise SystemExit(1)
    migrar(dry_run=args.dry_run, forzar=args.forzar)
