"""
Siembra la tabla `lapape.categoria` con la lista canonica de categorias
de producto y reasigna los productos existentes.

Que hace:
  1. Borra TODAS las filas actuales de `categoria`.
  2. Inserta CATEGORIAS en orden (columna 'orden' = posicion en la lista).
  3. Reasigna `producto.categoria = 'Escolar'` en todos los productos
     (las categorias viejas eran texto libre y no mapean 1:1 a la lista
     nueva; se decidio mandarlas todas a 'Escolar' por ahora y
     reclasificar producto por producto al editarlos).

La tabla `categoria` debe existir antes -- corre primero:
    cd backend
    python -m esquema.crear_dataset

Uso:
    cd backend
    python -m esquema.sembrar_categorias            # siembra y reasigna
    python -m esquema.sembrar_categorias --dry-run  # solo reporta
    python -m esquema.sembrar_categorias --no-reasignar-productos

Nota BigQuery: si se acaba de sembrar por streaming, las filas quedan un
rato en el streaming buffer y un DELETE inmediato podria no verlas.
Correr el script de nuevo pasados ~90 min limpia cualquier resto.
"""

import argparse
import datetime

import acceso_datos.repositorios.categorias as categorias_repo
from acceso_datos.consultas import ejecutar_query
from esquema.tablas import DATASET
from utilidades import sucursal

TABLA_PRODUCTO = f"{DATASET}.producto"

CATEGORIA_POR_DEFECTO = "Escolar"

CATEGORIAS = [
    "Lapiceros",
    "Lápices",
    "Marcatextos",
    "Plumones",
    "Pinturas de Madera",
    "Cuadernos",
    "Libretas",
    "Blocs",
    "Hojas",
    "Papeles",
    "Cartulinas",
    "Carpetas",
    "Sobres",
    "De Corte",
    "Adhesivos",
    "Cintas",
    "Geometría",
    "Correctores",
    "Gomas",
    "Sacapuntas",
    "Sujetapapeles",
    "Engrapado",
    "Perforación",
    "Organizadores",
    "Calculadoras",
    "Plastificado",
    "Etiquetas",
    "Manualidades",
    "Escolar",
    "Regalos",
    "Foami",
    "Tintas",
]


def _reasignar_productos():
    sql = f"""
        UPDATE `{TABLA_PRODUCTO}`
        SET categoria = @categoria, actualizado_en = @ahora
        WHERE TRUE
    """
    ejecutar_query(
        sql,
        {
            "categoria": CATEGORIA_POR_DEFECTO,
            "ahora": datetime.datetime.now(datetime.timezone.utc),
        },
    )


def sembrar(dry_run: bool = False, reasignar_productos: bool = True):
    print(f"Categorias a sembrar: {len(CATEGORIAS)}")
    for indice, nombre in enumerate(CATEGORIAS):
        print(f"  {indice:2d}  {nombre}")
    if reasignar_productos:
        print(f"\nSe reasignaran TODOS los productos a '{CATEGORIA_POR_DEFECTO}'.")

    if dry_run:
        print("\n--dry-run: no se escribio nada.")
        return

    categorias_repo.borrar_todas()
    categorias_repo.sembrar(CATEGORIAS)
    print(f"\n`{DATASET}.categoria`: {len(CATEGORIAS)} filas insertadas.")

    if reasignar_productos:
        _reasignar_productos()
        print(f"`{TABLA_PRODUCTO}`: categoria = '{CATEGORIA_POR_DEFECTO}' en todos.")

    print("\nListo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Siembra lapape.categoria.")
    parser.add_argument("--dry-run", action="store_true", help="Reporta, no escribe.")
    parser.add_argument(
        "--no-reasignar-productos",
        action="store_true",
        help="No toca producto.categoria; solo siembra la tabla categoria.",
    )
    parser.add_argument("--si", action="store_true", help="No pedir confirmacion.")
    args = parser.parse_args()
    if not args.dry_run and not sucursal.confirmar_destino('borrar y volver a sembrar las categorias', si=args.si):
        print("Cancelado. No se escribio nada.")
        raise SystemExit(1)
    sembrar(
        dry_run=args.dry_run,
        reasignar_productos=not args.no_reasignar_productos,
    )
