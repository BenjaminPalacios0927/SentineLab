import math
import os
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient, QBrush

# =========================================================
# PALETA DE COLORES (tema claro corporativo)
# =========================================================
# Fondo principal
C_BG           = QColor(237, 245, 252)   # azul hielo claro
C_BG_CARD      = QColor(255, 255, 255)   # blanco puro para tarjetas
C_BG_FIELD     = QColor(241, 239, 232)   # gris cálido para campos

# Acento primario (azul corporativo)
C_PRIMARY      = QColor(24,  95,  165)   # azul oscuro — botones principales
C_PRIMARY_DARK = QColor(12,  68,  124)   # hover
C_PRIMARY_PALE = QColor(181, 212, 244)   # borde / decoración

# Acento secundario (teal — botón Lector, detalles)
C_TEAL         = QColor(15,  110,  86)
C_TEAL_PALE    = QColor(159, 225, 203)

# Texto
C_TEXT_DARK    = QColor(24,  95,  165)   # títulos sobre fondo claro
C_TEXT_MID     = QColor(95,  94,  90)    # subtítulos
C_TEXT_LIGHT   = QColor(255, 255, 255)   # texto sobre fondos oscuros
C_TEXT_HINT    = QColor(136, 135, 128)   # placeholders / hints

# Barra superior fija
C_TOPBAR       = QColor(24,  95,  165)

# Barra inferior
C_BOTTOMBAR    = QColor(255, 255, 255)
C_BOTTOMBAR_BORDER = QColor(181, 212, 244)

# Mensajes
C_ERROR_BG     = QColor(163,  45,  45, 230)
C_STATUS_BG    = QColor(24,   95, 165, 220)


