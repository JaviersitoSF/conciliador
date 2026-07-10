import subprocess
from decimal import Decimal
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from conciliador import operations as main
from conciliador import printing


def test_exportar_conciliacion_pdf_excluye_cheques_cobrados_y_abre_archivo(tmp_path):
    resultado = {
        "cuenta": {"id": 4, "banco": "Banco", "nombre": "Cuenta", "numero": "123"},
        "fecha_corte": "2026-06-30",
        "estado_cuenta": {"numero": "123", "fecha_fin": "2026-06-30", "moneda": "GTQ"},
        "cheques_cobrados": [{"num": "99", "monto_nuestro": Decimal("99.00")}],
        "cheques_transito": [
            {"num": "10", "monto_nuestro": Decimal("25.50"), "mensaje": "Pendiente"}
        ],
        "diferencias_depositos": [],
        "diferencias_notas_debito": [],
    }
    destino = tmp_path / "conciliacion.pdf"

    with patch("conciliador.printing.abrir_pdf") as abrir:
        ruta = printing.exportar_conciliacion_pdf(resultado, destino)

    assert ruta == destino
    assert destino.read_bytes().startswith(b"%PDF")
    abrir.assert_called_once_with(destino)
    contenido = destino.read_bytes()
    assert b"99.00" not in contenido


def crear_estado_bi(ruta, cuenta="0480003228", fin="30/06/2026", filas=None):
    if filas is None:
        filas = [
            "01-06-2026,CQ,PRIMERA COMPENSACIÓN,46941,430.10,,1000.00",
            "02-06-2026,ND,TRANSFERENCIA T.I./BI-ENLINEA,23898,25.50,,974.50",
            "03-06-2026,DE,AGENCIA EUROPLAZA,16504742,,100.00,1074.50",
        ]
    contenido = "\r\n".join(
        [
            "Tipo de Transacciones,",
            "Cuenta: %s - BENISA S A" % cuenta,
            "Saldo inicial (GTQ): 1430.10",
            "Del 01/06/2026 al %s" % fin,
            "",
            "Fecha,TT,Descripción,No. Doc,Debe (GTQ),Haber (GTQ),Saldo (GTQ)",
            *filas,
            "",
        ]
    )
    Path(ruta).write_bytes(contenido.encode("latin-1"))


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_conciliacion_reporta_archivo_faltante_y_columnas_invalidas():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")

    with pytest.raises(main.ErrorOperacion, match="Selecciona el estado"):
        main.obtener_conciliacion()

    Path("invalido.csv").write_text("Otra,Cabecera\n1,2\n", encoding="utf-8")
    with pytest.raises(main.ErrorOperacion, match="cabecera de movimientos"):
        main.obtener_conciliacion(archivo_banco="invalido.csv")


def test_conciliacion_envuelve_errores_de_lectura():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")
    Path("estado.xlsx").write_bytes(b"")

    with pytest.raises(main.ErrorOperacion, match="no es compatible"):
        main.obtener_conciliacion(archivo_banco="estado.xlsx")


def test_conciliacion_distingue_anulado_no_cobrado_y_monto_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "ANULADO", "10")
    main.anular_cheque_numero("1")
    main.guardar_cheque_en_archivo("2", "2026-06-01", "INVALIDO", "20")
    crear_estado_bi(
        "estado.csv",
        filas=["01-06-2026,CQ,COMPENSACIÓN,2,monto malo,,100.00"],
    )

    resultado = main.obtener_conciliacion(archivo_banco="estado.csv")
    estados = {fila["num"]: fila["resultado"] for fila in resultado["cheques"]}

    assert estados == {"1": "ANULADO", "2": "INVALIDO"}


def test_conciliacion_no_suma_parcialmente_duplicados_con_monto_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "100")
    crear_estado_bi(
        "estado.csv",
        filas=[
            "01-06-2026,CQ,COMPENSACIÓN,1,100.00,,100.00",
            "02-06-2026,CQ,COMPENSACIÓN,1,malo,,100.00",
        ],
    )

    resultado = main.obtener_conciliacion(archivo_banco="estado.csv")["cheques"][0]

    assert resultado["resultado"] == "DUPLICADO_INVALIDO"
    assert resultado["monto_banco"] is None
    assert "monto" in resultado["mensaje"].lower()


