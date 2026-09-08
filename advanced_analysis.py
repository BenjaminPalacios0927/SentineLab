"""
advanced_analysis.py
--------------------
Análisis avanzado de asistencia con I.A. de aprendizaje por retroalimentación.

SISTEMA DE NIVELES (alineado con attendance_processor.calcular_nivel_gravedad):
  Nivel 1 — Bueno / Estable   (≤2 puntos)
  Nivel 2 — Alerta            (3-5 puntos)
  Nivel 3 — Crítico           (>5 puntos)

El pool de sugerencias vive en Railway (tabla ia_suggestions_pool).
Cada vez que el supervisor vota "útil", el peso_aprendizaje sube 0.20.
Cada vez que vota "mostrar otra", baja 0.20.
Así la I.A. aprende qué sugerencias funcionan mejor para cada nivel.
"""

import sys
import os
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import mysql.connector


def _log(msg):
    """Escribe en un archivo de log en lugar de stdout/stderr.
    Evita [WinError 6] cuando el handle de consola no existe
    (proceso lanzado con DETACHED_PROCESS o --windowed en PyInstaller)."""
    try:
        log_dir = os.path.join(os.path.expanduser('~'), '.SistemaAsistencia')
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'advanced_analysis.log'), 'a',
                  encoding='utf-8') as f:
            f.write(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')
    except Exception:
        pass


def ocultar_consola_windows():
    # FreeConsole() destruye el handle de consola y provoca [WinError 6]
    # en cualquier hilo que intente escribir despues. La consola se suprime
    # correctamente con --windowed en PyInstaller. No-op intencional.
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QLabel, QDialog, QScrollArea, QFrame,
    QMessageBox, QDateEdit, QGridLayout, QLineEdit,
)
from PyQt6.QtCore import QTimer, Qt, QDate, pyqtSignal, QThread
from PyQt6.QtGui import QPainter, QColor, QFont

try:
    from interface_graphics import InterfaceGraphics
    GRAPHICS_IMPORTED = True
except ImportError:
    GRAPHICS_IMPORTED = False

try:
    from attendance_processor import ProcesadorReporteAsistencia, EmpleadoAsistencia
    PROCESSOR_AVAILABLE = True
except ImportError:
    PROCESSOR_AVAILABLE = False

def _db_cfg() -> dict:
    """
    Devuelve el dict de conexión desde la configuración guardada
    por el administrador. Nunca contiene credenciales hardcodeadas.
    """
    try:
        from device_config import construir_db_config_conexion
        return construir_db_config_conexion()
    except Exception:
        return {}


# =========================================================
# DATACLASSES (idénticas al original)
# =========================================================
@dataclass
class PatronAsistencia:
    tipo:        str
    descripcion: str
    severidad:   int    # 1-5
    frecuencia:  float  # porcentaje
    tendencia:   str


@dataclass
class Sugerencia:
    id:            Optional[int]   # PRIMARY KEY en Railway (None = fallback local)
    categoria:     str             # "Nivel 1" / "Nivel 2" / "Nivel 3"
    nivel_gravedad: int            # 1 / 2 / 3
    accion:        str
    justificacion: str
    prioridad:     int             # 1=Alta, 2=Media, 3=Baja
    peso:          float           # peso_aprendizaje actual


# =========================================================
# SUGERENCIAS LOCALES — FALLBACK si Railway no responde
# Organizadas en tres niveles que replican las listas originales
# pero ahora clasificadas por nivel de gravedad
# =========================================================
_SUGERENCIAS_FALLBACK: Dict[int, List[str]] = {
    1: [   # Nivel 1 — Bueno/Estable: refuerzo positivo y seguimiento ligero
        "Reconoce verbalmente los dias en que el empleado cumple con los horarios establecidos.",
        "Establece un seguimiento mensual para evaluar mejoras en la puntualidad y registros completos.",
        "Comparte ejemplos de buenas practicas de registro entre el equipo para fomentar el cumplimiento.",
        "Solicita al empleado que confirme sus registros semanalmente para evitar omisiones.",
        "Aplica una revision cruzada entre el sistema de asistencia y las tareas asignadas.",
        "Refuerza la importancia del registro completo como parte de la cultura organizacional.",
        "Ofrece retroalimentacion positiva cuando el empleado mejora su comportamiento de asistencia.",
        "Revisa junto al empleado si existen errores tecnicos en el sistema de control de asistencia.",
        "Ofrece una capacitacion breve sobre el uso correcto del sistema de registro de entradas y salidas.",
    ],
    2: [   # Nivel 2 — Alerta: conversacion formal y plan de seguimiento
        "Realiza una conversacion informal con el empleado para abordar los incidentes de asistencia recientes.",
        "Envia un recordatorio por escrito sobre las politicas de puntualidad y registro de jornada.",
        "Establece alertas automaticas para detectar registros incompletos en tiempo real.",
        "Invita al empleado a proponer soluciones para mejorar su puntualidad.",
        "Documenta los incidentes leves como referencia interna sin aplicar sanciones.",
        "Sugiere ajustes menores en el horario si el empleado presenta razones justificadas.",
        "Establece un seguimiento quincenal con metas claras de mejora.",
        "Solicita al empleado justificar por escrito las ausencias o registros incompletos.",
        "Evalua causas personales o externas que puedan estar afectando la asistencia.",
        "Refuerza la obligatoriedad del registro completo mediante comunicados internos.",
    ],
    3: [   # Nivel 3 — Crítico: intervención formal, medidas disciplinarias
        "Realiza una entrevista formal con el empleado para discutir su patron de asistencia deficiente.",
        "Implementa un plan de mejora individual con metas claras y plazos definidos.",
        "Emite una advertencia escrita detallando las faltas y las consecuencias futuras.",
        "Aplica una suspension temporal si el comportamiento persiste sin mejora.",
        "Reasigna al empleado a un area con supervision mas estricta si es necesario.",
        "Registra los incidentes en el expediente laboral para futuras decisiones disciplinarias.",
        "Solicita apoyo de Recursos Humanos para intervenir en casos reincidentes.",
        "Aplica medidas correctivas proporcionales segun la gravedad y frecuencia de las faltas.",
        "Establece reuniones semanales de seguimiento con el empleado hasta ver mejoras sostenidas.",
        "Ofrece una ultima oportunidad con condiciones especificas antes de escalar el caso.",
        "Considera la terminacion del contrato si no hay cambios tras multiples intervenciones.",
        "Documenta cada paso del proceso disciplinario para garantizar transparencia y legalidad.",
    ],
}

