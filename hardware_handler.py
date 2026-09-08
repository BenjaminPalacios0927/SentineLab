import datetime
import os
import subprocess

try:
    from zk import ZK, const
    ZK_LIBRARY_AVAILABLE = True
except ImportError:
    ZK_LIBRARY_AVAILABLE = False


# =========================================================
# CONFIGURACIÓN DEL DISPOSITIVO
# =========================================================
DISPOSITIVO_REAL = {
    'nombre':        'ZkTeco K30',
    'ip':            '192.168.1.201',   # Ajusta a tu IP
    'puerto':        4370,
    'password':      '0',
    'tipo':          'Tiempo y Asistencia',
    'formato_fecha': 'YY-MM-DD',
    'timeout':       5,
    'force_udp':     False,
}


# =========================================================
# CONTROLADOR
# =========================================================
class K30Controller:
    """Controlador para el lector de huella ZKTeco K30."""

    def __init__(self, ip=None, port=None, password=None, use_mock=False):
        self.ip       = ip       or DISPOSITIVO_REAL['ip']
        self.port     = port     or DISPOSITIVO_REAL['puerto']
        self.password = int(password) if password is not None else int(DISPOSITIVO_REAL['password'])
        self.conn     = None

    # ----------------------------------------------------------
    # CONEXIÓN
    # ----------------------------------------------------------
    def conectar(self) -> bool:
        """
        Establece conexión física con el lector ZKTeco K30.
        Versión optimizada para evitar ventanas negras de ping.exe.
        """
        try:
            # 1. Configuramos la instancia del lector
            zk = ZK(
                self.ip, 
                port=self.port, 
                timeout=5, 
                password=self.password, 
                force_udp=DISPOSITIVO_REAL['force_udp']
            )

            # 2. PARCHE PARA WINDOWS: Evitar ventana negra de ping.exe
            # Creamos un objeto STARTUPINFO que le dice a Windows que NO cree una ventana
            if os.name == 'nt':
                info = subprocess.STARTUPINFO()
                info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                info.wShowWindow = 0 # SW_HIDE
                
                # Inyectamos este comportamiento en la función Popen que usa la librería internamente
                import subprocess as sp
                original_popen = sp.Popen
                
                def nuevo_popen(*args, **kwargs):
                    kwargs['startupinfo'] = info
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                    return original_popen(*args, **kwargs)
                
                sp.Popen = nuevo_popen

            # 3. Intentamos la conexión real
            # Al llamar a connect(), la librería hará el ping, pero ahora será invisible
            self.conn = zk.connect()
            
            # Restauramos Popen por seguridad si lo deseas, 
            # aunque para el ejecutable no es estrictamente necesario
            if os.name == 'nt':
                sp.Popen = original_popen

            return True

        except Exception as e:
            print(f"Error de conexión física con el lector: {e}")
            self.conn = None
            return False

    def desconectar(self):
        if self.conn:
            try:
                self.conn.disconnect()
            except Exception:
                pass
            self.conn = None
            print("Desconectado del K30.")

    # ----------------------------------------------------------
    # LECTURA DE DATOS
    # ----------------------------------------------------------
    def descargar_asistencias(self) -> list:
        """
        Retorna lista de dicts:
          { 'user_id': str, 'timestamp': datetime, 'status': int }
        """
        registros = []
        if self.conn:
            try:
                for record in self.conn.get_attendance():
                    registros.append({
                        'user_id':   str(record.user_id),
                        'timestamp': record.timestamp,
                        'status':    record.status,
                    })
            except Exception as e:
                print(f"Error descargando asistencias del K30: {e}")
        return registros

    def obtener_usuarios(self) -> list:
        """
        Retorna lista de dicts:
          { 'user_id': str, 'nombre': str, 'departamento': str,
            'huella': True|None, 'horario': int }

        'huella' es True si el lector tiene al menos un template
        registrado para ese usuario, None si no tiene ninguno.
        """
        usuarios = []
        if not self.conn:
            return usuarios
        try:
            # Obtener qué uids tienen template de huella registrado
            uids_con_huella = set()
            try:
                for t in self.conn.get_templates():
                    uids_con_huella.add(int(t.uid))
            except Exception:
                pass  # Si get_templates falla, seguimos sin info de huellas

            for u in self.conn.get_users():
                tiene_huella = True if int(u.uid) in uids_con_huella else None
                usuarios.append({
                    'user_id':      str(u.user_id),
                    'nombre':       u.name,
                    'departamento': '',
                    'huella':       tiene_huella,
                    'horario':      int(u.group_id) if str(u.group_id).strip().isdigit() else 0,
                })
        except Exception as e:
            print(f"Error obteniendo usuarios del K30: {e}")
        return usuarios

    # ----------------------------------------------------------
    # ESCRITURA DE DATOS
    # ----------------------------------------------------------
    def crear_usuario(self, user_id: str, nombre: str,
                      departamento: str = '', horario: int = 0) -> bool:
        """Crea un nuevo perfil en el lector."""
        if self.conn:
            try:
                self.conn.set_user(
                    uid=int(user_id),
                    name=nombre,
                    privilege=0,
                    group_id=str(horario),
                    user_id=str(user_id),
                )
                return True
            except Exception as e:
                print(f"Error al crear usuario en K30: {e}")
        return False

    def eliminar_usuario(self, user_id: str) -> bool:
        """Elimina un perfil del lector."""
        if self.conn:
            try:
                self.conn.delete_user(uid=int(user_id))
                return True
            except Exception as e:
                print(f"Error al eliminar usuario del K30: {e}")
        return False