def test_conciliacion_no_descarta_filas_con_numero_invalido():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "100")
    crear_estado_bi(
        "estado.csv",
        filas=[
            "01-06-2026,CQ,COMPENSACIÓN,1,100.00,,100.00",
            "02-06-2026,CQ,COMPENSACIÓN,ABC,12.00,,88.00",
            "03-06-2026,CQ,COMPENSACIÓN,,8.00,,80.00",
        ],
    )

    resultado = main.obtener_conciliacion(archivo_banco="estado.csv")
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
    crear_estado_bi(
        "estado.csv",
        filas=[
            "01-06-2026,CQ,COMPENSACIÓN,1,100,,300.00",
            "15-06-2026,CQ,COMPENSACIÓN,2,200,,100.00",
        ],
    )

    resultado = main.obtener_conciliacion(
        archivo_banco="estado.csv",
        fecha_corte="2026-06-30",
    )

    assert [fila["num"] for fila in resultado["cheques"]] == ["1", "2"]
    assert resultado["fecha_corte"] == "2026-06-30"


def test_conciliacion_lee_csv_banco_industrial_y_separa_otros_cargos():
    cuenta_id = main.crear_cuenta_bancaria(
        "BANCO INDUSTRIAL", "Monetaria", "048-000322-8"
    )
    main.guardar_cheque_en_archivo(
        "46941", "2026-06-01", "Proveedor", "430.10", cuenta_id=cuenta_id
    )
    crear_estado_bi("estado-bi.csv")

    resultado = main.obtener_conciliacion(
        cuenta_id, "estado-bi.csv", "2026-06-30"
    )

    assert resultado["cheques"][0]["resultado"] == "COBRADO"
    assert resultado["estado_cuenta"] == {
        "numero": "0480003228",
        "nombre": "BENISA S A",
        "fecha_inicio": "2026-06-01",
        "fecha_fin": "2026-06-30",
        "moneda": "GTQ",
    }
    assert [fila["resultado"] for fila in resultado["no_registrados"]] == [
        "CARGO_BANCO"
    ]
    assert resultado["no_registrados"][0]["num"] == "23898"


def test_conciliacion_bi_rechaza_cuenta_y_periodo_incorrectos():
    cuenta_id = main.crear_cuenta_bancaria(
        "BANCO INDUSTRIAL", "Monetaria", "0480003228"
    )
    main.guardar_cheque_en_archivo(
        "46941", "2026-06-01", "Proveedor", "430.10", cuenta_id=cuenta_id
    )
    crear_estado_bi("otra-cuenta.csv", cuenta="2070036814")
    with pytest.raises(main.ErrorOperacion, match="pertenece a la cuenta"):
        main.obtener_conciliacion(cuenta_id, "otra-cuenta.csv", "2026-06-30")

    crear_estado_bi("otro-periodo.csv", fin="31/07/2026")
    with pytest.raises(main.ErrorOperacion, match="estado termina"):
        main.obtener_conciliacion(cuenta_id, "otro-periodo.csv", "2026-06-30")


def test_conciliacion_bi_funciona_sin_cheques_locales_ni_bancarios():
    cuenta_id = main.crear_cuenta_bancaria(
        "BANCO INDUSTRIAL", "Ahorro", "0000625485"
    )
    crear_estado_bi(
        "ahorro.csv",
        cuenta="0000625485",
        filas=[
            "23-06-2026,ND,BANCA ELECTRÓNICA,200758,40000.00,,80449.99",
            "30-06-2026,CA,PAGO DE INTERESES,2622370,,0.96,80450.95",
        ],
    )

    resultado = main.obtener_conciliacion(
        cuenta_id, "ahorro.csv", "2026-06-30"
    )

    assert resultado["cheques"] == []
    assert len(resultado["no_registrados"]) == 1
    assert resultado["no_registrados"][0]["resultado"] == "CARGO_BANCO"


