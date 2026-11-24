"""
Comando de linea: reconstruye y muestra las ventas del journal local
para un rango de fechas, sin tocar BigQuery (#14).

Sirve para dos cosas:
  - Auditar o recuperar a mano si algo se ve raro (por ejemplo, el
    total del dia en la pantalla no cuadra con lo que se recuerda).
  - Confirmar que el journal sigue siendo legible y consistente.

Uso:
    cd backend
    python -m almacen_local.reconstruir --dia 2026-08-31
    python -m almacen_local.reconstruir --desde 2026-08-01 --hasta 2026-08-31
"""

import argparse
import datetime

from almacen_local.journal import leer_dia, reconstruir_desde


def _parsear_fecha(texto: str) -> datetime.date:
    return datetime.date.fromisoformat(texto)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dia", type=_parsear_fecha, help="Un solo dia, YYYY-MM-DD")
    parser.add_argument("--desde", type=_parsear_fecha, help="Inicio del rango, YYYY-MM-DD")
    parser.add_argument("--hasta", type=_parsear_fecha, help="Fin del rango, YYYY-MM-DD")
    args = parser.parse_args(argv)

    if args.dia:
        ventas = leer_dia(args.dia)
    elif args.desde and args.hasta:
        ventas = reconstruir_desde(args.desde, args.hasta)
    else:
        parser.error("Especifica --dia, o --desde y --hasta")
        return

    total = sum(v["total"] for v in ventas)
    pendientes = [v for v in ventas if v["estado_local"] == "pendiente"]

    print(f"{len(ventas)} ventas, total {total:.2f}")
    print(f"{len(pendientes)} pendientes de subir a BigQuery")
    for v in ventas:
        marca = "pendiente" if v["estado_local"] == "pendiente" else "enviada "
        print(f"  [{marca}] {v['fecha_hora']}  {v['id'][:8]}  ${v['total']:.2f}  {v['metodo_pago']}")


if __name__ == "__main__":
    main()
