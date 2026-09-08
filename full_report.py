import sys
import os
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QFrame,
    QFileDialog, QMessageBox, QDateEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import QTimer, Qt, QDate, pyqtSignal, QThread
from PyQt6.QtGui import QPainter, QColor, QBrush


def ocultar_consola_windows():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

try:
    from interface_graphics import InterfaceGraphics
    GRAPHICS_IMPORTED = True
except ImportError:
    GRAPHICS_IMPORTED = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from attendance_processor import ProcesadorReporteAsistencia
    PROCESSOR_AVAILABLE = True
except ImportError:
    PROCESSOR_AVAILABLE = False

# =========================================================
# ESTILOS
# =========================================================
STYLE_BTN_BLANCO = """
    QPushButton {
        background-color: rgb(15, 110, 86);
        color: white;
        font-family: Arial;
        font-size: 17px;
        font-weight: bold;
        padding: 14px 32px;
        border-radius: 10px;
        border: none;
    }
    QPushButton:hover { background-color: rgb(10, 80, 62); }
    QPushButton:disabled { background-color: rgb(159, 225, 203); color: white; }
"""
STYLE_BTN_GRIS = """
    QPushButton {
        background-color: white;
        color: rgb(24, 95, 165);
        font-family: Arial;
        font-size: 17px;
        font-weight: bold;
        padding: 14px 32px;
        border-radius: 10px;
        border: 2px solid rgb(24, 95, 165);
    }
    QPushButton:hover { background-color: rgb(230, 241, 251); }
    QPushButton:disabled { background-color: rgb(241, 239, 232); color: rgb(181, 212, 244); }
"""
STYLE_BTN_VERDE = """
    QPushButton {
        background-color: rgb(24, 95, 165);
        color: white;
        font-family: Arial;
        font-size: 17px;
        font-weight: bold;
        padding: 14px 32px;
        border-radius: 10px;
        border: none;
    }
    QPushButton:hover { background-color: rgb(12, 68, 124); }
    QPushButton:disabled { background-color: rgb(181, 212, 244); color: white; }
"""

def _estilo_calendario() -> str:
    return """
        QDateEdit {
            background-color: white;
            color: black;
            font-family: Arial;
            font-size: 16px;
            padding: 6px;
            border-radius: 4px;
            border: none;
        }
        QCalendarWidget QWidget { background-color: white; color: black; }
        QCalendarWidget QToolButton { color: black; background-color: transparent; icon-size: 20px; }
        QCalendarWidget QMenu { background-color: white; color: black; }
        QCalendarWidget QSpinBox {
            background-color: white; color: black;
            selection-background-color: #2196F3;
        }
        QCalendarWidget QAbstractItemView:enabled {
            color: black; background-color: white;
            selection-background-color: #2196F3; selection-color: white;
        }
    """

# =========================================================
# HILOS
# =========================================================
class HiloCargaEmpleados(QThread):
    """Carga empleados desde device_users sin filtro de fechas."""
    completado = pyqtSignal(object)
    error      = pyqtSignal(str)

    def __init__(self, procesador):
        super().__init__()
        self.procesador = procesador

    def run(self):
        try:
            self.procesador.cargar_datos_desde_railway()
            self.completado.emit(self.procesador.obtener_lista_empleados())
        except Exception as e:
            self.error.emit(str(e))


class HiloGenerarTabla(QThread):
    completado = pyqtSignal(object)
    error      = pyqtSignal(str)

    def __init__(self, procesador, id_empleado, fecha_inicio, fecha_fin):
        super().__init__()
        self.procesador  = procesador
        self.id_empleado = id_empleado
        self.f_inicio    = fecha_inicio
        self.f_fin       = fecha_fin

    def run(self):
        try:
            self.procesador.cargar_datos_desde_railway(
                self.f_inicio.date(), self.f_fin.date())
            resultado = self.procesador.filtrar_por_periodo(
                self.id_empleado, self.f_inicio, self.f_fin)
            self.completado.emit(resultado)
        except Exception as e:
            self.error.emit(str(e))



class HiloGenerarTodos(QThread):
    """Genera reportes individuales para TODOS los empleados en el periodo."""
    progreso   = pyqtSignal(str)
    completado = pyqtSignal(object)   # lista de dicts, uno por empleado
    error      = pyqtSignal(str)

    def __init__(self, procesador, empleados, fecha_inicio, fecha_fin):
        super().__init__()
        self.procesador  = procesador
        self.empleados   = empleados   # lista de dicts con 'display_name'
        self.f_inicio    = fecha_inicio
        self.f_fin       = fecha_fin

    def run(self):
        try:
            self.procesador.cargar_datos_desde_railway(
                self.f_inicio.date(), self.f_fin.date())

            resultados = []
            total = len(self.empleados)
            for idx, emp in enumerate(self.empleados, start=1):
                try:
                    id_emp = emp['display_name'].split("ID: ")[1].rstrip(")")
                except (IndexError, KeyError):
                    id_emp = emp.get('nombre', '')

                self.progreso.emit(
                    f"Procesando {idx}/{total}: {emp.get('nombre', id_emp)}")

                datos = self.procesador.filtrar_por_periodo(
                    id_emp, self.f_inicio, self.f_fin)
                if datos:
                    resultados.append(datos)

            self.completado.emit(resultados)
        except Exception as e:
            self.error.emit(str(e))


