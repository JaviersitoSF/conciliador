import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .errors import ErrorPersistencia


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    upgrade: Callable[[sqlite3.Connection], None]


BASE_TABLES = {
    "cuentas_bancarias": {
        "id", "banco", "nombre", "numero", "activa", "creada_en"
    },
    "cheques": {
        "id", "cuenta_id", "numero", "fecha", "nombre", "monto", "estado",
        "descripcion", "creado_en", "actualizado_en",
    },
    "depositos": {
        "id", "cuenta_id", "fecha", "descripcion", "monto", "estado",
        "creado_en", "actualizado_en",
    },
    "auditoria": {
        "id", "fecha_hora", "accion", "entidad", "entidad_id", "detalle"
    },
    "formatos_impresion": {
        "cuenta_id", "ancho", "alto", "fecha_x", "fecha_y", "nombre_x",
        "nombre_y", "monto_x", "monto_y", "no_negociable_x",
        "no_negociable_y", "monto_letras_x", "monto_letras_y",
        "descripcion_x", "descripcion_y",
    },
}

SCHEMA_SQL = """
CREATE TABLE cuentas_bancarias (
    id INTEGER PRIMARY KEY,
    banco TEXT NOT NULL,
    nombre TEXT NOT NULL,
    numero TEXT NOT NULL DEFAULT '',
    formato_conciliacion TEXT NOT NULL DEFAULT 'Banco Industrial'
        CHECK (formato_conciliacion IN ('Banco Industrial', 'G&T Continental', 'Banrural')),
    activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
    creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (banco, nombre, numero)
);
CREATE TABLE cheques (
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
CREATE TABLE depositos (
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
CREATE TABLE auditoria (
    id INTEGER PRIMARY KEY,
    fecha_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accion TEXT NOT NULL,
    entidad TEXT NOT NULL,
    entidad_id TEXT,
    detalle TEXT NOT NULL
);
CREATE TABLE formatos_impresion (
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
INSERT INTO cuentas_bancarias (id, banco, nombre, numero)
VALUES (1, 'SIN CONFIGURAR', 'Cuenta principal', '');
INSERT INTO formatos_impresion (
    cuenta_id, ancho, alto, fecha_x, fecha_y, nombre_x, nombre_y, monto_x,
    monto_y, no_negociable_x, no_negociable_y, monto_letras_x, monto_letras_y,
    descripcion_x, descripcion_y
) VALUES (
    1, 22.0, 14.0, 1.8, 13.0, 1.9, 12.1, 15.0, 13.0, 2.5, 10.0, 1.0,
    11.2, 2.5, 5.9
);
"""


def _upgrade_1(connection):
    for statement in SCHEMA_SQL.split(";"):
        if statement.strip():
            connection.execute(statement)


def _upgrade_2(connection):
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(depositos)")
    }
    if "numero" not in columns:
        connection.execute(
            "ALTER TABLE depositos ADD COLUMN numero TEXT NOT NULL DEFAULT ''"
        )

def _upgrade_3(connection):
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(depositos)")
    }
    if "estado" not in columns:
        connection.execute(
            "ALTER TABLE depositos ADD COLUMN estado TEXT NOT NULL "
            "DEFAULT 'REGISTRADO' CHECK (estado IN ('REGISTRADO', 'ANULADO'))"
        )
    if "actualizado_en" not in columns:
        connection.execute(
            "ALTER TABLE depositos ADD COLUMN actualizado_en TEXT"
        )
        connection.execute(
            "UPDATE depositos SET actualizado_en = COALESCE(creado_en, CURRENT_TIMESTAMP)"
        )


def _upgrade_4(connection):
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(cuentas_bancarias)")
    }
    if "formato_conciliacion" not in columns:
        connection.execute(
            "ALTER TABLE cuentas_bancarias ADD COLUMN formato_conciliacion "
            "TEXT NOT NULL DEFAULT 'Banco Industrial' "
            "CHECK (formato_conciliacion IN ('Banco Industrial'))"
        )


def _upgrade_5(connection):
    """Amplía el CHECK de cuentas sin perder ids ni relaciones existentes."""
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cuentas_bancarias'"
    ).fetchone()[0]
    if "G&T Continental" in sql:
        return
    connection.execute(
        """
        CREATE TABLE cuentas_bancarias_nueva (
            id INTEGER PRIMARY KEY,
            banco TEXT NOT NULL,
            nombre TEXT NOT NULL,
            numero TEXT NOT NULL DEFAULT '',
            formato_conciliacion TEXT NOT NULL DEFAULT 'Banco Industrial'
                CHECK (formato_conciliacion IN ('Banco Industrial', 'G&T Continental')),
            activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (banco, nombre, numero)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO cuentas_bancarias_nueva
            (id, banco, nombre, numero, formato_conciliacion, activa, creada_en)
        SELECT id, banco, nombre, numero, formato_conciliacion, activa, creada_en
        FROM cuentas_bancarias
        """
    )
    connection.execute("DROP TABLE cuentas_bancarias")
    connection.execute("ALTER TABLE cuentas_bancarias_nueva RENAME TO cuentas_bancarias")


