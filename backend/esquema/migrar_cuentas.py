"""
Migracion #10: cuentas historicas (agregado diario) -> esquema nuevo.

Convierte cada fila de `nuevas_tablas.cuentas` -- una fila por dia con un
monto por categoria (copias, dulces, helados, recargas, productos) -- en
una `venta` del esquema de #8, con `detallada = false` y
`origen = 'migracion'`. No hay producto ni servicio detras: cada
categoria con monto distinto de cero se materializa como una linea
`tipo = 'categoria'`.

Lee del legado, nunca lo modifica. El dataset `nuevas_tablas` se conserva
intacto (ver esquema/tablas.py).

Mapeo (cuentas -> venta):
    id                    -> venta.id = 'migracion-' + id   (traza el origen)
    fecha (DATE)          -> fecha_hora = medianoche UTC de ese dia
    copias / dulces /
      helados / recargas /
      productos           -> una linea 'categoria' por monto no NULL y != 0
    papeleria, telefono   -> se descartan

Sin equivalente en el legado, valores fijos:
    metodo_pago -> 'desconocido'   usuario_id  -> 'sistema'
    estado      -> 'activa'        detallada   -> False   extemporanea -> False

Reglas:
    - Una fila de `cuentas` con TODAS las categorias en 0/NULL no genera venta.
    - Una fila con `fecha` NULL se descarta (una venta sin fecha no sirve
      para los reportes).
    - Varias filas del legado pueden compartir `fecha`: cada una es su
      propia venta (el id no colisiona porque viene del id legado).

Idempotencia: aborta si `lapape.venta` ya tiene filas con
`origen = 'migracion'`, salvo --forzar. No deduplica: correrlo dos veces
con --forzar duplica.

Al terminar (si no es --dry-run) verifica el cuadre por anio: el total de
las ventas migradas contra la suma de categorias de `cuentas`, anio por
anio. Si algun anio no cuadra, imprime el detalle y sale con codigo != 0.

Uso:
    cd backend
    python -m esquema.migrar_cuentas            # migra si no hay ventas migradas
    python -m esquema.migrar_cuentas --dry-run  # reporta, no escribe
    python -m esquema.migrar_cuentas --forzar   # migra aunque ya haya migradas
"""

import argparse
import datetime

from acceso_datos.cliente import obtener_cliente
from acceso_datos.consultas import ejecutar_query
from acceso_datos.escrituras import insertar_filas
from acceso_datos.modelos_venta import construir_venta
from esquema.tablas import DATASET
from utilidades import sucursal

TABLA_LEGADA = "nuevas_tablas.cuentas"
TABLA_VENTA = f"{DATASET}.venta"

USUARIO_MIGRACION = "sistema"
METODO_PAGO_MIGRACION = "desconocido"

# Columna en `cuentas` -> descripcion legible de la linea de venta.
CATEGORIAS = {
    "productos": "Productos",
    "copias": "Copias",
    "dulces": "Dulces",
    "helados": "Helados",
    "recargas": "Recargas",
}


def _proyecto():
    return obtener_cliente().project


def _leer_legado():
    return ejecutar_query(f"SELECT * FROM `{_proyecto()}.{TABLA_LEGADA}`")


def _contar_migradas():
    sql = f"SELECT COUNT(*) AS n FROM `{TABLA_VENTA}` WHERE origen = 'migracion'"
    return ejecutar_query(sql)[0]["n"]


def _lineas_de(fila: dict) -> list:
    """Una linea 'categoria' por cada monto de categoria no NULL y != 0."""
    lineas = []
    for columna, descripcion in CATEGORIAS.items():
        monto = fila.get(columna)
        if monto is None or monto == 0:
            continue
        lineas.append(
            {
                "tipo": "categoria",
                "categoria": columna,
                "descripcion": descripcion,
                "cantidad": 1,
                "precio_unitario": monto,
                "subtotal": monto,
            }
        )
    return lineas


def _venta_de(fila: dict):
    """
    Fila de `venta` lista para insertar, o None si la fila legada no debe
    migrarse (sin fecha, o sin ninguna categoria con monto).
    """
    if fila.get("fecha") is None:
        return None
    lineas = _lineas_de(fila)
    if not lineas:
        return None

    fecha = fila["fecha"]
    fecha_hora = datetime.datetime(
        fecha.year, fecha.month, fecha.day, tzinfo=datetime.timezone.utc
    )
    total = sum(linea["subtotal"] for linea in lineas)

    return construir_venta(
        {
            "id": f"migracion-{fila['id']}",
            "fecha_hora": fecha_hora,
            "total": total,
            "metodo_pago": METODO_PAGO_MIGRACION,
            "usuario_id": USUARIO_MIGRACION,
            "estado": "activa",
            "detallada": False,
            "origen": "migracion",
            "extemporanea": False,
            "lineas": lineas,
        }
    )


