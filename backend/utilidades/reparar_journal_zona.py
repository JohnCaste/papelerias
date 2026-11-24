"""
Repara los journals locales escritos antes del arreglo de zona horaria.

Hasta este cambio, `journal.escribir_venta` elegia el archivo del dia
con `fecha_hora.date()` sobre un datetime en UTC. Con UTC-6 eso corre
la frontera del dia a las 18:00 hora local: toda venta capturada de las
6pm en adelante quedo guardada en el archivo del dia SIGUIENTE (y por
eso aparecia al dia siguiente en "Ventas de hoy", y no entraba en el
cierre de su propio dia).

Este script relee todos los `ventas-*.jsonl`, recalcula a que dia del
negocio pertenece cada evento y reescribe los archivos con las ventas
en el dia correcto. Los eventos `confirmacion` viajan junto a la venta
que confirman (se busca su id), asi el estado 'enviada' se conserva.

    python -m utilidades.reparar_journal_zona            # muestra el plan
    python -m utilidades.reparar_journal_zona --aplicar  # lo ejecuta

Es idempotente: correrlo dos veces no cambia nada la segunda vez.
Antes de escribir nada, respalda la carpeta completa en
`journal_respaldo-<marca de tiempo>` al lado de la original.

NO toca BigQuery: alla las agregaciones siempre cortaron con
`DATE(fecha_hora, 'America/Mexico_City')`, asi que los datos subidos
estaban bien desde el principio.
"""

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

from almacen_local import journal
from utilidades import zona_negocio


def _leer_eventos(archivo: Path) -> list:
    eventos = []
    with open(archivo, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                eventos.append(json.loads(linea))
    return eventos


def planear(carpeta: Path) -> tuple[dict, dict]:
    """
    Devuelve (eventos_por_dia_correcto, resumen_de_movimientos).

    Primero se reparten las ventas por su dia real; despues cada
    `confirmacion` se manda al dia de la venta con ese id (si la venta
    no aparece en ningun archivo -- caso raro -- se deja donde estaba).
    """
    archivos = sorted(carpeta.glob("ventas-*.jsonl"))
    ventas = []          # (dia_original, evento)
    confirmaciones = []  # (dia_original, evento)

    for archivo in archivos:
        dia_original = datetime.date.fromisoformat(archivo.stem.removeprefix("ventas-"))
        for evento in _leer_eventos(archivo):
            if evento.get("evento") == "venta":
                ventas.append((dia_original, evento))
            else:
                confirmaciones.append((dia_original, evento))

    dia_de_venta = {}
    por_dia = {}
    movidas = {}

    for dia_original, evento in ventas:
        dia_real = zona_negocio.fecha_de(evento["fecha_hora"])
        dia_de_venta[evento["id"]] = dia_real
        por_dia.setdefault(dia_real, []).append(evento)
        if dia_real != dia_original:
            movidas[(dia_original, dia_real)] = movidas.get((dia_original, dia_real), 0) + 1

    for dia_original, evento in confirmaciones:
        destino = dia_de_venta.get(evento.get("id"), dia_original)
        por_dia.setdefault(destino, []).append(evento)

    # Orden estable dentro de cada archivo: la venta antes que su
    # confirmacion, y las ventas por hora.
    for dia, eventos in por_dia.items():
        eventos.sort(
            key=lambda e: (
                e.get("fecha_hora") or e.get("confirmado_en") or "",
                0 if e.get("evento") == "venta" else 1,
            )
        )

    return por_dia, movidas


def aplicar(carpeta: Path, por_dia: dict):
    marca = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    respaldo = carpeta.parent / f"{carpeta.name}_respaldo-{marca}"
    shutil.copytree(carpeta, respaldo)
    print(f"Respaldo en: {respaldo}")

    for archivo in carpeta.glob("ventas-*.jsonl"):
        archivo.unlink()

    for dia, eventos in sorted(por_dia.items()):
        destino = carpeta / f"ventas-{dia.isoformat()}.jsonl"
        with open(destino, "w", encoding="utf-8") as f:
            for evento in eventos:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios (sin esto solo muestra el plan)")
    parser.add_argument("--carpeta", default=None, help="Carpeta del journal (por defecto, la del sistema)")
    args = parser.parse_args(argv)

    carpeta = Path(args.carpeta) if args.carpeta else journal.CARPETA_POR_DEFECTO
    if not carpeta.exists():
        print(f"No existe la carpeta {carpeta}: nada que reparar.")
        return 0

    por_dia, movidas = planear(carpeta)

    if not movidas:
        print("Todos los journals ya estan en el dia correcto: nada que hacer.")
        return 0

    total = sum(movidas.values())
    print(f"{total} venta(s) guardadas en el dia equivocado:")
    for (origen, destino), cuantas in sorted(movidas.items()):
        print(f"  {cuantas:>4}  {origen} -> {destino}")

    if not args.aplicar:
        print("\n(Simulacion. Vuelve a correrlo con --aplicar para escribir los cambios.)")
        return 0

    aplicar(carpeta, por_dia)
    print("\nListo. Revisa el dia en la pantalla de Vender.")
    print("Si algun dia YA tenia acta de cierre, regenerala desde la pantalla")
    print("(o borra su cierre-<fecha>.jsonl) para que el acta cuadre con las ventas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
