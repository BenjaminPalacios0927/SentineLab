"""
create_admin.py
================
Crea el primer usuario administrador en la tabla `users`.

La tabla `users` (login de la aplicación) nunca se crea ni se
puebla automáticamente desde la app — a diferencia de
device_users, attendance_raw e ia_suggestions_pool, que se
auto-crean solas la primera vez que se usan. Este script cubre
ese hueco: sin él, nadie puede iniciar sesión en una base de
datos nueva.

Uso:
    1. Ejecuta primero schema.sql contra tu base de datos
       (crea la tabla `users`, entre otras).
    2. Asegúrate de tener un db.cfg válido en esta misma carpeta
       (copia db.cfg.example y complétalo con tus credenciales).
    3. Corre:
           python create_admin.py
       y sigue las instrucciones en pantalla.

El script inserta al nuevo usuario con id = 0 si la tabla está
vacía, porque registros.py trata ese id como una cuenta protegida
que no se puede borrar desde la interfaz de administración.
"""
import getpass
import json
import os
import sys

try:
    import bcrypt
    import mysql.connector
except ImportError:
    print("Faltan dependencias. Instálalas con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

ROL_ADMIN = 0
ROL_USUARIO = 1


def cargar_db_config() -> dict:
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.cfg")
    if not os.path.exists(ruta):
        print(f"No se encontró {ruta}.")
        print("Copia db.cfg.example a db.cfg y completa tus credenciales antes de continuar.")
        sys.exit(1)
    with open(ruta, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["port"] = int(cfg["port"])
    return cfg


def main():
    print("=== Crear usuario administrador — SentineLab ===\n")
    cfg = cargar_db_config()

    try:
        conn = mysql.connector.connect(**cfg)
    except mysql.connector.Error as e:
        print(f"No se pudo conectar a la base de datos: {e}")
        sys.exit(1)

    cursor = conn.cursor(dictionary=True)

    # Aseguramos que la tabla exista por si no se corrió schema.sql
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id      INT AUTO_INCREMENT PRIMARY KEY,
            name    VARCHAR(100) NOT NULL UNIQUE,
            pasw    VARCHAR(255) NOT NULL,
            rol     TINYINT      NOT NULL DEFAULT 1,
            status  TINYINT      NOT NULL DEFAULT 1,
            `del`   TINYINT      NOT NULL DEFAULT 0
        )
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) AS n FROM users")
    tabla_vacia = cursor.fetchone()["n"] == 0

    nombre = input("Nombre de usuario para el administrador: ").strip()
    if not nombre:
        print("El nombre de usuario no puede estar vacío.")
        sys.exit(1)

    cursor.execute("SELECT id FROM users WHERE name = %s", (nombre,))
    if cursor.fetchone():
        print(f"Ya existe un usuario llamado '{nombre}'.")
        sys.exit(1)

    pwd = getpass.getpass("Contraseña: ")
    pwd_confirm = getpass.getpass("Confirma la contraseña: ")
    if not pwd or pwd != pwd_confirm:
        print("Las contraseñas no coinciden o están vacías.")
        sys.exit(1)

    pwd_hash = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()

    if tabla_vacia:
        # Primer usuario del sistema: se inserta con id=0, la cuenta
        # protegida que registros.py nunca deja eliminar desde la UI.
        cursor.execute(
            "INSERT INTO users (id, name, pasw, rol, status, `del`) "
            "VALUES (0, %s, %s, %s, 1, 0)",
            (nombre, pwd_hash, ROL_ADMIN),
        )
    else:
        cursor.execute(
            "INSERT INTO users (name, pasw, rol, status, `del`) "
            "VALUES (%s, %s, %s, 1, 0)",
            (nombre, pwd_hash, ROL_ADMIN),
        )

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\nUsuario administrador '{nombre}' creado correctamente.")
    print("Ya puedes iniciar sesión con estas credenciales desde la aplicación.")


if __name__ == "__main__":
    main()
