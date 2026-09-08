# SentineLab · Attendance System (Sistema Autónomo v2.0)

*[Leer en español](README.es.md)*

Desktop application for attendance management using a **ZKTeco K30**
fingerprint reader, with storage in a cloud MySQL database (tested with
[Railway](https://railway.app)) and reporting, analysis, and rule-based
("AI") suggestions.

> This project was built as a university assignment. It's published here
> as part of a personal portfolio, for demonstration purposes. It is not
> actively maintained and is not intended for production use.

---

## Repository contents

| File                        | Description                                                        |
|-----------------------------|----------------------------------------------------------------------|
| `main.py`                  | Entry point, login screen, and main window (PyQt6).                 |
| `device_config.py`         | Fingerprint reader and database configuration.                      |
| `hardware_handler.py`      | Communication controller for the ZKTeco K30 reader (`pyzk`).        |
| `registros.py`             | Employee create/edit/delete, reader ↔ cloud sync.                   |
| `attendance_processor.py`  | Loading and processing of attendance records.                       |
| `qck_info.py`               | Quick info view / per-employee reports.                             |
| `full_report.py`           | Full reports, Excel and PDF export.                                  |
| `advanced_analysis.py`     | Advanced analysis and suggestion engine.                            |
| `interface_graphics.py`    | Custom graphical UI elements.                                        |
| `SistemaAsistencia.spec`   | PyInstaller build configuration for the executable.                  |
| `schema.sql`                | Database schema, reconstructed from the code.                       |
| `create_admin.py`          | Script to create the first administrator user.                       |
| `db.cfg.example`           | Database configuration template (no credentials).                   |

---

## Requirements

- Python 3.10+
- A ZKTeco K30 reader reachable on the network (optional if you only want
  to try the UI / reports with data already loaded in the database).
- A MySQL database reachable over the network. It was developed and
  tested using [Railway](https://railway.app), but it works with any
  MySQL-compatible provider (or a local MySQL instance).

## Installation (development mode)

```bash
git clone <this-repository-url>
cd <repository-folder>

python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 1. Configure the database

This repository **does not include credentials for any database**. You
need to use your own:

```bash
cp db.cfg.example db.cfg
```

Edit `db.cfg` with your own connection details:

```json
{
  "host": "your-host",
  "port": "your-port",
  "user": "your-user",
  "password": "your-password",
  "database": "your-database"
}
```

You can also skip this step and configure the connection directly from the
UI (**Hardware Configuration → Database Provider** screen), which saves
the configuration to:
- Windows: `%APPDATA%\SistemaAsistencia\db.cfg`
- Linux/Mac: `~/.config/SistemaAsistencia/db.cfg`

### 2. Create the database schema

`schema.sql` contains the four tables the application uses: `users`,
`device_users`, `attendance_raw`, and `ia_suggestions_pool` (reconstructed
from the SQL statements already embedded in the code — the file itself
includes comments explaining where each table came from). Run it against
your empty database:

```bash
mysql -h <host> -P <port> -u <user> -p <database> < schema.sql
```

Of the four tables, three are created automatically the first time the
app needs them (`device_users`, `attendance_raw`, `ia_suggestions_pool`),
so in practice this step is optional for those. The exception is
**`users`** (the login table): it is never created automatically, so this
step is required if you want to be able to log in.

### 3. Create the first administrator user

Since `users` starts out empty and passwords are stored as bcrypt hashes
(never in plain text), there's no way to log in the first time without
seeding a user. That's what `create_admin.py` is for:

```bash
python create_admin.py
```

It will ask for a username and password, and create the administrator
account with the correct hash. You can then log in with it from the
application.

### 4. Run in development mode

```bash
python main.py
```

If you don't have a K30 reader connected, most of the reporting and
analysis screens will still work as long as there's data in the database.

---

## Building the executable (Windows)

The project uses PyInstaller to generate a `.exe` that bundles a copy of
`db.cfg` as factory-default configuration (it's copied to `%APPDATA%` on
first run).

```bash
cp db.cfg.example db.cfg
# edit db.cfg with whatever credentials you want to ship as factory defaults
pyinstaller SistemaAsistencia.spec
```

The executable will end up at `dist/SistemaAsistencia/SistemaAsistencia.exe`.

> ⚠️ Any credentials you put in `db.cfg` before building will be embedded
> in the executable. Don't distribute a compiled `.exe` with real
> credentials for a database you want to keep private.

---

## Notes on the hardware

`hardware_handler.py` uses the [`pyzk`](https://github.com/fananimi/pyzk)
library to communicate with the ZKTeco K30 reader over the network
(TCP/UDP). The device's IP, port, and password are configured from the
app's hardware configuration screen (they are not hardcoded in the code).

---

## Project status

This project was built for academic purposes and **is not actively
maintained**. There are far more complete, production-tested commercial
attendance-tracking solutions available. It's published here as a code
sample / portfolio piece, not as a ready-to-use product.

## License

No license specified — for educational / portfolio use. If you'd like to
reuse parts of the code, feel free to reach out.
