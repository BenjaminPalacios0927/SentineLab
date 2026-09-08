import os
import json
import mysql.connector
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QLabel, QFrame, QMessageBox,
                             QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QPainter, QColor

try:
    from interface_graphics import InterfaceGraphics
    GRAPHICS_AVAILABLE = True
except ImportError:
    GRAPHICS_AVAILABLE = False

# =========================================================
# ROLES DE USUARIO
# Fuente única de verdad para el sistema de permisos.
# registros.py y cualquier otro módulo importan desde aquí.
# =========================================================
ROL_ADMIN   = 0
ROL_USUARIO = 1

# =========================================================
# CONFIGURACIÓN DB — proveedor de nube
# connection_timeout / connect_timeout: tiempo máximo para
# establecer la conexión TCP (en segundos). Impide que el
# programa se congele en redes públicas.
#
# IMPORTANTE: este diccionario ya NO contiene credenciales
# reales. Es solo el valor de arranque que se usa la primera
# vez que el programa corre, antes de que el usuario guarde
# su propia configuración (ver guardar_config_db / db.cfg).
# La conexión real en tiempo de ejecución siempre se arma con
# cargar_config_db(), nunca leyendo este dict directamente.
# =========================================================
DB_CONFIG_DEFAULT = {
    'host':               '',
    'user':               '',
    'password':           '',
    'database':           '',
    'port':               3306,
    'connection_timeout': 10,
    'connect_timeout':    10,
}


