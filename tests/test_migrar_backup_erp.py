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
    deposito = ["NULL"] * 20
    deposito[0] = "9"
    deposito[1] = "7"
    deposito[3] = "1234"
    deposito[5] = "'Venta caja'"
    deposito[6] = "'2026-06-11 00:00:00'"
    deposito[7] = "850.4"
    deposito[12] = "'Venta caja'"
    deposito[17] = "'2026-06-11 09:15:00'"
    origen.write_text(
        "INSERT INTO `erp_chequera` VALUES (" + ",".join(chequera) + ");\n"
        "INSERT INTO `erp_cheque_cab` VALUES (" + ",".join(cheque) + ");\n"
        "INSERT INTO `erp_deposito_cab` VALUES ("
        + ",".join(deposito)
        + ");\n",
        encoding="utf-8",
    )

    assert migrar_backup_erp.migrar(origen, destino) == (1, 1, 1, 0, 0, 0)

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
        deposito_migrado = conexion.execute(
            """
            SELECT cuenta_id, numero, fecha, descripcion, monto, creado_en
            FROM depositos
            """
        ).fetchone()

    assert version == LATEST_VERSION
    assert cuenta == (
        "BANCO INDUSTRIAL", "Cuenta Banco Industrial", "123-456", 1
    )
    assert cheque_migrado == (7, "42", "Proveedor, S.A.", "125.50", "TRANSITO")
    assert deposito_migrado == (
        7,
        "1234",
        "2026-06-11",
        "Venta caja",
        "850.40",
        "2026-06-11 09:15:00",
    )


def test_omite_depositos_anulados_o_sin_cuenta(tmp_path):
    origen = tmp_path / "erp.sql"
    destino = tmp_path / "salida.db"
    chequera = [
        "7", "0", "'123-456'", "0", "0", "'Cuenta Banco Industrial'",
        "0", "1",
    ]
    depositos = []
    for cuenta_id, razon in (("99", "NULL"), ("7", "'Duplicado'")):
        deposito = ["NULL"] * 20
        deposito[0] = str(len(depositos) + 1)
        deposito[1] = cuenta_id
        deposito[3] = "1234"
        deposito[5] = "'Venta caja'"
        deposito[6] = "'2026-06-11 00:00:00'"
        deposito[7] = "850.4"
        deposito[17] = "'2026-06-11 09:15:00'"
        deposito[19] = razon
        depositos.append("(" + ",".join(deposito) + ")")
    origen.write_text(
        "INSERT INTO `erp_chequera` VALUES (" + ",".join(chequera) + ");\n"
        "INSERT INTO `erp_deposito_cab` VALUES "
        + ",".join(depositos)
        + ";\n",
        encoding="utf-8",
    )

    assert migrar_backup_erp.migrar(origen, destino) == (1, 0, 0, 0, 0, 2)

    with sqlite3.connect(destino) as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM depositos").fetchone()[0] == 0