_NOMBRES_NIVEL = {1: "Nivel 1 — Bueno / Estable",
                  2: "Nivel 2 — Alerta",
                  3: "Nivel 3 — Critico"}
_PRIORIDAD_NIVEL = {1: 3, 2: 2, 3: 1}   # nivel → prioridad (1=Alta,2=Media,3=Baja)


# =========================================================
# MOTOR DE ANÁLISIS (lógica del original, sin simulación)
# =========================================================
class AnalizadorAvanzadoAsistencia:
    """
    Analiza datos de asistencia → detecta patrones → consulta/actualiza
    el pool de sugerencias en Railway.

    FLUJO DE ML:
      cargar_datos → calcular_nivel_gravedad (en procesador) →
        obtener_sugerencia_por_nivel (Railway, ORDER BY peso_aprendizaje DESC) →
          mostrar al supervisor →
            votar_sugerencia (+0.20 / -0.20 en peso_aprendizaje)
    """

    # ----------------------------------------------------------
    # ANÁLISIS DE PATRONES (idéntico al original, sin random)
    # ----------------------------------------------------------
    def analizar_patrones(self, datos: dict) -> List[PatronAsistencia]:
        patrones = []
        total_dias = max(datos.get('dias_trabajados', 1), 1)

        registros_incompletos = datos.get('registros_incompletos', 0)
        if registros_incompletos > 0:
            porc = (registros_incompletos / total_dias) * 100
            if porc > 30:
                sev, tipo = 5, "Registros incompletos critico"
            elif porc > 15:
                sev, tipo = 4, "Registros incompletos frecuente"
            else:
                sev, tipo = 2, "Registros incompletos esporadico"
            patrones.append(PatronAsistencia(
                tipo, f"{porc:.1f}% de registros incompletos",
                sev, porc, "estable"))

        faltas = datos.get('faltas', 0)
        if faltas > 0:
            if faltas >= 5:
                sev, tipo = 5, "Ausentismo critico"
            elif faltas >= 3:
                sev, tipo = 4, "Ausentismo frecuente"
            else:
                sev, tipo = 2, "Ausentismo esporadico"
            patrones.append(PatronAsistencia(
                tipo, f"{faltas} faltas en el periodo",
                sev, (faltas / total_dias) * 100, "estable"))

        return patrones

    def generar_predicciones(self, patrones: List[PatronAsistencia]) -> dict:
        if not patrones:
            return {"riesgo_general": "Bajo", "probabilidad_mejora": 85,
                    "areas_criticas": [],
                    "recomendacion_seguimiento": "Seguimiento mensual"}

        sev_max = max(p.severidad for p in patrones)
        if sev_max >= 4:
            return {"riesgo_general": "Alto",  "probabilidad_mejora": 40,
                    "areas_criticas": [p.tipo for p in patrones if p.severidad >= 3],
                    "recomendacion_seguimiento": "Seguimiento semanal intensivo"}
        elif sev_max >= 3:
            return {"riesgo_general": "Medio", "probabilidad_mejora": 65,
                    "areas_criticas": [p.tipo for p in patrones if p.severidad >= 3],
                    "recomendacion_seguimiento": "Seguimiento quincenal"}
        return {"riesgo_general": "Bajo",  "probabilidad_mejora": 80,
                "areas_criticas": [],
                "recomendacion_seguimiento": "Seguimiento mensual"}

    # ----------------------------------------------------------
    # POOL DE SUGERENCIAS EN RAILWAY (el corazón del ML)
    # ----------------------------------------------------------
    def _asegurar_tabla(self, cursor):
        """Crea ia_suggestions_pool si no existe y la puebla con el fallback."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ia_suggestions_pool (
                id                INT AUTO_INCREMENT PRIMARY KEY,
                nivel_gravedad    INT NOT NULL COMMENT '1=Bueno 2=Alerta 3=Critico',
                sugerencia_texto  TEXT NOT NULL,
                peso_aprendizaje  FLOAT DEFAULT 1.0,
                veces_mostrada    INT   DEFAULT 0,
                votos_positivos   INT   DEFAULT 0,
                votos_negativos   INT   DEFAULT 0,
                creada_en         DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Poblar solo si está vacía
        cursor.execute("SELECT COUNT(*) as n FROM ia_suggestions_pool")
        if cursor.fetchone()['n'] == 0:
            rows = []
            for nivel, textos in _SUGERENCIAS_FALLBACK.items():
                for texto in textos:
                    rows.append((nivel, texto, 1.0))
            cursor.executemany(
                "INSERT INTO ia_suggestions_pool "
                "(nivel_gravedad, sugerencia_texto, peso_aprendizaje) VALUES (%s, %s, %s)",
                rows)

    def obtener_sugerencia(self, nivel_gravedad: int,
                           excluir_id: Optional[int] = None) -> Sugerencia:
        """
        Trae la sugerencia con mayor peso para el nivel dado.
        Si Railway no está disponible, usa el fallback local.
        excluir_id: excluir la sugerencia actual al pedir "mostrar otra".
        """
        try:
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor(dictionary=True)
            self._asegurar_tabla(cursor)
            conn.commit()

            sql = """
                SELECT id, nivel_gravedad, sugerencia_texto, peso_aprendizaje
                FROM ia_suggestions_pool
                WHERE nivel_gravedad = %s
            """
            params: list = [nivel_gravedad]
            if excluir_id is not None:
                sql += " AND id != %s"
                params.append(excluir_id)
            sql += " ORDER BY peso_aprendizaje DESC, RAND() LIMIT 1"

            cursor.execute(sql, params)
            row = cursor.fetchone()

            # Incrementar veces_mostrada
            if row:
                cursor.execute(
                    "UPDATE ia_suggestions_pool SET veces_mostrada = veces_mostrada + 1 WHERE id = %s",
                    (row['id'],))
                conn.commit()

            cursor.close()
            conn.close()

            if row:
                return Sugerencia(
                    id=row['id'],
                    categoria=_NOMBRES_NIVEL.get(nivel_gravedad, f"Nivel {nivel_gravedad}"),
                    nivel_gravedad=nivel_gravedad,
                    accion=row['sugerencia_texto'],
                    justificacion=self._generar_justificacion(nivel_gravedad),
                    prioridad=_PRIORIDAD_NIVEL.get(nivel_gravedad, 2),
                    peso=row['peso_aprendizaje'],
                )
        except Exception as e:
            _log(f"[IA] Railway no disponible, usando fallback local: {e}")

        # Fallback local si Railway falla
        import random
        textos = _SUGERENCIAS_FALLBACK.get(nivel_gravedad, _SUGERENCIAS_FALLBACK[2])
        return Sugerencia(
            id=None,
            categoria=_NOMBRES_NIVEL.get(nivel_gravedad, f"Nivel {nivel_gravedad}"),
            nivel_gravedad=nivel_gravedad,
            accion=random.choice(textos),
            justificacion=self._generar_justificacion(nivel_gravedad),
            prioridad=_PRIORIDAD_NIVEL.get(nivel_gravedad, 2),
            peso=1.0,
        )

    def votar_sugerencia(self, sugerencia_id: int, positivo: bool) -> bool:
        """
        Ajusta el peso_aprendizaje de una sugerencia.
        +0.20 si el supervisor la considera util.
        -0.20 si prefiere otra.
        Retorna True si se pudo registrar en Railway.
        """
        if sugerencia_id is None:
            return False
        cambio     = 0.20 if positivo else -0.20
        col_voto   = "votos_positivos" if positivo else "votos_negativos"
        try:
            conn   = mysql.connector.connect(**_db_cfg())
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE ia_suggestions_pool
                SET peso_aprendizaje = GREATEST(0.1, peso_aprendizaje + %s),
                    {col_voto} = {col_voto} + 1
                WHERE id = %s
            """, (cambio, sugerencia_id))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            _log(f"[IA] No se pudo registrar voto: {e}")
            return False

    def _generar_justificacion(self, nivel: int) -> str:
        return {
            1: "El empleado muestra un comportamiento de asistencia bueno o estable. "
               "Una intervencion ligera puede consolidar el habito positivo.",
            2: "Se detectaron patrones de alerta que requieren atencion antes de que "
               "se conviertan en problemas cronicos.",
            3: "El patron de asistencia es critico y requiere intervencion formal "
               "y seguimiento riguroso para revertir la tendencia.",
        }.get(nivel, "Patron de asistencia requiere atencion.")