# =========================================================
# GESTOR DE CONFIGURACIÓN PERSISTENTE DEL DISPOSITIVO
# Guarda en %APPDATA%/SistemaAsistencia/ (Windows) o
# ~/.config/SistemaAsistencia/ (Linux/Mac).
# El usuario nunca interactúa con este archivo directamente.
# =========================================================
def _ruta_config():
    """Devuelve la ruta completa del archivo de configuración."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.join(os.path.expanduser('~'), '.config')
    carpeta = os.path.join(base, 'SistemaAsistencia')
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, 'device.cfg')


def guardar_config_dispositivo(config: dict):
    """Escribe la configuración del lector en el archivo persistente."""
    try:
        with open(_ruta_config(), 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Advertencia: no se pudo guardar la configuración del dispositivo: {e}")


def cargar_config_dispositivo() -> dict:
    """
    Lee la configuración guardada. Devuelve {} si no existe
    o si el archivo está corrupto.
    """
    ruta = _ruta_config()
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# =========================================================
# GESTOR DE CONFIGURACIÓN PERSISTENTE DEL PROVEEDOR DE NUBE
# Mismo patrón que la config del dispositivo, pero en un
# archivo separado (db.cfg) para no mezclar credenciales de
# BD con la configuración del lector.
# =========================================================
def _ruta_config_db():
    """Devuelve la ruta completa del archivo de configuración de BD."""
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    else:
        base = os.path.join(os.path.expanduser('~'), '.config')
    carpeta = os.path.join(base, 'SistemaAsistencia')
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, 'db.cfg')


def _ruta_db_cfg_bundleada():
    """
    Devuelve la ruta del db.cfg que viaja dentro del paquete PyInstaller,
    o None si el programa está corriendo como script normal (desarrollo).

    PyInstaller expone sys.frozen = True cuando corre como ejecutable.
    En modo carpeta (COLLECT), los archivos de datas quedan junto al .exe.
    En modo archivo único, quedan en sys._MEIPASS (carpeta temporal).
    """
    import sys
    if not getattr(sys, 'frozen', False):
        return None
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    ruta = os.path.join(base, 'db.cfg')
    return ruta if os.path.exists(ruta) else None


def guardar_config_db(config: dict):
    """Escribe la configuración del proveedor de nube en el archivo persistente."""
    try:
        with open(_ruta_config_db(), 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Advertencia: no se pudo guardar la configuración de BD: {e}")


def cargar_config_db() -> dict:
    """
    Lee la configuración de BD en este orden de prioridad:

    1. %APPDATA%\\SistemaAsistencia\\db.cfg  — config guardada por el admin.
    2. db.cfg bundleado junto al ejecutable  — config de fábrica incluida en el
       instalable. En la primera ejecución se copia automáticamente a %APPDATA%
       para que la pantalla de admin pueda actualizarla desde la UI sin recompilar.
    3. DB_CONFIG_DEFAULT                     — valores vacíos si no hay nada.
    """
    ruta = _ruta_config_db()

    # Prioridad 1: configuración guardada por el admin
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                return {**DB_CONFIG_DEFAULT, **cfg}
        except Exception:
            pass

    # Prioridad 2: db.cfg bundleado (solo en ejecutable PyInstaller)
    bundleado = _ruta_db_cfg_bundleada()
    if bundleado:
        try:
            with open(bundleado, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            cfg_completo = {**DB_CONFIG_DEFAULT, **cfg}
            # Copiarlo a %APPDATA% para que futuras ediciones desde la UI persistan
            guardar_config_db(cfg_completo)
            return cfg_completo
        except Exception:
            pass

    # Prioridad 3: valores vacíos de arranque
    return dict(DB_CONFIG_DEFAULT)


def construir_db_config_conexion() -> dict:
    """
    Arma el dict listo para mysql.connector.connect(**cfg) a partir
    de la configuración guardada, normalizando tipos (puerto a int).
    """
    cfg = cargar_config_db()
    try:
        puerto = int(cfg.get('port', 3306) or 3306)
    except (TypeError, ValueError):
        puerto = 3306
    return {
        'host':               cfg.get('host', ''),
        'user':               cfg.get('user', ''),
        'password':           cfg.get('password', ''),
        'database':           cfg.get('database', ''),
        'port':               puerto,
        'connection_timeout': DB_CONFIG_DEFAULT['connection_timeout'],
        'connect_timeout':    DB_CONFIG_DEFAULT['connect_timeout'],
    }


# =========================================================
# ESTILOS COMPARTIDOS
# =========================================================
STYLE_LABEL_FIELD = (
    "color: #FFFFFF; font-family: Arial; "
    "font-size: 18px; font-weight: 600; background: transparent;"
)
STYLE_INPUT = (
    "QLineEdit { background: white; color: #000000; "
    "padding: 11px 14px; border-radius: 6px; font-size: 16px; border: 2px solid #CCCCCC; font-weight: 500; }"
    "QLineEdit:focus { background: white; border: 2px solid #0078D4; }"
    "QLineEdit::placeholder { color: #999999; }"
)
STYLE_COMBO = (
    "QComboBox { background: white; color: #000000; "
    "padding: 11px 14px; border-radius: 6px; font-size: 16px; border: 2px solid #CCCCCC; font-weight: 500; }"
    "QComboBox::drop-down { border: none; width: 20px; }"
    "QComboBox QAbstractItemView { background: white; color: #000000; "
    "selection-background-color: #0078D4; font-size: 16px; padding: 6px; }"
    "QComboBox:focus { border: 2px solid #0078D4; }"
)


# =========================================================
# CANVAS DE FONDO (mismo patrón que el resto del sistema)
# =========================================================
class CanvasFondo(QWidget):
    def __init__(self, parent, graphics_engine):
        super().__init__(parent)
        self.tiempo   = 0
        self.graphics = graphics_engine
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.graphics:
            self.graphics.dibujar_gradiente_animado(
                painter, self.width(), self.height(), self.tiempo
            )
        else:
            painter.fillRect(0, 0, self.width(), self.height(), QColor(30, 60, 114))
        self.tiempo += 1


# =========================================================
# HILO: CONEXIÓN AL LECTOR + DESCARGA INICIAL A RAILWAY
# =========================================================
class HiloConexionLector(QThread):
    progreso   = pyqtSignal(str)
    completado = pyqtSignal(object)  # emite (eventos, usuarios)
    error      = pyqtSignal(str)

    def __init__(self, nombre, ip, puerto, password, db_config):
        super().__init__()
        self.nombre    = nombre
        self.ip        = ip
        self.puerto    = int(puerto)
        self.password  = password
        self.db_config = db_config  # dict listo para mysql.connector.connect(**db_config)

    def run(self):
        try:
            from hardware_handler import K30Controller
            self.progreso.emit(f"Conectando a '{self.nombre}'...")

            ctrl = K30Controller(self.ip, self.puerto, password=self.password)
            if not ctrl.conectar():
                self.error.emit("No se pudo conectar al lector. Verifica los datos.")
                return

            # Descargar eventos de asistencia
            self.progreso.emit("Descargando eventos del lector...")
            eventos = ctrl.descargar_asistencias()

            # Descargar perfiles de usuarios
            self.progreso.emit("Descargando registros de usuarios...")
            usuarios = ctrl.obtener_usuarios()

            ctrl.desconectar()

            conn   = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()
            BATCH  = 100

            # Guardar eventos en lotes
            eventos_subidos = 0
            if eventos:
                self.progreso.emit(f"Subiendo {len(eventos)} eventos a la nube...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS attendance_raw (
                        id        INT AUTO_INCREMENT PRIMARY KEY,
                        user_id   VARCHAR(50),
                        timestamp DATETIME,
                        status    INT,
                        synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                filas = [(r['user_id'], r['timestamp'], r['status']) for r in eventos]
                for i in range(0, len(filas), BATCH):
                    lote = filas[i:i + BATCH]
                    cursor.executemany(
                        "INSERT INTO attendance_raw (user_id, timestamp, status) "
                        "VALUES (%s, %s, %s)",
                        lote
                    )
                    conn.commit()
                    eventos_subidos += len(lote)
                    self.progreso.emit(
                        f"Eventos: {eventos_subidos}/{len(filas)}..."
                    )

            # Guardar usuarios en lotes (upsert)
            usuarios_subidos = 0
            if usuarios:
                self.progreso.emit(f"Subiendo {len(usuarios)} registros de usuarios...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS device_users (
                        user_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
                        nombre       VARCHAR(100) NOT NULL,
                        departamento VARCHAR(100) DEFAULT \'\',
                        horario      INT          DEFAULT 0,
                        tiene_huella TINYINT      DEFAULT 0,
                        synced_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                filas_u = [
                    (
                        str(u['user_id']),
                        u.get('nombre', ''),
                        u.get('departamento', ''),
                        u.get('horario', 0),
                        1 if u.get('huella') else 0,
                    )
                    for u in usuarios
                ]
                for i in range(0, len(filas_u), BATCH):
                    lote = filas_u[i:i + BATCH]
                    cursor.executemany("""
                        INSERT INTO device_users
                            (user_id, nombre, departamento, horario, tiene_huella, synced_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            nombre       = VALUES(nombre),
                            departamento = VALUES(departamento),
                            horario      = VALUES(horario),
                            tiene_huella = VALUES(tiene_huella),
                            synced_at    = NOW()
                    """, lote)
                    conn.commit()
                    usuarios_subidos += len(lote)
                    self.progreso.emit(
                        f"Usuarios: {usuarios_subidos}/{len(filas_u)}..."
                    )

            cursor.close()
            conn.close()

            self.completado.emit((eventos_subidos, usuarios_subidos))

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except OSError as e:
            # Captura específicamente el [WinError 6] u otros fallos de hardware en Windows
            if getattr(e, 'winerror', None) == 6:
                self.error.emit("No se pudo conectar con el lector.")
            else:
                self.error.emit(f"Error de comunicación con el hardware: {str(e)}")
        except Exception as e:
            self.error.emit(str(e))


# =========================================================

# =========================================================
# RADIO BUTTON PERSONALIZADO (estilo ZKT — círculo relleno)
# =========================================================
class _RadioOpcion(QWidget):
    seleccionado = pyqtSignal()
    _RADIO = 8

    def __init__(self, texto, valor, parent=None):
        super().__init__(parent)
        self.valor   = valor
        self._activo = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.circulo = QLabel()
        self.circulo.setFixedSize(self._RADIO * 2, self._RADIO * 2)
        self._actualizar_circulo()

        lbl = QLabel(texto)
        lbl.setStyleSheet(
            "color: #FFFFFF; font-family: Arial; font-size: 16px; "
            "font-weight: 600; background: transparent;"
        )
        row.addWidget(self.circulo)
        row.addWidget(lbl)

    def _actualizar_circulo(self):
        r = self._RADIO
        if self._activo:
            self.circulo.setStyleSheet(
                f"background-color: white; border-radius: {r}px; border: 2px solid white;"
            )
        else:
            self.circulo.setStyleSheet(
                f"background-color: transparent; border-radius: {r}px; "
                f"border: 3px solid rgba(255,255,255,0.9);"
            )

    def set_seleccionado(self, valor: bool):
        self._activo = valor
        self._actualizar_circulo()

    def esta_seleccionado(self):
        return self._activo

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_seleccionado(True)
            self.seleccionado.emit()


# =========================================================
# PANTALLA 1 — MENÚ DE HARDWARE  (equivalente a PantallaMenuRegistros)
# =========================================================
class PantallaMenuHardware(QWidget):
    """
    Menú de entrada al módulo de hardware.
    • Todos los usuarios ven la tarjeta "Configuración del Lector".
    • Solo el administrador ve la tarjeta "Proveedor de Base de Datos".
    Sigue el mismo patrón de tarjetas que PantallaMenuRegistros.
    """

    def __init__(self, sesion, ir_lector_cb, ir_db_cb, volver_cb, parent=None):
        super().__init__(parent)
        self.es_admin    = sesion is not None and sesion.rol == ROL_ADMIN
        self.ir_lector   = ir_lector_cb
        self.ir_db       = ir_db_cb
        self.volver_cb   = volver_cb
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        titulo = QLabel("CONFIGURACIÓN DE HARDWARE")
        titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 55px; "
            "font-weight: bold; background: transparent;"
        )
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        sub = QLabel("Selecciona una opción para continuar")
        sub.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; "
            "font-size: 30px; background: transparent;"
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addStretch(1)

        # Fila de tarjetas
        cards_row = QHBoxLayout()
        cards_row.setSpacing(30)
        cards_row.addStretch(1)

        cards_row.addWidget(self._tarjeta(
            "🔌", "Configuración del Lector",
            "Conecta el dispositivo ZKT K30\ny sincroniza los registros con la nube",
            "Acceso completo" if self.es_admin else "Acceso limitado",
            "#2196F3",
            self.ir_lector,
        ))

        if self.es_admin:
            cards_row.addWidget(self._tarjeta(
                "☁️", "Proveedor de Base de Datos",
                "Configura el servidor de\nbase de datos en la nube",
                "Solo Administrador",
                "#4CAF50",
                self.ir_db,
            ))

        cards_row.addStretch(1)
        layout.addLayout(cards_row)

        layout.addStretch(1)

        # Botón volver
        btn_row = QHBoxLayout()
        btn_volver = QPushButton("← Menú principal")
        btn_volver.setStyleSheet("""
            QPushButton {
                background-color: rgb(255, 255, 255); color: rgb(24, 95, 165);
                font-family: Arial; font-size: 17px; font-weight: bold;
                padding: 14px 32px; border-radius: 10px;
                border: 2px solid rgb(24, 95, 165);
            }
            QPushButton:hover { background-color: rgb(230, 241, 251); }
        """)
        btn_volver.clicked.connect(self.volver_cb)
        btn_row.addWidget(btn_volver)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _tarjeta(self, icono, titulo, descripcion, badge, color_badge, callback):
        frame = QFrame()
        frame.setFixedSize(360, 420)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setStyleSheet("""
            QFrame {
                background-color: rgb(255, 255, 255);
                border-radius: 24px;
                border: 1px solid rgb(181, 212, 244);
            }
            QFrame:hover {
                background-color: rgb(230, 241, 251);
                border: 1px solid rgb(24, 95, 165);
            }
        """)

        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(30, 42, 30, 30)
        card_layout.setSpacing(15)

        lbl_icono = QLabel(icono)
        lbl_icono.setStyleSheet("font-size: 66px; background: transparent;")
        lbl_icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_icono)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 28px; "
            "font-weight: bold; background: transparent;"
        )
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setWordWrap(True)
        card_layout.addWidget(lbl_titulo)

        lbl_desc = QLabel(descripcion)
        lbl_desc.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; "
            "font-size: 21px; background: transparent;"
        )
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        card_layout.addWidget(lbl_desc)

        lbl_badge = QLabel(badge)
        lbl_badge.setStyleSheet(f"""
            color: white; background-color: {color_badge};
            font-family: Arial; font-size: 21px; font-weight: bold;
            padding: 6px 16px; border-radius: 12px;
        """)
        lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_badge.setFixedHeight(33)
        card_layout.addWidget(lbl_badge)

        card_layout.addStretch()

        btn = QPushButton("Abrir →")
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgb(24, 95, 165); color: white;
                font-family: Arial; font-size: 18px; font-weight: bold;
                padding: 18px 36px; border-radius: 8px; border: none;
            }
            QPushButton:hover { background-color: rgb(12, 68, 124); }
        """)
        btn.setMinimumHeight(52)
        btn.clicked.connect(callback)
        card_layout.addWidget(btn)

        return frame


