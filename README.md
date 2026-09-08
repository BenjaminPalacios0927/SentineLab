# SentineLab · Sistema de Asistencia (Sistema Autónomo v2.0)

Aplicación de escritorio para gestión de asistencia mediante lector de huella
digital **ZKTeco K30**, con almacenamiento en una base de datos MySQL en la
nube (probado con [Railway](https://railway.app)) y generación de reportes,
análisis y sugerencias asistidas por un pool de reglas ("IA").

> Proyecto desarrollado como trabajo universitario. Se publica aquí como
> parte de un portafolio personal, con fines demostrativos. No recibe
> mantenimiento activo ni está pensado para producción.

---

## Contenido del repositorio

| Archivo                    | Descripción                                                       |
|-----------------------------|--------------------------------------------------------------------|
| `main.py`                  | Punto de entrada, login y ventana principal (PyQt6).               |
| `device_config.py`         | Configuración del lector de huella y de la base de datos.          |
| `hardware_handler.py`      | Controlador de comunicación con el lector ZKTeco K30 (`pyzk`).     |
| `registros.py`             | Alta/baja/edición de empleados, sincronización lector ↔ nube.      |
| `attendance_processor.py`  | Carga y procesamiento de los registros de asistencia.              |
| `qck_info.py`               | Vista rápida de información / reportes por empleado.               |
| `full_report.py`           | Reportes completos, exportación a Excel y PDF.                     |
| `advanced_analysis.py`     | Análisis avanzado y motor de sugerencias.                          |
| `interface_graphics.py`    | Elementos gráficos personalizados de la interfaz.                  |
| `SistemaAsistencia.spec`   | Configuración de PyInstaller para generar el ejecutable.           |
| `schema.sql`                | Esquema de la base de datos, reconstruido desde el código.        |
| `create_admin.py`          | Script para crear el primer usuario administrador.                 |
| `db.cfg.example`           | Plantilla de configuración de base de datos (sin credenciales).    |

---

## Requisitos

- Python 3.10+
- Un lector ZKTeco K30 accesible en red (opcional para probar solo la UI /
  reportes con datos ya cargados en la base de datos).
- Una base de datos MySQL accesible por red. Se desarrolló y probó usando
  [Railway](https://railway.app), pero funciona con cualquier proveedor
  MySQL (o un MySQL local).

## Instalación (modo desarrollo)

```bash
git clone <url-de-este-repositorio>
cd <carpeta-del-repositorio>

python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 1. Configurar la base de datos

Este repositorio **no incluye credenciales de ninguna base de datos**. Debes
usar la tuya propia:

```bash
cp db.cfg.example db.cfg
```

Edita `db.cfg` con tus propios datos de conexión:

```json
{
  "host": "tu-host",
  "port": "tu-puerto",
  "user": "tu-usuario",
  "password": "tu-password",
  "database": "tu-base-de-datos"
}
```

También puedes omitir este paso y configurar la conexión directamente desde
la interfaz (pantalla **Configuración de Hardware → Proveedor de base de
datos**), que guarda la configuración en:
- Windows: `%APPDATA%\SistemaAsistencia\db.cfg`
- Linux/Mac: `~/.config/SistemaAsistencia/db.cfg`

### 2. Crear el esquema de la base de datos

`schema.sql` contiene las cuatro tablas que usa la aplicación:
`users`, `device_users`, `attendance_raw` e `ia_suggestions_pool`
(reconstruidas a partir de las sentencias SQL que ya estaban embebidas en
el código — el propio archivo trae comentarios explicando de dónde salió
cada tabla). Ejecútalo contra tu base de datos vacía:

```bash
mysql -h <host> -P <puerto> -u <usuario> -p <basedatos> < schema.sql
```

De las cuatro tablas, tres se auto-crean solas la primera vez que la app
las necesita (`device_users`, `attendance_raw`, `ia_suggestions_pool`), así
que en la práctica este paso es opcional para ellas. La excepción es
**`users`** (la tabla de login): esa nunca se crea sola, así que este paso
sí es obligatorio si quieres poder iniciar sesión.

### 3. Crear el primer usuario administrador

Como `users` empieza vacía y las contraseñas se guardan como hash bcrypt
(nunca en texto plano), no hay forma de iniciar sesión la primera vez sin
sembrar un usuario. Para eso está `create_admin.py`:

```bash
python create_admin.py
```

Te pedirá un nombre de usuario y una contraseña, y creará la cuenta de
administrador con el hash correcto. Ya puedes iniciar sesión con ella desde
la aplicación.

### 4. Ejecutar en modo desarrollo

```bash
python main.py
```

Si no tienes un lector K30 conectado, la mayoría de las pantallas de
reportes y análisis igualmente funcionan siempre que existan datos en la
base de datos.

---

## Compilar el ejecutable (Windows)

El proyecto usa PyInstaller para generar un `.exe` que incluye una copia de
`db.cfg` como configuración de fábrica (se copia a `%APPDATA%` en el primer
arranque).

```bash
cp db.cfg.example db.cfg
# edita db.cfg con las credenciales que quieras distribuir de fábrica
pyinstaller SistemaAsistencia.spec
```

El ejecutable quedará en `dist/SistemaAsistencia/SistemaAsistencia.exe`.

> ⚠️ Cualquier credencial que pongas en `db.cfg` antes de compilar quedará
> embebida en el ejecutable. No distribuyas un `.exe` compilado con
> credenciales reales de una base de datos que quieras mantener privada.

---

## Notas sobre el hardware

`hardware_handler.py` usa la librería [`pyzk`](https://github.com/fananimi/pyzk)
para comunicarse con el lector ZKTeco K30 por red (TCP/UDP). La IP, puerto y
contraseña del dispositivo se configuran desde la pantalla de configuración
de hardware de la aplicación (no están hardcodeadas en el código).

---

## Estado del proyecto

Este proyecto fue desarrollado con fines académicos y **no se mantiene
activamente**. Existen soluciones comerciales de control de asistencia
mucho más completas y probadas en producción. Se publica como muestra de
código / portafolio, no como un producto listo para usar.

## Licencia

Sin licencia definida — uso educativo / de portafolio. Si quieres reutilizar
partes del código, contáctame.