# =========================================================
# HILOS
# =========================================================
class HiloCargaEmpleados(QThread):
    """
    Carga la lista de empleados desde device_users sin filtro de fechas.
    Garantiza que todos los empleados del lector aparezcan en el combo
    aunque no tengan registros en un rango específico.
    """
    completado = pyqtSignal(object)
    error      = pyqtSignal(str)

    def __init__(self, procesador):
        super().__init__()
        self.procesador = procesador

    def run(self):
        try:
            # Sin rango → carga todos los empleados desde device_users
            self.procesador.cargar_datos_desde_railway()
            self.completado.emit(self.procesador.obtener_lista_empleados())
        except Exception as e:
            self.error.emit(str(e))


class HiloAnalisis(QThread):
    """Carga datos + ejecuta análisis + trae sugerencia de Railway en background."""
    completado = pyqtSignal(object, object, object, object)  # datos, patrones, predicciones, sugerencia
    error      = pyqtSignal(str)

    def __init__(self, procesador, analizador, id_empleado, f_inicio, f_fin):
        super().__init__()
        self.procesador  = procesador
        self.analizador  = analizador
        self.id_empleado = id_empleado
        self.f_inicio    = f_inicio
        self.f_fin       = f_fin

    def run(self):
        try:
            # Recargar desde Railway con el rango exacto (dentro del hilo,
            # no en el hilo principal para no bloquear la UI)
            self.procesador.cargar_datos_desde_railway(
                self.f_inicio.date(), self.f_fin.date())
            datos = self.procesador.filtrar_por_periodo(
                self.id_empleado, self.f_inicio, self.f_fin)
            if not datos:
                self.completado.emit(None, [], {}, None)
                return

            patrones     = self.analizador.analizar_patrones(datos)
            predicciones = self.analizador.generar_predicciones(patrones)

            # calcular_nivel_gravedad recibe el dict de filtrar_por_periodo
            # que incluye los días de falta total (sin registro en el lector),
            # garantizando que las ausencias se reflejen en el nivel calculado.
            nivel      = self.procesador.calcular_nivel_gravedad(datos)
            sugerencia = self.analizador.obtener_sugerencia(nivel)

            self.completado.emit(datos, patrones, predicciones, sugerencia)
        except Exception as e:
            self.error.emit(str(e))


