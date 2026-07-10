import sqlite3
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
    assert {"cheques", "depositos", "auditoria", "formatos_impresion"} <= tables


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
