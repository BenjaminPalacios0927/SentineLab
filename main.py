import sys
import os
import ctypes
import traceback

if getattr(sys, 'frozen', False) and os.name == 'nt':
    # Redirigir stdout y stderr a devnull para que no salten ventanas negras
    f = open(os.devnull, 'w')
    sys.stdout = f
    sys.stderr = f
    # Intentar desvincular la consola física si el sistema intentó crear una
    try:
        ctypes.windll.kernel32.FreeConsole()
    except:
        pass

import mysql.connector
import bcrypt

def resource_path(relative_path):
    """ Obtiene la ruta absoluta de los recursos, compatible con PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
 
    return os.path.join(base_path, relative_path)

# --- Configuración DPI ---
if os.name == "nt":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

    # Desvincula la consola en Windows para evitar ventana negra
    try:
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLineEdit,
    QPushButton,
    QLabel,
    QStackedWidget,
    QMessageBox,
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QPointF, QThread, QRectF, QSize
from PyQt6.QtGui import QPainter, QFont, QColor, QPen, QBrush

# --- IMPORTACIONES MODULARES ---
try:
    from interface_graphics import InterfaceGraphics
except ImportError:
    class InterfaceGraphics:
        def dibujar_gradiente_animado(self, *args): ...
        def dibujar_escena_bienvenida(self, *args): ...
        def dibujar_escena_menu(self, *args): return []
        def dibujar_notificaciones(self, *args): ...
        def dibujar_mensajes_estado(self, *args): ...

# =========================================================
# CONFIGURACIÓN DE BASE DE DATOS
# Las credenciales ya no están hardcodeadas aquí.
# Se leen en tiempo de ejecución desde db.cfg, que el
# administrador configura desde la pantalla de hardware.
# =========================================================
def _db_cfg() -> dict:
    try:
        from device_config import construir_db_config_conexion
        return construir_db_config_conexion()
    except Exception:
        return {}

# =========================================================
# SESIÓN
# =========================================================
class SessionData:
    def __init__(self):
        self.user_name = None
        self.rol = None
        self.is_active = False

    def clear(self):
        self.user_name = None
        self.rol = None
        self.is_active = False

# =========================================================
# HILO DE AUTENTICACIÓN
# =========================================================
class DBLoginThread(QThread):
    progreso = pyqtSignal(str)
    login_exitoso = pyqtSignal(int)  # Envía el Rol
    login_fallido = pyqtSignal(str)

    def __init__(self, user, pwd):
        super().__init__()
        self.user = user
        self.pwd = pwd

    def run(self):
        try:
            self.progreso.emit("Conectando a la nube...")
            import mysql.connector
            import bcrypt
            conn = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor(dictionary=True)

            query = "SELECT pasw, rol, status, `del` FROM users WHERE name = %s"
            cursor.execute(query, (self.user,))
            result = cursor.fetchone()

            if not result or result['del'] == 1 or result['status'] == 0:
                self.login_fallido.emit("Acceso denegado")
                return

            if bcrypt.checkpw(self.pwd.encode('utf-8'), result['pasw'].encode('utf-8')):
                self.login_exitoso.emit(result['rol'])
            else:
                self.login_fallido.emit("Contraseña incorrecta")

            cursor.close()
            conn.close()
        except mysql.connector.errors.InterfaceError as e:
            self.login_fallido.emit("Sin conexión. Verifica tu red e inténtalo de nuevo.")
        except Exception as e:
            self.login_fallido.emit(f"Error: {str(e)}")

# =========================================================
# HILO: SINCRONIZACIÓN DE DATOS DEL LECTOR
# =========================================================
class HiloSincronizacion(QThread):
    """
    Usa la configuración guardada del lector para descargar
    los marcajes más recientes y subirlos a Railway.
    """
    progreso   = pyqtSignal(str)
    completado = pyqtSignal(int)
    error      = pyqtSignal(str)

    def __init__(self, config_lector):
        super().__init__()
        self.config = config_lector  # {'ip': '...', 'puerto': '...'}

    def run(self):
        try:
            from hardware_handler import K30Controller
            import mysql.connector

            self.progreso.emit("Conectando al lector...")
            ctrl = K30Controller(
                ip=self.config.get('ip'),
                port=int(self.config.get('puerto', 4370)),
                password=self.config.get('password'),
            )
            if not ctrl.conectar():
                self.error.emit("No se pudo conectar al lector.")
                return

            # ── Descargar asistencias ──────────────────────────
            self.progreso.emit("Descargando registros de asistencia...")
            registros = ctrl.descargar_asistencias()

            # ── Descargar perfiles ─────────────────────────────
            self.progreso.emit("Descargando perfiles del lector...")
            perfiles = ctrl.obtener_usuarios()

            ctrl.desconectar()

            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()
            BATCH  = 100   # registros por commit

            # Guardar asistencias en lotes
            if registros:
                self.progreso.emit(f"Guardando {len(registros)} registros de asistencia...")
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
                filas = [(r['user_id'], r['timestamp'], r['status']) for r in registros]
                for i in range(0, len(filas), BATCH):
                    lote = filas[i:i + BATCH]
                    cursor.executemany(
                        "INSERT INTO attendance_raw (user_id, timestamp, status) "
                        "VALUES (%s, %s, %s)",
                        lote
                    )
                    conn.commit()
                    self.progreso.emit(
                        f"Asistencias: {min(i + BATCH, len(filas))}/{len(filas)}..."
                    )

            # Guardar perfiles en lotes (upsert)
            if perfiles:
                self.progreso.emit(f"Guardando {len(perfiles)} perfiles...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS device_users (
                        user_id      VARCHAR(20)  NOT NULL PRIMARY KEY,
                        nombre       VARCHAR(100) NOT NULL,
                        departamento VARCHAR(100) DEFAULT '',
                        horario      INT          DEFAULT 0,
                        tiene_huella TINYINT      DEFAULT 0,
                        synced_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                filas_p = [
                    (
                        str(p['user_id']),
                        p.get('nombre', ''),
                        p.get('departamento', ''),
                        p.get('horario', 0),
                        1 if p.get('huella') else 0,
                    )
                    for p in perfiles
                ]
                for i in range(0, len(filas_p), BATCH):
                    lote = filas_p[i:i + BATCH]
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
                    self.progreso.emit(
                        f"Perfiles: {min(i + BATCH, len(filas_p))}/{len(filas_p)}..."
                    )

            cursor.close()
            conn.close()

            total = len(registros) + len(perfiles)
            self.completado.emit(total)

        except mysql.connector.errors.InterfaceError:
            self.error.emit("Sin conexión a Railway. Verifica tu red e inténtalo de nuevo.")
        except OSError as e:
            # Captura específicamente el [WinError 6] u otros fallos de hardware en Windows
            if getattr(e, 'winerror', None) == 6:
                self.error.emit("No se pudo conectar con el lector.")
            else:
                self.error.emit(f"Error de comunicación con el hardware: {str(e)}")
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# ESCENA 1: LOGIN
# =========================================================
class LoginScene(QWidget):
    login_exitoso = pyqtSignal(int) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gfx = InterfaceGraphics()
        self.tiempo_animacion = 0

        self.txt_usuario = QLineEdit(self)
        self.txt_usuario.setPlaceholderText("Usuario")
        self.txt_usuario.setStyleSheet(self._get_input_style())

        self.txt_password = QLineEdit(self)
        self.txt_password.setPlaceholderText("Contraseña")
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setStyleSheet(self._get_input_style())
        self.txt_password.returnPressed.connect(self.iniciar_proceso_login)

        self.btn_ingresar = QPushButton("INGRESAR", self)
        self.btn_ingresar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ingresar.setStyleSheet(self._get_btn_style())
        self.btn_ingresar.clicked.connect(self.iniciar_proceso_login)

        self.mensaje_estado = ""
        self.mensaje_error = ""
        self.db_thread = None

    def resizeEvent(self, event):
        cx = self.width() // 2
        cy = self.height() // 2
        self.txt_usuario.setGeometry(cx - 175, cy - 42, 350, 46)
        self.txt_password.setGeometry(cx - 175, cy + 18, 350, 46)
        self.btn_ingresar.setGeometry(cx - 120, cy + 84, 240, 50)
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.gfx.dibujar_gradiente_animado(painter, self.width(), self.height(), self.tiempo_animacion)
        self.gfx.dibujar_escena_bienvenida(painter, self.width(), self.height())
        self.gfx.dibujar_mensajes_estado(painter, self.width(), self.mensaje_error, self.mensaje_estado)

    def iniciar_proceso_login(self):
        user = self.txt_usuario.text().strip()
        pwd = self.txt_password.text().strip()

        if not user or not pwd:
            self.mensaje_error = "Complete los campos"
            self.update()
            return

        self.mensaje_error = ""
        self.btn_ingresar.setEnabled(False)
        self.mensaje_estado = "Conectando..."
        self.update()

        self.db_thread = DBLoginThread(user, pwd)
        self.db_thread.progreso.connect(self.actualizar_progreso)
        self.db_thread.login_fallido.connect(self.manejar_error)
        self.db_thread.login_exitoso.connect(self.manejar_exito)
        self.db_thread.start()

    def actualizar_progreso(self, msg):
        self.mensaje_estado = msg
        self.update()

    def manejar_error(self, error):
        self.mensaje_estado = ""
        self.mensaje_error = str(error)
        self.btn_ingresar.setEnabled(True)
        self.update()

    def manejar_exito(self, rol):
        self.mensaje_estado = "Acceso concedido"
        self.mensaje_error = ""
        self.update()
        QTimer.singleShot(800, lambda: self.login_exitoso.emit(rol))

    def _get_input_style(self):
        return (
            "QLineEdit { background-color: rgb(241, 239, 232); border: 1px solid rgb(181, 212, 244); "
            "border-radius: 8px; color: #1a1a1a; padding: 6px 10px; font-size: 18px; } "
            "QLineEdit:focus { background-color: white; border: 2px solid rgb(24, 95, 165); }"
        )
    
    def _get_btn_style(self):
        return (
            "QPushButton { background-color: rgb(24, 95, 165); border-radius: 10px; color: white; "
            "font-size: 18px; font-weight: bold; } "
            "QPushButton:hover { background-color: rgb(12, 68, 124); } "
            "QPushButton:disabled { background-color: rgb(181, 212, 244); color: white; }"
        )

# =========================================================
# ESCENA 2: MENÚ
# =========================================================
class BtnSincronizar(QPushButton):
    RADIO = 28  

    def __init__(self, parent=None):
        super().__init__(parent)
        d = self.RADIO * 2
        self.setFixedSize(d, d)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Sincronizar datos del lector")
        self._sincronizando = False
        self._angulo        = 0          
        self._aplicar_estilo(False)

    def _aplicar_estilo(self, activo):
        base = "#2eaadc" if not activo else "#1a8db8"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {base};
                border-radius: {self.RADIO}px;
                color: white;
                font-size: 20px;
                font-weight: bold;
                border: 2px solid rgba(255,255,255,0.4);
            }}
            QPushButton:hover {{
                background-color: #3bbcee;
            }}
            QPushButton:disabled {{
                background-color: #7ab8d0;
            }}
        """)
        self.setText("↻")

    def set_sincronizando(self, valor: bool):
        self._sincronizando = valor
        self.setEnabled(not valor)
        self._aplicar_estilo(valor)
        self.setText("↻" if not valor else "…")


