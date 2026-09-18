import sqlite3
from datetime import date
from pathlib import Path

import pytest

from conciliador.database import Database
from conciliador.errors import ErrorPersistencia
from conciliador.migrations import LATEST_VERSION, MIGRATIONS, SCHEMA_SQL, migrate
from conciliador.paths import AppPaths
from conciliador import printing


def test_rutas_portables_no_dependen_del_cwd(tmp_path, monkeypatch):
    portable = tmp_path / "portable"
    monkeypatch.chdir(tmp_path)

    paths = AppPaths.portable(portable)

    assert paths.database == portable / "data" / "conciliador.db"
    assert paths.log_file == portable / "logs" / "conciliador.log"
    assert paths.exports_dir == portable / "exports"


def test_impresion_resuelve_archivos_relativos_en_exports(tmp_path, monkeypatch):
    paths = AppPaths.portable(tmp_path / "portable")
    monkeypatch.setattr(printing, "DIRECTORIO_EXPORTACIONES", paths.exports_dir)

    ruta = printing.resolver_archivo_salida("cheque_1.pdf")

    assert ruta == paths.exports_dir / "cheque_1.pdf"
    assert paths.exports_dir.is_dir()


def test_base_nueva_migra_y_repetir_es_inocuo(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)

    assert database.initialize() == LATEST_VERSION
    assert database.initialize() == LATEST_VERSION

    with database.connect() as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert version == LATEST_VERSION
    assert {
        "cheques", "depositos", "auditoria", "formatos_impresion",
        "configuracion",
    } <= tables
    with database.connect() as connection:
        columnas_cheque = {
            row[1] for row in connection.execute("PRAGMA table_info(cheques)")
        }
    assert {
        "fecha_cobro", "fecha_cobro_origen", "fecha_anulacion",
        "fecha_anulacion_origen",
    } <= columnas_cheque


def test_migracion_fecha_cobro_marca_cheques_existentes_no_anulados(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto, estado) "
            "VALUES (1, '1', '2026-01-01', 'A', '10', 'TRANSITO'), "
            "(1, '2', '2026-01-01', 'B', '20', 'ANULADO')"
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 9")
        connection.execute("ALTER TABLE cheques DROP COLUMN fecha_cobro")

    assert database.initialize() == LATEST_VERSION
    with database.connect() as connection:
        fechas = [
            tuple(row)
            for row in connection.execute(
                "SELECT numero, fecha_cobro FROM cheques ORDER BY numero"
            ).fetchall()
        ]

    assert fechas == [("1", date.today().isoformat()), ("2", None)]


def test_migracion_recupera_origen_de_fechas_desde_auditoria(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "UPDATE schema_migrations SET applied_at = '2026-05-15 12:00:00' "
            "WHERE version = 9"
        )
        fecha_migracion = connection.execute(
            "SELECT date(applied_at, 'localtime') FROM schema_migrations "
            "WHERE version = 9"
        ).fetchone()[0]
        banco = connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto, fecha_cobro) "
            "VALUES (1, '10', '2026-01-01', 'A', '10', '2026-07-10')"
        ).lastrowid
        admin = connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto, fecha_cobro) "
            "VALUES (1, '11', '2026-01-01', 'B', '10', '2026-07-11')"
        ).lastrowid
        connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto, fecha_cobro) "
            "VALUES (1, '12', '2026-01-01', 'C', '10', ?)",
            (fecha_migracion,),
        )
        connection.execute(
            "INSERT INTO auditoria (accion, entidad, entidad_id, detalle) "
            "VALUES ('COBRAR', 'CHEQUE', '10', "
            "'SIN CONFIGURAR / Cuenta principal: cobrado el 2026-07-10')"
        )
        connection.execute("UPDATE cheques SET fecha_cobro_origen = NULL")
        connection.execute("DELETE FROM schema_migrations WHERE version = 10")

    assert database.initialize() == LATEST_VERSION
    with database.connect() as connection:
        origenes = [
            tuple(row)
            for row in connection.execute(
                "SELECT numero, fecha_cobro_origen FROM cheques ORDER BY numero"
            )
        ]

    assert banco and admin
    assert origenes == [
        ("10", "BANCO"), ("11", "ADMIN"), ("12", "MIGRACION")
    ]