# =========================================================
# CANVAS DE FONDO
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
                painter, self.width(), self.height(), self.tiempo)
        else:
            painter.fillRect(0, 0, self.width(), self.height(), QColor(30, 60, 114))
        self.tiempo += 1


# =========================================================
# WIDGET PRINCIPAL
# =========================================================
class InterfazReportesCompletos(QWidget):
    volver_menu = pyqtSignal()

    def __init__(self, sesion=None, parent=None):
        super().__init__(parent)
        self.sesion     = sesion
        self.graphics   = InterfaceGraphics() if GRAPHICS_IMPORTED else None
        self.procesador = ProcesadorReporteAsistencia() if PROCESSOR_AVAILABLE else None

        self.empleados_disponibles: List[Dict] = []
        self.datos_tabla: Optional[Dict] = None
        self._hilo = None
        self._pantalla_actual = "formulario"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.canvas_fondo = CanvasFondo(self, self.graphics)
        main_layout.addWidget(self.canvas_fondo)

        self.contenedor_widgets = QWidget(self)
        self.contenedor_widgets.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.contenedor_widgets.setStyleSheet("background: transparent;")

        self.timer = QTimer()
        self.timer.timeout.connect(self._actualizar_fondo)
        self.timer.start(33)

        self.cambiar_pantalla("formulario")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.contenedor_widgets.setGeometry(0, 0, self.width(), self.height())

    def _actualizar_fondo(self):
        if self._pantalla_actual != "tabla":
            self.canvas_fondo.update()

    def cambiar_pantalla(self, pantalla: str):
        self._pantalla_actual = pantalla

        if self.contenedor_widgets.layout():
            QWidget().setLayout(self.contenedor_widgets.layout())
        for child in self.contenedor_widgets.findChildren(QWidget):
            child.setParent(None)

        layout = QVBoxLayout(self.contenedor_widgets)
        layout.setContentsMargins(60, 50, 60, 50)
        layout.setSpacing(28)

        if pantalla == "formulario":
            self._crear_pantalla_formulario(layout)
            self._cargar_empleados_async()
        elif pantalla == "tabla":
            self._crear_pantalla_tabla(layout)

    # ----------------------------------------------------------
    # PANTALLA FORMULARIO
    # ----------------------------------------------------------
    def _crear_pantalla_formulario(self, layout):
        layout.addStretch(1)
        
        titulo = QLabel("Reportes Completos")
        titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 60px; font-weight: bold; background: transparent;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        layout.addStretch(1)

        instrucciones = QLabel(
            "Selecciona el empleado del que deseas generar un reporte completo")
        instrucciones.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 25px; background: transparent;")
        instrucciones.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instrucciones)

        self.combo_empleado = QComboBox()
        self.combo_empleado.addItem("-- Cargando empleados... --")
        self.combo_empleado.setStyleSheet("""
    QComboBox {
        background-color: rgb(241, 239, 232);
        color: rgb(26, 26, 26);
        font-family: Arial;
        font-size: 17px;
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid rgb(181, 212, 244);
        min-width: 420px;
    }
    QComboBox:focus { background-color: white; border: 2px solid rgb(24, 95, 165); }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView {
        background-color: white; color: rgb(26, 26, 26);
        selection-background-color: rgb(24, 95, 165); selection-color: white;
        font-size: 17px;
    }
""")
        combo_row = QHBoxLayout()
        combo_row.addStretch()
        combo_row.addWidget(self.combo_empleado)
        combo_row.addStretch()
        layout.addLayout(combo_row)

        layout.addSpacing(20)

        periodo_lbl = QLabel("Periodo de analisis:")
        periodo_lbl.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 25px; background: transparent;")
        periodo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(periodo_lbl)

        fecha_row = QHBoxLayout()
        fecha_row.addStretch()

        col_ini = QVBoxLayout()
        lbl_ini = QLabel("Fecha inicio")
        lbl_ini.setStyleSheet("color: rgb(26, 26, 26); font-family: Arial; font-size: 20px; font-weight: bold; background: transparent;")
        lbl_ini.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fecha_inicio_edit = QDateEdit()
        self.fecha_inicio_edit.setCalendarPopup(True)
        self.fecha_inicio_edit.setDate(QDate.currentDate().addDays(-30))
        self.fecha_inicio_edit.setStyleSheet(_estilo_calendario())
        col_ini.addWidget(lbl_ini)
        col_ini.addWidget(self.fecha_inicio_edit)
        fecha_row.addLayout(col_ini)
        fecha_row.addSpacing(30)

        col_fin = QVBoxLayout()
        lbl_fin = QLabel("Fecha fin")
        lbl_fin.setStyleSheet("color: rgb(26, 26, 26); font-family: Arial; font-size: 20px; font-weight: bold; background: transparent;")
        lbl_fin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fecha_fin_edit = QDateEdit()
        self.fecha_fin_edit.setCalendarPopup(True)
        self.fecha_fin_edit.setDate(QDate.currentDate())
        self.fecha_fin_edit.setStyleSheet(_estilo_calendario())
        col_fin.addWidget(lbl_fin)
        col_fin.addWidget(self.fecha_fin_edit)
        fecha_row.addLayout(col_fin)

        fecha_row.addStretch()
        layout.addLayout(fecha_row)
        layout.addStretch(2)

        btn_row = QHBoxLayout()
        btn_menu = QPushButton("Menu principal")
        btn_menu.setStyleSheet(STYLE_BTN_GRIS)
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)
        btn_row.addStretch()
        self.btn_generar = QPushButton("Generar reporte")
        self.btn_generar.setStyleSheet(STYLE_BTN_BLANCO)
        self.btn_generar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generar.clicked.connect(self._generar_tabla)
        btn_row.addWidget(self.btn_generar)
        layout.addLayout(btn_row)

    def _cargar_empleados_async(self):
        if not self.procesador:
            return
        self._hilo = HiloCargaEmpleados(self.procesador)
        self._hilo.completado.connect(self._on_empleados_cargados)
        self._hilo.error.connect(lambda e: self._combo_error())
        self._hilo.start()

    def _on_empleados_cargados(self, empleados: list):
        self.empleados_disponibles = empleados
        if not hasattr(self, 'combo_empleado'):
            return
        self.combo_empleado.clear()
        self.combo_empleado.addItem("-- Seleccionar empleado --")
        self.combo_empleado.addItem("★ Todos los empleados (compendio)")
        for emp in sorted(empleados, key=lambda e: e['nombre']):
            self.combo_empleado.addItem(emp['display_name'])
        if not empleados:
            self.combo_empleado.addItem("Sin empleados en el periodo")

    def _combo_error(self):
        if hasattr(self, 'combo_empleado'):
            self.combo_empleado.clear()
            self.combo_empleado.addItem("Error al cargar empleados")

    def _generar_tabla(self):
        if not self.procesador:
            QMessageBox.warning(self, "Error", "Modulo de procesamiento no disponible.")
            return

        seleccion = self.combo_empleado.currentText()
        if (not seleccion or seleccion.startswith("--") or
                seleccion.startswith("Sin") or seleccion.startswith("Error")):
            QMessageBox.warning(self, "Advertencia", "Por favor selecciona un empleado.")
            return

        f_inicio = self.fecha_inicio_edit.date().toPyDate()
        f_fin    = self.fecha_fin_edit.date().toPyDate()
        if f_inicio > f_fin:
            QMessageBox.warning(self, "Advertencia",
                                "La fecha de inicio debe ser anterior a la fecha fin.")
            return

        fecha_inicio_dt = datetime.combine(f_inicio, datetime.min.time())
        fecha_fin_dt    = datetime.combine(f_fin,    datetime.max.time())

        self.btn_generar.setEnabled(False)
        self.btn_generar.setText("Consultando...")

        # ── Modo compendio: todos los empleados ──────────────────────────────
        if seleccion.startswith("★"):
            if not self.empleados_disponibles:
                QMessageBox.warning(self, "Advertencia",
                                    "No hay empleados cargados para generar el compendio.")
                self.btn_generar.setEnabled(True)
                self.btn_generar.setText("Generar reporte")
                return
            self._modo_compendio = True
            self._hilo = HiloGenerarTodos(
                self.procesador, self.empleados_disponibles,
                fecha_inicio_dt, fecha_fin_dt)
            self._hilo.progreso.connect(
                lambda msg: self.btn_generar.setText(msg) if hasattr(self, 'btn_generar') else None)
            self._hilo.completado.connect(self._on_todos_listos)
            self._hilo.error.connect(self._on_tabla_error)
            self._hilo.start()
            return

        # ── Modo individual ──────────────────────────────────────────────────
        self._modo_compendio = False
        try:
            id_empleado = seleccion.split("ID: ")[1].rstrip(")")
        except IndexError:
            id_empleado = seleccion

        self._hilo = HiloGenerarTabla(
            self.procesador, id_empleado, fecha_inicio_dt, fecha_fin_dt)
        self._hilo.completado.connect(self._on_tabla_lista)
        self._hilo.error.connect(self._on_tabla_error)
        self._hilo.start()

    def _on_tabla_lista(self, datos):
        if hasattr(self, 'btn_generar'):
            self.btn_generar.setEnabled(True)
            self.btn_generar.setText("Generar reporte")
        if datos:
            self.datos_tabla = datos
            self.cambiar_pantalla("tabla")
        else:
            QMessageBox.warning(self, "Sin datos",
                                "No se encontraron datos para este empleado en el periodo.\n"
                                "Verifica que las fechas esten dentro del rango con registros.")

    def _on_todos_listos(self, lista_datos):
        if hasattr(self, 'btn_generar'):
            self.btn_generar.setEnabled(True)
            self.btn_generar.setText("Generar reporte")
        if lista_datos:
            self.datos_tabla = lista_datos   # lista de dicts
            self.cambiar_pantalla("tabla")
        else:
            QMessageBox.warning(self, "Sin datos",
                                "No se encontraron registros para ningún empleado\n"
                                "en el periodo seleccionado.")

    def _on_tabla_error(self, msg):
        if hasattr(self, 'btn_generar'):
            self.btn_generar.setEnabled(True)
            self.btn_generar.setText("Generar reporte")
        QMessageBox.critical(self, "Error", f"Error al generar el reporte:\n{msg}")

    # ----------------------------------------------------------
    # PANTALLA TABLA (fondo blanco, identico al original)
    # ----------------------------------------------------------
    def _crear_pantalla_tabla(self, layout):
        if not self.datos_tabla:
            return

        layout.setContentsMargins(20, 20, 20, 20)

        # ── Modo compendio: todos los empleados ──────────────────────────────
        if isinstance(self.datos_tabla, list):
            self._crear_pantalla_compendio(layout)
            return

        tabla_widget = QWidget()
        tabla_widget.setStyleSheet("background-color: white; border-radius: 10px;")
        tabla_layout = QVBoxLayout(tabla_widget)
        tabla_layout.setContentsMargins(15, 15, 15, 15)

        titulo = QLabel(f"Reporte Completo - {self.datos_tabla['nombre']}")
        titulo.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #333; font-family: Arial;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tabla_layout.addWidget(titulo)

        info = QLabel(
            f"ID: {self.datos_tabla['id']}  |  "
            f"Departamento: {self.datos_tabla['departamento']}  |  "
            f"Periodo: {self.datos_tabla['periodo']}")
        info.setStyleSheet("font-size: 15px; color: #666; font-family: Arial;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tabla_layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Dia", "Entrada", "Salida", "Horas", "Estado"])
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #ddd;
                border: 1px solid #ddd;
                font-family: Arial;
            }
            QHeaderView::section {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
                font-family: Arial;
            }
            QTableWidget::item {
                color: #333;
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: rgba(33, 150, 243, 0.15);
                color: #333;
            }
            QTableWidget::item:hover {
                background-color: rgba(33, 150, 243, 0.08);
                color: #333;
            }
        """)
        self.table.setAlternatingRowColors(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self._llenar_tabla()
        tabla_layout.addWidget(self.table)

        resumen_frame = QFrame()
        resumen_frame.setStyleSheet("""
            QFrame {
                background-color: #e3f2fd;
                border: 2px solid #2196F3;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        resumen_lay = QVBoxLayout(resumen_frame)
        resumen_lbl = QLabel(
            f"Resumen: {self.datos_tabla['dias_trabajados']} dias trabajados  |  "
            f"{self.datos_tabla['total_horas_periodo']} horas totales  |  "
            f"{self.datos_tabla['registros_incompletos']} registros incompletos  |  "
            f"{self.datos_tabla.get('faltas', 0)} faltas")
        resumen_lbl.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #1976D2; font-family: Arial;")
        resumen_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        resumen_lay.addWidget(resumen_lbl)
        tabla_layout.addWidget(resumen_frame)

        layout.addWidget(tabla_widget)

        btn_row = QHBoxLayout()

        btn_nueva = QPushButton("Nueva consulta")
        btn_nueva.setStyleSheet(STYLE_BTN_GRIS)
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.clicked.connect(lambda: self.cambiar_pantalla("formulario"))
        btn_row.addWidget(btn_nueva)
        btn_row.addStretch()

        btn_guardar = QPushButton("Guardar XLSX")
        btn_guardar.setStyleSheet(STYLE_BTN_VERDE)
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.clicked.connect(self._guardar_reporte)
        btn_row.addWidget(btn_guardar)
        btn_row.addStretch()

        btn_menu = QPushButton("Menu")
        btn_menu.setStyleSheet(STYLE_BTN_GRIS)
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)

        layout.addLayout(btn_row)

    # ----------------------------------------------------------
    # PANTALLA COMPENDIO (todos los empleados)
    # ----------------------------------------------------------
    def _crear_pantalla_compendio(self, layout):
        """Muestra un resumen por empleado con scroll; exporta todo en un XLSX."""
        lista = self.datos_tabla   # list[dict]

        scroll_area = __import__('PyQt6.QtWidgets', fromlist=['QScrollArea']).QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { background: white; border: none; }")

        contenedor = QWidget()
        contenedor.setStyleSheet("background-color: white;")
        v = QVBoxLayout(contenedor)
        v.setSpacing(0)
        v.setContentsMargins(0, 0, 0, 0)

        # Encabezado del compendio
        hdr = QWidget()
        hdr.setStyleSheet("background-color: #1E3A5F; padding: 10px;")
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(16, 12, 16, 12)
        lbl_titulo = QLabel("Compendio de Asistencia — Todos los empleados")
        lbl_titulo.setStyleSheet(
            "color: white; font-family: Arial; font-size: 18px; font-weight: bold;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_lay.addWidget(lbl_titulo)
        if lista:
            periodo = lista[0].get("periodo", "")
            lbl_periodo = QLabel(f"Periodo: {periodo}  |  {len(lista)} empleado(s) con registros")
            lbl_periodo.setStyleSheet(
                "color: rgba(255,255,255,0.8); font-family: Arial; font-size: 12px;")
            lbl_periodo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hdr_lay.addWidget(lbl_periodo)
        v.addWidget(hdr)

        COLOR_FILA = {
            "Completo":   (QColor(232, 245, 233), QColor(220, 237, 220)),
            "Incompleto": (QColor(255, 248, 225), QColor(255, 240, 200)),
            "Falta":      (QColor(255, 235, 238), QColor(255, 220, 225)),
        }
        COLOR_TEXTO = QColor(51, 51, 51)

        for emp_datos in lista:
            # ── Cabecera del empleado ──────────────────────────────────────
            emp_hdr = QWidget()
            emp_hdr.setStyleSheet("background-color: #2E6DA4; padding: 6px;")
            emp_hdr_lay = QHBoxLayout(emp_hdr)
            emp_hdr_lay.setContentsMargins(16, 8, 16, 8)
            lbl_emp = QLabel(
                f"  {emp_datos['nombre']}   "
                f"<span style='font-weight:normal; font-size:11px;'>"
                f"ID: {emp_datos['id']}  |  "
                f"Dpto: {emp_datos['departamento']}</span>")
            lbl_emp.setStyleSheet(
                "color: white; font-family: Arial; font-size: 13px; font-weight: bold;")
            emp_hdr_lay.addWidget(lbl_emp)
            emp_hdr_lay.addStretch()
            lbl_resumen = QLabel(
                f"{emp_datos['dias_trabajados']} días  |  "
                f"{emp_datos['total_horas_periodo']} hrs  |  "
                f"{emp_datos['registros_incompletos']} incompletos  |  "
                f"{emp_datos.get('faltas', 0)} faltas")
            lbl_resumen.setStyleSheet(
                "color: rgba(255,255,255,0.85); font-family: Arial; font-size: 11px;")
            emp_hdr_lay.addWidget(lbl_resumen)
            v.addWidget(emp_hdr)

            # ── Tabla de días ───────────────────────────────────────────────
            tbl = QTableWidget()
            tbl.setColumnCount(6)
            tbl.setHorizontalHeaderLabels(
                ["Fecha", "Día", "Entrada", "Salida", "Horas", "Estado"])
            tbl.setStyleSheet("""
                QTableWidget {
                    background-color: white; gridline-color: #ddd;
                    border: none; font-family: Arial; font-size: 11px;
                }
                QHeaderView::section {
                    background-color: #4A90C4; color: white;
                    padding: 5px; border: none; font-weight: bold;
                }
                QTableWidget::item { color: #333; padding: 3px; border: none; }
            """)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(True)

            dias = emp_datos.get("detalle_dias", [])
            tbl.setRowCount(len(dias))
            for i, dia in enumerate(dias):
                estado = dia.get("estado", "-")
                par    = i % 2 == 0
                bg = COLOR_FILA.get(estado, (QColor(255,255,255), QColor(245,245,245)))[0 if par else 1]
                for col, texto in enumerate([
                    dia.get("fecha", "-"),
                    (dia.get("dia_semana", "-") or "-")[:3],
                    dia.get("entrada") or "--:--",
                    dia.get("salida")  or "--:--",
                    dia.get("horas_trabajadas") or "-",
                    estado,
                ]):
                    it = QTableWidgetItem(str(texto) if texto else "-")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    it.setBackground(QBrush(bg))
                    it.setForeground(QBrush(COLOR_TEXTO))
                    tbl.setItem(i, col, it)

            row_h = 24
            tbl.setFixedHeight(min(len(dias), 12) * row_h + 30)
            v.addWidget(tbl)

            # Separador
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #ccc; margin: 0px;")
            v.addWidget(sep)

        v.addStretch()
        scroll_area.setWidget(contenedor)
        layout.addWidget(scroll_area)

        btn_row = QHBoxLayout()
        btn_nueva = QPushButton("Nueva consulta")
        btn_nueva.setStyleSheet(STYLE_BTN_GRIS)
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.clicked.connect(lambda: self.cambiar_pantalla("formulario"))
        btn_row.addWidget(btn_nueva)
        btn_row.addStretch()
        btn_guardar = QPushButton("Guardar Compendio XLSX")
        btn_guardar.setStyleSheet(STYLE_BTN_VERDE)
        btn_guardar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_guardar.clicked.connect(self._guardar_compendio_xlsx)
        btn_row.addWidget(btn_guardar)
        btn_row.addStretch()
        btn_menu = QPushButton("Menu")
        btn_menu.setStyleSheet(STYLE_BTN_GRIS)
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)
        layout.addLayout(btn_row)

    def _guardar_compendio_xlsx(self):
        """Exporta todos los empleados: una hoja por empleado + hoja resumen general."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            lista = self.datos_tabla
            periodo_str = lista[0].get("periodo", datetime.now().strftime("%Y%m%d")) if lista else ""
            nombre_arch = f"Compendio_Asistencia_{datetime.now().strftime('%Y%m%d')}.xlsx"
            archivo, _ = QFileDialog.getSaveFileName(
                self, "Guardar compendio como Excel", nombre_arch,
                "Archivos Excel (*.xlsx);;Todos los archivos (*.*)")
            if not archivo:
                return

            wb = Workbook()

            # ── Estilos comunes ──────────────────────────────────────────────
            f_titulo   = Font(name="Arial", bold=True, size=13, color="FFFFFF")
            f_header   = Font(name="Arial", bold=True, size=10, color="FFFFFF")
            f_label    = Font(name="Arial", bold=True, size=10)
            f_normal   = Font(name="Arial", size=10)
            f_resumen  = Font(name="Arial", bold=True, size=11)
            fill_titulo   = PatternFill("solid", fgColor="1E3A5F")
            fill_emp_hdr  = PatternFill("solid", fgColor="2E6DA4")
            fill_header   = PatternFill("solid", fgColor="4A90C4")
            fill_info     = PatternFill("solid", fgColor="EBF3FB")
            fill_completo   = PatternFill("solid", fgColor="D4EDDA")
            fill_incompleto = PatternFill("solid", fgColor="FFF3CD")
            fill_falta      = PatternFill("solid", fgColor="F8D7DA")
            fill_resumen_hdr = PatternFill("solid", fgColor="1E3A5F")
            fill_resumen_row = PatternFill("solid", fgColor="EBF3FB")
            borde  = Border(
                left=Side(style="thin"), right=Side(style="thin"),
                top=Side(style="thin"),  bottom=Side(style="thin"))
            centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
            izq    = Alignment(horizontal="left",   vertical="center")
            fill_map = {"Completo": fill_completo,
                        "Incompleto": fill_incompleto,
                        "Falta": fill_falta}

            # ── Única hoja: todos los empleados en secuencia ─────────────────
            ws = wb.active
            ws.title = "Compendio Asistencia"

            # Encabezado general del libro
            ws.merge_cells("A1:F1")
            ws["A1"] = "COMPENDIO DE ASISTENCIA"
            ws["A1"].font = f_titulo
            ws["A1"].fill = fill_titulo
            ws["A1"].alignment = centro
            ws.row_dimensions[1].height = 28

            ws.merge_cells("A2:F2")
            ws["A2"] = f"Periodo: {periodo_str}  |  {len(lista)} empleado(s) con registros"
            ws["A2"].font = Font(name="Arial", size=10, color="FFFFFF")
            ws["A2"].fill = fill_emp_hdr
            ws["A2"].alignment = centro
            ws.row_dimensions[2].height = 18

            fila_cursor = 4   # fila donde empieza el primer empleado

            for emp in lista:
                # ── Cabecera del empleado ────────────────────────────────────
                ws.merge_cells(f"A{fila_cursor}:F{fila_cursor}")
                ws[f"A{fila_cursor}"] = (
                    f"{emp.get('nombre', '-')}   "
                    f"(ID: {emp.get('id', '-')}  |  "
                    f"Dpto: {emp.get('departamento', '-')}  |  "
                    f"Periodo: {emp.get('periodo', '-')})"
                )
                ws[f"A{fila_cursor}"].font = Font(name="Arial", bold=True,
                                                  size=11, color="FFFFFF")
                ws[f"A{fila_cursor}"].fill = fill_emp_hdr
                ws[f"A{fila_cursor}"].alignment = izq
                ws.row_dimensions[fila_cursor].height = 20
                fila_cursor += 1

                # ── Fila de resumen del empleado ─────────────────────────────
                resumen_labels = [
                    "Días trabajados", "Total horas",
                    "Promedio hrs/día", "Registros incompletos", "Faltas", "",
                ]
                resumen_vals = [
                    emp.get("dias_trabajados", 0),
                    emp.get("total_horas_periodo", "-"),
                    emp.get("promedio_horas_dia", "-"),
                    emp.get("registros_incompletos", 0),
                    emp.get("faltas", 0),
                    "",
                ]
                for ci, (lbl, val) in enumerate(
                        zip(resumen_labels, resumen_vals), start=1):
                    c_lbl = ws.cell(row=fila_cursor,   column=ci, value=lbl)
                    c_val = ws.cell(row=fila_cursor+1, column=ci, value=val)
                    c_lbl.font = Font(name="Arial", bold=True, size=9, color="FFFFFF")
                    c_lbl.fill = fill_header
                    c_lbl.alignment = centro
                    c_lbl.border = borde
                    c_val.font = Font(name="Arial", bold=True, size=10)
                    c_val.fill = fill_info
                    c_val.alignment = centro
                    c_val.border = borde
                fila_cursor += 2

                # ── Cabecera de la tabla de días ─────────────────────────────
                for ci, h in enumerate(
                        ["Fecha", "Día", "Entrada", "Salida",
                         "Horas trabajadas", "Estado"], 1):
                    c = ws.cell(row=fila_cursor, column=ci, value=h)
                    c.font = f_header
                    c.fill = fill_header
                    c.alignment = centro
                    c.border = borde
                ws.row_dimensions[fila_cursor].height = 16
                fila_cursor += 1

                # ── Detalle de días ──────────────────────────────────────────
                for dia in emp.get("detalle_dias", []):
                    estado = dia.get("estado", "-")
                    fill_d = fill_map.get(estado, PatternFill())
                    vals = [
                        dia.get("fecha", "-"),
                        (dia.get("dia_semana", "-") or "-")[:3],
                        dia.get("entrada") or "-",
                        dia.get("salida")  or "-",
                        dia.get("horas_trabajadas") or "-",
                        estado,
                    ]
                    for ci, val in enumerate(vals, 1):
                        c = ws.cell(row=fila_cursor, column=ci, value=val)
                        c.font = f_normal
                        c.fill = fill_d
                        c.alignment = centro
                        c.border = borde
                    ws.row_dimensions[fila_cursor].height = 15
                    fila_cursor += 1

                # Espacio entre empleados
                fila_cursor += 2

            # Anchos de columna fijos para toda la hoja
            for ci, ancho in enumerate([14, 7, 9, 9, 18, 13], 1):
                ws.column_dimensions[get_column_letter(ci)].width = ancho

            wb.save(archivo)
            QMessageBox.information(
                self, "Éxito",
                f"Compendio guardado:\n{archivo}\n\n"
                f"{len(lista)} empleado(s) exportados en una sola hoja.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar el compendio:\n{str(e)}")

    def _llenar_tabla(self):
        if not self.datos_tabla or not hasattr(self, 'table'):
            return

        dias = self.datos_tabla.get('detalle_dias', [])
        self.table.setRowCount(len(dias))

        # Colores de fila según estado (filas pares/impares con tono diferente
        # para mantener legibilidad sin depender de setAlternatingRowColors)
        COLOR_FILA = {
            'Completo':   (QColor(232, 245, 233), QColor(220, 237, 220)),   # verde claro
            'Incompleto': (QColor(255, 248, 225), QColor(255, 240, 200)),   # amarillo claro
            'Falta':      (QColor(255, 235, 238), QColor(255, 220, 225)),   # rojo claro
        }
        COLOR_TEXTO = QColor(51, 51, 51)   # #333 siempre visible

        for i, dia in enumerate(dias):
            estado = dia.get('estado', '-')
            par    = i % 2 == 0
            colores_estado = COLOR_FILA.get(estado, (QColor(255,255,255), QColor(245,245,245)))
            bg = colores_estado[0] if par else colores_estado[1]

            valores = [
                dia.get('fecha', '-'),
                (dia.get('dia_semana', '-') or '-')[:3],
                dia.get('entrada') or '--:--',
                dia.get('salida')  or '--:--',
                dia.get('horas_trabajadas') or '-',
                estado,
            ]
            for col, texto in enumerate(valores):
                it = QTableWidgetItem(str(texto) if texto else '-')
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                # Color explícito en cada celda → visible siempre, sin hover
                it.setBackground(QBrush(bg))
                it.setForeground(QBrush(COLOR_TEXTO))
                self.table.setItem(i, col, it)

    # ----------------------------------------------------------
    # GUARDAR
    # ----------------------------------------------------------
    def _guardar_reporte(self):
        if not self.datos_tabla:
            QMessageBox.warning(self, "Advertencia", "No hay datos para guardar.")
            return
        self._guardar_como_xlsx()

    def _guardar_como_pdf(self):
        try:
            nombre_arch = (
                f"Reporte_{self.datos_tabla['nombre']}_"
                f"{datetime.now().strftime('%Y%m%d')}.pdf")
            archivo, _ = QFileDialog.getSaveFileName(
                self, "Guardar reporte como PDF", nombre_arch,
                "Archivos PDF (*.pdf);;Todos los archivos (*.*)")
            if not archivo:
                return

            doc      = SimpleDocTemplate(archivo, pagesize=A4)
            elementos = []
            estilos  = getSampleStyleSheet()
            titulo_style = ParagraphStyle(
                "CustomTitle", parent=estilos["Heading1"],
                fontSize=16, spaceAfter=30, alignment=1)

            elementos.append(Paragraph("Reporte Completo de Asistencia", titulo_style))
            elementos.append(Spacer(1, 12))
            elementos.append(Paragraph(
                f"<b>Empleado:</b> {self.datos_tabla['nombre']}<br/>"
                f"<b>ID:</b> {self.datos_tabla['id']}<br/>"
                f"<b>Departamento:</b> {self.datos_tabla['departamento']}<br/>"
                f"<b>Periodo:</b> {self.datos_tabla['periodo']}",
                estilos["Normal"]))
            elementos.append(Spacer(1, 20))
            elementos.append(Paragraph(
                f"<b>Resumen del periodo:</b><br/>"
                f"Dias trabajados: {self.datos_tabla['dias_trabajados']}<br/>"
                f"Total horas: {self.datos_tabla['total_horas_periodo']}<br/>"
                f"Registros incompletos: {self.datos_tabla['registros_incompletos']}<br/>"
                f"Faltas: {self.datos_tabla.get('faltas', 0)}",
                estilos["Normal"]))
            elementos.append(Spacer(1, 20))

            filas_pdf = [["Fecha", "Dia", "Entrada", "Salida", "Horas", "Estado"]]
            for dia in self.datos_tabla['detalle_dias']:
                filas_pdf.append([
                    dia.get('fecha', '-'),
                    (dia.get('dia_semana', '-') or '-')[:9],
                    dia.get('entrada') or '-',
                    dia.get('salida')  or '-',
                    dia.get('horas_trabajadas') or '-',
                    dia.get('estado', '-'),
                ])

            tabla_pdf = Table(
                filas_pdf,
                colWidths=[1.2*inch, 1*inch, 0.8*inch, 0.8*inch, 0.8*inch, 1*inch])
            estilo_t = TableStyle([
                ('BACKGROUND',    (0, 0), (-1,  0), colors.grey),
                ('TEXTCOLOR',     (0, 0), (-1,  0), colors.whitesmoke),
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME',      (0, 0), (-1,  0), 'Helvetica-Bold'),
                ('FONTSIZE',      (0, 0), (-1,  0), 10),
                ('BOTTOMPADDING', (0, 0), (-1,  0), 12),
                ('BACKGROUND',    (0, 1), (-1, -1), colors.beige),
                ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE',      (0, 1), (-1, -1), 8),
                ('GRID',          (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ])
            for i, dia in enumerate(self.datos_tabla['detalle_dias'], start=1):
                estado = dia.get('estado', '')
                if estado == 'Incompleto':
                    estilo_t.add('BACKGROUND', (0, i), (-1, i), colors.lightyellow)
                elif estado == 'Falta':
                    estilo_t.add('BACKGROUND', (0, i), (-1, i), colors.lightpink)
                elif estado == 'Completo':
                    estilo_t.add('BACKGROUND', (0, i), (-1, i), colors.lightgreen)

            tabla_pdf.setStyle(estilo_t)
            elementos.append(tabla_pdf)
            doc.build(elementos)
            QMessageBox.information(self, "Exito",
                                    f"Reporte PDF guardado:\n{archivo}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar el PDF:\n{str(e)}")

    def _guardar_como_xlsx(self):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            nombre_arch = (
                f"Reporte_{self.datos_tabla['nombre']}_"
                f"{datetime.now().strftime('%Y%m%d')}.xlsx")
            archivo, _ = QFileDialog.getSaveFileName(
                self, "Guardar reporte como Excel", nombre_arch,
                "Archivos Excel (*.xlsx);;Todos los archivos (*.*)")
            if not archivo:
                return

            wb = Workbook()
            ws = wb.active
            ws.title = "Reporte Asistencia"

            fuente_titulo   = Font(name="Arial", bold=True, size=14, color="FFFFFF")
            fuente_header   = Font(name="Arial", bold=True, size=10, color="FFFFFF")
            fuente_label    = Font(name="Arial", bold=True, size=10)
            fuente_normal   = Font(name="Arial", size=10)
            fill_titulo     = PatternFill("solid", fgColor="1E3A5F")
            fill_header     = PatternFill("solid", fgColor="2E6DA4")
            fill_completo   = PatternFill("solid", fgColor="D4EDDA")
            fill_incompleto = PatternFill("solid", fgColor="FFF3CD")
            fill_falta      = PatternFill("solid", fgColor="F8D7DA")
            fill_info       = PatternFill("solid", fgColor="EBF3FB")
            borde  = Border(left=Side(style="thin"), right=Side(style="thin"),
                            top=Side(style="thin"),  bottom=Side(style="thin"))
            centro = Alignment(horizontal="center", vertical="center")
            izq    = Alignment(horizontal="left",   vertical="center")

            ws.merge_cells("A1:F1")
            ws["A1"] = "REPORTE COMPLETO DE ASISTENCIA"
            ws["A1"].font = fuente_titulo
            ws["A1"].fill = fill_titulo
            ws["A1"].alignment = centro
            ws.row_dimensions[1].height = 28

            info = [
                ("Empleado",              self.datos_tabla['nombre']),
                ("ID",                    self.datos_tabla['id']),
                ("Departamento",          self.datos_tabla['departamento']),
                ("Periodo",               self.datos_tabla['periodo']),
                ("Dias trabajados",       self.datos_tabla['dias_trabajados']),
                ("Total horas",           self.datos_tabla['total_horas_periodo']),
                ("Promedio horas/dia",    self.datos_tabla.get('promedio_horas_dia', '-')),
                ("Registros incompletos", self.datos_tabla['registros_incompletos']),
                ("Faltas",                self.datos_tabla.get('faltas', 0)),
            ]
            for fila_i, (label, valor) in enumerate(info, start=2):
                ws.merge_cells(f"A{fila_i}:B{fila_i}")
                ws[f"A{fila_i}"] = label
                ws[f"A{fila_i}"].font = fuente_label
                ws[f"A{fila_i}"].fill = fill_info
                ws[f"A{fila_i}"].alignment = izq
                ws.merge_cells(f"C{fila_i}:F{fila_i}")
                ws[f"C{fila_i}"] = valor
                ws[f"C{fila_i}"].font = fuente_normal
                ws[f"C{fila_i}"].alignment = izq

            fila_header = len(info) + 3
            headers = ["Fecha", "Dia", "Entrada", "Salida", "Horas trabajadas", "Estado"]
            for col_i, h in enumerate(headers, start=1):
                cell = ws.cell(row=fila_header, column=col_i, value=h)
                cell.font = fuente_header
                cell.fill = fill_header
                cell.alignment = centro
                cell.border = borde

            fill_map = {"Completo": fill_completo, "Incompleto": fill_incompleto, "Falta": fill_falta}
            for idx, dia in enumerate(self.datos_tabla['detalle_dias'], start=fila_header + 1):
                estado = dia.get('estado', '-')
                fill   = fill_map.get(estado, PatternFill())
                valores = [
                    dia.get('fecha', '-'),
                    (dia.get('dia_semana', '-') or '-')[:3],
                    dia.get('entrada') or '-',
                    dia.get('salida')  or '-',
                    dia.get('horas_trabajadas') or '-',
                    estado,
                ]
                for col_i, val in enumerate(valores, start=1):
                    cell = ws.cell(row=idx, column=col_i, value=val)
                    cell.font = fuente_normal
                    cell.fill = fill
                    cell.alignment = centro
                    cell.border = borde

            for col_i, ancho in enumerate([13, 8, 9, 9, 17, 13], start=1):
                ws.column_dimensions[get_column_letter(col_i)].width = ancho

            wb.save(archivo)
            QMessageBox.information(self, "Exito", f"Reporte Excel guardado:\n{archivo}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al guardar el archivo:\n{str(e)}")

    def _volver(self):
        self.timer.stop()
        self.volver_menu.emit()


# =========================================================
# MAIN (debug standalone)
# =========================================================
def main():
    if os.name == 'nt' and GRAPHICS_IMPORTED:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    ocultar_consola_windows()
    app = QApplication(sys.argv)

    class SesionDebug:
        user_name = "admin"

    ventana = QMainWindow()
    ventana.setWindowTitle("Reportes Completos - Debug")
    widget = InterfazReportesCompletos(sesion=SesionDebug())
    widget.volver_menu.connect(app.quit)
    ventana.setCentralWidget(widget)
    ventana.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()