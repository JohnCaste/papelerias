"""
Script de un solo uso: re-hashea con bcrypt las contraseñas que sigan en
texto plano en `nuevas_tablas.login` (#3).

Complementa, no reemplaza, la re-hasheo perezoso que ya hace
`credenciales._verificar_password` en cada login exitoso. Corre esto
para cubrir de una vez a los usuarios que no han vuelto a iniciar
sesión, en vez de esperar a que cada quien entre por su cuenta.

Idempotente: una fila cuyo password ya tiene el prefijo de un hash de
bcrypt se deja intacta.

#1/#2 ya estan resueltos (llave revocada, historial purgado), asi que
correr esto contra el proyecto real ya no esta bloqueado por ahi -- es
parte del alcance de #3 y aun no se ha corrido.

Uso:
    cd backend
    python -m autentificacion.rehashear_passwords
"""

import bcrypt

from acceso_datos.consultas import ejecutar_query
from autentificacion.credenciales import PAPELERIA, TABLA_LOGIN_LEGADO, es_hash_bcrypt


def rehashear_todas():
    # Solo las filas de esta sucursal (ver credenciales.PAPELERIA).
    filas = ejecutar_query(
        f"SELECT id, nombre, password FROM `{TABLA_LOGIN_LEGADO}` WHERE papeleria = @papeleria",
        {"papeleria": PAPELERIA},
    )

    actualizadas = 0
    for fila in filas:
        if es_hash_bcrypt(fila.get("password")):
            continue

        if not fila.get("password"):
            print(f"  aviso: usuario '{fila.get('nombre')}' sin password, se omite")
            continue

        nuevo_hash = bcrypt.hashpw(
            fila["password"].encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        ejecutar_query(
            f"UPDATE `{TABLA_LOGIN_LEGADO}` SET password = @password WHERE id = @id",
            {"password": nuevo_hash, "id": fila["id"]},
        )
        actualizadas += 1
        print(f"  rehasheado: {fila.get('nombre')}")

    print(f"Listo. {actualizadas} de {len(filas)} contraseñas rehasheadas.")


if __name__ == "__main__":
    rehashear_todas()
