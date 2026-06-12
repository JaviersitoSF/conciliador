import subprocess
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pandas as pd
import pytest

from conciliador import operations as main


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

    with patch("conciliador.analytics.pd.read_excel", side_effect=RuntimeError("archivo roto")), \
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


def test_conciliacion_incluye_pendientes_anteriores_y_excluye_cheques_futuros():
    main.guardar_cheque_en_archivo("1", "2026-05-20", "ANTERIOR", "100")
    main.guardar_cheque_en_archivo("2", "2026-06-15", "DEL MES", "200")
    main.guardar_cheque_en_archivo("3", "2026-07-01", "FUTURO", "300")
    pd.DataFrame(
        {"Num_cheque": [1, 2], "Monto": ["100", "200"]}
    ).to_excel(main.ARCHIVO_BANCO, index=False)

    resultado = main.obtener_conciliacion(
        archivo_banco=main.ARCHIVO_BANCO,
        fecha_corte="2026-06-30",
    )

    assert [fila["num"] for fila in resultado["cheques"]] == ["1", "2"]
    assert resultado["fecha_corte"] == "2026-06-30"


def test_abrir_pdf_propaga_detalle_del_comando():
    error = subprocess.CalledProcessError(
        1, ["lp", "cheque.pdf"], stderr="impresora no disponible"
    )
    with patch("conciliador.printing.subprocess.run", side_effect=error), \
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
    with patch("conciliador.printing.canvas.Canvas", return_value=pdf), \
            patch("conciliador.printing.platform.system", return_value="Linux"), \
            patch("conciliador.printing.subprocess.run") as ejecutar:
        main.imprimir_cheque_pdf("1", "2026-06-03", "A", "1234567.89")
    assert pdf.guardado
    from conciliador.printing import cm
    assert (15 * cm, 13 * cm, "1,234,567.89") in pdf.textos
    ejecutar.assert_called_once()

    with patch("conciliador.printing.canvas.Canvas", return_value=PdfFalso()), \
            patch("conciliador.printing.platform.system", return_value="Darwin"), \
            patch("conciliador.printing.subprocess.run") as ejecutar:
        main.imprimir_cheque_pdf("2", "2026-06-03", "A", "10")
    assert ejecutar.call_args.args[0][0] == "lp"

    pdf_windows = PdfFalso()
    with patch("conciliador.printing.canvas.Canvas", return_value=pdf_windows) as crear_pdf, \
            patch("conciliador.printing.platform.system", return_value="Windows"), \
            patch("conciliador.printing.os.startfile", create=True) as startfile:
        main.imprimir_cheque_pdf("3", "2026-06-03", "A", "10")
    crear_pdf.assert_called_once_with(
        "cheque_3.pdf", pagesize=(22 * cm, 14 * cm)
    )
    assert pdf_windows.traslados == []
    startfile.assert_called_once_with("cheque_3.pdf", "print")

    salida = StringIO()
    with patch("conciliador.printing.canvas.Canvas", return_value=PdfFalso()), \
            patch("conciliador.printing.platform.system", return_value="Windows"), \
            patch("conciliador.printing.os.startfile", None, create=True), \
            redirect_stdout(salida):
        resultado = main.imprimir_cheque_pdf("4", "2026-06-03", "A", "10")
    assert "Abre el PDF manual" in salida.getvalue()
    assert resultado is False
