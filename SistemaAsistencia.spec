# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
# ============================================================
# SistemaAsistencia.spec  —  PyInstaller build file
# Generado para: Sistema Autónomo v2.0
#
# Para compilar, ejecuta desde la carpeta del proyecto:
#   pyinstaller SistemaAsistencia.spec
#
# El ejecutable quedará en:
#   dist/SistemaAsistencia/SistemaAsistencia.exe
# ============================================================

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # db.cfg se incluye junto al ejecutable como configuración de arranque.
        # En la primera ejecución, device_config.py lo detecta y lo copia
        # automáticamente a %APPDATA%\SistemaAsistencia\db.cfg.
        #
        # IMPORTANTE: este repositorio NO incluye un db.cfg real (por
        # seguridad). Antes de compilar, copia db.cfg.example a db.cfg
        # y coloca ahí las credenciales de tu propia base de datos.
        # Ver README.md, sección "Compilar el ejecutable".
        ('db.cfg', '.'),
    ],

    # -----------------------------------------------------------
    # hiddenimports: módulos que PyInstaller NO detecta solo
    # porque se cargan dinámicamente con importlib.import_module()
    # o están dentro de hilos / try-except en tiempo de ejecución.
    # -----------------------------------------------------------
    hiddenimports=[
        # Módulos propios del proyecto (carga lazy en abrir_modulo)
        'registros',
        'device_config',
        'interface_graphics',
        'hardware_handler',
        'qck_info',
        'full_report',
        'advanced_analysis',
        'attendance_processor',
        'zk',

        # mysql-connector-python completo — collect_submodules detecta
        # automáticamente locales.eng.client_error y cualquier otro
        # submódulo que se cargue dinámicamente en tiempo de ejecución,
        # evitando el error 'has no attribute client_error'.
        *collect_submodules('mysql'),
        *collect_submodules('mysql.connector'),

        # bcrypt
        'bcrypt',

        # PyQt6 — módulos auxiliares que a veces se pierden
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    # Excluir librerías pesadas que ya no se usan en el proyecto
    excludes=[
        'pytesseract',
        'tesseract',
        'PIL',
        'cv2',
        'numpy',
        'pandas',
        'matplotlib',
        'sklearn',
        'scipy',
        'tkinter',
    ],

    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SistemaAsistencia',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # Mantener en False es más estable
    console=False,          # <--- ESTO es lo más importante
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['SentineLab.ico'], # Asegúrate de que el archivo exista en la carpeta
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,                   # Desactiva UPX para consistencia
    upx_exclude=[],
    name='SistemaAsistencia',
)