class HiloVoto(QThread):
    completado = pyqtSignal(bool)

    def __init__(self, analizador, sugerencia_id, positivo):
        super().__init__()
        self.analizador    = analizador
        self.sugerencia_id = sugerencia_id
        self.positivo      = positivo

    def run(self):
        ok = self.analizador.votar_sugerencia(self.sugerencia_id, self.positivo)
        self.completado.emit(ok)


class HiloOtraSugerencia(QThread):
    completado = pyqtSignal(object)
    error      = pyqtSignal(str)

    def __init__(self, analizador, nivel, excluir_id):
        super().__init__()
        self.analizador = analizador
        self.nivel      = nivel
        self.excluir_id = excluir_id

    def run(self):
        try:
            sug = self.analizador.obtener_sugerencia(self.nivel, excluir_id=self.excluir_id)
            self.completado.emit(sug)
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
# ESTILOS
# =========================================================
_BTN_BLANCO = """
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
_BTN_GRIS = """
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
_BTN_VERDE = """
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
_BTN_ROJO = """
    QPushButton {
        background-color: rgb(163, 45, 45);
        color: white;
        font-family: Arial;
        font-size: 17px;
        font-weight: bold;
        padding: 14px 32px;
        border-radius: 10px;
        border: none;
    }
    QPushButton:hover { background-color: rgb(120, 30, 30); }
"""
_SCROLL = """
    QScrollArea { background: rgb(237, 245, 252); border: none; }
    QScrollBar:vertical { background: rgb(181, 212, 244); width: 8px; border-radius: 4px; }
    QScrollBar::handle:vertical { background: rgb(24, 95, 165); border-radius: 4px; }