def test_conciliacion_presenta_las_cuatro_categorias_contables():
    cuenta_id = main.crear_cuenta_bancaria(
        "BANCO INDUSTRIAL", "Monetaria", "0480003228"
    )
    main.guardar_cheque_en_archivo("1", "2026-06-01", "Cobrado", "100", cuenta_id=cuenta_id)
    main.guardar_cheque_en_archivo("2", "2026-06-02", "Pendiente", "50", cuenta_id=cuenta_id)
    main.registrar_deposito_datos("25", "Pendiente banco", fecha="2026-06-03", numero="D-1", cuenta_id=cuenta_id)
    main.registrar_deposito_datos("40", "Ya acreditado", fecha="2026-06-04", numero="D-2", cuenta_id=cuenta_id)
    main.registrar_nota_debito_datos("10", "Ya registrada", fecha="2026-06-05", numero="N-1", cuenta_id=cuenta_id)
    main.registrar_nota_debito_datos("7", "No aparece banco", fecha="2026-06-07", numero="N-3", cuenta_id=cuenta_id)
    crear_estado_bi(
        "estado.csv",
        filas=[
            "01-06-2026,CQ,COMPENSACIÓN,1,100.00,,100.00",
            "04-06-2026,DE,DEPÓSITO,D-2,,40.00,140.00",
            "04-06-2026,DE,DEPÓSITO SIN REGISTRO,D-3,,12.00,152.00",
            "05-06-2026,ND,CARGO,N-1,10.00,,130.00",
            "06-06-2026,ND,COMISIÓN,N-2,5.00,,125.00",
        ],
    )

    resultado = main.obtener_conciliacion(cuenta_id, "estado.csv", "2026-06-30")

    assert [fila["num"] for fila in resultado["cheques_cobrados"]] == ["1"]
    assert [fila["num"] for fila in resultado["cheques_transito"]] == ["2"]
    assert [fila["num"] for fila in resultado["depositos_no_ingresados"]] == ["D-1"]
    assert [fila["num"] for fila in resultado["notas_debito_no_ingresadas"]] == ["N-2"]
    assert [fila["num"] for fila in resultado["depositos_banco_sin_registro"]] == ["D-3"]
    assert [fila["num"] for fila in resultado["notas_debito_locales_sin_banco"]] == ["N-3"]
    assert [fila["diferencia"] for fila in resultado["diferencias_depositos"]] == [
        "Pendiente en banco",
        "No registrado localmente",
    ]
    assert [fila["diferencia"] for fila in resultado["diferencias_notas_debito"]] == [
        "No aparece en el banco",
        "No registrada localmente",
    ]
    assert resultado["resumen"]["depositos_no_ingresados"] == {
        "cantidad": 1,
        "total": main.convertir_monto("25"),
    }


def test_lector_bi_tolera_comas_sin_comillas_en_descripcion():
    crear_estado_bi(
        "estado.csv",
        filas=[
            "30-06-2026,NC,ACH BENISA, S.A. A,297472,,30000.00,88657.09"
        ],
    )

    resultado = main.obtener_conciliacion(archivo_banco="estado.csv")

    assert resultado["cheques"] == []
    assert resultado["no_registrados"] == []


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
        "cheque_3.pdf", pagesize=printing.LETTER
    )
    assert pdf_windows.traslados == [(0, printing.LETTER[1] - 14 * cm)]
    startfile.assert_called_once_with("cheque_3.pdf", "print")

    salida = StringIO()
    with patch("conciliador.printing.canvas.Canvas", return_value=PdfFalso()), \
            patch("conciliador.printing.platform.system", return_value="Windows"), \
            patch("conciliador.printing.os.startfile", None, create=True), \
            redirect_stdout(salida):
        resultado = main.imprimir_cheque_pdf("4", "2026-06-03", "A", "10")
    assert "Abre el PDF manual" in salida.getvalue()
    assert resultado is False
