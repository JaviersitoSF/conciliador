import subprocess
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest

import main


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_conciliacion_reporta_archivo_faltante_y_columnas_invalidas():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")

    with pytest.raises(main.ErrorOperacion, match="Faltan archivos"):
        main.obtener_conciliacion()

    pd.DataFrame({"Otra": [1]}).to_excel(main.ARCHIVO_BANCO, index=False)
    with pytest.raises(main.ErrorOperacion, match="Num_cheque.*Monto"):
        main.obtener_conciliacion()


def test_conciliacion_envuelve_errores_de_lectura():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")
    open(main.ARCHIVO_BANCO, "wb").close()

    with patch("main.pd.read_excel", side_effect=RuntimeError("archivo roto")), \
            pytest.raises(main.ErrorOperacion, match="archivo roto"):
        main.obtener_conciliacion()


def test_conciliacion_distingue_anulado_no_cobrado_y_monto_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "ANULADO", "10")
    main.anular_cheque_numero("1")
    main.guardar_cheque_en_archivo("2", "2026-06-01", "INVALIDO", "20")
    pd.DataFrame(
        {" Num_cheque ": [2], " MONTO ": ["monto malo"]}
    ).to_excel(main.ARCHIVO_BANCO, index=False)

    resultado = main.obtener_conciliacion()
    estados = {fila["num"]: fila["resultado"] for fila in resultado["cheques"]}

    assert estados == {"1": "ANULADO", "2": "INVALIDO"}


def test_conciliacion_no_suma_parcialmente_duplicados_con_monto_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "100")
    pd.DataFrame(
        {"Num_cheque": [1, 1], "Monto": ["100.00", "malo"]}
    ).to_excel(main.ARCHIVO_BANCO, index=False)

    resultado = main.obtener_conciliacion()["cheques"][0]

    assert resultado["resultado"] == "DUPLICADO_INVALIDO"
    assert resultado["monto_banco"] is None
    assert "monto" in resultado["mensaje"].lower()


def test_conciliacion_no_descarta_filas_con_numero_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "100")
    pd.DataFrame(
        {
            "Num_cheque": [1, "ABC", None],
            "Monto": ["100.00", "12.00", "8.00"],
        }
    ).to_excel(main.ARCHIVO_BANCO, index=False)

    resultado = main.obtener_conciliacion()
    invalidos = [
        fila
        for fila in resultado["no_registrados"]
        if fila.get("resultado") == "INVALIDO"
    ]

    assert [fila["num"] for fila in invalidos] == ["ABC", "N/D"]
    assert all("inválido" in fila["mensaje"].lower() for fila in invalidos)


def test_validadores_de_consola_reintentan_hasta_recibir_datos_validos():
    with patch("builtins.input", side_effect=["", " listo "]):
        assert main.pedir_texto_no_vacio("x") == "listo"

    with patch("builtins.input", side_effect=["abc", "0", "15.25"]):
        assert str(main.pedir_monto_positivo("x")) == "15.25"

    with patch("builtins.input", side_effect=["", "abc", "0", "42"]):
        assert main.pedir_numero_cheque("x") == "42"


def test_abrir_pdf_propaga_detalle_del_comando():
    error = subprocess.CalledProcessError(
        1, ["lp", "cheque.pdf"], stderr="impresora no disponible"
    )
    with patch("main.subprocess.run", side_effect=error), \
            pytest.raises(RuntimeError, match="impresora no disponible"):
        main.abrir_pdf_silenciosamente(["lp", "cheque.pdf"])


def test_imprimir_pdf_cubre_linux_macos_windows_y_falla_de_apertura():
    class PdfFalso:
        def __init__(self):
            self.textos = []
            self.fuentes = []
            self.traslados = []
            self.guardado = False

        def drawString(self, *args):
            self.textos.append(args)

        def setFont(self, *args):
            self.fuentes.append(args)

        def translate(self, *args):
            self.traslados.append(args)

        def save(self):
            self.guardado = True

    pdf = PdfFalso()
    with patch("main.canvas.Canvas", return_value=pdf), \
            patch("main.platform.system", return_value="Linux"), \
            patch("main.subprocess.run") as ejecutar:
        main.imprimir_cheque_pdf("1", "2026-06-03", "A", "1234567.89")
    assert pdf.guardado
    assert (14.5 * main.cm, 13 * main.cm, "1,234,567.89") in pdf.textos
    ejecutar.assert_called_once()

    with patch("main.canvas.Canvas", return_value=PdfFalso()), \
            patch("main.platform.system", return_value="Darwin"), \
            patch("main.subprocess.run") as ejecutar:
        main.imprimir_cheque_pdf("2", "2026-06-03", "A", "10")
    assert ejecutar.call_args.args[0][0] == "lp"

    pdf_windows = PdfFalso()
    with patch("main.canvas.Canvas", return_value=pdf_windows) as crear_pdf, \
            patch("main.platform.system", return_value="Windows"), \
            patch("main.os.startfile", create=True) as startfile:
        main.imprimir_cheque_pdf("3", "2026-06-03", "A", "10")
    crear_pdf.assert_called_once_with("cheque_3.pdf", pagesize=main.LETTER)
    assert pdf_windows.traslados == [(0, main.LETTER[1] - 14 * main.cm)]
    startfile.assert_called_once_with("cheque_3.pdf", "print")

    salida = StringIO()
    with patch("main.canvas.Canvas", return_value=PdfFalso()), \
            patch("main.platform.system", return_value="Windows"), \
            patch("main.os.startfile", None, create=True), \
            redirect_stdout(salida):
        resultado = main.imprimir_cheque_pdf("4", "2026-06-03", "A", "10")
    assert "Abre el PDF manual" in salida.getvalue()
    assert resultado is False


def test_menu_despacha_todas_las_opciones_y_sale():
    acciones = {
        "1": "registrar_e_imprimir",
        "2": "registrar_deposito",
        "3": "conciliar_cuentas",
        "4": "anular_cheque",
        "5": "reporte_movimientos",
        "6": "reimprimir_cheque",
        "7": "registrar_cuenta_bancaria",
    }
    for opcion, funcion in acciones.items():
        with patch("builtins.input", return_value=opcion), \
                patch(f"main.{funcion}", side_effect=SystemExit), \
                pytest.raises(SystemExit):
            main.main()

    with patch("builtins.input", side_effect=["x", "8"]), \
            pytest.raises(SystemExit):
        main.main()
