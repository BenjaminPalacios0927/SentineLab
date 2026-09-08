import mysql.connector
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict

def _construir_db_config():

    from device_config import construir_db_config_conexion
    return construir_db_config_conexion()


# =========================================================
# CLASES DE DATOS
# =========================================================

class TiempoHorasMinutos:
    """Maneja tiempo expresado solo en horas y minutos."""

    def __init__(self, horas: int = 0, minutos: int = 0):
        self.horas   = horas
        self.minutos = minutos
        self._normalizar()

    @classmethod
    def from_timedelta(cls, td: timedelta):
        total_seconds = int(td.total_seconds())
        horas   = max(0, total_seconds // 3600)
        minutos = max(0, (total_seconds % 3600) // 60)
        return cls(horas, minutos)

    def _normalizar(self):
        if self.minutos >= 60:
            self.horas   += self.minutos // 60
            self.minutos  = self.minutos % 60

    def __add__(self, other):
        return TiempoHorasMinutos(self.horas + other.horas,
                                  self.minutos + other.minutos)

    def __str__(self):
        return f"{self.horas:02d}:{self.minutos:02d}"

    def to_decimal_hours(self) -> float:
        """Convierte a horas decimales (para promedios)."""
        return self.horas + (self.minutos / 60)


@dataclass
class RegistroAsistencia:
    """Evento individual de entrada o salida tal como llega del lector."""
    fecha: datetime
    tipo:  str        # 'Entrada' o 'Salida'
    hora:  datetime


@dataclass
class DiaLaboral:
    """Información consolidada de un día de trabajo."""
    fecha:            datetime
    entrada:          Optional[datetime]           = None
    salida:           Optional[datetime]           = None
    horas_trabajadas: Optional[TiempoHorasMinutos] = None

    def calcular_horas(self) -> Optional[TiempoHorasMinutos]:
        if self.entrada and self.salida:
            td = self.salida - self.entrada
            self.horas_trabajadas = TiempoHorasMinutos.from_timedelta(td)
        return self.horas_trabajadas


@dataclass
class EmpleadoAsistencia:
    """Toda la información de asistencia de un empleado en el periodo cargado."""
    id:                  str
    nombre:              str
    departamento:        str
    registros:           List[RegistroAsistencia]      = field(default_factory=list)
    dias_laborales:      Dict[str, DiaLaboral]          = field(default_factory=dict)
    total_horas_periodo: TiempoHorasMinutos             = field(default_factory=TiempoHorasMinutos)

    def __post_init__(self):
        # Garantiza que total_horas_periodo nunca sea None
        if self.total_horas_periodo is None:
            self.total_horas_periodo = TiempoHorasMinutos()


# =========================================================
# PROCESADOR PRINCIPAL
# =========================================================

class ProcesadorReporteAsistencia:
    """
    Carga y procesa datos de asistencia desde el proveedor de base de
    datos en la nube configurado por el usuario (Railway u otro host
    MySQL/MariaDB compatible). Mantiene la misma API que la versión
    original (PDF) para que todas las interfaces existentes sigan
    funcionando.
    """

    def __init__(self):
        self.empleados: Dict[str, EmpleadoAsistencia] = {}

    # ----------------------------------------------------------
    # CARGA DESDE EL PROVEEDOR DE NUBE CONFIGURADO
    # (el nombre del método se conserva por compatibilidad con
    # el resto de la app, aunque ya no asume Railway)
    # ----------------------------------------------------------

    def cargar_datos_desde_railway(self,
                                   fecha_inicio: date = None,
                                   fecha_fin:    date = None) -> Dict[str, EmpleadoAsistencia]:
        """
        Reemplaza a procesar_reporte(pdf).
        Extrae eventos de attendance_raw, los cruza con device_users
        y construye la misma estructura EmpleadoAsistencia que producía
        el procesador PDF, para que las interfaces no noten la diferencia.

        Lanza una excepción si no puede conectarse, para que el hilo
        que llama a este método pueda propagar el error a la UI.
        """
        try:
            db_config = _construir_db_config()
            if not db_config.get('host') or not db_config.get('database'):
                raise RuntimeError(
                    "No hay un proveedor de base de datos configurado todavía. "
                    "Ve a 'Configuración de Hardware' y completa los datos del "
                    "proveedor de nube (host, puerto, usuario, contraseña y BD)."
                )
            conn   = mysql.connector.connect(**db_config)
            cursor = conn.cursor(dictionary=True)

            # 1. Info de empleados desde device_users
            cursor.execute(
                "SELECT user_id, nombre, departamento FROM device_users"
            )
            info_usuarios = {str(u['user_id']): u for u in cursor.fetchall()}

            # 2. Eventos de asistencia
            query  = ("SELECT user_id, timestamp, status "
                      "FROM attendance_raw")
            params = []
            if fecha_inicio and fecha_fin:
                query += " WHERE DATE(timestamp) BETWEEN %s AND %s"
                params = [fecha_inicio, fecha_fin]
            query += " ORDER BY user_id, timestamp ASC"

            cursor.execute(query, params)
            eventos = cursor.fetchall()
            cursor.close()
            conn.close()

            self.empleados = {}

            # 3a. Pre-poblar empleados desde device_users aunque no tengan
            #     eventos en el rango — garantiza que el combo los muestre
            #     incluso si attendance_raw está vacía o el rango no coincide.
            for uid_str, u_info in info_usuarios.items():
                self.empleados[uid_str] = EmpleadoAsistencia(
                    id           = uid_str,
                    nombre       = u_info['nombre'],
                    departamento = u_info.get('departamento', ''),
                )

            # 3b. Convertir eventos → RegistroAsistencia
            #    El campo status del K30: 0 = Check-In (Entrada), 1 = Check-Out (Salida)
            #    Si el dispositivo no envía status fiable se usa la posición cronológica
            for ev in eventos:
                uid      = str(ev['user_id'])
                ts       = ev['timestamp']   # ya es datetime desde mysql.connector
                status   = ev.get('status', -1)

                # El K30 frecuentemente envía status=255 cuando el usuario
                # no selecciona modo explícitamente. Para evitar clasificaciones
                # erróneas, ignoramos el status y usamos siempre la posición
                # cronológica (primera marca del día = Entrada, última = Salida).
                tipo = 'Desconocido'

                # Si el uid viene en attendance_raw pero no estaba en device_users,
                # crearlo de todas formas para no perder registros
                if uid not in self.empleados:
                    u_info = info_usuarios.get(uid, {
                        'nombre':       f'Usuario {uid}',
                        'departamento': 'Sin departamento'
                    })
                    self.empleados[uid] = EmpleadoAsistencia(
                        id           = uid,
                        nombre       = u_info['nombre'],
                        departamento = u_info.get('departamento', ''),
                    )

                registro = RegistroAsistencia(
                    fecha = ts,
                    tipo  = tipo,
                    hora  = ts,
                )
                self.empleados[uid].registros.append(registro)

            # 4. Misma pipeline del original
            for emp in self.empleados.values():
                self.organizar_dias_laborales(emp)
                self.calcular_horas_trabajadas(emp)

            return self.empleados

        except mysql.connector.errors.InterfaceError as e:
            # Re-lanzar con mensaje amigable para que la UI lo muestre
            raise ConnectionError(
                "Sin conexión a Railway. Verifica tu red e inténtalo de nuevo."
            ) from e
        except Exception as e:
            # Re-lanzar para que el hilo que llama propague el error a la UI
            raise

    # ----------------------------------------------------------
    # PIPELINE DE PROCESAMIENTO (idéntica al original)
    # ----------------------------------------------------------

    def organizar_dias_laborales(self, empleado: EmpleadoAsistencia) -> None:
        """
        Organiza los RegistroAsistencia por días laborales.
        Excluye fines de semana.
        Cuando el status del lector es fiable, usa Entrada/Salida directamente.
        Cuando no lo es (Desconocido), aplica la regla: primera lectura del
        día = Entrada, última = Salida.
        """
        for registro in empleado.registros:
            # Excluir fines de semana (sábado=5, domingo=6)
            if registro.fecha.weekday() >= 5:
                continue

            fecha_key = registro.fecha.strftime('%Y-%m-%d')

            if fecha_key not in empleado.dias_laborales:
                empleado.dias_laborales[fecha_key] = DiaLaboral(
                    fecha=registro.fecha
                )

            dia = empleado.dias_laborales[fecha_key]

            if registro.tipo == 'Entrada':
                if dia.entrada is None or registro.hora < dia.entrada:
                    dia.entrada = registro.hora

            elif registro.tipo == 'Salida':
                if dia.salida is None or registro.hora > dia.salida:
                    dia.salida = registro.hora

            else:
                # Lógica cronológica: acumulamos todas las marcas y al final
                # la más temprana será Entrada y la más tardía Salida.
                # Aquí solo guardamos la primera y la última marca del día.
                if dia.entrada is None:
                    dia.entrada = registro.hora   # primera marca del día
                elif registro.hora < dia.entrada:
                    # llegó una marca más temprana → actualizar entrada
                    if dia.salida is None:
                        dia.salida = dia.entrada   # la anterior pasa a ser salida provisional
                    dia.entrada = registro.hora
                else:
                    # marca más tardía → candidata a salida
                    if dia.salida is None or registro.hora > dia.salida:
                        dia.salida = registro.hora

    def calcular_horas_trabajadas(self, empleado: EmpleadoAsistencia) -> None:
        """Calcula horas por día y acumula el total del periodo."""
        total = TiempoHorasMinutos()
        for dia in empleado.dias_laborales.values():
            horas_dia = dia.calcular_horas()
            if horas_dia:
                total = total + horas_dia
        empleado.total_horas_periodo = total

    # ----------------------------------------------------------
    # CONSULTAS Y RESÚMENES (API idéntica al original)
    # ----------------------------------------------------------

    def obtener_empleado_por_id(self, id_empleado: str) -> Optional[EmpleadoAsistencia]:
        return self.empleados.get(id_empleado)

    def obtener_empleados_por_departamento(self, departamento: str) -> List[EmpleadoAsistencia]:
        return [e for e in self.empleados.values()
                if departamento.lower() in e.departamento.lower()]

    def obtener_lista_empleados(self) -> List[dict]:
        """
        Devuelve dicts con id, nombre, departamento y display_name.
        Misma estructura que el original para no romper las interfaces.
        """
        return [
            {
                'id':           emp.id,
                'nombre':       emp.nombre,
                'departamento': emp.departamento,
                'display_name': f"{emp.nombre} (ID: {emp.id})"
            }
            for emp in self.empleados.values()
        ]

    def filtrar_por_empleado(self, nombre_empleado: str) -> Optional[EmpleadoAsistencia]:
        """Búsqueda por nombre (usado por algunas interfaces)."""
        for emp in self.empleados.values():
            if emp.nombre == nombre_empleado:
                return emp
        return None

    def generar_resumen_empleado(self, id_empleado: str) -> Optional[dict]:
        """
        Resumen detallado de un empleado.
        Misma estructura de salida que el original.
        """
        emp = self.obtener_empleado_por_id(id_empleado)
        if not emp:
            return None

        dias_completos    = [d for d in emp.dias_laborales.values()
                             if d.entrada and d.salida]
        dias_incompletos  = [d for d in emp.dias_laborales.values()
                             if (d.entrada is None) != (d.salida is None)]

        dias_trabajados       = len(dias_completos)
        registros_incompletos = len(dias_incompletos)

        promedio = (emp.total_horas_periodo.to_decimal_hours() / dias_trabajados
                    if dias_trabajados > 0 else 0.0)

        return {
            'id':                   emp.id,
            'nombre':               emp.nombre,
            'departamento':         emp.departamento,
            'dias_trabajados':      dias_trabajados,
            'total_horas_periodo':  str(emp.total_horas_periodo),
            'promedio_horas_dia':   f"{promedio:.2f}",
            'registros_incompletos': registros_incompletos,
            'detalle_dias': [
                {
                    'fecha':           dia.fecha.strftime('%d/%m/%Y'),
                    'dia_semana':      dia.fecha.strftime('%A'),
                    'entrada':         dia.entrada.strftime('%H:%M') if dia.entrada else None,
                    'salida':          dia.salida.strftime('%H:%M')  if dia.salida  else None,
                    'horas_trabajadas': str(dia.horas_trabajadas) if dia.horas_trabajadas else None,
                    'estado': (
                        'Completo'   if dia.entrada and dia.salida else
                        'Incompleto' if dia.entrada or  dia.salida else
                        'Falta'
                    )
                }
                for dia in sorted(emp.dias_laborales.values(), key=lambda x: x.fecha)
            ]
        }

    def filtrar_por_periodo(self,
                             id_empleado:  str,
                             fecha_inicio: datetime,
                             fecha_fin:    datetime) -> Optional[dict]:
        """
        Devuelve el resumen de un empleado acotado a un periodo.
        Misma estructura de salida que el original.

        IMPORTANTE: genera un DiaLaboral vacío (estado='Falta') para cada
        día laboral (lun-vie) del rango que no tenga ningún registro, de modo
        que las ausencias totales se detecten aunque el lector no haya
        guardado ningún marcaje para ese día.
        """
        emp = self.obtener_empleado_por_id(id_empleado)
        if not emp:
            return None

        emp_filtrado = EmpleadoAsistencia(
            id           = emp.id,
            nombre       = emp.nombre,
            departamento = emp.departamento,
        )

        # 1. Copiar los días que SÍ tienen registro dentro del rango
        for fecha_key, dia in emp.dias_laborales.items():
            if fecha_inicio.date() <= dia.fecha.date() <= fecha_fin.date():
                emp_filtrado.dias_laborales[fecha_key] = dia

        # 2. Rellenar los días laborales del rango SIN ningún registro → Falta
        from datetime import date as date_type
        cursor = fecha_inicio.date()
        fin    = fecha_fin.date()
        delta  = timedelta(days=1)
        while cursor <= fin:
            if cursor.weekday() < 5:          # lunes-viernes
                fecha_key = cursor.strftime('%Y-%m-%d')
                if fecha_key not in emp_filtrado.dias_laborales:
                    # Día laboral sin ningún marcaje → falta total
                    emp_filtrado.dias_laborales[fecha_key] = DiaLaboral(
                        fecha=datetime.combine(cursor, datetime.min.time())
                    )
            cursor += delta

        self.calcular_horas_trabajadas(emp_filtrado)

        dias_completos   = [d for d in emp_filtrado.dias_laborales.values()
                            if d.entrada and d.salida]
        dias_incompletos = [d for d in emp_filtrado.dias_laborales.values()
                            if (d.entrada is None) != (d.salida is None)]
        dias_falta       = [d for d in emp_filtrado.dias_laborales.values()
                            if not d.entrada and not d.salida]

        dias_trabajados       = len(dias_completos)
        registros_incompletos = len(dias_incompletos)
        total_dias            = len(emp_filtrado.dias_laborales)
        faltas                = len(dias_falta)

        promedio = (emp_filtrado.total_horas_periodo.to_decimal_hours() / dias_trabajados
                    if dias_trabajados > 0 else 0.0)

        return {
            'id':                    emp_filtrado.id,
            'nombre':                emp_filtrado.nombre,
            'departamento':          emp_filtrado.departamento,
            'periodo':               (f"{fecha_inicio.strftime('%d/%m/%Y')} "
                                      f"- {fecha_fin.strftime('%d/%m/%Y')}"),
            'dias_trabajados':       dias_trabajados,
            'total_horas_periodo':   str(emp_filtrado.total_horas_periodo),
            'promedio_horas_dia':    f"{promedio:.2f}",
            'registros_incompletos': registros_incompletos,
            'faltas':                faltas,
            'detalle_dias': [
                {
                    'fecha':            dia.fecha.strftime('%d/%m/%Y'),
                    'dia_semana':       dia.fecha.strftime('%A'),
                    'entrada':          dia.entrada.strftime('%H:%M') if dia.entrada else None,
                    'salida':           dia.salida.strftime('%H:%M')  if dia.salida  else None,
                    'horas_trabajadas': str(dia.horas_trabajadas) if dia.horas_trabajadas else None,
                    'estado': (
                        'Completo'   if dia.entrada and dia.salida else
                        'Incompleto' if dia.entrada or  dia.salida else
                        'Falta'
                    )
                }
                for dia in sorted(emp_filtrado.dias_laborales.values(), key=lambda x: x.fecha)
            ]
        }

    # ----------------------------------------------------------
    # ANÁLISIS DE COMPORTAMIENTO
    # ----------------------------------------------------------

    def calcular_nivel_gravedad(self,
                                fuente,
                                fecha_inicio: Optional[datetime] = None,
                                fecha_fin:    Optional[datetime] = None) -> int:
        """
        Clasifica el desempeño del empleado en tres niveles:
          1 — Bueno / Estable   (≤ 2 puntos)
          2 — Alerta            (3-5 puntos)
          3 — Crítico           (> 5 puntos)

        Puntuación por día laboral:
          +3  falta total (sin entrada ni salida)
          +2  registro incompleto (solo entrada o solo salida)
          +1  retardo (entrada después de las 09:15)

        fuente puede ser:
          - Un dict (resultado de filtrar_por_periodo) — recomendado, incluye
            los días de falta total aunque no haya registro en el lector.
          - Un EmpleadoAsistencia — solo tiene días CON registro; las faltas
            totales no serán visibles a menos que se haya llamado
            filtrar_por_periodo previamente.

        fecha_inicio / fecha_fin: solo aplican cuando fuente es EmpleadoAsistencia.
        """
        hora_limite = datetime.strptime("09:15", "%H:%M").time()
        puntos = 0

        # ── Modo dict (viene de filtrar_por_periodo) ──────────────────
        if isinstance(fuente, dict):
            for dia in fuente.get('detalle_dias', []):
                estado  = dia.get('estado', '')
                entrada = dia.get('entrada')    # str "HH:MM" o None

                if estado == 'Falta':
                    puntos += 3
                elif estado == 'Incompleto':
                    puntos += 2
                elif estado == 'Completo' and entrada:
                    try:
                        h, m = map(int, entrada.split(':'))
                        if (h, m) > (9, 15):
                            puntos += 1
                    except (ValueError, AttributeError):
                        pass
            if puntos <= 2:  return 1
            if puntos <= 5:  return 2
            return 3

        # ── Modo EmpleadoAsistencia (fallback) ───────────────────────
        emp = fuente
        for dia in emp.dias_laborales.values():
            if fecha_inicio and dia.fecha.date() < fecha_inicio.date():
                continue
            if fecha_fin   and dia.fecha.date() > fecha_fin.date():
                continue

            if not dia.entrada and not dia.salida:
                puntos += 3
            elif dia.entrada is None or dia.salida is None:
                puntos += 2
            elif dia.entrada.time() > hora_limite:
                puntos += 1

        if puntos <= 2:  return 1
        if puntos <= 5:  return 2
        return 3

    def obtener_metricas_departamento(self, departamento: str) -> dict:
        """
        Métricas agregadas de un departamento.
        Usadas por las interfaces de resumen grupal.
        """
        empleados = self.obtener_empleados_por_departamento(departamento)
        if not empleados:
            return {}

        total_horas     = TiempoHorasMinutos()
        total_faltas    = 0
        total_retardos  = 0
        niveles         = []

        hora_limite = datetime.strptime("09:15", "%H:%M").time()

        for emp in empleados:
            total_horas = total_horas + emp.total_horas_periodo
            for dia in emp.dias_laborales.values():
                if not dia.entrada and not dia.salida:
                    total_faltas += 1
                elif dia.entrada and dia.entrada.time() > hora_limite:
                    total_retardos += 1
            niveles.append(self.calcular_nivel_gravedad(emp))

        promedio_nivel = sum(niveles) / len(niveles) if niveles else 1

        return {
            'departamento':   departamento,
            'num_empleados':  len(empleados),
            'total_horas':    str(total_horas),
            'total_faltas':   total_faltas,
            'total_retardos': total_retardos,
            'nivel_promedio': round(promedio_nivel, 2),
        }


# =========================================================
# FUNCIÓN DE CONVENIENCIA
# =========================================================

def cargar_reporte_asistencia(fecha_inicio: date = None,
                               fecha_fin:    date = None
                               ) -> Dict[str, EmpleadoAsistencia]:
    """Equivalente a procesar_reporte_asistencia() del original."""
    procesador = ProcesadorReporteAsistencia()
    return procesador.cargar_datos_desde_railway(fecha_inicio, fecha_fin)