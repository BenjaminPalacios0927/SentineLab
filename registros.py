import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QScrollArea, QFrame,
    QMessageBox, QDialog, QSizePolicy
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt6.QtGui import QPainter, QColor, QFont, QPen


def ocultar_consola_windows():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

try:
    from interface_graphics import InterfaceGraphics
    GRAPHICS_AVAILABLE = True
except ImportError:
    GRAPHICS_AVAILABLE = False

try:
    import mysql.connector
    import bcrypt
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("Advertencia: mysql.connector o bcrypt no disponibles.")

def _cargar_config_lector() -> dict:
    try:
        from device_config import cargar_config_dispositivo
        return cargar_config_dispositivo()
    except Exception:
        return {}

def _db_cfg() -> dict:
    """
    Devuelve el dict de conexión construido a partir de la configuración
    guardada por el usuario en la pantalla de hardware (db.cfg).
    Se llama en tiempo de ejecución dentro de cada hilo para que siempre
    use el proveedor actualmente configurado, sin credenciales fijas.
    """
    try:
        from device_config import construir_db_config_conexion
        return construir_db_config_conexion()
    except Exception:
        return {}

# ROL_ADMIN y ROL_USUARIO se importan desde device_config para
# mantener una única fuente de verdad en todo el sistema.
from device_config import ROL_ADMIN, ROL_USUARIO

# =========================================================
# ESTILOS COMPARTIDOS (coherentes con el resto del sistema)
# =========================================================
STYLE_INPUT = """
    QLineEdit {
        background-color: rgb(241, 239, 232);
        color: rgb(26, 26, 26);
        font-family: Arial;
        font-size: 17px;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid rgb(181, 212, 244);
    }
    QLineEdit:focus {
        background-color: rgb(255, 255, 255);
        border: 2px solid rgb(24, 95, 165);
    }
"""
STYLE_COMBO = """
    QComboBox {
        background-color: rgb(241, 239, 232);
        color: rgb(26, 26, 26);
        font-family: Arial;
        font-size: 17px;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid rgb(181, 212, 244);
    }
    QComboBox:focus { background-color: rgb(255, 255, 255); border: 2px solid rgb(24, 95, 165); }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background-color: rgb(255, 255, 255);
        color: rgb(26, 26, 26);
        font-size: 17px;
        selection-background-color: rgb(24, 95, 165);
        selection-color: white;
    }
"""
STYLE_BTN_PRIMARY = """
    QPushButton {
        background-color: rgb(24, 95, 165); color: white; font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: none;
    }
    QPushButton:hover { background-color: rgb(12, 68, 124); }
    QPushButton:disabled { background-color: rgb(181, 212, 244); color: white; }
"""
STYLE_BTN_SECONDARY = """
    QPushButton {
        background-color: rgb(255, 255, 255); color: rgb(24, 95, 165); font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: 2px solid rgb(24, 95, 165);
    }
    QPushButton:hover { background-color: rgb(230, 241, 251); }
"""
STYLE_BTN_DANGER = """
    QPushButton {
        background-color: rgb(163, 45, 45);
        color: white;
        font-family: Arial;
        font-size: 16px;
        font-weight: bold;
        padding: 10px 20px;
        border-radius: 8px;
        border: none;
    }
    QPushButton:hover { background-color: rgb(120, 30, 30); }
"""
STYLE_LABEL_TITULO = "color: rgb(24, 95, 165); font-family: Arial; font-size: 55px; font-weight: bold; background: transparent; height: 100px;"
STYLE_LABEL_SUB    = "color: rgb(26, 26, 26); font-family: Arial; font-size: 30px; background: transparent; height: 150px;"
STYLE_LABEL_SMALL  = "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; background: transparent;"


# =========================================================
# CANVAS DE FONDO (mismo patrón que los otros módulos)
# =========================================================
class CanvasFondo(QWidget):
    def __init__(self, parent, graphics_engine):
        super().__init__(parent)
        self.tiempo = 0
        self.graphics = graphics_engine
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.graphics:
            self.graphics.dibujar_gradiente_animado(painter, self.width(), self.height(), self.tiempo)
        else:
            painter.fillRect(0, 0, self.width(), self.height(), QColor(30, 60, 114))
        self.tiempo += 1


# =========================================================
# HILO DB GENÉRICO
# =========================================================
class DBThread(QThread):
    resultado = pyqtSignal(object)
    error     = pyqtSignal(str)

    def __init__(self, operacion, *args):
        super().__init__()
        self.operacion = operacion
        self.args = args

    def run(self):
        try:
            conn = mysql.connector.connect(**_db_cfg())
            res  = self.operacion(conn, *self.args)
            conn.close()
            self.resultado.emit(res)
        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# DIÁLOGO: CREAR / EDITAR USUARIO
