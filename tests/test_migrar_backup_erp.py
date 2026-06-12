import importlib.util
import sqlite3
from pathlib import Path

from conciliador.migrations import LATEST_VERSION


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrar_backup_erp.py"
SPEC = importlib.util.spec_from_file_location("migrar_backup_erp", SCRIPT)
migrar_backup_erp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migrar_backup_erp)


def test_migra_dump_al_esquema_versionado_actual(tmp_path):
    origen = tmp_path / "erp.sql"
    destino = tmp_path / "salida.db"
    chequera = [
        "7", "0", "'123-456'", "0", "0", "'Cuenta Banco Industrial'",
        "0", "1",
    ]
    cheque = ["NULL"] * 25
    cheque[1] = "7"
    cheque[3] = "42"
    cheque[5] = "'Pago proveedor'"
    cheque[6] = "'2026-06-10 00:00:00'"
    cheque[7] = "125.5"
    cheque[8] = "1"
    cheque[12] = "'Proveedor, S.A.'"
    cheque[22] = "'2026-06-10 08:30:00'"
    origen.write_text(
        "INSERT INTO `erp_chequera` VALUES (" + ",".join(chequera) + ");\n"
        "INSERT INTO `erp_cheque_cab` VALUES (" + ",".join(cheque) + ");\n",
        encoding="utf-8",
    )

    assert migrar_backup_erp.migrar(origen, destino) == (1, 1, 0, 0)

    with sqlite3.connect(destino) as conexion:
        version = conexion.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        cuenta = conexion.execute(
            "SELECT banco, nombre, numero, activa FROM cuentas_bancarias"
        ).fetchone()
        cheque_migrado = conexion.execute(
            "SELECT cuenta_id, numero, nombre, monto, estado FROM cheques"
        ).fetchone()

    assert version == LATEST_VERSION
    assert cuenta == (
        "BANCO INDUSTRIAL", "Cuenta Banco Industrial", "123-456", 1
    )
    assert cheque_migrado == (7, "42", "Proveedor, S.A.", "125.50", "TRANSITO")