class MenuScene(QWidget):
    abrir_modulo  = pyqtSignal(str)
    sincronizar   = pyqtSignal()       

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gfx = InterfaceGraphics()
        self.tiempo_animacion = 0
        self.user_rol = 1
        self.setMouseTracking(True)
        self.botones_rects = []
        self.hover_idx     = -1
        self.cargando      = False

        self.btn_sync = BtnSincronizar(self)
        self.btn_sync.clicked.connect(self.sincronizar.emit)

        self.lbl_sync = QLabel("", self)
        self.lbl_sync.setStyleSheet(
            "color: rgba(0,0,0,0.85); font-size: 10px; "
            "background: transparent;"
        )
        self.lbl_sync.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sync.setFixedWidth(90)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        BOTTOMBAR_H = 82
        lector_w    = 154
        lector_h    = 50
        lector_x    = 20
        bar_y       = self.height() - BOTTOMBAR_H
        lector_y    = bar_y + (BOTTOMBAR_H - lector_h) / 2

        r = BtnSincronizar.RADIO
        sync_x = int(lector_x + lector_w + 14)
        btn_y  = int(lector_y + (lector_h - r * 2) / 2)
        self.btn_sync.move(sync_x, btn_y)

        self.lbl_sync.move(
            sync_x - (self.lbl_sync.width() - r * 2) // 2,
            btn_y + r * 2 + 4
        )

    def set_estado_sync(self, msg: str, sincronizando: bool = False):
        self.btn_sync.set_sincronizando(sincronizando)
        self.lbl_sync.setText(msg)
        self.lbl_sync.adjustSize()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            self.gfx.dibujar_gradiente_animado(painter, w, h, self.tiempo_animacion)
            self.botones_rects = self.gfx.dibujar_escena_menu(painter, w, h, [], self.hover_idx)
            if self.cargando:
                self._dibujar_overlay_carga(painter, w, h)
        except Exception as e:
            print(f"Error en paintEvent Menú: {e}")

    def _dibujar_overlay_carga(self, painter, w, h):
        painter.setBrush(QColor(0, 0, 0, 180))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Cargando módulo...")

    def mouseMoveEvent(self, event):
        if self.cargando:
            return
        pos = event.pos()
        nuevo_hover = -1
        for idx, (rect, _) in enumerate(self.botones_rects):
            if rect.contains(QPointF(pos)):
                nuevo_hover = idx
                break
        if nuevo_hover != self.hover_idx:
            self.hover_idx = nuevo_hover
            self.update()

    def mousePressEvent(self, event):
        if self.cargando:
            return
        if event.button() == Qt.MouseButton.LeftButton and self.hover_idx != -1:
            _, accion = self.botones_rects[self.hover_idx]
            self.ejecutar_accion(accion)

    def ejecutar_accion(self, accion):
        if accion == "Salir":
            ventana = self.window()
            if hasattr(ventana, 'logout'):
                ventana.logout()
            return

        modulos_embebidos = {
            "Informe rápido":         "qck_info",
            "Reportes":               "full_report",
            "Análisis y\npredicción": "advanced_analysis",
            "Registros":              "registros",
            "Lector":                 "lector",
        }

        if accion in modulos_embebidos:
            self.abrir_modulo.emit(modulos_embebidos[accion])
            return

        print(f"Acción '{accion}' no tiene módulo asignado.")