def test_migracion_fecha_anulacion_marca_anulados_existentes(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto, estado) "
            "VALUES (1, '30', '2026-01-01', 'A', '10', 'ANULADO')"
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 11")

    assert database.initialize() == LATEST_VERSION
    with database.connect() as connection:
        cheque = connection.execute(
            "SELECT fecha_anulacion, fecha_anulacion_origen FROM cheques "
            "WHERE numero = '30'"
        ).fetchone()

    assert tuple(cheque) == (date.today().isoformat(), "MIGRACION")


def test_migracion_recupera_fecha_anulacion_desde_auditoria(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO cheques (cuenta_id, numero, fecha, nombre, monto, estado, "
            "fecha_anulacion, fecha_anulacion_origen) "
            "VALUES (1, '40', '2026-07-31', 'A', '10', 'ANULADO', "
            "'2026-09-11', 'MIGRACION')"
        )
        connection.execute(
            "INSERT INTO auditoria "
            "(fecha_hora, accion, entidad, entidad_id, detalle) VALUES "
            "('2026-09-03 17:12:09', 'ANULAR', 'CHEQUE', '40', "
            "'Estado cambiado a ANULADO.')"
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 12")

    assert database.initialize() == LATEST_VERSION
    with database.connect() as connection:
        cheque = connection.execute(
            "SELECT fecha_anulacion, fecha_anulacion_origen FROM cheques "
            "WHERE numero = '40'"
        ).fetchone()

    assert tuple(cheque) == ("2026-09-03", "OPERACION")


def test_migracion_agrega_formato_de_conciliacion_a_cuentas_existentes(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    connection = sqlite3.connect(paths.database)
    try:
        connection.execute("DELETE FROM schema_migrations WHERE version = 4")
        connection.execute(
            "ALTER TABLE cuentas_bancarias DROP COLUMN formato_conciliacion"
        )
        connection.commit()
    finally:
        connection.close()

    assert database.initialize() == LATEST_VERSION
    with database.connect() as connection:
        formato = connection.execute(
            "SELECT formato_conciliacion FROM cuentas_bancarias WHERE id = 1"
        ).fetchone()[0]

    assert formato == "Banco Industrial"


def test_migracion_bac_conserva_relaciones_existentes(tmp_path):
    paths = AppPaths.portable(tmp_path)
    paths.ensure_directories()
    connection = sqlite3.connect(paths.database)
    try:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for migration in MIGRATIONS[:6]:
            migration.upgrade(connection)
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )
        connection.execute(
            "INSERT INTO cheques "
            "(cuenta_id, numero, fecha, nombre, monto) "
            "VALUES (1, '100', '2026-07-10', 'Proveedor', '10.00')"
        )
        connection.commit()
    finally:
        connection.close()

    assert Database(paths).initialize() == LATEST_VERSION

    with Database(paths).connect() as connection:
        cheque = connection.execute(
            "SELECT cuenta_id, numero FROM cheques WHERE numero = '100'"
        ).fetchone()
        assert tuple(cheque) == (1, "100")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_conexion_aplica_pragmas(tmp_path):
    database = Database(AppPaths.portable(tmp_path))

    with database.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_adopta_base_existente_y_crea_respaldo(tmp_path):
    paths = AppPaths.portable(tmp_path)
    paths.ensure_directories()
    connection = sqlite3.connect(paths.database)
    connection.executescript(SCHEMA_SQL)
    connection.commit()
    connection.close()

    assert Database(paths).initialize() == 1

    assert len(list(paths.migration_backups.glob("*.db"))) == 1


def test_rechaza_version_superior(tmp_path):
    paths = AppPaths.portable(tmp_path)
    database = Database(paths)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO schema_migrations(version, name) VALUES (?, 'futura')",
            (LATEST_VERSION + 1,),
        )

    with pytest.raises(ErrorPersistencia, match="superior"):
        database.initialize()


def test_migracion_fallida_hace_rollback(tmp_path, monkeypatch):
    paths = AppPaths.portable(tmp_path)
    paths.ensure_directories()
    connection = sqlite3.connect(paths.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    from conciliador import migrations

    def fallar(connection):
        connection.execute("CREATE TABLE tabla_temporal(id INTEGER)")
        raise RuntimeError("fallo intencional")

    migration = migrations.Migration(1, "fallida", fallar)
    monkeypatch.setattr(migrations, "MIGRATIONS", (migration,))
    monkeypatch.setattr(migrations, "LATEST_VERSION", 1)

    with pytest.raises(RuntimeError, match="intencional"):
        migrate(connection, paths.database, paths.migration_backups)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    connection.close()
    assert "tabla_temporal" not in tables