"""
_COMBO = """
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
"""
_DATE = """
    QDateEdit {
        background-color: rgb(241, 239, 232);
        color: rgb(26, 26, 26);
        font-family: Arial;
        font-size: 16px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid rgb(181, 212, 244);
        min-width: 160px;
    }
    QDateEdit:focus { background-color: white; border: 2px solid rgb(24, 95, 165); }
    QCalendarWidget QWidget { background-color: white; color: black; }
    QCalendarWidget QToolButton { color: black; background-color: transparent; icon-size: 20px; }
    QCalendarWidget QMenu { background-color: white; color: black; }
    QCalendarWidget QSpinBox { background-color: white; color: black; selection-background-color: #2196F3; }
    QCalendarWidget QAbstractItemView:enabled {
        color: black; background-color: white;
        selection-background-color: #2196F3; selection-color: white;
    }
"""


# =========================================================
# WIDGET PRINCIPAL
# =========================================================
class InterfazAnalisisAvanzado(QWidget):
    """
    Análisis avanzado con I.A. de aprendizaje por retroalimentación.
    Arranca directamente en selección de empleado (sin pantalla de carga PDF).
    """
    volver_menu = pyqtSignal()

    def __init__(self, sesion=None, parent=None):
        super().__init__(parent)
        self.sesion     = sesion
        self.graphics   = InterfaceGraphics() if GRAPHICS_IMPORTED else None
        self.procesador = ProcesadorReporteAsistencia() if PROCESSOR_AVAILABLE else None
        self.analizador = AnalizadorAvanzadoAsistencia()

        self.empleados_disponibles: list = []
        self.datos_empleado: Optional[dict]        = None
        self.patrones:       List[PatronAsistencia] = []
        self.predicciones:   dict                  = {}
        self.sugerencia_actual: Optional[Sugerencia] = None
        self._hilo       = None   # hilo de carga/análisis principal
        self._hilo_voto  = None   # hilo de voto (referencia fuerte anti-GC)
        self._hilo_otra  = None   # hilo de "mostrar otra" (ídem)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.canvas_fondo = CanvasFondo(self, self.graphics)
        main_layout.addWidget(self.canvas_fondo)

        self.contenedor_widgets = QWidget(self)
        self.contenedor_widgets.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.contenedor_widgets.setStyleSheet("background: transparent;")

        self.timer = QTimer()
        self.timer.timeout.connect(self.canvas_fondo.update)
        self.timer.start(33)

        self.cambiar_pantalla("seleccion")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.contenedor_widgets.setGeometry(0, 0, self.width(), self.height())

    # ----------------------------------------------------------
    def cambiar_pantalla(self, pantalla: str):
        if self.contenedor_widgets.layout():
            QWidget().setLayout(self.contenedor_widgets.layout())
        for child in self.contenedor_widgets.findChildren(QWidget):
            child.setParent(None)

        layout = QVBoxLayout(self.contenedor_widgets)
        layout.setContentsMargins(60, 50, 60, 50)
        layout.setSpacing(28)

        if pantalla == "seleccion":
            self._crear_pantalla_seleccion(layout)
            self._cargar_empleados_async()
        elif pantalla == "analisis":
            self._crear_pantalla_analisis(layout)
        elif pantalla == "sugerencias":
            self._crear_pantalla_sugerencias(layout)

    # ----------------------------------------------------------
    # PANTALLA SELECCIÓN
    # ----------------------------------------------------------
    def _crear_pantalla_seleccion(self, layout):
        layout.addStretch(1)

        titulo = QLabel("Seleccion de Analisis")
        titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 60px; font-weight: bold; background: transparent;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        layout.addStretch(1)

        emp_lbl_sub = QLabel("Selecciona el empleado que deseas analizar")
        emp_lbl_sub.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 25px; background: transparent;")
        emp_lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(emp_lbl_sub)

        self.combo_empleado = QComboBox()
        self.combo_empleado.addItem("-- Cargando empleados... --")
        self.combo_empleado.setStyleSheet(_COMBO)
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
        self.fecha_inicio_edit.setDate(QDate.currentDate().addDays(-7))
        self.fecha_inicio_edit.setStyleSheet(_DATE)
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
        self.fecha_fin_edit.setStyleSheet(_DATE)
        col_fin.addWidget(lbl_fin)
        col_fin.addWidget(self.fecha_fin_edit)
        fecha_row.addLayout(col_fin)
        fecha_row.addStretch()
        layout.addLayout(fecha_row)

        layout.addStretch(2)

        btn_row = QHBoxLayout()
        btn_menu = QPushButton("Menu principal")
        btn_menu.setStyleSheet("QPushButton { background-color: rgb(255, 255, 255); color: rgb(24, 95, 165); font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: 2px solid rgb(24, 95, 165); } QPushButton:hover { background-color: rgb(230, 241, 251); }")
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)
        btn_row.addStretch()
        self.btn_analizar = QPushButton("Analizar")
        self.btn_analizar.setStyleSheet(_BTN_BLANCO)
        self.btn_analizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_analizar.clicked.connect(self._iniciar_analisis)
        btn_row.addWidget(self.btn_analizar)
        layout.addLayout(btn_row)

    def _cargar_empleados_async(self):
        """Carga todos los empleados desde device_users sin filtro de fechas."""
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
        for emp in sorted(empleados, key=lambda e: e['nombre']):
            self.combo_empleado.addItem(emp['display_name'])
        if not empleados:
            self.combo_empleado.addItem("Sin empleados en el periodo")

    def _combo_error(self):
        if hasattr(self, 'combo_empleado'):
            self.combo_empleado.clear()
            self.combo_empleado.addItem("Error al cargar empleados")

    # ----------------------------------------------------------
    def _iniciar_analisis(self):
        if not self.procesador:
            QMessageBox.warning(self, "Error", "Modulo de procesamiento no disponible.")
            return

        seleccion = self.combo_empleado.currentText()
        if not seleccion or seleccion.startswith("--") or seleccion.startswith("Sin") or seleccion.startswith("Error"):
            QMessageBox.warning(self, "Advertencia", "Por favor selecciona un empleado.")
            return

        try:
            id_empleado = seleccion.split("ID: ")[1].rstrip(")")
        except IndexError:
            id_empleado = seleccion

        f_inicio = self.fecha_inicio_edit.date().toPyDate()
        f_fin    = self.fecha_fin_edit.date().toPyDate()

        if f_inicio > f_fin:
            QMessageBox.warning(self, "Advertencia",
                                "La fecha de inicio debe ser anterior a la fecha fin.")
            return

        self.btn_analizar.setEnabled(False)
        self.btn_analizar.setText("Analizando...")

        f_inicio_dt = datetime.combine(f_inicio, datetime.min.time())
        f_fin_dt    = datetime.combine(f_fin,    datetime.max.time())

        self._hilo = HiloAnalisis(
            self.procesador, self.analizador, id_empleado, f_inicio_dt, f_fin_dt)
        self._hilo.completado.connect(self._on_analisis_listo)
        self._hilo.error.connect(self._on_analisis_error)
        self._hilo.start()

    def _on_analisis_listo(self, datos, patrones, predicciones, sugerencia):
        if hasattr(self, 'btn_analizar'):
            self.btn_analizar.setEnabled(True)
            self.btn_analizar.setText("Analizar")
        if datos is None:
            QMessageBox.warning(self, "Sin datos",
                                "No se encontraron registros para este empleado en el periodo.")
            return
        self.datos_empleado  = datos
        self.patrones        = patrones
        self.predicciones    = predicciones
        self.sugerencia_actual = sugerencia
        self.cambiar_pantalla("analisis")

    def _on_analisis_error(self, msg):
        if hasattr(self, 'btn_analizar'):
            self.btn_analizar.setEnabled(True)
            self.btn_analizar.setText("Analizar")
        QMessageBox.critical(self, "Error", f"Error al generar el analisis:\n{msg}")

    # ----------------------------------------------------------
    # PANTALLA ANÁLISIS (idéntica al original)
    # ----------------------------------------------------------
    def _crear_pantalla_analisis(self, layout):

        if not self.datos_empleado:
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_SCROLL)

        contenedor = QWidget()
        contenedor.setStyleSheet("background: rgb(237, 245, 252);")
        cl = QVBoxLayout(contenedor)
        cl.setSpacing(20)

        titulo = QLabel("Analisis Completo de Asistencia")
        titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 28px; font-weight: bold; background: transparent;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(titulo)

        # Nivel de gravedad — badge prominente
        # Usamos el dict ya calculado en HiloAnalisis (incluye días de falta total)
        nivel = 1
        if self.procesador and self.datos_empleado:
            nivel = self.procesador.calcular_nivel_gravedad(self.datos_empleado)

        nivel_info = {
            1: ("Nivel 1 — Bueno / Estable",   "#27AE60", "✅"),
            2: ("Nivel 2 — Alerta",            "#F39C12", "⚡"),
            3: ("Nivel 3 — Critico",           "#E74C3C", "⚠️"),
        }
        n_texto, n_color, n_icono = nivel_info.get(nivel, nivel_info[2])

        nivel_lbl = QLabel(f"{n_icono}  {n_texto}")
        nivel_lbl.setStyleSheet(
            f"color: {n_color}; font-family: Arial; font-size: 18px; "
            "font-weight: bold; background: transparent;")
        nivel_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(nivel_lbl)

        # Info empleado
        info = QLabel(
            f"{self.datos_empleado.get('nombre', 'N/A')}\n"
            f"Periodo: {self.datos_empleado.get('periodo', 'N/A')}")
        info.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 18px; background: transparent;")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(info)

        cl.addWidget(self._crear_seccion_patrones())
        if self.predicciones:
            cl.addWidget(self._crear_seccion_predicciones())
        cl.addStretch()

        scroll.setWidget(contenedor)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_nueva = QPushButton("Nueva consulta")
        btn_nueva.setStyleSheet("QPushButton { background-color: rgb(255, 255, 255); color: rgb(24, 95, 165); font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: 2px solid rgb(24, 95, 165); } QPushButton:hover { background-color: rgb(230, 241, 251); }")
        btn_nueva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_nueva.clicked.connect(lambda: self.cambiar_pantalla("seleccion"))
        btn_row.addWidget(btn_nueva)
        btn_row.addStretch()
        btn_sug = QPushButton("Ver Sugerencia I.A.")
        btn_sug.setStyleSheet("""
            QPushButton { background-color: rgb(15, 110, 86); color: white; font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: none; } QPushButton:hover { background-color: rgb(10, 80, 62); }
        """)
        btn_sug.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sug.clicked.connect(lambda: self.cambiar_pantalla("sugerencias"))
        btn_row.addWidget(btn_sug)
        btn_row.addStretch()
        btn_menu = QPushButton("Menu principal")
        btn_menu.setStyleSheet("QPushButton { background-color: rgb(255, 255, 255); color: rgb(24, 95, 165); font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: 2px solid rgb(24, 95, 165); } QPushButton:hover { background-color: rgb(230, 241, 251); }")
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)
        layout.addLayout(btn_row)

    def _crear_seccion_patrones(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: rgb(255, 255, 255); border-radius: 12px; border: 1px solid rgb(181, 212, 244); padding: 18px; }
        """)
        fl = QVBoxLayout(frame)

        tit = QLabel("Patrones Identificados")
        tit.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        fl.addWidget(tit)

        if not self.patrones:
            ok = QLabel("Sin patrones problematicos detectados\nCumplimiento satisfactorio")
            ok.setStyleSheet(
                "color: #4CAF50; font-family: Arial; font-size: 14px; "
                "background: none; padding: 15px;")
            ok.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fl.addWidget(ok)
        else:
            for patron in self.patrones:
                fl.addWidget(self._crear_widget_patron(patron))

        return frame

    def _crear_widget_patron(self, patron: PatronAsistencia) -> QWidget:
        w  = QWidget()
        w.setStyleSheet("background-color: rgb(241, 239, 232); border-radius: 8px; padding: 10px; border-left: 4px solid rgb(24, 95, 165); ")
        wl = QVBoxLayout(w)

        if patron.severidad >= 4:
            color, nivel = "#E74C3C", "CRITICO"
        elif patron.severidad >= 3:
            color, nivel = "#F39C12", "MEDIO"
        else:
            color, nivel = "#F1C40F", "LEVE"

        tipo_lbl = QLabel(f"• {patron.tipo} ({nivel})")
        tipo_lbl.setStyleSheet(
            f"color: {color}; font-family: Arial; font-size: 13px; "
            "font-weight: bold; background: none;")
        wl.addWidget(tipo_lbl)

        desc_lbl = QLabel(patron.descripcion)
        desc_lbl.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 14px; background: transparent;")
        wl.addWidget(desc_lbl)

        return w

    def _crear_seccion_predicciones(self) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background-color: rgb(255, 255, 255); border-radius: 12px; border: 1px solid rgb(181, 212, 244); padding: 18px; }
        """)
        fl = QVBoxLayout(frame)

        tit = QLabel("Predicciones y Recomendaciones")
        tit.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        fl.addWidget(tit)

        if not self.predicciones:
            return frame

        riesgo = self.predicciones.get('riesgo_general', 'N/A')
        if riesgo == "Alto":
            cr, icono = "#E74C3C", "⚠️"
        elif riesgo == "Medio":
            cr, icono = "#F39C12", "⚡"
        else:
            cr, icono = "#4CAF50", "✅"

        r_lbl = QLabel(f"{icono} Nivel de Riesgo: {riesgo}")
        r_lbl.setStyleSheet(
            f"color: {cr}; font-family: Arial; font-size: 16px; "
            "font-weight: bold; background: transparent; padding: 10px;")
        r_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(r_lbl)

        prob = self.predicciones.get('probabilidad_mejora', 0)
        p_lbl = QLabel(f"Probabilidad de Mejora: {prob}%")
        p_lbl.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        p_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(p_lbl)

        areas = self.predicciones.get('areas_criticas', [])
        if areas:
            a_tit = QLabel("Areas Criticas:")
            a_tit.setStyleSheet(
                "color: rgb(26, 26, 26); font-family: Arial; font-size: 14px; "
                "font-weight: bold; background: transparent; padding-top: 10px;")
            fl.addWidget(a_tit)
            for area in areas[:3]:
                a_item = QLabel(f"  • {area}")
                a_item.setStyleSheet(
                    "color: rgb(26, 26, 26); font-family: Arial; font-size: 12px; "
                    "background: transparent; padding-left: 20px;")
                fl.addWidget(a_item)

        seg = self.predicciones.get('recomendacion_seguimiento', 'N/A')
        s_tit = QLabel("Seguimiento Recomendado:")
        s_tit.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        fl.addWidget(s_tit)
        s_val = QLabel(seg)
        s_val.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; background: transparent;")
        fl.addWidget(s_val)

        return frame

    # ----------------------------------------------------------
    # PANTALLA SUGERENCIAS — el corazón del ML
    # ----------------------------------------------------------
    def _crear_pantalla_sugerencias(self, layout):
        if not self.sugerencia_actual:
            return

        sug = self.sugerencia_actual

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_SCROLL)

        contenedor = QWidget()
        contenedor.setStyleSheet("background: rgb(237, 245, 252);")
        cl = QVBoxLayout(contenedor)
        cl.setSpacing(20)

        titulo = QLabel("Sugerencia de Accion I.A.")
        titulo.setStyleSheet(
            "color: rgb(24, 95, 165); font-family: Arial; font-size: 28px; font-weight: bold; background: transparent;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(titulo)

        nombre_lbl = QLabel(self.datos_empleado.get('nombre', 'N/A') if self.datos_empleado else '')
        nombre_lbl.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        nombre_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(nombre_lbl)

        # Badge de nivel
        nivel_colores = {1: "#27AE60", 2: "#F39C12", 3: "#E74C3C"}
        n_color = nivel_colores.get(sug.nivel_gravedad, "#9b59b6")
        nivel_badge = QLabel(f"{sug.categoria}")
        nivel_badge.setStyleSheet(
            f"color: {n_color}; font-family: Arial; font-size: 15px; "
            "font-weight: bold; background: transparent;")
        nivel_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(nivel_badge)

        # Card de sugerencia
        sug_frame = QFrame()
        sug_frame.setStyleSheet("""
            QFrame { background-color: rgb(255, 255, 255); border-radius: 12px; border: 1px solid rgb(181, 212, 244); padding: 20px; }
        """)
        sf = QVBoxLayout(sug_frame)

        prioridades = {1: "Alta", 2: "Media", 3: "Baja"}
        prior = prioridades.get(sug.prioridad, "Media")
        cat_lbl = QLabel(f"Prioridad: {prior}")
        cat_lbl.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        cat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sf.addWidget(cat_lbl)

        just_tit = QLabel("Justificacion:")
        just_tit.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        sf.addWidget(just_tit)

        just_txt = QLabel(sug.justificacion)
        just_txt.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 14px; background: transparent;")
        just_txt.setWordWrap(True)
        sf.addWidget(just_txt)

        accion_tit = QLabel("Accion Recomendada:")
        accion_tit.setStyleSheet(
            "color: rgb(26, 26, 26); font-family: Arial; font-size: 16px; font-weight: bold; background: transparent;")
        sf.addWidget(accion_tit)

        accion_txt = QLabel(sug.accion)
        accion_txt.setStyleSheet("""
            color: rgb(26, 26, 26); font-family: Arial; font-size: 15px; background-color: rgb(241, 239, 232); padding: 15px; border-radius: 8px; border-left: 4px solid rgb(15, 110, 86);
        """)
        accion_txt.setWordWrap(True)
        sf.addWidget(accion_txt)

        # Peso de aprendizaje actual (transparente para el usuario)
        if sug.id is not None:
            peso_lbl = QLabel(f"Peso I.A.: {sug.peso:.2f}")
            peso_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.35); font-size: 10px; "
                "font-family: Arial; background: none; padding-top: 8px;")
            peso_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            sf.addWidget(peso_lbl)

        cl.addWidget(sug_frame)

        # Retroalimentación — aquí ocurre el ML
        retro_lbl = QLabel("Esta sugerencia es apropiada para la situacion?")
        retro_lbl.setStyleSheet(
            "color: white; font-family: Arial; font-size: 14px; "
            "background: transparent; padding-top: 20px;")
        retro_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(retro_lbl)

        retro_row = QHBoxLayout()
        retro_row.addStretch()

        btn_si = QPushButton("Si, es apropiada")
        btn_si.setStyleSheet(_BTN_VERDE)
        btn_si.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_si.clicked.connect(self._respuesta_si)
        retro_row.addWidget(btn_si)

        retro_row.addSpacing(20)

        btn_no = QPushButton("Mostrar otra sugerencia")
        btn_no.setStyleSheet(_BTN_ROJO)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.clicked.connect(self._respuesta_no)
        retro_row.addWidget(btn_no)

        retro_row.addStretch()
        cl.addLayout(retro_row)
        cl.addStretch()

        scroll.setWidget(contenedor)
        layout.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_reg = QPushButton("Regresar al analisis")
        btn_reg.setStyleSheet(_BTN_GRIS)
        btn_reg.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reg.clicked.connect(lambda: self.cambiar_pantalla("analisis"))
        btn_row.addWidget(btn_reg)
        btn_row.addStretch()
        btn_menu = QPushButton("Menu principal")
        btn_menu.setStyleSheet("QPushButton { background-color: rgb(255, 255, 255); color: rgb(24, 95, 165); font-family: Arial; font-size: 17px; font-weight: bold; padding: 14px 32px; border-radius: 10px; border: 2px solid rgb(24, 95, 165); } QPushButton:hover { background-color: rgb(230, 241, 251); }")
        btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_menu.clicked.connect(self._volver)
        btn_row.addWidget(btn_menu)
        layout.addLayout(btn_row)

    # ----------------------------------------------------------
    # RETROALIMENTACIÓN — ML
    # ----------------------------------------------------------
    def _respuesta_si(self):
        """Voto positivo → sube peso en Railway → regresa a selección."""
        sug = self.sugerencia_actual
        if sug and sug.id is not None:
            # Referencia fuerte: evita destrucción por GC antes de emitir la señal
            self._hilo_voto = HiloVoto(self.analizador, sug.id, positivo=True)
            self._hilo_voto.completado.connect(
                lambda ok: QMessageBox.information(
                    self, "I.A. Aprendiendo",
                    "Retroalimentacion registrada.\n"
                    "La I.A. dara mayor prioridad a este tipo de sugerencias."
                    if ok else
                    "Retroalimentacion guardada localmente."
                ))
            self._hilo_voto.start()
        else:
            QMessageBox.information(self, "Gracias",
                                    "Retroalimentacion registrada.")
        self.cambiar_pantalla("seleccion")

    def _respuesta_no(self):
        """Voto negativo → baja peso → trae otra sugerencia del mismo nivel."""
        sug = self.sugerencia_actual
        if not sug:
            return

        # Guardar referencia fuerte al hilo de voto para evitar que el GC
        # destruya el QThread mientras sigue ejecutándose (causa crash en PyQt6)
        if sug.id is not None:
            self._hilo_voto = HiloVoto(self.analizador, sug.id, positivo=False)
            self._hilo_voto.start()

        # Guardar referencia fuerte al hilo de "mostrar otra"
        # Si se guarda solo en variable local, Python puede destruirlo
        # antes de que termine run() → segfault / crash silencioso
        self._hilo_otra = HiloOtraSugerencia(
            self.analizador, sug.nivel_gravedad, sug.id)
        self._hilo_otra.completado.connect(self._on_nueva_sugerencia)
        self._hilo_otra.error.connect(
            lambda e: print(f"[IA] Error buscando alternativa: {e}"))
        self._hilo_otra.start()

    def _on_nueva_sugerencia(self, nueva: Sugerencia):
        self.sugerencia_actual = nueva
        self.cambiar_pantalla("sugerencias")

    # ----------------------------------------------------------
    def _volver(self):
        self.timer.stop()
        self.volver_menu.emit()


# =========================================================
# MAIN (debug standalone)
# =========================================================
def main():
    if not PROCESSOR_AVAILABLE:
        _log("ADVERTENCIA: attendance_processor no disponible.")

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
    ventana.setWindowTitle("Analisis Avanzado — Debug")
    widget = InterfazAnalisisAvanzado(sesion=SesionDebug())
    widget.volver_menu.connect(app.quit)
    ventana.setCentralWidget(widget)
    ventana.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()