def _descartes(legado: list):
    """(ids sin fecha, ids con fecha pero sin ninguna categoria con monto)."""
    sin_fecha = [f["id"] for f in legado if f.get("fecha") is None]
    sin_montos = [
        f["id"] for f in legado if f.get("fecha") is not None and not _lineas_de(f)
    ]
    return sin_fecha, sin_montos


def _cuadre_legado_por_anio() -> dict:
    sql = f"""
        SELECT
          EXTRACT(YEAR FROM fecha) AS anio,
          SUM(
            IFNULL(productos, 0) + IFNULL(copias, 0) + IFNULL(dulces, 0)
            + IFNULL(helados, 0) + IFNULL(recargas, 0)
          ) AS total
        FROM `{_proyecto()}.{TABLA_LEGADA}`
        WHERE fecha IS NOT NULL
        GROUP BY anio
    """
    return {fila["anio"]: float(fila["total"]) for fila in ejecutar_query(sql)}


def _cuadre_migrado_por_anio(ventas: list) -> dict:
    por_anio: dict = {}
    for venta in ventas:
        anio = venta["fecha_hora"].year
        por_anio[anio] = por_anio.get(anio, 0.0) + venta["total"]
    return por_anio


def _verificar_cuadre_anual(ventas: list):
    """
    Compara, anio por anio, el total de lo migrado contra la suma de
    categorias de `cuentas`. El total migrado se calcula sobre las filas
    recien construidas (no re-consultando `venta`) para no chocar con el
    buffer de streaming de BigQuery, que tarda en exponer lo insertado.
    """
    legado = _cuadre_legado_por_anio()
    migrado = _cuadre_migrado_por_anio(ventas)

    descuadres = []
    print("\nCuadre anual (legado vs migrado):")
    for anio in sorted(set(legado) | set(migrado)):
        t_legado = round(legado.get(anio, 0.0), 2)
        t_migrado = round(migrado.get(anio, 0.0), 2)
        ok = t_legado == t_migrado
        print(f"  {anio}: legado={t_legado}  migrado={t_migrado}  [{'ok' if ok else 'DESCUADRE'}]")
        if not ok:
            descuadres.append((anio, t_legado, t_migrado))

    if descuadres:
        detalle = "; ".join(
            f"{a}: legado {tl} vs migrado {tm} (dif {round(tm - tl, 2)})"
            for a, tl, tm in descuadres
        )
        raise SystemExit(f"Cuadre anual FALLIDO -> {detalle}")

    print("Cuadre anual OK: todos los anios coinciden.")


def migrar(dry_run: bool = False, forzar: bool = False):
    existentes = _contar_migradas()
    if existentes and not forzar:
        raise SystemExit(
            f"`{TABLA_VENTA}` ya tiene {existentes} venta(s) con "
            "origen = 'migracion'. La migracion no deduplica: correrla de "
            "nuevo duplicaria. Usa --forzar solo si limpiaste antes "
            "(DELETE FROM venta WHERE origen = 'migracion')."
        )

    legado = _leer_legado()
    ventas = [v for v in (_venta_de(fila) for fila in legado) if v is not None]
    sin_fecha, sin_montos = _descartes(legado)

    print(f"Leidas del legado: {len(legado)} filas de {TABLA_LEGADA}")
    print(f"  venta:  {len(ventas)} filas a insertar (origen = 'migracion')")
    if sin_fecha:
        print(f"  descartadas sin fecha: {len(sin_fecha)} -> {', '.join(sin_fecha)}")
    if sin_montos:
        print(
            f"  descartadas sin categorias con monto: {len(sin_montos)} -> "
            f"{', '.join(sin_montos)}"
        )

    if dry_run:
        print("\n--dry-run: no se escribio nada.")
        return

    insertar_filas(TABLA_VENTA, ventas)
    print(f"\nInsertadas {len(ventas)} ventas en `{TABLA_VENTA}`.")

    _verificar_cuadre_anual(ventas)
    print("\nMigracion completa.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migracion #10: cuentas historicas.")
    parser.add_argument("--dry-run", action="store_true", help="Reporta, no escribe.")
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Migra aunque ya existan ventas con origen='migracion'.",
    )
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion.")
    args = parser.parse_args()
    if not args.dry_run and not sucursal.confirmar_destino('migrar las cuentas historicas a venta', si=args.si):
        print("Cancelado. No se escribio nada.")
        raise SystemExit(1)
    migrar(dry_run=args.dry_run, forzar=args.forzar)