# =========================================================
# PANTALLA 2 — CONFIGURACIÓN DEL LECTOR  (todos los usuarios)
# =========================================================
class PantallaLector(QWidget):
    """
    Formulario de conexión al lector ZKT K30.
    Visible para todos los roles. Usa la config de BD guardada
    por el admin (db.cfg) para la sincronización con la nube.
    """
    dispositivo_conectado = pyqtSignal(dict)

    def __init__(self, sesion, volver_cb, parent=None):
        super().__init__(parent)
        self.sesion    = sesion
        self.volver_cb = volver_cb
        self._hilo     = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()
        self._cargar_config_guardada()

    # ── Construcción de UI ──────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(16)

        titulo = QLabel("CONFIGURACIÓN DEL LECTOR")
        titulo.setStyleSheet(
            "color: #003d66; font-family: Arial; font-size: 30px; "
            "font-weight: bold; background: transparent;"
        )
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        sub = QLabel("Ingresa los datos de conexión del lector ZKT K30")
        sub.setStyleSheet(
            "color: #003d66; font-family: Arial; "
            "font-size: 26px; background: transparent;"
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addStretch(1)

        # Tarjeta del formulario
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(20, 40, 80, 0.75);
                border-radius: 16px;
                border: 2px solid rgba(255, 255, 255, 0.35);
            }
        """)
        card.setFixedWidth(420)
        f = QVBoxLayout(card)
        f.setContentsMargins(30, 28, 30, 28)
        f.setSpacing(10)

        f.addWidget(self._lbl("Nombre del dispositivo"))
        self.input_nombre = QLineEdit()
        self.input_nombre.setPlaceholderText("Ej: Lector Entrada Principal")
        self.input_nombre.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_nombre)

        f.addWidget(self._lbl("Dirección IP"))
        self.input_ip = QLineEdit()
        self.input_ip.setPlaceholderText("Ej: 192.168.1.201")
        self.input_ip.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_ip)

        f.addWidget(self._lbl("Puerto"))
        self.input_port = QLineEdit()
        self.input_port.setPlaceholderText("Default: 4370")
        self.input_port.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_port)

        f.addWidget(self._lbl("Contraseña del dispositivo"))
        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("Default: 0  (sin contraseña)")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_password)

        f.addWidget(self._lbl("Tipo de dispositivo"))
        self.combo_tipo = QComboBox()
        self.combo_tipo.setStyleSheet(STYLE_COMBO)
        for t in ("Tiempo y Asistencia", "Control de Acceso", "Videoportero"):
            self.combo_tipo.addItem(t)
        f.addWidget(self.combo_tipo)

        f.addWidget(self._lbl("Formato de fecha"))
        self.combo_fecha = QComboBox()
        self.combo_fecha.setStyleSheet(STYLE_COMBO)
        for fmt in ("YY-MM-DD", "DD-MM-YY", "MM-DD-YY", "DD/MM/YYYY", "YYYY-MM-DD"):
            self.combo_fecha.addItem(fmt)
        f.addWidget(self.combo_fecha)

        f.addWidget(self._lbl("Estado del dispositivo"))
        estado_row = QHBoxLayout()
        estado_row.setSpacing(24)
        self.radio_activo   = _RadioOpcion("Activo",   True,  self)
        self.radio_inactivo = _RadioOpcion("Inactivo", False, self)
        self.radio_activo.seleccionado.connect(
            lambda: self.radio_inactivo.set_seleccionado(False))
        self.radio_inactivo.seleccionado.connect(
            lambda: self.radio_activo.set_seleccionado(False))
        self.radio_activo.set_seleccionado(True)
        estado_row.addStretch()
        estado_row.addWidget(self.radio_activo)
        estado_row.addWidget(self.radio_inactivo)
        estado_row.addStretch()
        f.addLayout(estado_row)

        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(
            "color: #000000; font-family: Arial; font-size: 18px; "
            "font-weight: 700; background: transparent;"
        )
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_estado)

        layout.addStretch(1)

        # Botones
        btns = QHBoxLayout()
        btn_back = QPushButton("← Volver")
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton {
                color: white; border: 2px solid rgba(255,255,255,0.9);
                padding: 13px 28px; border-radius: 8px;
                background: rgba(60, 120, 200, 0.7);
                font-family: Arial; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background: rgba(80, 140, 220, 0.85); }
        """)
        btn_back.clicked.connect(self.volver_cb)

        self.btn_connect = QPushButton("ESTABLECER CONEXIÓN")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background: #27d43f; color: white; font-family: Arial;
                font-weight: bold; padding: 14px 36px; border-radius: 8px;
                border: 2px solid #1fa030; font-size: 15px;
            }
            QPushButton:hover { background: #2fee54; }
            QPushButton:disabled { background: rgba(46,204,113,0.3); color: #999; }
        """)
        self.btn_connect.clicked.connect(self._iniciar_conexion)

        btns.addWidget(btn_back)
        btns.addStretch()
        btns.addWidget(self.btn_connect)
        layout.addLayout(btns)

    def _lbl(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(STYLE_LABEL_FIELD)
        return l

    # ── Datos persistidos ────────────────────────────────────

    def _cargar_config_guardada(self):
        cfg = cargar_config_dispositivo()
        if not cfg:
            return
        self.input_nombre.setText(cfg.get('nombre', ''))
        self.input_ip.setText(cfg.get('ip', ''))
        self.input_port.setText(cfg.get('puerto', ''))
        self.input_password.setText(cfg.get('password', ''))
        idx = self.combo_tipo.findText(cfg.get('tipo_dispositivo', ''))
        if idx >= 0:
            self.combo_tipo.setCurrentIndex(idx)
        idx = self.combo_fecha.findText(cfg.get('formato_fecha', ''))
        if idx >= 0:
            self.combo_fecha.setCurrentIndex(idx)
        activo = cfg.get('activo', True)
        self.radio_activo.set_seleccionado(activo)
        self.radio_inactivo.set_seleccionado(not activo)
        self.lbl_estado.setText("✔ Configuración anterior cargada")

    # ── Conexión ─────────────────────────────────────────────

    def _iniciar_conexion(self):
        nombre   = self.input_nombre.text().strip()
        ip       = self.input_ip.text().strip()
        puerto   = self.input_port.text().strip() or "4370"
        password = self.input_password.text().strip() or "0"

        if not nombre:
            QMessageBox.warning(self, "Error", "Ingresa un nombre para el dispositivo.")
            return
        if not ip:
            QMessageBox.warning(self, "Error", "Ingresa una dirección IP.")
            return

        db_config = construir_db_config_conexion()
        if not db_config.get('host') or not db_config.get('database'):
            QMessageBox.warning(
                self, "Sin configuración de nube",
                "El proveedor de base de datos aún no está configurado.\n"
                "Solicita al administrador que lo configure primero."
            )
            return

        self.btn_connect.setEnabled(False)
        self.lbl_estado.setText("Iniciando conexión...")

        self._hilo = HiloConexionLector(nombre, ip, puerto, password, db_config)
        self._hilo.progreso.connect(self.lbl_estado.setText)
        self._hilo.completado.connect(self._on_completado)
        self._hilo.error.connect(self._on_error)
        self._hilo.start()

    def _on_completado(self, resultado):
        self.btn_connect.setEnabled(True)
        eventos, usuarios = resultado

        config = {
            'nombre':           self.input_nombre.text().strip(),
            'ip':               self.input_ip.text().strip(),
            'puerto':           self.input_port.text().strip() or "4370",
            'password':         self.input_password.text().strip() or "0",
            'tipo_dispositivo': self.combo_tipo.currentText(),
            'formato_fecha':    self.combo_fecha.currentText(),
            'activo':           self.radio_activo.esta_seleccionado(),
        }
        guardar_config_dispositivo(config)

        self.lbl_estado.setText(
            f"✔ Conexión exitosa — "
            f"{usuarios} usuario{'s' if usuarios != 1 else ''}, "
            f"{eventos} evento{'s' if eventos != 1 else ''} sincronizado{'s' if eventos != 1 else ''}"
        )
        self.dispositivo_conectado.emit(config)

    def _on_error(self, msg):
        self.btn_connect.setEnabled(True)
        self.lbl_estado.setText(f"✘ {msg}")
        QMessageBox.critical(self, "Error de conexión", msg)


# =========================================================
# PANTALLA 3 — PROVEEDOR DE BASE DE DATOS  (solo admin)
# =========================================================
class PantallaProveedorDB(QWidget):
    """
    Formulario para configurar el host MySQL/MariaDB en la nube.
    Solo accesible para administradores.
    """

    def __init__(self, sesion, volver_cb, parent=None):
        super().__init__(parent)
        self.volver_cb = volver_cb
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()
        self._cargar_config_guardada()

    # ── Construcción de UI ──────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(16)

        titulo = QLabel("PROVEEDOR DE BASE DE DATOS")
        titulo.setStyleSheet(
            "color: #003d66; font-family: Arial; font-size: 30px; "
            "font-weight: bold; background: transparent;"
        )
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        sub = QLabel("Configura el servidor MySQL/MariaDB en la nube")
        sub.setStyleSheet(
            "color: #003d66; font-family: Arial; "
            "font-size: 26px; background: transparent;"
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addStretch(1)

        # Tarjeta del formulario
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(20, 40, 80, 0.75);
                border-radius: 16px;
                border: 2px solid rgba(255, 255, 255, 0.35);
            }
        """)
        card.setFixedWidth(420)
        f = QVBoxLayout(card)
        f.setContentsMargins(30, 28, 30, 28)
        f.setSpacing(10)

        f.addWidget(self._lbl("Host / servidor"))
        self.input_host = QLineEdit()
        self.input_host.setPlaceholderText("Ej: shortline.proxy.rlwy.net")
        self.input_host.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_host)

        f.addWidget(self._lbl("Puerto"))
        self.input_port = QLineEdit()
        self.input_port.setPlaceholderText("Default: 3306")
        self.input_port.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_port)

        f.addWidget(self._lbl("Usuario"))
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Ej: root")
        self.input_user.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_user)

        f.addWidget(self._lbl("Contraseña"))
        self.input_password = QLineEdit()
        self.input_password.setPlaceholderText("Contraseña del proveedor")
        self.input_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_password.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_password)

        f.addWidget(self._lbl("Nombre de la base de datos"))
        self.input_db = QLineEdit()
        self.input_db.setPlaceholderText("Ej: railway")
        self.input_db.setStyleSheet(STYLE_INPUT)
        f.addWidget(self.input_db)

        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_estado = QLabel("")
        self.lbl_estado.setStyleSheet(
            "color: #000000; font-family: Arial; font-size: 18px; "
            "font-weight: 700; background: transparent;"
        )
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_estado)

        layout.addStretch(1)

        # Botones
        btns = QHBoxLayout()
        btn_back = QPushButton("← Volver")
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton {
                color: white; border: 2px solid rgba(255,255,255,0.9);
                padding: 13px 28px; border-radius: 8px;
                background: rgba(60, 120, 200, 0.7);
                font-family: Arial; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover { background: rgba(80, 140, 220, 0.85); }
        """)
        btn_back.clicked.connect(self.volver_cb)

        self.btn_guardar = QPushButton("GUARDAR CONFIGURACIÓN")
        self.btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guardar.setStyleSheet("""
            QPushButton {
                background: #27d43f; color: white; font-family: Arial;
                font-weight: bold; padding: 14px 36px; border-radius: 8px;
                border: 2px solid #1fa030; font-size: 15px;
            }
            QPushButton:hover { background: #2fee54; }
            QPushButton:disabled { background: rgba(46,204,113,0.3); color: #999; }
        """)
        self.btn_guardar.clicked.connect(self._guardar)

        btns.addWidget(btn_back)
        btns.addStretch()
        btns.addWidget(self.btn_guardar)
        layout.addLayout(btns)

    def _lbl(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(STYLE_LABEL_FIELD)
        return l

    # ── Datos persistidos ────────────────────────────────────

    def _cargar_config_guardada(self):
        cfg = cargar_config_db()
        self.input_host.setText(str(cfg.get('host', '')))
        self.input_port.setText(str(cfg.get('port', '') or ''))
        self.input_user.setText(str(cfg.get('user', '')))
        self.input_password.setText(str(cfg.get('password', '')))
        self.input_db.setText(str(cfg.get('database', '')))
        if cfg.get('host'):
            self.lbl_estado.setText("✔ Configuración anterior cargada")

    # ── Guardado ─────────────────────────────────────────────

    def _guardar(self):
        host     = self.input_host.text().strip()
        port     = self.input_port.text().strip() or "3306"
        user     = self.input_user.text().strip()
        password = self.input_password.text()
        db       = self.input_db.text().strip()

        if not host:
            QMessageBox.warning(self, "Error", "Ingresa el host del servidor.")
            return
        if not user:
            QMessageBox.warning(self, "Error", "Ingresa el usuario de la base de datos.")
            return
        if not db:
            QMessageBox.warning(self, "Error", "Ingresa el nombre de la base de datos.")
            return
        try:
            int(port)
        except ValueError:
            QMessageBox.warning(self, "Error", "El puerto debe ser un número.")
            return

        self.btn_guardar.setEnabled(False)
        self.lbl_estado.setText("Guardando...")

        guardar_config_db({
            'host':     host,
            'port':     port,
            'user':     user,
            'password': password,
            'database': db,
        })

        self.lbl_estado.setText("✔ Configuración guardada correctamente")
        self.btn_guardar.setEnabled(True)
        QMessageBox.information(
            self, "Guardado",
            "La configuración del proveedor de nube se guardó correctamente."
        )


# =========================================================
# WIDGET PRINCIPAL — CONTENEDOR DE NAVEGACIÓN
# (equivalente a InterfazRegistros)
# =========================================================
class InterfazConfigLector(QWidget):
    """
    Contenedor de navegación del módulo de hardware.
    Sigue exactamente el mismo patrón que InterfazRegistros:
    fondo animado compartido + contenedor translúcido que monta
    y desmonta pantallas sin recrear el fondo en cada cambio.
    """
    volver_menu          = pyqtSignal()
    conectar_dispositivo = pyqtSignal(dict)

    def __init__(self, sesion=None, parent=None):
        super().__init__(parent)
        self.sesion   = sesion

        self.graphics     = InterfaceGraphics() if GRAPHICS_AVAILABLE else None
        self.canvas_fondo = CanvasFondo(self, self.graphics)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.canvas_fondo)

        self.contenedor = QWidget(self)
        self.contenedor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.contenedor.setStyleSheet("background: transparent;")

        self.timer = QTimer()
        self.timer.timeout.connect(self.canvas_fondo.update)
        self.timer.start(33)

        self._ir_menu_hardware()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.contenedor.setGeometry(0, 0, self.width(), self.height())

    # ── Navegación interna ────────────────────────────────────

    def _limpiar(self):
        layout = self.contenedor.layout()
        if layout:
            QWidget().setLayout(layout)
        for child in self.contenedor.findChildren(QWidget):
            child.setParent(None)
            child.deleteLater()

    def _montar(self, widget):
        layout = QVBoxLayout(self.contenedor)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        self.contenedor.setGeometry(0, 0, self.width(), self.height())

    def _ir_menu_hardware(self):
        self._limpiar()
        self._montar(PantallaMenuHardware(
            sesion        = self.sesion,
            ir_lector_cb  = self._ir_lector,
            ir_db_cb      = self._ir_proveedor_db,
            volver_cb     = self._salir,
            parent        = self.contenedor,
        ))

    def _ir_lector(self):
        self._limpiar()
        pantalla = PantallaLector(
            sesion    = self.sesion,
            volver_cb = self._ir_menu_hardware,
            parent    = self.contenedor,
        )
        pantalla.dispositivo_conectado.connect(self.conectar_dispositivo)
        self._montar(pantalla)

    def _ir_proveedor_db(self):
        self._limpiar()
        self._montar(PantallaProveedorDB(
            sesion    = self.sesion,
            volver_cb = self._ir_menu_hardware,
            parent    = self.contenedor,
        ))

    def _salir(self):
        self.timer.stop()
        self.volver_menu.emit()

    # ── Compatibilidad con código existente ───────────────────

    def obtener_config(self):
        """Mantiene compatibilidad con llamadas externas previas."""
        return cargar_config_dispositivo()