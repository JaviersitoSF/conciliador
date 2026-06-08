import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pandas as pd

import main


class SistemaBancarioTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir.name)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.tmpdir.cleanup()

    def auditoria(self):
        with main.conectar_db() as conexion:
            return conexion.execute(
                "SELECT accion, entidad, entidad_id, detalle FROM auditoria ORDER BY id"
            ).fetchall()

    def test_convertir_monto_rechaza_formatos_ambiguos(self):
        self.assertEqual(main.convertir_monto("Q 1,234.567"), Decimal("1234.57"))
        self.assertEqual(main.convertir_monto("(Q 10.005)"), Decimal("-10.01"))
        self.assertEqual(main.convertir_monto("−5"), Decimal("-5.00"))
        self.assertIsNone(main.convertir_monto("1,50"))
        self.assertIsNone(main.convertir_monto("1,2,3"))
        self.assertIsNone(main.convertir_monto("1e3"))
        self.assertIsNone(main.convertir_monto("abc"))

    def test_base_se_inicializa_con_esquema(self):
        main.inicializar_db()

        with main.conectar_db() as conexion:
            tablas = {
                fila[0]
                for fila in conexion.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        self.assertTrue(
            {"cuentas_bancarias", "cheques", "depositos", "auditoria"} <= tablas
        )

    def test_registrar_deposito_es_transaccional_y_auditable(self):
        resultado = main.registrar_deposito_datos(
            "125.50", "venta caja", fecha="2026-06-03"
        )

        depositos = main.cargar_depositos_registrados()
        self.assertEqual(resultado["monto"], Decimal("125.50"))
        self.assertEqual(depositos.iloc[0]["Descripcion"], "VENTA CAJA")
        self.assertEqual(depositos.iloc[0]["Monto_valor"], Decimal("125.50"))
        self.assertEqual(self.auditoria()[0]["accion"], "CREAR")

    def test_emitir_cheque_crea_registro_auditoria_y_respaldo(self):
        with patch("main.imprimir_cheque_pdf"):
            resultado = main.emitir_cheque_datos(
                "35",
                "proveedor",
                "100.00",
                fecha="2026-06-03",
                descripcion="compra",
            )

        cheque = main.cargar_cheques_registrados().iloc[0]
        self.assertEqual(resultado["num"], "35")
        self.assertEqual(cheque["Descripcion"], "COMPRA")
        self.assertEqual(self.auditoria()[0]["entidad_id"], "35")
        self.assertTrue(os.listdir(main.DIRECTORIO_RESPALDOS))

    def test_numero_cheque_es_unico_en_base_de_datos(self):
        main.guardar_cheque_en_archivo("35", "2026-06-03", "A", "10.00")

        with self.assertRaises(main.ErrorOperacion):
            main.guardar_cheque_en_archivo("35", "2026-06-03", "B", "20.00")

        self.assertEqual(len(main.cargar_cheques_registrados()), 1)
        self.assertEqual(len(self.auditoria()), 1)

    def test_transaccion_revierte_datos_y_auditoria(self):
        with self.assertRaises(RuntimeError):
            with main.transaccion() as conexion:
                conexion.execute(
                    """
                    INSERT INTO depositos (cuenta_id, fecha, descripcion, monto)
                    VALUES (1, '2026-06-03', 'PRUEBA', '10.00')
                    """
                )
                main.registrar_auditoria(
                    conexion, "CREAR", "DEPOSITO", "1", "Debe revertirse"
                )
                raise RuntimeError("fallo")

        self.assertTrue(main.cargar_depositos_registrados().empty)
        self.assertEqual(self.auditoria(), [])

    def test_anular_conserva_datos_y_registra_auditoria(self):
        main.guardar_cheque_en_archivo(
            "35", "2026-06-03", "PROVEEDOR", "10.00", "COMPRA URGENTE"
        )

        main.anular_cheque_numero("35")

        cheque = main.cargar_cheques_registrados().iloc[0]
        self.assertEqual(cheque["Estado"], "ANULADO")
        self.assertEqual(cheque["Descripcion"], "COMPRA URGENTE")
        self.assertEqual([fila["accion"] for fila in self.auditoria()], ["CREAR", "ANULAR"])

    def test_respaldos_se_rotan(self):
        main.inicializar_db()
        with patch.object(main, "MAX_RESPALDOS", 2):
            main.crear_respaldo()
            main.crear_respaldo()
            main.crear_respaldo()

        self.assertEqual(len(os.listdir(main.DIRECTORIO_RESPALDOS)), 2)

    def test_reporte_mensual_excluye_anulados(self):
        main.guardar_cheque_en_archivo("1", "2026-06-03", "A", "50.00")
        main.guardar_cheque_en_archivo("2", "2026-06-04", "B", "20.00")
        main.anular_cheque_numero("2")
        main.registrar_deposito_datos("100.00", "venta", fecha="2026-06-05")

        reporte = main.obtener_reporte_movimientos("2026-06-08")

        self.assertEqual(reporte["total_cheques"], Decimal("50.00"))
        self.assertEqual(reporte["total_depositos"], Decimal("100.00"))
        self.assertEqual(reporte["saldo"], Decimal("50.00"))

    def test_conciliacion_detecta_duplicados(self):
        main.guardar_cheque_en_archivo("35", "2026-06-03", "A", "100.00")
        pd.DataFrame(
            {"Num_cheque": [35, 35], "Monto": ["100.00", "100.00"]}
        ).to_excel(main.ARCHIVO_BANCO, index=False)

        resultado = main.obtener_conciliacion()["cheques"][0]

        self.assertEqual(resultado["resultado"], "DUPLICADO")
        self.assertEqual(resultado["monto_banco"], Decimal("200.00"))

    def test_conciliacion_cubre_estados_principales(self):
        main.guardar_cheque_en_archivo("1", "2026-06-03", "OK", "100.00")
        main.guardar_cheque_en_archivo("2", "2026-06-03", "DIF", "100.00")
        main.guardar_cheque_en_archivo("3", "2026-06-03", "TRANSITO", "100.00")
        main.guardar_cheque_en_archivo("4", "2026-06-03", "ANULADO", "100.00")
        main.anular_cheque_numero("4")
        pd.DataFrame(
            {
                "Num_cheque": [1, 2, 4, 99],
                "Monto": ["100.00", "90.00", "100.00", "12.00"],
            }
        ).to_excel(main.ARCHIVO_BANCO, index=False)

        resultado = main.obtener_conciliacion()
        estados = {fila["num"]: fila["resultado"] for fila in resultado["cheques"]}

        self.assertEqual(estados["1"], "COBRADO")
        self.assertEqual(estados["2"], "DIFERENCIA")
        self.assertEqual(estados["3"], "TRANSITO")
        self.assertEqual(estados["4"], "ALERTA")
        self.assertEqual(resultado["no_registrados"][0]["num"], "99")

    def test_cuentas_separan_numeros_movimientos_y_reportes(self):
        cuenta_a = main.crear_cuenta_bancaria("BANCO A", "Monetaria", "001")
        cuenta_b = main.crear_cuenta_bancaria("BANCO B", "Monetaria", "002")

        main.guardar_cheque_en_archivo(
            "100", "2026-06-03", "A", "10.00", cuenta_id=cuenta_a
        )
        main.guardar_cheque_en_archivo(
            "100", "2026-06-03", "B", "20.00", cuenta_id=cuenta_b
        )
        main.registrar_deposito_datos(
            "50.00", "venta a", fecha="2026-06-03", cuenta_id=cuenta_a
        )
        main.registrar_deposito_datos(
            "80.00", "venta b", fecha="2026-06-03", cuenta_id=cuenta_b
        )

        reporte_a = main.obtener_reporte_movimientos("2026-06-08", cuenta_a)
        reporte_b = main.obtener_reporte_movimientos("2026-06-08", cuenta_b)

        self.assertEqual(reporte_a["saldo"], Decimal("40.00"))
        self.assertEqual(reporte_b["saldo"], Decimal("60.00"))
        self.assertEqual(len(main.cargar_cheques_registrados(cuenta_a)), 1)
        self.assertEqual(len(main.cargar_cheques_registrados(cuenta_b)), 1)

    def test_consola_obliga_a_seleccionar_cuenta_para_emitir(self):
        cuenta_id = main.crear_cuenta_bancaria("BANCO A", "Operativa", "123456")
        cuentas = [
            cuenta
            for cuenta in main.listar_cuentas_bancarias()
            if cuenta["id"] == cuenta_id
        ]

        with patch("main.listar_cuentas_bancarias", return_value=cuentas), \
                patch(
                    "builtins.input",
                    side_effect=["x", "1", "10.00", "Proveedor", "Compra", "35"],
                ), \
                patch("main.imprimir_cheque_pdf"), \
                redirect_stdout(StringIO()):
            main.registrar_e_imprimir()

        cheque = main.cargar_cheques_registrados(cuenta_id).iloc[0]
        self.assertEqual(cheque["Num"], "35")
        self.assertEqual(cheque["Banco"], "BANCO A")

    def test_reimprimir_registra_auditoria(self):
        main.guardar_cheque_en_archivo("35", "2026-06-03", "A", "10.00")

        with patch("main.imprimir_cheque_pdf"):
            main.reimprimir_cheque_numero("35")

        self.assertEqual(self.auditoria()[-1]["accion"], "REIMPRIMIR")

    def test_restricciones_sqlite_impiden_estado_invalido(self):
        main.inicializar_db()

        with main.conectar_db() as conexion, self.assertRaises(sqlite3.IntegrityError):
            conexion.execute(
                """
                INSERT INTO cheques
                    (cuenta_id, numero, fecha, nombre, monto, estado, descripcion)
                VALUES (1, '1', '2026-06-03', 'A', '10.00', 'BORRADO', '')
                """
            )


if __name__ == "__main__":
    unittest.main()