# =========================================================
# VENTANA PRINCIPAL
# =========================================================
class SistemaAsistencia(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema Autónomo v2.0.")
        self.resize(1000, 700)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.sesion = SessionData()
        self.scene_login = LoginScene()
        self.scene_menu = MenuScene()

        self.stack.addWidget(self.scene_login)   
        self.stack.addWidget(self.scene_menu)    

        self.modulos = {}
        self._registrar_modulos()

        try:
            from device_config import cargar_config_dispositivo
            self.config_lector = cargar_config_dispositivo()
        except Exception:
            self.config_lector = {}
        self._hilo_sync = None

        self.scene_login.login_exitoso.connect(self.abrir_sesion)
        self.scene_menu.abrir_modulo.connect(self.abrir_modulo)
        self.scene_menu.sincronizar.connect(self.sincronizar_lector)

        self.timer_animacion = QTimer(self)
        self.timer_animacion.timeout.connect(self.actualizar_animacion)
        self.timer_animacion.start(16)

    def _registrar_modulos(self):
        self.modulos_registro = {
            "qck_info":          ("qck_info",          "InterfazAsistenciaMejorada"),
            "full_report":       ("full_report",       "InterfazReportesCompletos"),
            "advanced_analysis": ("advanced_analysis", "InterfazAnalisisAvanzado"),
            "registros":         ("registros",         "InterfazRegistros"),
            "lector":            ("device_config",     "InterfazConfigLector"),
        }
        self.modulos = {}

    def actualizar_animacion(self):
        t = self.scene_login.tiempo_animacion + 1
        self.scene_login.tiempo_animacion = t
        self.scene_menu.tiempo_animacion = t
        self.stack.currentWidget().update()

    def abrir_modulo(self, nombre):
        import importlib

        if nombre in self.modulos:
            widget = self.modulos[nombre]
            if hasattr(widget, 'timer') and not widget.timer.isActive():
                widget.timer.start(33)
            self.stack.setCurrentWidget(widget)
            return

        if nombre not in self.modulos_registro:
            QMessageBox.warning(self, "Módulo no disponible",
                f"El módulo '{nombre}' no está registrado en el sistema.")
            return

        modulo_archivo, clase_nombre = self.modulos_registro[nombre]
        try:
            import sys
            if modulo_archivo in sys.modules:
                del sys.modules[modulo_archivo]

            mod = importlib.import_module(modulo_archivo)

            if not hasattr(mod, clase_nombre):
                raise AttributeError(
                    f"El archivo '{modulo_archivo}.py' no contiene la clase '{clase_nombre}'.\n"
                    f"Clases disponibles: {[x for x in dir(mod) if not x.startswith('_')]}"
                )
            ClaseWidget = getattr(mod, clase_nombre)
            widget      = ClaseWidget(sesion=self.sesion)
            widget.volver_menu.connect(self.ir_al_menu_desde_modulo)
            if hasattr(widget, "conectar_dispositivo"):
                widget.conectar_dispositivo.connect(self.on_lector_conectado)
            self.modulos[nombre] = widget
            self.stack.addWidget(widget)
            self.stack.setCurrentWidget(widget)
        except Exception as e:
            QMessageBox.critical(self, "Error al cargar módulo",
                f"No se pudo abrir '{nombre}':\n{str(e)}")

    def ir_al_menu_desde_modulo(self):
        self.stack.setCurrentIndex(1)

    def ir_al_menu(self, rol):
        self.scene_menu.user_rol = rol
        self.stack.setCurrentIndex(1)
        self.scene_login.txt_password.clear()
        self.scene_login.btn_ingresar.setEnabled(True)

    def abrir_sesion(self, rol):
        self.sesion.user_name = self.scene_login.txt_usuario.text()
        self.sesion.rol = rol
        self.sesion.is_active = True
        
        self.scene_menu.user_rol = rol
        self.stack.setCurrentIndex(1) 
        self.scene_login.txt_password.clear()
        self.scene_login.btn_ingresar.setEnabled(True)

    def logout(self):
        self.sesion.clear()
        for nombre, widget in list(self.modulos.items()):
            if hasattr(widget, 'timer') and widget.timer.isActive():
                widget.timer.stop()
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.modulos.clear()
        self.stack.setCurrentIndex(0)
        self.scene_login.mensaje_estado = "Sesión cerrada"
        self.scene_login.txt_usuario.clear()
        self.scene_login.txt_password.clear()
        self.scene_login.btn_ingresar.setEnabled(True)
        self.scene_login.update()

    def on_lector_conectado(self, config: dict):
        self.config_lector = config

    def sincronizar_lector(self):
        if not self.config_lector:
            QMessageBox.information(
                self,
                "Sin configuración",
                "Primero configura el lector desde el módulo \'Lector\'."
            )
            return

        if self._hilo_sync and self._hilo_sync.isRunning():
            return  

        self.scene_menu.set_estado_sync("Sincronizando...", sincronizando=True)

        self._hilo_sync = HiloSincronizacion(self.config_lector)
        self._hilo_sync.progreso.connect(
            lambda msg: self.scene_menu.set_estado_sync(msg, sincronizando=True)
        )
        self._hilo_sync.completado.connect(self._on_sync_completada)
        self._hilo_sync.error.connect(self._on_sync_error)
        self._hilo_sync.start()

    def _on_sync_completada(self, cantidad):
        msg = f"✔ {cantidad} elemento{'s' if cantidad != 1 else ''} sincronizado{'s' if cantidad != 1 else ''}"
        self.scene_menu.set_estado_sync(msg, sincronizando=False)

    def _on_sync_error(self, msg):
        self.scene_menu.set_estado_sync("✘ Error", sincronizando=False)
        QMessageBox.critical(self, "Error de sincronización", msg)

    def closeEvent(self, event):
        self.sesion.clear()
        event.accept()

def run_main_app():
    app = QApplication(sys.argv)
    ventana = SistemaAsistencia()
    ventana.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_main_app()