# =========================================================
class DialogoUsuario(QDialog):
    """Crear (datos_usuario=None) o editar un usuario existente."""

    def __init__(self, parent, datos_usuario=None):
        super().__init__(parent)
        self.datos_usuario = datos_usuario
        self.modo = "editar" if datos_usuario else "crear"
        self.setWindowTitle("Editar usuario" if self.modo == "editar" else "Nuevo usuario")
        self.setMinimumSize(500, 420)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(26, 26, 26); border-radius: 14px;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 26, 30, 26)

        titulo = QLabel("Editar usuario" if self.modo == "editar" else "Registrar nuevo usuario")
        titulo.setStyleSheet("color: rgb(24, 95, 165); font-family: Arial; font-size: 21px; font-weight: bold;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        # Nombre
        layout.addWidget(self._lbl("Nombre de usuario"))
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setStyleSheet(STYLE_INPUT)
        self.txt_nombre.setPlaceholderText("usuario")
        if self.datos_usuario:
            self.txt_nombre.setText(self.datos_usuario.get('name', ''))
            self.txt_nombre.setEnabled(False)   # El nombre no se puede cambiar
        layout.addWidget(self.txt_nombre)

        # Contraseña
        hint = " (vacío = sin cambios)" if self.modo == "editar" else ""
        layout.addWidget(self._lbl(f"Contraseña{hint}"))
        self.txt_pwd = QLineEdit()
        self.txt_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pwd.setStyleSheet(STYLE_INPUT)
        self.txt_pwd.setPlaceholderText("••••••••")
        layout.addWidget(self.txt_pwd)

        # Rol
        layout.addWidget(self._lbl("Rol"))
        self.combo_rol = QComboBox()
        self.combo_rol.setStyleSheet(STYLE_COMBO)
        self.combo_rol.addItem("Usuario normal",   ROL_USUARIO)
        self.combo_rol.addItem("Administrador",    ROL_ADMIN)
        if self.datos_usuario:
            self.combo_rol.setCurrentIndex(1 if self.datos_usuario.get('rol') == ROL_ADMIN else 0)
        layout.addWidget(self.combo_rol)

        layout.addSpacing(8)

        btn_row = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_cancelar.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancelar)

        btn_ok = QPushButton("Guardar")
        btn_ok.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_ok.clicked.connect(self._validar)
        btn_row.addWidget(btn_ok)

        layout.addLayout(btn_row)

    def _lbl(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(STYLE_LABEL_SMALL)
        return l

    def _validar(self):
        nombre = self.txt_nombre.text().strip()
        pwd    = self.txt_pwd.text().strip()
        rol    = self.combo_rol.currentData()

        if not nombre:
            QMessageBox.warning(self, "Error", "El nombre de usuario es obligatorio.")
            return
        if self.modo == "crear" and not pwd:
            QMessageBox.warning(self, "Error", "La contraseña es obligatoria al crear un usuario.")
            return

        self._resultado = {'name': nombre, 'pwd': pwd, 'rol': rol}
        self.accept()

    def obtener_datos(self):
        return getattr(self, '_resultado', None)


# =========================================================
# PANTALLA: GESTIÓN DE USUARIOS (solo admin)
# =========================================================
class PantallaUsuarios(QWidget):

    def __init__(self, sesion, volver_cb, parent=None):
        super().__init__(parent)
        self.sesion    = sesion
        self.es_admin  = (sesion.rol == ROL_ADMIN)
        self.volver_cb = volver_cb
        self._thread   = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()
        self._cargar_usuarios()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        titulo = QLabel("Gestión de Usuarios")
        titulo.setStyleSheet(STYLE_LABEL_TITULO)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        sub = QLabel("Cuentas registradas en el sistema")
        sub.setStyleSheet(STYLE_LABEL_SUB)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # Lista con scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgb(181, 212, 244); width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgb(24, 95, 165); border-radius: 4px;
            }
        """)
        self.lista_widget = QWidget()
        self.lista_widget.setStyleSheet("background: transparent;")
        self.lista_layout = QVBoxLayout(self.lista_widget)
        self.lista_layout.setSpacing(10)
        self.lista_layout.setContentsMargins(0, 0, 0, 0)
        self.lista_layout.addStretch()
        self.scroll.setWidget(self.lista_widget)
        layout.addWidget(self.scroll)

        # Botones inferiores
        btn_row = QHBoxLayout()
        btn_volver = QPushButton("← Volver")
        btn_volver.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_volver.clicked.connect(self.volver_cb)
        btn_row.addWidget(btn_volver)
        btn_row.addStretch()
        btn_nuevo = QPushButton("Nuevo usuario")
        btn_nuevo.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_nuevo.clicked.connect(self._nuevo_usuario)
        btn_row.addWidget(btn_nuevo)
        layout.addLayout(btn_row)

    # --- DB ---

    def _cargar_usuarios(self):
        if not DB_AVAILABLE:
            self._mostrar_msg("Sin conexión a base de datos.")
            return

        def op(conn):
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT id, name, rol, status FROM users WHERE `del`=0 ORDER BY id"
            )
            return cur.fetchall()

        self._thread = DBThread(op)
        self._thread.resultado.connect(self._on_cargados)
        self._thread.error.connect(lambda e: self._mostrar_msg(f"Error al cargar: {e}"))
        self._thread.start()

    def _on_cargados(self, usuarios):
        # Limpiar filas anteriores (todo menos el stretch final)
        while self.lista_layout.count() > 1:
            item = self.lista_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not usuarios:
            self._mostrar_msg("No hay usuarios registrados.")
            return

        for u in usuarios:
            self.lista_layout.insertWidget(self.lista_layout.count() - 1, self._fila(u))

    def _fila(self, usuario):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: rgb(255, 255, 255);
                border-radius: 10px;
                border: 1px solid rgb(181, 212, 244);
            }
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        # Punto de color según rol
        dot = QLabel("●")
        color_dot = "#4CAF50" if usuario['rol'] == ROL_ADMIN else "#64B5F6"
        dot.setStyleSheet(f"color: {color_dot}; font-size: 18px; background: transparent;")
        row.addWidget(dot)

        # Info del usuario
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_name = QLabel(usuario['name'])
        lbl_name.setStyleSheet("color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        col.addWidget(lbl_name)
        rol_txt = "Administrador" if usuario['rol'] == ROL_ADMIN else "Usuario normal"
        estado_txt = "Activo" if usuario.get('status', 1) else "Inactivo"
        lbl_meta = QLabel(f"ID: {usuario['id']}  ·  {rol_txt}  ·  {estado_txt}")
        lbl_meta.setStyleSheet(STYLE_LABEL_SMALL)
        col.addWidget(lbl_meta)
        row.addLayout(col)
        row.addStretch()

        # Editar y Eliminar: solo admin
        if self.es_admin:
            btn_edit = QPushButton("Editar")
            btn_edit.setStyleSheet(STYLE_BTN_SECONDARY)
            btn_edit.setMinimumWidth(100)
            btn_edit.clicked.connect(lambda _, u=usuario: self._editar(u))
            row.addWidget(btn_edit)

            es_protegido = (usuario['id'] == 0 or usuario['name'] == self.sesion.user_name)
            if not es_protegido:
                btn_del = QPushButton("Eliminar")
                btn_del.setStyleSheet(STYLE_BTN_DANGER)
                btn_del.setMinimumWidth(100)
                btn_del.clicked.connect(lambda _, u=usuario: self._eliminar(u))
                row.addWidget(btn_del)

        return frame

    def _mostrar_msg(self, msg):
        lbl = QLabel(msg)
        lbl.setStyleSheet(STYLE_LABEL_SUB)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lista_layout.insertWidget(0, lbl)

    # --- Acciones ---

    def _nuevo_usuario(self):
        dlg = DialogoUsuario(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            datos = dlg.obtener_datos()
            if not datos:
                return
            pwd_hash = bcrypt.hashpw(datos['pwd'].encode(), bcrypt.gensalt()).decode()

            def op(conn):
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (name, pasw, rol) VALUES (%s, %s, %s)",
                    (datos['name'], pwd_hash, datos['rol'])
                )
                conn.commit()

            self._thread = DBThread(op)
            self._thread.resultado.connect(lambda _: [
                QMessageBox.information(self, "Éxito", f"Usuario '{datos['name']}' creado."),
                self._cargar_usuarios()
            ])
            self._thread.error.connect(lambda e: QMessageBox.critical(self, "Error", f"No se pudo crear:\n{e}"))
            self._thread.start()

    def _editar(self, usuario):
        dlg = DialogoUsuario(self, datos_usuario=usuario)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            datos = dlg.obtener_datos()
            if not datos:
                return

            def op(conn):
                cur = conn.cursor()
                if datos['pwd']:
                    pwd_hash = bcrypt.hashpw(datos['pwd'].encode(), bcrypt.gensalt()).decode()
                    cur.execute("UPDATE users SET pasw=%s, rol=%s WHERE name=%s",
                                (pwd_hash, datos['rol'], usuario['name']))
                else:
                    cur.execute("UPDATE users SET rol=%s WHERE name=%s",
                                (datos['rol'], usuario['name']))
                conn.commit()

            self._thread = DBThread(op)
            self._thread.resultado.connect(lambda _: [
                QMessageBox.information(self, "Éxito", "Usuario actualizado."),
                self._cargar_usuarios()
            ])
            self._thread.error.connect(lambda e: QMessageBox.critical(self, "Error", f"No se pudo actualizar:\n{e}"))
            self._thread.start()

    def _eliminar(self, usuario):
        resp = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar al usuario '{usuario['name']}'?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        def op(conn):
            cur = conn.cursor()
            cur.execute("UPDATE users SET `del`=1 WHERE id=%s", (usuario['id'],))
            conn.commit()

        self._thread = DBThread(op)
        self._thread.resultado.connect(lambda _: [
            QMessageBox.information(self, "Éxito", "Usuario eliminado."),
            self._cargar_usuarios()
        ])
        self._thread.error.connect(lambda e: QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{e}"))
        self._thread.start()


# =========================================================
# HILOS: OPERACIONES CON RAILWAY Y EL LECTOR
# =========================================================

class HiloCargarPerfiles(QThread):
    """
    Lee los perfiles desde Railway (tabla device_users).
    Si la tabla no existe la crea vacía.
    """
    resultado = pyqtSignal(object)   # lista de perfiles
    error     = pyqtSignal(str)

    def run(self):
        try:
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor(dictionary=True)

            # Crear tabla si no existe
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_users (
                    user_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
                    nombre       VARCHAR(100) NOT NULL,
                    departamento VARCHAR(100) DEFAULT '',
                    horario      INT          DEFAULT 0,
                    tiene_huella TINYINT      DEFAULT 0,
                    synced_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    lector_synced TINYINT     DEFAULT 1,
                    pending_op   VARCHAR(10)  DEFAULT NULL
                )
            """)
            # Migrar tabla existente si le faltan las columnas nuevas
            try:
                cursor.execute(
                    "ALTER TABLE device_users ADD COLUMN lector_synced TINYINT DEFAULT 1")
            except Exception:
                pass
            try:
                cursor.execute(
                    "ALTER TABLE device_users ADD COLUMN pending_op VARCHAR(10) DEFAULT NULL")
            except Exception:
                pass
            conn.commit()

            cursor.execute(
                "SELECT user_id, nombre, departamento, horario, tiene_huella, lector_synced, pending_op "
                "FROM device_users ORDER BY CAST(user_id AS UNSIGNED)"
            )
            perfiles = cursor.fetchall()
            cursor.close()
            conn.close()
            self.resultado.emit(perfiles)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


