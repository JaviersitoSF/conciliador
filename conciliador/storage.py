import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .errors import ErrorOperacion
from .printing import FORMATO_IMPRESION_DEFAULT, validar_formato_impresion

ARCHIVO_DATOS = "conciliador.db"
DIRECTORIO_RESPALDOS = "respaldos"
MAX_RESPALDOS = 10
FORMATOS_CONCILIACION = ("Banco Industrial", "G&T Continental", "Banrural", "BAC")
FORMATO_CONCILIACION_DEFAULT = FORMATOS_CONCILIACION[0]
MONEDAS = ("GTQ", "USD")
MONEDA_DEFAULT = MONEDAS[0]


def configure_paths(paths):
    global ARCHIVO_DATOS, DIRECTORIO_RESPALDOS
    ARCHIVO_DATOS = str(paths.database)
    DIRECTORIO_RESPALDOS = str(paths.data_dir / "operation_backups")

class ConexionSQLite(sqlite3.Connection):
    """Conexión que también se cierra al terminar un bloque with."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()

def conectar_db():
    conexion = sqlite3.connect(
        ARCHIVO_DATOS,
        timeout=10,
        factory=ConexionSQLite,
    )
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 10000")
    return conexion

def inicializar_db():
    with conectar_db() as conexion:
        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS cuentas_bancarias (
                id INTEGER PRIMARY KEY,
                banco TEXT NOT NULL,
                nombre TEXT NOT NULL,
                numero TEXT NOT NULL DEFAULT '',
                formato_conciliacion TEXT NOT NULL DEFAULT 'Banco Industrial'
                    CHECK (formato_conciliacion IN ('Banco Industrial', 'G&T Continental', 'Banrural', 'BAC')),
                moneda TEXT NOT NULL DEFAULT 'GTQ'
                    CHECK (moneda IN ('GTQ', 'USD')),
                activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
                creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (banco, nombre, numero)
            );

            CREATE TABLE IF NOT EXISTS cheques (
                id INTEGER PRIMARY KEY,
                cuenta_id INTEGER NOT NULL,
                numero TEXT NOT NULL,
                fecha TEXT NOT NULL,
                nombre TEXT NOT NULL,
                monto TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'TRANSITO'
                    CHECK (estado IN ('TRANSITO', 'ANULADO')),
                descripcion TEXT NOT NULL DEFAULT '',
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cuenta_id, numero),
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );

            CREATE TABLE IF NOT EXISTS depositos (
                id INTEGER PRIMARY KEY,
                cuenta_id INTEGER NOT NULL,
                numero TEXT NOT NULL DEFAULT '',
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'REGISTRADO'
                    CHECK (estado IN ('REGISTRADO', 'ANULADO')),
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );

            CREATE TABLE IF NOT EXISTS notas_debito (
                id INTEGER PRIMARY KEY,
                cuenta_id INTEGER NOT NULL,
                numero TEXT NOT NULL DEFAULT '',
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'REGISTRADO'
                    CHECK (estado IN ('REGISTRADO', 'ANULADO')),
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );

            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY,
                fecha_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                accion TEXT NOT NULL,
                entidad TEXT NOT NULL,
                entidad_id TEXT,
                detalle TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS formatos_impresion (
                cuenta_id INTEGER PRIMARY KEY,
                ancho REAL NOT NULL,
                alto REAL NOT NULL,
                fecha_x REAL NOT NULL,
                fecha_y REAL NOT NULL,
                nombre_x REAL NOT NULL,
                nombre_y REAL NOT NULL,
                monto_x REAL NOT NULL,
                monto_y REAL NOT NULL,
                no_negociable_x REAL NOT NULL,
                no_negociable_y REAL NOT NULL,
                monto_letras_x REAL NOT NULL,
                monto_letras_y REAL NOT NULL,
                descripcion_x REAL NOT NULL,
                descripcion_y REAL NOT NULL,
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );
            """
        )
        columnas_cuenta = {
            fila[1]
            for fila in conexion.execute("PRAGMA table_info(cuentas_bancarias)")
        }
        if "formato_conciliacion" not in columnas_cuenta:
            conexion.execute(
                "ALTER TABLE cuentas_bancarias ADD COLUMN formato_conciliacion "
                "TEXT NOT NULL DEFAULT 'Banco Industrial' "
                "CHECK (formato_conciliacion IN ('Banco Industrial', 'G&T Continental', 'Banrural', 'BAC'))"
            )
        if "moneda" not in columnas_cuenta:
            conexion.execute(
                "ALTER TABLE cuentas_bancarias ADD COLUMN moneda "
                "TEXT NOT NULL DEFAULT 'GTQ' "
                "CHECK (moneda IN ('GTQ', 'USD'))"
            )
        conexion.execute(
            """
            INSERT OR IGNORE INTO cuentas_bancarias (id, banco, nombre, numero)
            VALUES (1, 'SIN CONFIGURAR', 'Cuenta principal', '')
            """
        )
        _insertar_formato_default(conexion, 1)