def _upgrade_6(connection):
    """Agrega Banrural a los formatos permitidos por la cuenta."""
    sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cuentas_bancarias'"
    ).fetchone()[0]
    if "Banrural" in sql:
        return
    connection.execute(
        """
        CREATE TABLE cuentas_bancarias_nueva (
            id INTEGER PRIMARY KEY,
            banco TEXT NOT NULL,
            nombre TEXT NOT NULL,
            numero TEXT NOT NULL DEFAULT '',
            formato_conciliacion TEXT NOT NULL DEFAULT 'Banco Industrial'
                CHECK (formato_conciliacion IN ('Banco Industrial', 'G&T Continental', 'Banrural')),
            activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
            creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (banco, nombre, numero)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO cuentas_bancarias_nueva
            (id, banco, nombre, numero, formato_conciliacion, activa, creada_en)
        SELECT id, banco, nombre, numero, formato_conciliacion, activa, creada_en
        FROM cuentas_bancarias
        """
    )
    connection.execute("DROP TABLE cuentas_bancarias")
    connection.execute("ALTER TABLE cuentas_bancarias_nueva RENAME TO cuentas_bancarias")


MIGRATIONS = (
    Migration(1, "esquema_inicial", _upgrade_1),
    Migration(2, "numero_deposito", _upgrade_2),
    Migration(3, "estado_deposito", _upgrade_3),
    Migration(4, "formato_conciliacion_cuenta", _upgrade_4),
    Migration(5, "formato_conciliacion_gt_continental", _upgrade_5),
    Migration(6, "formato_conciliacion_banrural", _upgrade_6),
)
LATEST_VERSION = MIGRATIONS[-1].version


def _table_names(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _validate_legacy_schema(connection):
    tables = _table_names(connection)
    missing_tables = set(BASE_TABLES) - tables
    if missing_tables:
        raise ErrorPersistencia(
            "La base existente no coincide con el esquema soportado; faltan: "
            + ", ".join(sorted(missing_tables))
        )
    for table, required_columns in BASE_TABLES.items():
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        missing = required_columns - columns
        if missing:
            raise ErrorPersistencia(
                f"La tabla {table} no es compatible; faltan columnas: "
                + ", ".join(sorted(missing))
            )
    foreign_keys = {
        (table, row[2], row[3], row[4])
        for table in ("cheques", "depositos", "formatos_impresion")
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }
    expected = {
        ("cheques", "cuentas_bancarias", "cuenta_id", "id"),
        ("depositos", "cuentas_bancarias", "cuenta_id", "id"),
        ("formatos_impresion", "cuentas_bancarias", "cuenta_id", "id"),
    }
    if not expected <= foreign_keys:
        raise ErrorPersistencia("La base existente no tiene las claves foráneas esperadas.")


def _check_integrity(connection):
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise ErrorPersistencia(f"Falló la verificación de integridad: {result}")


def _backup(connection, backup_dir: Path, database: Path):
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_dir / f"{database.stem}_pre_migration_{stamp}.db"
    copy = sqlite3.connect(destination)
    try:
        connection.backup(copy)
    finally:
        copy.close()
    backups = sorted(backup_dir.glob("*_pre_migration_*.db"), reverse=True)
    for old_backup in backups[5:]:
        old_backup.unlink()
    return destination


def migrate(connection, database, backup_dir, logger: logging.Logger | None = None):
    database = Path(database)
    tables = _table_names(connection)
    has_user_schema = bool(tables - {"schema_migrations", "sqlite_sequence"})
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row[0] for row in connection.execute("SELECT version FROM schema_migrations")
    }
    if applied and max(applied) > LATEST_VERSION:
        raise ErrorPersistencia(
            f"La base usa la versión {max(applied)}, superior a la soportada "
            f"({LATEST_VERSION})."
        )
    if not applied and has_user_schema:
        _check_integrity(connection)
        _validate_legacy_schema(connection)
        _backup(connection, Path(backup_dir), database)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (1, ?)",
                ("adopcion_esquema_existente",),
            )
            _check_integrity(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return 1

    pending = [migration for migration in MIGRATIONS if migration.version not in applied]
    if not pending:
        return max(applied, default=0)

    _check_integrity(connection)
    backup = _backup(connection, Path(backup_dir), database) if database.exists() else None
    reconstruye_cuentas = any(migration.version in {5, 6} for migration in pending)
    if reconstruye_cuentas:
        connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for migration in pending:
            if logger:
                logger.info("Aplicando migracion %s: %s", migration.version, migration.name)
            migration.upgrade(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise ErrorPersistencia("La migración dejó claves foráneas inválidas.")
        _check_integrity(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        if logger and backup:
            logger.exception("Migracion fallida; respaldo conservado en %s", backup)
        raise
    finally:
        if reconstruye_cuentas:
            connection.execute("PRAGMA foreign_keys = ON")
    return LATEST_VERSION