class HiloSincronizarPerfiles(QThread):
    """
    Descarga los perfiles del lector y los guarda en Railway.
    Reemplaza completamente el contenido de device_users.
    """
    progreso  = pyqtSignal(str)
    resultado = pyqtSignal(object)   # lista de perfiles sincronizados
    error     = pyqtSignal(str)

    def run(self):
        try:
            from hardware_handler import K30Controller

            self.progreso.emit("Conectando al lector...")
            cfg  = _cargar_config_lector()
            ctrl = K30Controller(
                ip=cfg.get('ip'),
                port=int(cfg.get('puerto', 4370)) if cfg.get('puerto') else None,
                password=cfg.get('password'),
            )
            if not ctrl.conectar():
                self.error.emit("No se pudo conectar al lector.")
                return

            # ── PASO 1: Empujar pendientes de Railway → Lector ───────────────
            self.progreso.emit("Aplicando cambios pendientes al lector...")
            conn_p   = mysql.connector.connect(**_db_cfg())
            cursor_p = conn_p.cursor(dictionary=True)
            cursor_p.execute(
                "SELECT user_id, nombre, departamento, horario, pending_op "
                "FROM device_users WHERE lector_synced = 0 AND pending_op IS NOT NULL"
            )
            pendientes = cursor_p.fetchall()

            resueltos = []
            for p in pendientes:
                op = p['pending_op']
                try:
                    if op == 'crear' or op == 'editar':
                        if op == 'editar':
                            ctrl.eliminar_usuario(p['user_id'])
                        ctrl.crear_usuario(
                            p['user_id'], p['nombre'],
                            p.get('departamento', ''), p.get('horario', 0))
                    elif op == 'eliminar':
                        ctrl.eliminar_usuario(p['user_id'])
                    resueltos.append(p['user_id'])
                except Exception:
                    pass   # Si un pendiente falla, continuar con los demás

            # Marcar resueltos como sincronizados en Railway
            if resueltos:
                # Eliminar definitivamente los marcados como 'eliminar'
                cursor_p.execute(
                    "DELETE FROM device_users "
                    "WHERE user_id IN ({}) AND pending_op = 'eliminar'".format(
                        ','.join(['%s'] * len(resueltos))),
                    resueltos
                )
                # Limpiar bandera en los demás
                cursor_p.execute(
                    "UPDATE device_users SET lector_synced=1, pending_op=NULL "
                    "WHERE user_id IN ({}) AND pending_op != 'eliminar'".format(
                        ','.join(['%s'] * len(resueltos))),
                    resueltos
                )
                conn_p.commit()

            cursor_p.close()
            conn_p.close()

            if pendientes:
                self.progreso.emit(
                    f"{len(resueltos)}/{len(pendientes)} cambios pendientes aplicados...")

            # ── PASO 2: Descargar estado real del lector → Railway ────────────
            self.progreso.emit("Descargando perfiles del lector...")
            perfiles = ctrl.obtener_usuarios()
            ctrl.desconectar()

            self.progreso.emit(f"Guardando {len(perfiles)} perfiles en Railway...")
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_users (
                    user_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
                    nombre       VARCHAR(100) NOT NULL,
                    departamento VARCHAR(100) DEFAULT '',
                    horario      INT          DEFAULT 0,
                    tiene_huella TINYINT      DEFAULT 0,
                    synced_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
                    lector_synced TINYINT     DEFAULT 1,
                    pending_op   VARCHAR(10)  DEFAULT NULL
                )
            """)
            # Migrar tabla existente si le faltan las columnas nuevas
            try:
                cursor.execute(
                    "ALTER TABLE device_users ADD COLUMN lector_synced TINYINT DEFAULT 1")
            except Exception:
                pass
            try:
                cursor.execute(
                    "ALTER TABLE device_users ADD COLUMN pending_op VARCHAR(10) DEFAULT NULL")
            except Exception:
                pass

            # Upsert: insertar o actualizar si ya existe
            for p in perfiles:
                tiene_huella = 1 if p.get('huella') else 0
                cursor.execute("""
                    INSERT INTO device_users
                        (user_id, nombre, departamento, horario, tiene_huella, synced_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        nombre       = VALUES(nombre),
                        departamento = VALUES(departamento),
                        horario      = VALUES(horario),
                        tiene_huella = VALUES(tiene_huella),
                        synced_at    = NOW()
                """, (
                    str(p['user_id']),
                    p.get('nombre', ''),
                    p.get('departamento', ''),
                    p.get('horario', 0),
                    tiene_huella,
                ))

            conn.commit()

            # Leer el resultado final para devolvérselo a la UI
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT user_id, nombre, departamento, horario, tiene_huella, lector_synced, pending_op "
                "FROM device_users ORDER BY CAST(user_id AS UNSIGNED)"
            )
            resultado = cursor.fetchall()
            cursor.close()
            conn.close()
            self.resultado.emit(resultado)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


class HiloCrearPerfil(QThread):
    """
    Crea el perfil en el lector Y lo inserta en Railway.
    """
    resultado = pyqtSignal(object)
    error     = pyqtSignal(str)

    def __init__(self, datos):
        super().__init__()
        self.datos = datos

    def run(self):
        try:
            from hardware_handler import K30Controller

            cfg  = _cargar_config_lector()
            ctrl = K30Controller(
                ip=cfg.get('ip'),
                port=int(cfg.get('puerto', 4370)) if cfg.get('puerto') else None,
                password=cfg.get('password'),
            )
            lector_ok = ctrl.conectar()
            if lector_ok:
                ok = ctrl.crear_usuario(
                    self.datos['user_id'],
                    self.datos['nombre'],
                    self.datos.get('departamento', ''),
                    self.datos.get('horario', 0),
                )
                ctrl.desconectar()
                if not ok:
                    lector_ok = False  # Lector rechazó, pero igual guardamos en Railway

            # Siempre guardar en Railway (con o sin lector)
            synced = 1 if lector_ok else 0
            pending = None if lector_ok else 'crear'
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO device_users
                    (user_id, nombre, departamento, horario, tiene_huella,
                     lector_synced, pending_op, synced_at)
                VALUES (%s, %s, %s, %s, 0, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    nombre        = VALUES(nombre),
                    departamento  = VALUES(departamento),
                    horario       = VALUES(horario),
                    lector_synced = VALUES(lector_synced),
                    pending_op    = VALUES(pending_op),
                    synced_at     = NOW()
            """, (
                str(self.datos['user_id']),
                self.datos['nombre'],
                self.datos.get('departamento', ''),
                self.datos.get('horario', 0),
                synced, pending,
            ))
            conn.commit()
            cursor.close()
            conn.close()
            # True = lector+Railway, None = solo Railway (pendiente de sync)
            self.resultado.emit(True if lector_ok else None)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


