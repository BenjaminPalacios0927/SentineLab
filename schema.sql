-- =========================================================
-- SentineLab · Sistema de Asistencia — schema.sql
-- =========================================================
-- Esquema reconstruido a partir de las sentencias SQL que ya
-- existían embebidas en el código (CREATE TABLE IF NOT EXISTS,
-- INSERT, UPDATE, SELECT) en:
--   main.py, device_config.py, registros.py,
--   attendance_processor.py, advanced_analysis.py
--
-- No es un archivo que existiera en el proyecto original: se
-- documenta aquí para que el proyecto se pueda levantar desde
-- cero en una base de datos vacía. Motor: MySQL 8 / MariaDB.
--
-- Uso:
--   mysql -h <host> -P <puerto> -u <usuario> -p <basedatos> < schema.sql
-- =========================================================

-- ---------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------
-- Cuentas de acceso a la aplicación (no confundir con los
-- empleados del lector de huella, que viven en device_users).
--
-- Esta es la ÚNICA tabla que el código NUNCA crea
-- automáticamente (a diferencia de las tres siguientes, que sí
-- se auto-crean con CREATE TABLE IF NOT EXISTS la primera vez
-- que se usan). Debes ejecutar este script, o al menos esta
-- sección, antes del primer arranque.
--
-- Columnas inferidas de:
--   main.py      → SELECT pasw, rol, status, `del` FROM users WHERE name = %s
--   registros.py → SELECT id, name, rol, status FROM users WHERE `del`=0
--                   INSERT INTO users (name, pasw, rol) VALUES (...)
--                   UPDATE users SET pasw=%s, rol=%s WHERE name=%s
--                   UPDATE users SET `del`=1 WHERE id=%s   (borrado lógico)
--
-- rol:    0 = Administrador (ROL_ADMIN), 1 = Usuario normal (ROL_USUARIO)
--         (constantes definidas en device_config.py)
-- status: 1 = activo, 0 = deshabilitado (bloquea el login aunque
--         la contraseña sea correcta)
-- del:    0 = visible, 1 = eliminado (borrado lógico; registros.py
--         nunca hace DELETE físico sobre esta tabla)
--
-- Nota: registros.py trata el registro con id = 0 como una cuenta
-- protegida que no se puede eliminar desde la interfaz. Si vas a
-- sembrar un primer administrador, conviene que sea justamente el
-- id = 0 (ver create_admin.py, que lo hace automáticamente si la
-- tabla está vacía).
CREATE TABLE IF NOT EXISTS users (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    name    VARCHAR(100) NOT NULL UNIQUE,
    pasw    VARCHAR(255) NOT NULL,        -- hash bcrypt, nunca texto plano
    rol     TINYINT      NOT NULL DEFAULT 1,
    status  TINYINT      NOT NULL DEFAULT 1,
    `del`   TINYINT      NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------
-- 2. device_users
-- ---------------------------------------------------------
-- Perfiles de empleados sincronizados con el lector ZKTeco K30.
-- Es la versión final de la tabla: además de las columnas base
-- (creadas en main.py / device_config.py), registros.py agrega
-- lector_synced y pending_op vía ALTER TABLE para soportar
-- sincronización diferida cuando el lector no está disponible.
--
-- lector_synced: 1 = el perfil coincide con lo que hay en el
--                lector físico, 0 = hay un cambio pendiente
-- pending_op:    'crear' | 'editar' | 'eliminar' | NULL
--                (operación pendiente de aplicar al lector la
--                próxima vez que haya conexión con él)
CREATE TABLE IF NOT EXISTS device_users (
    user_id       VARCHAR(20)  NOT NULL PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL,
    departamento  VARCHAR(100) DEFAULT '',
    horario       INT          DEFAULT 0,   -- group_id del lector K30, sin tabla propia
    tiene_huella  TINYINT      DEFAULT 0,
    synced_at     DATETIME     DEFAULT CURRENT_TIMESTAMP,
    lector_synced TINYINT      DEFAULT 1,
    pending_op    VARCHAR(10)  DEFAULT NULL
);

-- ---------------------------------------------------------
-- 3. attendance_raw
-- ---------------------------------------------------------
-- Eventos de marcaje (entrada/salida) descargados tal cual del
-- lector K30. attendance_processor.py los cruza con device_users
-- y calcula entradas/salidas por posición cronológica (el status
-- crudo del K30 no se considera confiable, ver comentarios en
-- attendance_processor.py).
CREATE TABLE IF NOT EXISTS attendance_raw (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    user_id   VARCHAR(50),
    timestamp DATETIME,
    status    INT,
    synced_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- 4. ia_suggestions_pool
-- ---------------------------------------------------------
-- Pool de sugerencias del módulo de análisis avanzado
-- (advanced_analysis.py). Funciona como un mecanismo simple de
-- aprendizaje por refuerzo: cada sugerencia acumula un
-- peso_aprendizaje que sube o baja según el voto del supervisor,
-- y se ordenan por ese peso al elegir cuál mostrar.
--
-- Esta tabla SÍ se auto-crea y se auto-puebla la primera vez que
-- se pide una sugerencia (advanced_analysis.py:_asegurar_tabla),
-- usando el texto de respaldo (_SUGERENCIAS_FALLBACK) definido en
-- ese mismo archivo. No es necesario insertar datos aquí a mano.
CREATE TABLE IF NOT EXISTS ia_suggestions_pool (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    nivel_gravedad    INT NOT NULL COMMENT '1=Bueno 2=Alerta 3=Critico',
    sugerencia_texto  TEXT NOT NULL,
    peso_aprendizaje  FLOAT DEFAULT 1.0,
    veces_mostrada    INT   DEFAULT 0,
    votos_positivos   INT   DEFAULT 0,
    votos_negativos   INT   DEFAULT 0,
    creada_en         DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Índices recomendados (no existían en el código original,
-- que solo emitía CREATE TABLE IF NOT EXISTS sin índices
-- adicionales; se agregan aquí porque las consultas reales del
-- proyecto filtran/ordenan por estas columnas y sin ellas cada
-- reporte hace un full table scan de attendance_raw).
-- ---------------------------------------------------------
CREATE INDEX idx_attendance_user_ts ON attendance_raw (user_id, timestamp);
CREATE INDEX idx_suggestions_nivel  ON ia_suggestions_pool (nivel_gravedad, peso_aprendizaje);