class InterfaceGraphics:
    """
    Clase encargada exclusivamente de la renderización visual de la aplicación.
    Tema: claro corporativo — fondo azul hielo, botones blancos, tipografía legible.
    """

    # Altura fija de la barra superior (usada también por main.py para
    # calcular posiciones de widgets QLineEdit en LoginScene)
    TOPBAR_H    = 56
    BOTTOMBAR_H = 82   # ampliada para alojar botón Lector +40%

    def __init__(self):
        # Fuentes — +20% respecto a la iteración anterior
        self.font_topbar    = QFont("Arial", 13, QFont.Weight.Bold)
        self.font_title     = QFont("Arial", 36, QFont.Weight.Bold)
        self.font_subtitle  = QFont("Arial", 18)
        self.font_menu_q    = QFont("Arial", 40, QFont.Weight.Bold)
        self.font_button    = QFont("Arial", 17, QFont.Weight.Bold)
        self.font_btn_sub   = QFont("Arial", 12)
        self.font_msg       = QFont("Arial", 16, QFont.Weight.Bold)
        self.font_warn      = QFont("Arial", 13)

    # =========================================================
    # 1. FONDO
    # =========================================================
    def dibujar_gradiente_animado(self, painter: QPainter, width: int, height: int, tiempo: int):
        """
        Fondo claro animado — tres círculos estáticos que pulsan en tamaño
        de forma desfasada: mientras uno crece, los otros se encogen.

        Para ajustar a tu gusto:
          - radio_base  → tamaño en reposo de cada círculo (fracción de dim)
          - amplitud    → cuánto crece/encoge respecto al radio base (fracción de dim)
          - velocidad   → tiempo * X: más alto = pulso más rápido
          - desfase     → el offset en radianes entre círculos (ahora 2π/3 ≈ 120°)
          - Alpha       → opacidad del color (0-255)
        """
        painter.fillRect(0, 0, width, height, C_BG)
        painter.setPen(Qt.PenStyle.NoPen)

        dim = min(width, height)

        # Velocidad del pulso — misma para los tres para que el desfase sea limpio
        velocidad  = 0.008  
        # Desfase entre círculos: 2π/3 ≈ 120° → en cualquier momento
        # uno está en máximo, otro en punto medio y otro en mínimo
        desfase    = math.pi * 2 / 3

        # ── Círculo 1: superior-derecho, azul corporativo ────────────────
        radio_base1 = dim * 0.30
        amplitud1   = dim * 0.09
        r1 = radio_base1 + math.sin(tiempo * velocidad) * amplitud1
        painter.setBrush(QBrush(QColor(24, 95, 165, 85)))
        painter.drawEllipse(QPointF(width * 0.82, height * 0.18), r1, r1)

        # ── Círculo 2: inferior-izquierdo, teal ──────────────────────────
        radio_base2 = dim * 0.24
        amplitud2   = dim * 0.08
        r2 = radio_base2 + math.sin(tiempo * velocidad + desfase) * amplitud2
        painter.setBrush(QBrush(QColor(15, 110, 86, 75)))
        painter.drawEllipse(QPointF(width * 0.14, height * 0.82), r2, r2)

        # ── Círculo 3: centro, azul pálido ────────────────────────────────
        radio_base3 = dim * 0.18
        amplitud3   = dim * 0.07
        r3 = radio_base3 + math.sin(tiempo * velocidad + desfase * 2) * amplitud3
        painter.setBrush(QBrush(QColor(145, 186, 225, 80)))  # tono más oscuro y opacidad mayor
        painter.drawEllipse(QPointF(width * 0.38, height * 0.50), r3, r3)

    # =========================================================
    # 2. ESCENA: LOGIN / BIENVENIDA
    # =========================================================
    def dibujar_escena_bienvenida(self, painter: QPainter, width: int, height: int):
        """
        Barra superior fija + título + subtítulo + tarjeta blanca de login.
        Los widgets QLineEdit y el botón INGRESAR los posiciona main.py
        sobre esta tarjeta, por lo que aquí solo dibujamos el contenedor visual.
        """
        # ── Barra superior ──────────────────────────────────────
        painter.setBrush(QBrush(C_TOPBAR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, width, self.TOPBAR_H)

        painter.setPen(QPen(C_TEXT_LIGHT))
        painter.setFont(self.font_topbar)
        painter.drawText(
            QRectF(0, 0, width, self.TOPBAR_H),
            Qt.AlignmentFlag.AlignCenter,
            "SISTEMA DE GESTIÓN DE ASISTENCIA"
        )

        # ── Título principal ────────────────────────────────────
        cy = height // 2
        painter.setPen(QPen(C_TEXT_DARK))
        painter.setFont(self.font_title)
        painter.drawText(
            QRectF(0, cy - 375, width, 70),
            Qt.AlignmentFlag.AlignCenter,
            "Bienvenido a SentineLab"
        )

        # ── Subtítulo ───────────────────────────────────────────
        painter.setFont(self.font_subtitle)
        painter.setPen(QPen(QColor(0, 0, 0)))
        painter.drawText(
            QRectF(0, cy - 300, width, 36),
            Qt.AlignmentFlag.AlignCenter,
            "Ingresa tus credenciales para continuar"
        )

        # ── Tarjeta blanca contenedora del formulario (+40% alto) ──
        card_w = 476   # 340 * 1.4
        card_h = 336   # 240 * 1.4
        card_x = (width - card_w) / 2
        card_y = cy - 188

        painter.setBrush(QBrush(C_BG_CARD))
        painter.setPen(QPen(C_PRIMARY_PALE, 1))
        painter.drawRoundedRect(QRectF(card_x, card_y, card_w, card_h), 14, 14)

        # ── Línea de acento en el borde superior de la tarjeta ──
        painter.setBrush(QBrush(C_PRIMARY))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(card_x, card_y, card_w, 4), 4, 4)

        # ── Ícono de usuario (silueta) ──────────────────────────
        # Centro horizontal de la tarjeta, en el espacio libre
        # entre la línea de acento y el primer campo de texto.
        ico_cx = card_x + card_w / 2
        ico_cy = card_y + 68          # centro vertical del ícono

        # Fondo circular del ícono
        bg_r = 40
        painter.setBrush(QBrush(QColor(230, 241, 251)))
        painter.setPen(QPen(C_PRIMARY_PALE, 1.5))
        painter.drawEllipse(QPointF(ico_cx, ico_cy), bg_r, bg_r)

        # Cabeza
        head_r = 13
        painter.setBrush(QBrush(C_PRIMARY))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(ico_cx, ico_cy - 10), head_r, head_r)

        # Hombros (arco / segmento elíptico recortado dentro del círculo)
        from PyQt6.QtGui import QPainterPath
        shoulder_w = 46
        shoulder_h = 24
        path = QPainterPath()
        path.addEllipse(
            QPointF(ico_cx, ico_cy + 22),
            shoulder_w / 2, shoulder_h / 2
        )
        # Recortar para que no salga del círculo de fondo
        clip = QPainterPath()
        clip.addEllipse(QPointF(ico_cx, ico_cy), bg_r, bg_r)
        painter.setClipPath(clip)
        painter.drawPath(path)
        painter.setClipping(False)

        # ── Advertencia de administrador (solo Windows) ─────────
        if os.name == 'nt':
            try:
                import ctypes
                if not ctypes.windll.shell32.IsUserAnAdmin():
                    painter.setFont(self.font_warn)
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    painter.drawText(
                        QRectF(0, height - 72, width, 52),
                        Qt.AlignmentFlag.AlignCenter,
                        "⚠  Para mejor funcionalidad, ejecutar como administrador\n"
                        "(Click derecho → Ejecutar como administrador)"
                    )
            except Exception:
                pass

    # =========================================================
    # 3. ESCENA: MENÚ PRINCIPAL
    # =========================================================
    def dibujar_escena_menu(self, painter: QPainter, width: int, height: int,
                             botones_data: list, hover_idx) -> list:
        """
        Barra superior + cuadrícula de botones tarjeta + barra inferior.

        Retorna lista de (QRectF, texto) para detección de clicks en main.py.
        """
        # ── Barra superior ──────────────────────────────────────
        painter.setBrush(QBrush(C_TOPBAR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, width, self.TOPBAR_H)

        painter.setPen(QPen(C_TEXT_LIGHT))
        painter.setFont(self.font_topbar)
        painter.drawText(
            QRectF(0, 0, width, self.TOPBAR_H),
            Qt.AlignmentFlag.AlignCenter,
            "SISTEMA DE GESTIÓN DE ASISTENCIA"
        )

        # ── Barra inferior ──────────────────────────────────────
        bar_y = height - self.BOTTOMBAR_H
        painter.setBrush(QBrush(C_BOTTOMBAR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, bar_y, width, self.BOTTOMBAR_H)
        painter.setPen(QPen(C_BOTTOMBAR_BORDER, 1))
        painter.drawLine(0, bar_y, width, bar_y)

        # ── Pregunta central ────────────────────────────────────
        painter.setPen(QPen(C_TEXT_DARK))
        painter.setFont(self.font_menu_q)
        # El texto se centra entre la barra superior y el grid de botones.
        # Para ajustar la posición vertical del texto, modifica el valor +28:
        #   - Número más grande  → texto más abajo
        #   - Número más pequeño → texto más arriba
        painter.drawText(
            QRectF(0, self.TOPBAR_H + 125, width, 75),
            Qt.AlignmentFlag.AlignCenter,
            "¿Qué deseas hacer?"
        )

        # ── Cuadrícula de botones ────────────────────────────────
        # Área útil: entre barra superior y barra inferior
        area_top    = self.TOPBAR_H + 96
        area_bottom = bar_y - 16
        area_h      = area_bottom - area_top

        btn_w, btn_h = 290, 100
        col_gap      = 40
        row_gap      = 28

        # 4 botones en 2×2, centrados en el área útil
        grid_w = btn_w * 2 + col_gap
        grid_h = btn_h * 2 + row_gap
        gx     = (width - grid_w) / 2
        gy     = area_top + (area_h - grid_h) / 2 - btn_h * 0.10

        # Subtítulos descriptivos para cada botón del grid
        subtitulos = {
            "Informe rápido":         "Resumen de asistencia",
            "Reportes":               "Exportar y consultar",
            "Análisis y\npredicción": "Predicción y patrones",
            "Registros":              "Usuarios y dispositivo",
        }

        configuracion_botones = [
            ("Informe rápido",       0, 0),
            ("Reportes",             1, 0),
            ("Análisis y\npredicción", 0, 1),
            ("Registros",            1, 1),
            ("Salir",                0.5, 2),   # centrado
            ("Lector",               -1,  3),   # barra inferior izquierda
        ]

        rects_generados = []

        for idx, (texto, col, row) in enumerate(configuracion_botones):
            is_hover = (hover_idx == idx)

            if col == 0.5:
                # Botón "Salir" — debajo del grid, centrado
                bx = (width - btn_w) / 2
                by = gy + grid_h + row_gap + 6
                rect = QRectF(bx, by, btn_w, 44)

                # Estilo: borde azul, fondo blanco / hover azul pálido
                bg = QColor(230, 241, 251) if is_hover else C_BG_CARD
                painter.setBrush(QBrush(bg))
                painter.setPen(QPen(C_PRIMARY, 1.5))
                painter.drawRoundedRect(rect, 10, 10)

                painter.setPen(QPen(C_PRIMARY))
                painter.setFont(self.font_button)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, texto)

            elif col == -1:
                # Botón "Lector" — barra inferior izquierda (+40%)
                lector_w, lector_h = 154, 50
                bx = 20
                by = bar_y + (self.BOTTOMBAR_H - lector_h) / 2
                rect = QRectF(bx, by, lector_w, lector_h)

                bg = QColor(209, 240, 228) if is_hover else QColor(225, 245, 238)
                painter.setBrush(QBrush(bg))
                painter.setPen(QPen(C_TEAL, 1))
                painter.drawRoundedRect(rect, 10, 10)

                painter.setPen(QPen(C_TEAL))
                font_lector = QFont("Arial", 17, QFont.Weight.Bold)
                painter.setFont(font_lector)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "⚙  Lector")

            else:
                # Botones del grid 2×2 — tarjeta blanca con borde azul
                bx = gx + col * (btn_w + col_gap)
                by = gy + row * (btn_h + row_gap)
                rect = QRectF(bx, by, btn_w, btn_h)

                # Fondo: hover = azul muy pálido, normal = blanco
                bg = QColor(230, 241, 251) if is_hover else C_BG_CARD
                painter.setBrush(QBrush(bg))
                border_color = C_PRIMARY if is_hover else C_PRIMARY_PALE
                painter.setPen(QPen(border_color, 1.5 if is_hover else 1))
                painter.drawRoundedRect(rect, 12, 12)

                # Línea de acento superior del botón
                accent_color = C_PRIMARY if is_hover else QColor(181, 212, 244, 160)
                painter.setBrush(QBrush(accent_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(bx, by, btn_w, 4), 4, 4)

                # Texto principal del botón
                painter.setPen(QPen(C_PRIMARY))
                painter.setFont(self.font_button)
                # Para botones con salto de línea, ajustar posición vertical
                tiene_salto = "\n" in texto
                text_rect = QRectF(bx, by + (8 if tiene_salto else 14), btn_w, btn_h * 0.55)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, texto)

                # Subtítulo descriptivo
                sub = subtitulos.get(texto, "")
                if sub:
                    painter.setFont(self.font_btn_sub)
                    painter.setPen(QPen(QColor(0, 0, 0)))
                    sub_rect = QRectF(bx, by + btn_h * 0.62, btn_w, btn_h * 0.34)
                    painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, sub)

            rects_generados.append((rect, texto))

        return rects_generados

    # =========================================================
    # 4. NOTIFICACIONES
    # =========================================================
    def dibujar_notificaciones(self, painter: QPainter, width: int, height: int, contador: int):
        """Badge de notificaciones en la esquina inferior derecha."""
        notif_x = width - 100
        notif_y = height - self.BOTTOMBAR_H // 2

        painter.setBrush(QBrush(C_PRIMARY))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(notif_x, notif_y), 20, 20)

        painter.setPen(QPen(C_TEXT_LIGHT))
        painter.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        painter.drawText(
            QRectF(notif_x - 20, notif_y - 20, 40, 40),
            Qt.AlignmentFlag.AlignCenter,
            str(contador)
        )

        painter.setPen(QPen(QColor(0, 0, 0)))
        painter.setFont(QFont("Arial", 11))
        painter.drawText(
            QRectF(notif_x - 180, notif_y - 15, 100, 30),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "Notificaciones"
        )

    # =========================================================
    # 5. OVERLAYS — MENSAJES DE ESTADO / ERROR
    # =========================================================
    def dibujar_mensajes_estado(self, painter: QPainter, width: int,
                                 mensaje_error: str, mensaje_estado: str):
        """Cajas flotantes de mensajes debajo de la barra superior."""

        top = self.TOPBAR_H + 12

        if mensaje_error:
            rect = QRectF(width // 4, top, width // 2, 52)
            painter.setBrush(QBrush(C_ERROR_BG))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 10, 10)

            painter.setPen(QPen(C_TEXT_LIGHT))
            painter.setFont(self.font_msg)
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                mensaje_error
            )

        elif mensaje_estado:
            rect = QRectF(width // 4, top, width // 2, 44)
            painter.setBrush(QBrush(C_STATUS_BG))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 10, 10)

            painter.setPen(QPen(C_TEXT_LIGHT))
            painter.setFont(self.font_msg)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, mensaje_estado)

    # =========================================================
    # 6. TRANSICIONES
    # =========================================================
    def dibujar_overlay_transicion(self, painter: QPainter, width: int, height: int, alpha_val: float):
        """Negro semitransparente para transiciones entre escenas."""
        alpha = int((1.0 - alpha_val) * 255)
        if alpha > 0:
            painter.fillRect(0, 0, width, height, QColor(0, 0, 0, alpha))