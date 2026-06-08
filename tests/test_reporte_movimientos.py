import csv
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from unittest.mock import patch

import pandas as pd

import main


class ReporteMovimientosTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir.name)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.tmpdir.cleanup()

    def ejecutar_reporte(self):
        salida = io.StringIO()
        with patch("builtins.input", return_value=""), redirect_stdout(salida):
            main.reporte_movimientos()
        return salida.getvalue()

    def capturar(self, funcion, *args, **kwargs):
        salida = io.StringIO()
        with redirect_stdout(salida):
            resultado = funcion(*args, **kwargs)
        return resultado, salida.getvalue()

    def escribir_csv(self, ruta, filas):
        with open(ruta, "w", newline="", encoding="utf-8") as archivo:
            csv.writer(archivo).writerows(filas)

    def test_reporte_sin_archivos_no_usa_dt_sobre_object(self):
        salida = self.ejecutar_reporte()

        self.assertIn("No hay cheques registrados en el mes actual.", salida)
        self.assertIn("No hay depósitos registrados en el mes actual.", salida)
        self.assertIn("SALDO EN B", salida)
        self.assertFalse(os.path.exists(main.ARCHIVO_CHEQUES))
        self.assertFalse(os.path.exists(main.ARCHIVO_DEPOSITOS))

    def test_reporte_con_archivos_vacios_no_usa_dt_sobre_object(self):
        open(main.ARCHIVO_CHEQUES, "w", encoding="utf-8").close()
        open(main.ARCHIVO_DEPOSITOS, "w", encoding="utf-8").close()

        salida = self.ejecutar_reporte()

        self.assertIn("No hay cheques registrados en el mes actual.", salida)
        self.assertIn("No hay depósitos registrados en el mes actual.", salida)

    def test_cargadores_devuelven_fecha_datetime_aun_vacios(self):
        df_cheques = main.cargar_cheques_registrados()
        df_depositos = main.cargar_depositos_registrados()

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df_cheques["Fecha_dt"]))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df_depositos["Fecha_dt"]))

    def test_reporte_filtra_mes_actual_y_suma_sin_cheques_anulados(self):
        periodo_actual = pd.Timestamp(main.datetime.now().date()).to_period("M")
        fecha_mes = periodo_actual.to_timestamp().strftime("%Y-%m-%d")
        fecha_otro_mes = (periodo_actual - 1).to_timestamp().strftime("%Y-%m-%d")

        self.escribir_csv(
            main.ARCHIVO_CHEQUES,
            [
                ["100", fecha_mes, "PROVEEDOR UNO", "Q 150.25", "TRANSITO"],
                ["101", fecha_mes, "ERROR", "999.00", "ANULADO"],
                ["102", fecha_otro_mes, "FUERA DE MES", "25.00", "TRANSITO"],
                ["103", "no-es-fecha", "SIN FECHA", "10.00", "TRANSITO"],
                ["104", fecha_mes, "SIN MONTO", "malo", "TRANSITO"],
            ],
        )
        self.escribir_csv(
            main.ARCHIVO_DEPOSITOS,
            [
                [fecha_mes, "venta mostrador", "200.00"],
                [fecha_mes, "transferencia", "300.50"],
                [fecha_otro_mes, "fuera de mes", "900.00"],
                ["", "sin fecha", "50.00"],
                [fecha_mes, "sin monto", "malo"],
            ],
        )

        salida = self.ejecutar_reporte()

        self.assertIn("100", salida)
        self.assertIn("101", salida)
        self.assertNotIn("102", salida)
        self.assertIn("TOTAL INGRESOS", salida)
        self.assertIn("Q 500.50", salida)
        self.assertIn("TOTAL EGRESOS", salida)
        self.assertIn("Q 150.25", salida)
        self.assertIn("Q 350.25", salida)

    def test_registro_deposito_y_cheque_escriben_en_cwd_actual(self):
        with patch("main.datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "2026-06-03"
            with patch("builtins.input", side_effect=["125.5", "venta caja"]):
                main.registrar_deposito()

        main.guardar_en_archivo("777", "2026-06-03", "PROVEEDOR", Decimal("10.00"))

        self.assertTrue(os.path.exists(os.path.join(self.tmpdir.name, main.ARCHIVO_DEPOSITOS)))
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir.name, main.ARCHIVO_CHEQUES)))

    def test_convertir_y_formatear_montos(self):
        self.assertIsNone(main.convertir_monto(None))
        self.assertIsNone(main.convertir_monto(float("nan")))
        self.assertIsNone(main.convertir_monto(""))
        self.assertIsNone(main.convertir_monto("--"))
        self.assertIsNone(main.convertir_monto("abc"))
        self.assertEqual(main.convertir_monto("Q 1,234.567"), Decimal("1234.57"))
        self.assertEqual(main.convertir_monto("(Q 10.005)"), Decimal("-10.01"))
        self.assertEqual(main.convertir_monto(Decimal("1.234")), Decimal("1.23"))
        self.assertEqual(main.convertir_monto("−5"), Decimal("-5.00"))
        self.assertEqual(main.formatear_monto("2"), "2.00")
        with patch("main.pd.isna", side_effect=TypeError):
            self.assertEqual(main.convertir_monto("3"), Decimal("3.00"))
        with self.assertRaises(ValueError):
            main.formatear_monto("malo")

    def test_normalizar_numero_cheque(self):
        self.assertIsNone(main.normalizar_numero_cheque(None))
        self.assertIsNone(main.normalizar_numero_cheque(float("nan")))
        self.assertIsNone(main.normalizar_numero_cheque(""))
        self.assertIsNone(main.normalizar_numero_cheque("0"))
        self.assertIsNone(main.normalizar_numero_cheque("12.5"))
        self.assertIsNone(main.normalizar_numero_cheque("abc"))
        self.assertEqual(main.normalizar_numero_cheque("0012"), "12")
        self.assertEqual(main.normalizar_numero_cheque("12.0"), "12")
        self.assertEqual(main.normalizar_numero_cheque("13.00"), "13")
        with patch("main.pd.isna", side_effect=TypeError):
            self.assertEqual(main.normalizar_numero_cheque("14"), "14")

    def test_pedir_validadores_reintentan_hasta_valor_valido(self):
        with patch("builtins.input", side_effect=["", " listo "]):
            self.assertEqual(main.pedir_texto_no_vacio("x"), "listo")

        with patch("builtins.input", side_effect=["abc", "0", "15.25"]):
            self.assertEqual(main.pedir_monto_positivo("x"), Decimal("15.25"))

        with patch("builtins.input", side_effect=["", "abc", "0", "42"]):
            self.assertEqual(main.pedir_numero_cheque("x"), "42")

    def test_cargadores_limpian_filas_y_valores(self):
        self.escribir_csv(
            main.ARCHIVO_CHEQUES,
            [
                ["", "", "", "", ""],
                ["001", "2026-06-03", "  proveedor  ", "Q 10.00", ""],
                ["bad", "no", "x", "bad", "nan"],
            ],
        )
        self.escribir_csv(
            main.ARCHIVO_DEPOSITOS,
            [
                ["", "", ""],
                ["2026-06-03", " venta ", "Q 20"],
            ],
        )

        cheques = main.cargar_cheques_registrados()
        depositos = main.cargar_depositos_registrados()

        self.assertEqual(len(cheques), 2)
        self.assertEqual(cheques.iloc[0]["Estado"], "TRANSITO")
        self.assertEqual(cheques.iloc[0]["Num_norm"], "1")
        self.assertEqual(cheques.iloc[0]["Monto_valor"], Decimal("10.00"))
        self.assertTrue(pd.isna(cheques.iloc[1]["Fecha_dt"]))
        self.assertEqual(depositos.iloc[0]["Descripcion"], "VENTA")
        self.assertEqual(depositos.iloc[0]["Monto_valor"], Decimal("20.00"))

    def test_cargadores_manejan_emptydataerror_y_columnas_faltantes(self):
        with patch("main.pd.read_csv", side_effect=pd.errors.EmptyDataError("vacio")):
            open(main.ARCHIVO_CHEQUES, "w", encoding="utf-8").close()
            open(main.ARCHIVO_DEPOSITOS, "w", encoding="utf-8").close()
            self.assertTrue(main.cargar_cheques_registrados().empty)
            self.assertTrue(main.cargar_depositos_registrados().empty)

        with patch("main.pd.read_csv", return_value=pd.DataFrame({"Num": ["1"]})):
            df = main.cargar_cheques_registrados()
            self.assertIn("Fecha", df.columns)
            self.assertEqual(df.iloc[0]["Estado"], "TRANSITO")

        with patch("main.pd.read_csv", return_value=pd.DataFrame({"Fecha": ["2026-06-03"]})):
            df = main.cargar_depositos_registrados()
            self.assertIn("Monto", df.columns)

    def test_cheque_ya_registrado(self):
        self.assertFalse(main.cheque_ya_registrado("1"))
        self.escribir_csv(main.ARCHIVO_CHEQUES, [["1", "2026-06-03", "A", "1", "TRANSITO"]])
        self.assertTrue(main.cheque_ya_registrado("1"))
        with patch("main.cargar_cheques_registrados", return_value=pd.DataFrame({"Otra": []})):
            self.assertFalse(main.cheque_ya_registrado("1"))

    def test_registrar_e_imprimir_flujos(self):
        with patch("builtins.input", side_effect=["10", "proveedor", "9"]), \
                patch("main.cheque_ya_registrado", return_value=True):
            _, salida = self.capturar(main.registrar_e_imprimir)
        self.assertIn("ya existe", salida)

        with patch("builtins.input", side_effect=["10", "proveedor", "9"]), \
                patch("main.cheque_ya_registrado", return_value=False), \
                patch("main.imprimir_cheque_pdf", side_effect=RuntimeError("sin impresora")):
            _, salida = self.capturar(main.registrar_e_imprimir)
        self.assertIn("No se pudo completar", salida)

        with patch("builtins.input", side_effect=["10", "proveedor", "9"]), \
                patch("main.cheque_ya_registrado", return_value=False), \
                patch("main.imprimir_cheque_pdf"), \
                patch("main.datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "2026-06-03"
            _, salida = self.capturar(main.registrar_e_imprimir)
        self.assertIn("listo para imprimir", salida)
        self.assertTrue(os.path.exists(main.ARCHIVO_CHEQUES))

    def test_anular_cheque_flujos(self):
        _, salida = self.capturar(main.anular_cheque)
        self.assertIn("No hay registro", salida)

        open(main.ARCHIVO_CHEQUES, "w", encoding="utf-8").close()
        with patch("builtins.input", return_value="1"):
            _, salida = self.capturar(main.anular_cheque)
        self.assertIn("No hay registro", salida)

        self.escribir_csv(main.ARCHIVO_CHEQUES, [["1", "2026-06-03", "A", "1", "TRANSITO"]])
        with patch("builtins.input", return_value="2"):
            _, salida = self.capturar(main.anular_cheque)
        self.assertIn("no existe", salida)

        with patch("builtins.input", return_value="1"):
            _, salida = self.capturar(main.anular_cheque)
        self.assertIn("marcado como ANULADO", salida)
        with open(main.ARCHIVO_CHEQUES, encoding="utf-8") as archivo:
            self.assertIn("ANULADO", archivo.read())

        self.escribir_csv(
            main.ARCHIVO_CHEQUES,
            [
                ["3", "2026-06-03", "A", "1", "TRANSITO"],
                ["3", "2026-06-03", "B", "2", "TRANSITO"],
            ],
        )
        with patch("builtins.input", return_value="3"):
            _, salida = self.capturar(main.anular_cheque)
        self.assertIn("aparecía 2 veces", salida)

    def test_conciliar_cuentas_flujos(self):
        _, salida = self.capturar(main.conciliar_cuentas)
        self.assertIn("Faltan archivos", salida)

        self.escribir_csv(main.ARCHIVO_CHEQUES, [["1", "2026-06-03", "A", "1", "TRANSITO"]])
        pd.DataFrame({"Otra": [1]}).to_excel(main.ARCHIVO_BANCO, index=False)
        _, salida = self.capturar(main.conciliar_cuentas)
        self.assertIn("debe incluir", salida)

        self.escribir_csv(
            main.ARCHIVO_CHEQUES,
            [
                ["", "2026-06-03", "SIN NUM", "1", "TRANSITO"],
                ["1", "2026-06-03", "OK", "100", "TRANSITO"],
                ["2", "2026-06-03", "DIF", "100", "TRANSITO"],
                ["3", "2026-06-03", "TRANSITO", "100", "TRANSITO"],
                ["4", "2026-06-03", "ANULADO NO COBRADO", "100", "ANULADO"],
                ["5", "2026-06-03", "ANULADO COBRADO", "100", "ANULADO"],
                ["6", "2026-06-03", "MALO", "bad", "TRANSITO"],
            ],
        )
        pd.DataFrame(
            {
                "Num_cheque": [1, 2, 5, 6, 99],
                "Monto": ["100.00", "90.00", "100.00", "bad", "12.00"],
            }
        ).to_excel(main.ARCHIVO_BANCO, index=False)
        _, salida = self.capturar(main.conciliar_cuentas)
        self.assertIn("cobrado perfectamente", salida)
        self.assertIn("diferencia", salida)
        self.assertIn("en TR", salida)
        self.assertIn("ANULADO y no aparece", salida)
        self.assertIn("ANULADO pero el banco", salida)
        self.assertIn("datos inválidos", salida)
        self.assertIn("NO está en nuestro sistema", salida)

        with patch("main.pd.read_excel", side_effect=RuntimeError("xls roto")):
            _, salida = self.capturar(main.conciliar_cuentas)
        self.assertIn("Ocurrió un error", salida)

        df_nuestro = pd.DataFrame(
            {
                "Num_norm": ["", "7"],
                "Estado": ["TRANSITO", "TRANSITO"],
                "Monto_valor": [Decimal("1.00"), Decimal("1.00")],
            }
        )
        df_banco = pd.DataFrame({"Num_cheque": [7], "Monto": ["1.00"]})
        with patch("main.cargar_cheques_registrados", return_value=df_nuestro), \
                patch("main.pd.read_excel", return_value=df_banco):
            _, salida = self.capturar(main.conciliar_cuentas)
        self.assertIn("Cheque 7 cobrado perfectamente", salida)

    def test_imprimir_cheque_pdf_sin_abrir_programas_reales(self):
        class PdfFalso:
            def __init__(self):
                self.textos = []

            def drawString(self, *args):
                self.textos.append(args)

            def setFont(self, *args):
                self.fuentes = getattr(self, "fuentes", [])
                self.fuentes.append(args)

            def save(self):
                self.guardado = True

        pdf = PdfFalso()
        with patch("main.canvas.Canvas", return_value=pdf), \
                patch("main.platform.system", return_value="Linux"), \
                patch("main.subprocess.run") as run:
            main.imprimir_cheque_pdf("1", "2026-06-03", "A", "1234567.89")
        run.assert_called_once_with(
            ["xdg-open", "cheque_1.pdf"],
            stdout=main.subprocess.PIPE,
            stderr=main.subprocess.PIPE,
            text=True,
            check=True,
        )
        self.assertTrue(pdf.guardado)
        self.assertIn(
            (5 * main.cm, 11.5 * main.cm, "Guatemala 3 de junio del 2026"),
            pdf.textos,
        )
        self.assertIn((16.5 * main.cm, 11.5 * main.cm, "1,234,567.89"), pdf.textos)
        self.assertIn(("Helvetica-Bold", 12), pdf.fuentes)
        self.assertIn((4.5 * main.cm, 8.5 * main.cm, "NO NEGOCIABLE"), pdf.textos)
        self.assertTrue(all(len(texto) == 3 for texto in pdf.textos))

        with patch("main.canvas.Canvas", return_value=PdfFalso()), \
                patch("main.platform.system", return_value="Darwin"), \
                patch("main.subprocess.run") as run:
            main.imprimir_cheque_pdf("2", "2026-06-03", "A", "10")
        run.assert_called_once_with(
            [
                "lp",
                "-o", "media=Custom.220x140mm",
                "-o", "scaling=100",
                "-o", "position=top-left",
                "cheque_2.pdf",
            ],
            stdout=main.subprocess.PIPE,
            stderr=main.subprocess.PIPE,
            text=True,
            check=True,
        )

        with patch("main.canvas.Canvas", return_value=PdfFalso()), \
                patch("main.platform.system", return_value="Windows"), \
                patch("main.os.startfile", create=True) as startfile:
            main.imprimir_cheque_pdf("3", "2026-06-03", "A", "10")
        startfile.assert_called_once_with("cheque_3.pdf", "print")

        with patch("main.canvas.Canvas", return_value=PdfFalso()), \
                patch("main.platform.system", return_value="Windows"), \
                patch("main.os.startfile", None, create=True):
            _, salida = self.capturar(main.imprimir_cheque_pdf, "4", "2026-06-03", "A", "10")
        self.assertIn("Abre el PDF manual", salida)

        error = main.subprocess.CalledProcessError(
            1,
            ["xdg-open", "cheque_5.pdf"],
            stderr="chrome no pudo abrir el PDF",
        )
        with patch("main.canvas.Canvas", return_value=PdfFalso()), \
                patch("main.platform.system", return_value="Linux"), \
                patch("main.subprocess.run", side_effect=error):
            _, salida = self.capturar(main.imprimir_cheque_pdf, "5", "2026-06-03", "A", "10")
        self.assertIn("Abre el PDF manual", salida)
        self.assertIn("chrome no pudo abrir el PDF", salida)

    def test_menu_clear_y_main(self):
        _, salida = self.capturar(main.clear_ide_terminal)
        self.assertGreaterEqual(salida.count("\n"), 45)

        _, salida = self.capturar(main.mostrar_menu)
        self.assertIn("SISTEMA DE CONTROL", salida)

        acciones = {
            "1": "registrar_e_imprimir",
            "2": "registrar_deposito",
            "3": "conciliar_cuentas",
            "4": "anular_cheque",
            "5": "reporte_movimientos",
            "6": "reimprimir_cheque",
        }
        for opcion, funcion in acciones.items():
            with patch("builtins.input", return_value=opcion), \
                    patch(f"main.{funcion}", side_effect=SystemExit), \
                    self.assertRaises(SystemExit):
                main.main()

        with patch("builtins.input", side_effect=["x", "7"]), self.assertRaises(SystemExit):
            main.main()


if __name__ == "__main__":
    unittest.main()