class HiloEliminarPerfil(QThread):
    """
    Elimina el perfil del lector Y de Railway.
    """
    resultado = pyqtSignal(bool)
    error     = pyqtSignal(str)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    def run(self):
        try:
            from hardware_handler import K30Controller

            cfg  = _cargar_config_lector()
            ctrl = K30Controller(
                ip=cfg.get('ip'),
                port=int(cfg.get('puerto', 4370)) if cfg.get('puerto') else None,
                password=cfg.get('password'),
            )
            lector_ok = ctrl.conectar()
            if lector_ok:
                ctrl.eliminar_usuario(self.user_id)
                ctrl.desconectar()

            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()
            if lector_ok:
                # Lector disponible: eliminar definitivamente de Railway
                cursor.execute(
                    "DELETE FROM device_users WHERE user_id = %s",
                    (str(self.user_id),)
                )
            else:
                # Sin lector: marcar como pendiente de eliminación
                cursor.execute(
                    "UPDATE device_users "
                    "SET lector_synced=0, pending_op='eliminar' "
                    "WHERE user_id = %s",
                    (str(self.user_id),)
                )
            conn.commit()
            cursor.close()
            conn.close()
            self.resultado.emit(True if lector_ok else None)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# HILO: EDITAR PERFIL EN LECTOR Y RAILWAY