def _insertar_formato_default(conexion, cuenta_id):
    campos = ", ".join(FORMATO_IMPRESION_DEFAULT)
    marcadores = ", ".join("?" for _ in FORMATO_IMPRESION_DEFAULT)
    conexion.execute(
        f"""
        INSERT OR IGNORE INTO formatos_impresion (cuenta_id, {campos})
        VALUES (?, {marcadores})
        """,
        (cuenta_id, *FORMATO_IMPRESION_DEFAULT.values()),
    )

def listar_cuentas_bancarias(solo_activas=True):
    inicializar_db()
    consulta = """
        SELECT id, banco, nombre, numero, formato_conciliacion, moneda, activa
        FROM cuentas_bancarias
    """
    if solo_activas:
        consulta += " WHERE activa = 1"
    consulta += " ORDER BY banco, nombre"
    with conectar_db() as conexion:
        return [dict(fila) for fila in conexion.execute(consulta).fetchall()]

def crear_cuenta_bancaria(
    banco, nombre, numero="", formato_conciliacion=FORMATO_CONCILIACION_DEFAULT,
    moneda=MONEDA_DEFAULT,
):
    banco, nombre, numero = _normalizar_datos_cuenta(banco, nombre, numero)
    formato_conciliacion = _validar_formato_conciliacion(formato_conciliacion)
    moneda = _validar_moneda(moneda)
    if not banco or not nombre:
        raise ErrorOperacion("⚠️ Banco y nombre de cuenta son obligatorios.")

    try:
        with transaccion() as conexion:
            cursor = conexion.execute(
                """
                INSERT INTO cuentas_bancarias (
                    banco, nombre, numero, formato_conciliacion, moneda
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (banco, nombre, numero, formato_conciliacion, moneda),
            )
            cuenta_id = cursor.lastrowid
            _insertar_formato_default(conexion, cuenta_id)
            registrar_auditoria(
                conexion,
                "CREAR",
                "CUENTA_BANCARIA",
                cuenta_id,
                f"{banco} - {nombre} - {numero or 'sin número'}",
            )
    except sqlite3.IntegrityError as e:
        raise ErrorOperacion("⚠️ Esa cuenta bancaria ya está registrada.") from e
    crear_respaldo_posterior()
    return cuenta_id

def _normalizar_datos_cuenta(banco, nombre, numero):
    banco = str(banco or "").strip().upper()
    nombre = str(nombre or "").strip()
    numero = str(numero or "").strip()
    return banco, nombre, numero

def _validar_formato_conciliacion(formato):
    formato = str(formato or "").strip()
    if formato not in FORMATOS_CONCILIACION:
        raise ErrorOperacion("⚠️ Formato de conciliación inválido.")
    return formato


def _validar_moneda(moneda):
    moneda = str(moneda or "").strip().upper()
    if moneda not in MONEDAS:
        raise ErrorOperacion("⚠️ Moneda de cuenta inválida.")
    return moneda


def actualizar_cuenta_bancaria(
    cuenta_id, banco, nombre, numero="", formato_conciliacion=None, moneda=None
):
    cuenta = obtener_cuenta(cuenta_id)
    banco, nombre, numero = _normalizar_datos_cuenta(banco, nombre, numero)
    formato_conciliacion = _validar_formato_conciliacion(
        cuenta["formato_conciliacion"]
        if formato_conciliacion is None
        else formato_conciliacion
    )
    moneda = _validar_moneda(cuenta["moneda"] if moneda is None else moneda)
    if not banco or not nombre:
        raise ErrorOperacion("⚠️ Banco y nombre de cuenta son obligatorios.")

    try:
        with transaccion() as conexion:
            conexion.execute(
                """
                UPDATE cuentas_bancarias
                SET banco = ?, nombre = ?, numero = ?, formato_conciliacion = ?,
                    moneda = ?
                WHERE id = ?
                """,
                (
                    banco, nombre, numero, formato_conciliacion, moneda,
                    cuenta["id"],
                ),
            )
            registrar_auditoria(
                conexion,
                "ACTUALIZAR",
                "CUENTA_BANCARIA",
                cuenta["id"],
                f"{banco} - {nombre} - {numero or 'sin número'}",
            )
    except sqlite3.IntegrityError as e:
        raise ErrorOperacion("⚠️ Esa cuenta bancaria ya está registrada.") from e
    crear_respaldo_posterior()
    return obtener_cuenta(cuenta["id"])

def obtener_cuenta(cuenta_id=None):
    cuenta_id = 1 if cuenta_id is None else cuenta_id
    try:
        cuenta_id = int(cuenta_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Cuenta bancaria inválida.") from e

    inicializar_db()
    with conectar_db() as conexion:
        cuenta = conexion.execute(
            """
            SELECT id, banco, nombre, numero, formato_conciliacion, moneda, activa
            FROM cuentas_bancarias
            WHERE id = ? AND activa = 1
            """,
            (cuenta_id,),
        ).fetchone()
    if cuenta is None:
        raise ErrorOperacion("⚠️ La cuenta bancaria no existe o está inactiva.")
    return dict(cuenta)

def obtener_formato_impresion(cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    with conectar_db() as conexion:
        fila = conexion.execute(
            "SELECT * FROM formatos_impresion WHERE cuenta_id = ?",
            (cuenta["id"],),
        ).fetchone()
    if fila is None:
        raise ErrorOperacion("⚠️ La cuenta no tiene formato de impresión configurado.")
    return {campo: float(fila[campo]) for campo in FORMATO_IMPRESION_DEFAULT}

def guardar_formato_impresion(cuenta_id, valores):
    cuenta = obtener_cuenta(cuenta_id)
    formato = validar_formato_impresion(valores)
    asignaciones = ", ".join(f"{campo} = ?" for campo in formato)
    with transaccion() as conexion:
        conexion.execute(
            f"UPDATE formatos_impresion SET {asignaciones} WHERE cuenta_id = ?",
            (*formato.values(), cuenta["id"]),
        )
        registrar_auditoria(
            conexion,
            "ACTUALIZAR",
            "FORMATO_IMPRESION",
            cuenta["id"],
            f"{cuenta['banco']} / {cuenta['nombre']}: formato de cheque actualizado.",
        )
    crear_respaldo_posterior()
    return formato

@contextmanager
def transaccion():
    inicializar_db()
    conexion = conectar_db()
    try:
        conexion.execute("BEGIN IMMEDIATE")
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()

def registrar_auditoria(conexion, accion, entidad, entidad_id, detalle):
    conexion.execute(
        """
        INSERT INTO auditoria (accion, entidad, entidad_id, detalle)
        VALUES (?, ?, ?, ?)
        """,
        (accion, entidad, str(entidad_id) if entidad_id is not None else None, detalle),
    )

def crear_respaldo():
    if not os.path.exists(ARCHIVO_DATOS):
        return None

    directorio = Path(DIRECTORIO_RESPALDOS)
    directorio.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = directorio / f"conciliador_{marca}.db"

    origen = conectar_db()
    copia = sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()

    respaldos = sorted(directorio.glob("conciliador_*.db"), reverse=True)
    for respaldo_antiguo in respaldos[MAX_RESPALDOS:]:
        respaldo_antiguo.unlink()
    return str(destino)

def crear_respaldo_posterior():
    try:
        return crear_respaldo()
    except Exception as e:
        raise ErrorOperacion(
            "⚠️ La operación sí se guardó, pero no se pudo crear el respaldo "
            "automático. No repitas la operación; revisa el espacio y permisos "
            "del directorio de respaldos."
        ) from e