# =========================================================
class HiloEditarPerfil(QThread):
    resultado = pyqtSignal(object)   # True=lector+Railway, None=solo Railway
    error     = pyqtSignal(str)

    def __init__(self, datos_nuevos, user_id_original):
        super().__init__()
        self.datos    = datos_nuevos
        self.uid_orig = user_id_original

    def run(self):
        try:
            from hardware_handler import K30Controller
            cfg  = _cargar_config_lector()
            ctrl = K30Controller(
                ip=cfg.get('ip'),
                port=int(cfg.get('puerto', 4370)) if cfg.get('puerto') else None,
                password=cfg.get('password'),
            )
            lector_ok = ctrl.conectar()
            if lector_ok:
                # K30 no tiene update: borrar y recrear
                ctrl.eliminar_usuario(self.uid_orig)
                ctrl.crear_usuario(
                    self.datos['user_id'],
                    self.datos['nombre'],
                    self.datos.get('departamento', ''),
                    self.datos.get('horario', 0),
                )
                ctrl.desconectar()

            # Siempre actualizar Railway
            synced  = 1 if lector_ok else 0
            pending = None if lector_ok else 'editar'
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()
            if str(self.datos['user_id']) != str(self.uid_orig):
                cursor.execute(
                    "DELETE FROM device_users WHERE user_id = %s", (str(self.uid_orig),))
            cursor.execute("""
                INSERT INTO device_users
                    (user_id, nombre, departamento, horario, tiene_huella,
                     lector_synced, pending_op, synced_at)
                VALUES (%s, %s, %s, %s, 0, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    nombre        = VALUES(nombre),
                    departamento  = VALUES(departamento),
                    horario       = VALUES(horario),
                    lector_synced = VALUES(lector_synced),
                    pending_op    = VALUES(pending_op),
                    synced_at     = NOW()
            """, (
                str(self.datos['user_id']),
                self.datos['nombre'],
                self.datos.get('departamento', ''),
                self.datos.get('horario', 0),
                synced, pending,
            ))
            conn.commit()
            cursor.close()
            conn.close()
            self.resultado.emit(True if lector_ok else None)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión con el servidor de base de datos. Verifica el host, puerto y tu red.")
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# DIÁLOGO: EDITAR PERFIL DEL LECTOR
# =========================================================
class DialogoEditarPerfil(QDialog):

    def __init__(self, parent, perfil):
        super().__init__(parent)
        self.perfil = perfil
        self.setWindowTitle("Editar perfil")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(26, 26, 26); border-radius: 14px;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 26, 30, 26)

        titulo = QLabel("Editar perfil del lector")
        titulo.setStyleSheet("color: rgb(24, 95, 165); font-family: Arial; font-size: 21px; font-weight: bold;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        layout.addWidget(self._lbl("ID del empleado en el lector"))
        self.txt_id = QLineEdit()
        self.txt_id.setStyleSheet(STYLE_INPUT)
        self.txt_id.setText(str(self.perfil.get('user_id', '')))
        layout.addWidget(self.txt_id)

        layout.addWidget(self._lbl("Nombre completo"))
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setStyleSheet(STYLE_INPUT)
        self.txt_nombre.setText(self.perfil.get('nombre', ''))
        layout.addWidget(self.txt_nombre)

        layout.addWidget(self._lbl("Departamento"))
        self.txt_depto = QLineEdit()
        self.txt_depto.setStyleSheet(STYLE_INPUT)
        self.txt_depto.setText(self.perfil.get('departamento', ''))
        layout.addWidget(self.txt_depto)

        layout.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_cancelar.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancelar)
        btn_ok = QPushButton("Guardar")
        btn_ok.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_ok.clicked.connect(self._validar)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _lbl(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(STYLE_LABEL_SMALL)
        return l

    def _validar(self):
        uid    = self.txt_id.text().strip()
        nombre = self.txt_nombre.text().strip()
        if not uid or not uid.isdigit():
            QMessageBox.warning(self, "Error", "El ID debe ser un número.")
            return
        if not nombre:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return
        self._resultado = {
            'user_id':      uid,
            'nombre':       nombre,
            'departamento': self.txt_depto.text().strip(),
            'horario':      self.perfil.get('horario', 0),
        }
        self.accept()

    def obtener_datos(self):
        return getattr(self, '_resultado', None)


# =========================================================
# DIÁLOGO: CREAR PERFIL EN EL LECTOR
# =========================================================
class DialogoPerfil(QDialog):
    """Formulario para crear un nuevo perfil en el lector."""

    def __init__(self, parent, ultimo_id=0):
        super().__init__(parent)
        self.ultimo_id = ultimo_id
        self.setWindowTitle("Nuevo perfil en el lector")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setStyleSheet("background-color: rgb(255, 255, 255); color: rgb(26, 26, 26); border-radius: 14px;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 26, 30, 26)

        titulo = QLabel("Registrar perfil en el lector")
        titulo.setStyleSheet("color: rgb(24, 95, 165); font-family: Arial; font-size: 21px; font-weight: bold;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        # ID
        layout.addWidget(self._lbl("ID del empleado en el lector"))
        self.txt_id = QLineEdit()
        self.txt_id.setStyleSheet(STYLE_INPUT)
        self.txt_id.setPlaceholderText(f"Siguiente sugerido: {self.ultimo_id + 1}")
        self.txt_id.setText(str(self.ultimo_id + 1))
        layout.addWidget(self.txt_id)

        # Nombre
        layout.addWidget(self._lbl("Nombre completo"))
        self.txt_nombre = QLineEdit()
        self.txt_nombre.setStyleSheet(STYLE_INPUT)
        self.txt_nombre.setPlaceholderText("Nombre Apellido")
        layout.addWidget(self.txt_nombre)

        # Departamento
        layout.addWidget(self._lbl("Departamento"))
        self.txt_depto = QLineEdit()
        self.txt_depto.setStyleSheet(STYLE_INPUT)
        self.txt_depto.setPlaceholderText("Ej: Sistemas")
        layout.addWidget(self.txt_depto)

        layout.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_cancelar.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancelar)

        btn_ok = QPushButton("Crear")
        btn_ok.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_ok.clicked.connect(self._validar)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _lbl(self, texto):
        l = QLabel(texto)
        l.setStyleSheet(STYLE_LABEL_SMALL)
        return l

    def _validar(self):
        uid    = self.txt_id.text().strip()
        nombre = self.txt_nombre.text().strip()

        if not uid or not uid.isdigit():
            QMessageBox.warning(self, "Error", "El ID debe ser un número.")
            return
        if not nombre:
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return

        self._resultado = {
            'user_id':      uid,
            'nombre':       nombre,
            'departamento': self.txt_depto.text().strip(),
            'horario':      0,
        }
        self.accept()

    def obtener_datos(self):
        return getattr(self, '_resultado', None)


# =========================================================
# PANTALLA: GESTIÓN DE PERFILES DEL DISPOSITIVO
# =========================================================
class PantallaDispositivo(QWidget):

    def __init__(self, sesion, volver_cb, parent=None):
        super().__init__(parent)
        self.sesion    = sesion
        self.volver_cb = volver_cb
        self.es_admin  = (sesion.rol == ROL_ADMIN)
        self._thread   = None
        self._perfiles  = []   # cache de perfiles cargados
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()
        self._cargar_perfiles()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        titulo = QLabel("Perfiles del Dispositivo")
        titulo.setStyleSheet(STYLE_LABEL_TITULO)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        self.lbl_sub = QLabel("Cargando perfiles desde Railway...")
        self.lbl_sub.setStyleSheet(STYLE_LABEL_SUB)
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_sub)

        # Lista con scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgb(181, 212, 244); width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgb(24, 95, 165); border-radius: 4px;
            }
        """)
        self.lista_widget = QWidget()
        self.lista_widget.setStyleSheet("background: transparent;")
        self.lista_layout = QVBoxLayout(self.lista_widget)
        self.lista_layout.setSpacing(10)
        self.lista_layout.setContentsMargins(0, 0, 0, 0)
        self.lista_layout.addStretch()
        self.scroll.setWidget(self.lista_widget)
        layout.addWidget(self.scroll)

        # Barra de búsqueda
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setStyleSheet(STYLE_INPUT)
        self.txt_buscar.setPlaceholderText("Buscar por nombre, ID o departamento...")
        self.txt_buscar.textChanged.connect(self._filtrar_perfiles)
        layout.addWidget(self.txt_buscar)

        # Botones inferiores
        btn_row = QHBoxLayout()
        btn_volver = QPushButton("← Volver")
        btn_volver.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_volver.clicked.connect(self.volver_cb)
        btn_row.addWidget(btn_volver)

        btn_row.addStretch()

        # Sincronizar: descarga del lector y actualiza Railway
        self.btn_sync = QPushButton("Sincronizar con lector")
        self.btn_sync.setStyleSheet(STYLE_BTN_SECONDARY)
        self.btn_sync.setToolTip("Descarga los perfiles del lector y los guarda en Railway")
        self.btn_sync.clicked.connect(self._sincronizar)
        btn_row.addWidget(self.btn_sync)

        if self.es_admin:
            self.btn_nuevo = QPushButton("Nuevo perfil")
            self.btn_nuevo.setStyleSheet(STYLE_BTN_PRIMARY)
            self.btn_nuevo.clicked.connect(self._nuevo_perfil)
            btn_row.addWidget(self.btn_nuevo)

        layout.addLayout(btn_row)

    # --- Carga desde Railway ---

    def _cargar_perfiles(self):
        """Lee los perfiles desde Railway (fuente de verdad de la UI)."""
        self.lbl_sub.setText("Cargando desde Railway...")
        self._thread = HiloCargarPerfiles()
        self._thread.resultado.connect(self._on_perfiles_cargados)
        self._thread.error.connect(self._on_error_db)
        self._thread.start()

    def _sincronizar(self):
        """Conecta al lector, descarga perfiles y los guarda en Railway."""
        self.btn_sync.setEnabled(False)
        self.lbl_sub.setText("Conectando al lector...")

        self._thread = HiloSincronizarPerfiles()
        self._thread.progreso.connect(self.lbl_sub.setText)
        self._thread.resultado.connect(self._on_sync_completada)
        self._thread.error.connect(self._on_error_lector)
        self._thread.start()

    def _on_sync_completada(self, perfiles):
        self.btn_sync.setEnabled(True)
        self._on_perfiles_cargados(perfiles)

    def _on_perfiles_cargados(self, perfiles):
        self._perfiles = perfiles
        count = len(perfiles)
        self.lbl_sub.setText(
            f"{count} perfil{'es' if count != 1 else ''} registrado{'s' if count != 1 else ''}"
        )
        self._refrescar_lista()

    def _on_error_db(self, msg):
        self.lbl_sub.setText("⚠ Error al leer Railway")
        self._limpiar_lista()
        lbl = QLabel(f"No se pudieron cargar los perfiles:\n{msg}")
        lbl.setStyleSheet(STYLE_LABEL_SUB)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self.lista_layout.insertWidget(0, lbl)

    def _on_error_lector(self, msg):
        if hasattr(self, 'btn_sync'):
            self.btn_sync.setEnabled(True)
        self.lbl_sub.setText("⚠ Sin conexión al lector")
        self._limpiar_lista()
        lbl = QLabel(
            f"No se pudo conectar al lector:\n{msg}\n\n"
            "Verifica la configuración en el módulo Lector.\n"
            "Los perfiles guardados en Railway siguen disponibles."
        )
        lbl.setStyleSheet(STYLE_LABEL_SUB)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self.lista_layout.insertWidget(0, lbl)
        # Cargar igual desde Railway aunque el lector falle
        self._cargar_perfiles()

    def _limpiar_lista(self):
        while self.lista_layout.count() > 1:
            item = self.lista_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refrescar_lista(self, perfiles=None):
        if perfiles is None:
            perfiles = self._perfiles
        self._limpiar_lista()
        if not perfiles:
            lbl = QLabel("No hay perfiles registrados en el lector.")
            lbl.setStyleSheet(STYLE_LABEL_SUB)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lista_layout.insertWidget(0, lbl)
            return
        for p in perfiles:
            self.lista_layout.insertWidget(
                self.lista_layout.count() - 1,
                self._fila(p)
            )

    def _filtrar_perfiles(self):
        query = self.txt_buscar.text().strip().lower()
        if not query:
            self._refrescar_lista()
            return
        filtrados = []
        for p in self._perfiles:
            nombre = p.get('nombre', '').lower()
            user_id = str(p.get('user_id', '')).lower()
            depto = p.get('departamento', '').lower()
            if query in nombre or query in user_id or query in depto:
                filtrados.append(p)
        self._refrescar_lista(filtrados)

    def _fila(self, perfil):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: rgb(255, 255, 255);
                border-radius: 10px;
                border: 1px solid rgb(181, 212, 244);
            }
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        # Indicador de huella
        tiene_huella = bool(perfil.get('tiene_huella', 0))
        dot = QLabel("👆" if tiene_huella else "○")
        dot.setStyleSheet(
            "font-size: 18px; background: transparent;" if tiene_huella
            else "color: rgba(255,255,255,0.3); font-size: 18px; background: transparent;"
        )
        row.addWidget(dot)

        # Info del perfil
        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_nombre = QLabel(perfil.get('nombre', '—'))
        lbl_nombre.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;"
        )
        col.addWidget(lbl_nombre)

        depto   = perfil.get('departamento') or 'Sin departamento'
        horario = perfil.get('horario', 0)
        huella_txt = "Huella registrada" if tiene_huella else "Sin huella"
        lbl_meta = QLabel(
            f"ID: {perfil.get('user_id', '?')}  ·  {depto}  ·  {huella_txt}  ·  Horario: {horario}"
        )
        lbl_meta.setStyleSheet(STYLE_LABEL_SMALL)
        col.addWidget(lbl_meta)
        row.addLayout(col)

        # Indicador de pendiente de sincronización
        if not perfil.get('lector_synced', 1):
            op = perfil.get('pending_op', '')
            iconos = {'crear': '＋', 'editar': '✎', 'eliminar': '✕'}
            lbl_pending = QLabel(f"{iconos.get(op, '?')} Pendiente")
            lbl_pending.setStyleSheet(
                "color: #FFD54F; font-family: Arial; font-size: 14px; "
                "font-weight: bold; background: rgba(255,180,0,0.18); "
                "border-radius: 4px; padding: 2px 7px;"
            )
            row.addWidget(lbl_pending)

        row.addStretch()

        # Editar y Eliminar (solo admin)
        if self.es_admin:
            btn_edit = QPushButton("Editar")
            btn_edit.setStyleSheet(STYLE_BTN_SECONDARY)
            btn_edit.setMinimumWidth(100)
            btn_edit.clicked.connect(lambda _, p=perfil: self._editar_perfil(p))
            row.addWidget(btn_edit)

            btn_del = QPushButton("Eliminar")
            btn_del.setStyleSheet(STYLE_BTN_DANGER)
            btn_del.setMinimumWidth(100)
            btn_del.clicked.connect(lambda _, p=perfil: self._eliminar_perfil(p))
            row.addWidget(btn_del)

        return frame

    # --- Acciones ---

    def _editar_perfil(self, perfil):
        dlg = DialogoEditarPerfil(self, perfil)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.obtener_datos()
        if not datos:
            return
        self.lbl_sub.setText("Aplicando cambios...")
        self._thread = HiloEditarPerfil(datos, perfil['user_id'])
        self._thread.resultado.connect(self._on_perfil_editado)
        self._thread.error.connect(self._on_error_lector)
        self._thread.start()

    def _on_perfil_editado(self, resultado):
        if resultado is True:
            QMessageBox.information(self, "Éxito",
                "Perfil actualizado en el lector y en Railway.")
        else:
            QMessageBox.information(self, "Guardado en Railway",
                "El lector no estaba disponible.\n"
                "Los cambios se guardaron en Railway y se aplicarán\n"
                "al lector en la próxima sincronización.")
        self._cargar_perfiles()

    def _nuevo_perfil(self):
        ultimo_id = max(
            (int(p['user_id']) for p in self._perfiles if str(p['user_id']).isdigit()),
            default=0
        )
        dlg = DialogoPerfil(self, ultimo_id)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        datos = dlg.obtener_datos()
        if not datos:
            return

        if hasattr(self, 'btn_nuevo'):
            self.btn_nuevo.setEnabled(False)
        self.lbl_sub.setText("Creando perfil en lector y Railway...")

        self._thread = HiloCrearPerfil(datos)
        self._thread.resultado.connect(self._on_perfil_creado)
        self._thread.error.connect(self._on_error_lector)
        self._thread.start()

    def _on_perfil_creado(self, resultado):
        if hasattr(self, 'btn_nuevo'):
            self.btn_nuevo.setEnabled(True)
        if resultado is True:
            QMessageBox.information(
                self, "Éxito",
                "Perfil creado en el lector y guardado en Railway.\n\n"
                "Recuerda que la huella debe registrarse físicamente en el dispositivo."
            )
        else:
            QMessageBox.information(
                self, "Guardado en Railway",
                "El lector no estaba disponible.\n"
                "El perfil se guardó en Railway y se aplicará\n"
                "al lector en la próxima sincronización."
            )
        self._cargar_perfiles()

    def _eliminar_perfil(self, perfil):
        resp = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar el perfil de '{perfil.get('nombre', perfil['user_id'])}'?\n"
            "Se eliminará del lector y de Railway.\n"
            "Esta acción también borrará su huella registrada.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.lbl_sub.setText("Eliminando perfil del lector y Railway...")

        self._thread = HiloEliminarPerfil(perfil['user_id'])
        self._thread.resultado.connect(self._on_perfil_eliminado)
        self._thread.error.connect(self._on_error_lector)
        self._thread.start()

    def _on_perfil_eliminado(self, resultado):
        if resultado is True:
            QMessageBox.information(self, "Éxito",
                "Perfil eliminado del lector y de Railway.")
        else:
            QMessageBox.information(self, "Eliminado de Railway",
                "El lector no estaba disponible.\n"
                "El perfil se eliminó de Railway y se borrará del lector\n"
                "en la próxima sincronización.")
        self._cargar_perfiles()


# =========================================================
# PANTALLA: MENÚ INTERNO DE REGISTROS
# =========================================================
class PantallaMenuRegistros(QWidget):

    def __init__(self, sesion, ir_usuarios_cb, ir_dispositivo_cb, volver_menu_cb, parent=None):
        super().__init__(parent)
        self.sesion          = sesion
        self.es_admin        = (sesion.rol == ROL_ADMIN)
        self.ir_usuarios_cb  = ir_usuarios_cb
        self.ir_dispositivo_cb = ir_dispositivo_cb
        self.volver_menu_cb  = volver_menu_cb
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 90, 40, 40)
        layout.setSpacing(20)

        titulo = QLabel("Registros")
        titulo.setStyleSheet(STYLE_LABEL_TITULO)
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        rol_txt = "Administrador" if self.es_admin else "Usuario normal"
        sub = QLabel(f"Sesión: {rol_txt}")
        sub.setStyleSheet(STYLE_LABEL_SUB)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addStretch(1)

        # Fila de tarjetas
        cards_row = QHBoxLayout()
        cards_row.setSpacing(30)
        cards_row.addStretch(1)

        if self.es_admin:
            cards_row.addWidget(self._tarjeta(
                "👥", "Gestión de Usuarios",
                "Registra, edita y elimina\ncuentas del sistema",
                "Solo Administrador", "#4CAF50",
                self.ir_usuarios_cb
            ))

        cards_row.addWidget(self._tarjeta(
            "🔌", "Registros de Dispositivo",
            "Administra los registros\ndel hardware de asistencia",
            "Acceso completo" if self.es_admin else "Acceso limitado",
            "#2196F3",
            self.ir_dispositivo_cb
        ))

        cards_row.addStretch(1)
        layout.addLayout(cards_row)

        layout.addStretch(1)

        # Botón volver al menú principal
        btn_row = QHBoxLayout()
        btn_volver = QPushButton("← Menú principal")
        btn_volver.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_volver.clicked.connect(self.volver_menu_cb)
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
        lbl_titulo.setStyleSheet("color: rgb(24, 95, 165); font-family: Arial; font-size: 28px; font-weight: bold; background: transparent;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_titulo.setWordWrap(True)
        card_layout.addWidget(lbl_titulo)

        lbl_desc = QLabel(descripcion)
        lbl_desc.setStyleSheet("color: rgb(26, 26, 26); font-family: Arial; font-size: 21px; background: transparent;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        card_layout.addWidget(lbl_desc)

        lbl_badge = QLabel(badge)
        lbl_badge.setStyleSheet(f"""
            color: white;
            background-color: {color_badge};
            font-family: Arial;
            font-size: 21px;
            font-weight: bold;
            padding: 6px 16px;
            border-radius: 12px;
        """)
        lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_badge.setFixedHeight(33)
        card_layout.addWidget(lbl_badge)

        card_layout.addStretch()

        btn = QPushButton("Abrir →")
        btn.setStyleSheet(STYLE_BTN_PRIMARY + " font-size: 18px; padding: 18px 36px;")
        btn.setMinimumHeight(52)
        btn.clicked.connect(callback)
        card_layout.addWidget(btn)

        return frame


# =========================================================
# WIDGET PRINCIPAL: InterfazRegistros
# =========================================================
class InterfazRegistros(QWidget):
    """
    Módulo de Registros.
    Sigue exactamente el mismo patrón estructural que qck_info,
    full_report y advanced_analysis.
    """

    volver_menu = pyqtSignal()

    def __init__(self, sesion=None, parent=None):
        super().__init__(parent)
        self.sesion = sesion

        self.graphics = InterfaceGraphics() if GRAPHICS_AVAILABLE else None

        # Layout raíz
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fondo animado
        self.canvas_fondo = CanvasFondo(self, self.graphics)
        main_layout.addWidget(self.canvas_fondo)

        # Contenedor translúcido sobre el fondo
        self.contenedor = QWidget(self)
        self.contenedor.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.contenedor.setStyleSheet("background: transparent;")

        # Timer de animación
        self.timer = QTimer()
        self.timer.timeout.connect(self.canvas_fondo.update)
        self.timer.start(33)

        self._ir_menu_registros()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.contenedor.setGeometry(0, 0, self.width(), self.height())

    # --- Navegación interna ---

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

    def _ir_menu_registros(self):
        self._limpiar()
        self._montar(PantallaMenuRegistros(
            sesion=self.sesion,
            ir_usuarios_cb=self._ir_usuarios,
            ir_dispositivo_cb=self._ir_dispositivo,
            volver_menu_cb=self._salir,
            parent=self.contenedor
        ))

    def _ir_usuarios(self):
        self._limpiar()
        self._montar(PantallaUsuarios(
            sesion=self.sesion,
            volver_cb=self._ir_menu_registros,
            parent=self.contenedor
        ))

    def _ir_dispositivo(self):
        self._limpiar()
        self._montar(PantallaDispositivo(
            sesion=self.sesion,
            volver_cb=self._ir_menu_registros,
            parent=self.contenedor
        ))

    def _salir(self):
        self.timer.stop()
        self.volver_menu.emit()


# =========================================================
# MAIN (ejecución independiente para debugging)
# =========================================================
def main():
    if os.name == 'nt' and GRAPHICS_AVAILABLE:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    ocultar_consola_windows()
    app = QApplication(sys.argv)

    # Sesión de prueba — cambia rol a ROL_USUARIO para probar permisos normales
    class SesionDebug:
        user_name = "admin"
        rol       = ROL_ADMIN

    ventana = QMainWindow()
    ventana.setWindowTitle("Registros — Debug")
    widget = InterfazRegistros(sesion=SesionDebug())
    widget.volver_menu.connect(app.quit)
    ventana.setCentralWidget(widget)
    ventana.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()