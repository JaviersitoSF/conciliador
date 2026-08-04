import re
from decimal import Decimal
from unittest.mock import patch

from conciliador import printing


def _resultado_base():
    cheques = [{
        "num": "101",
        "fecha": "2026-06-03",
        "nombre": "Proveedor & Compañía",
        "monto_nuestro": Decimal("100.11"),
        "mensaje": "Pendiente <por confirmar>",
    }]
    depositos_transito = [{"monto": Decimal("20.06")}]
    creditos_banco = [{"monto": Decimal("50.07")}]
    notas_credito = [{"monto": Decimal("5.02")}]
    notas_debito_transito = [{"monto": Decimal("2.03")}]
    debitos_banco = [{"monto": Decimal("7.04")}]
    cheques_banco_sin_registro = [{
        "num": "202",
        "fecha": "2026-06-08",
        "descripcion": "Cheque bancario",
        "monto": Decimal("9.05"),
        "diferencia": "Cobrado sin registro local",
    }]
    return {
        "cuenta": {
            "id": 1,
            "banco": "Banco",
            "nombre": "Cuenta corriente",
            "numero": "123",
        },
        "fecha_corte": "2026-06-30",
        "estado_cuenta": {
            "numero": "123",
            "fecha_fin": "2026-06-30",
            "moneda": "GTQ",
            "saldo_final": Decimal("1000.37"),
        },
        "cheques_transito": cheques,
        "cheques_banco_sin_registro": cheques_banco_sin_registro,
        "filas_invalidas": [{
            "num": "Fila 10",
            "fecha": "fecha mala",
            "descripcion": "Movimiento inválido",
            "monto": None,
            "diferencia": "Fecha inválida",
        }],
        "depositos_no_ingresados": depositos_transito,
        "depositos_banco_sin_registro": creditos_banco,
        "notas_credito_banco": notas_credito,
        "notas_debito_locales_sin_banco": notas_debito_transito,
        "notas_debito_no_ingresadas": debitos_banco,
        # Las listas combinadas contienen las mismas filas. Su presencia prueba
        # que la impresión no duplica categorías que ya vienen separadas.
        "diferencias_depositos": depositos_transito + creditos_banco,
        "diferencias_notas_debito": notas_debito_transito + debitos_banco,
    }


def _paginas_y_tamanos(contenido):
    paginas = len(re.findall(rb"/Type\s*/Page\b", contenido))
    tamanos = [
        (float(ancho), float(alto))
        for ancho, alto in re.findall(
            rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]",
            contenido,
        )
    ]
    return paginas, tamanos


def test_resumen_cuadra_saldo_final_con_ajustes_disjuntos_y_centavos():
    resumen = printing.calcular_resumen_conciliacion(_resultado_base())

    assert resumen == {
        "saldo_libros": Decimal("879.29"),
        "saldo_libros_calculado": True,
        "cheques_transito": Decimal("100.11"),
        "cheques_banco_sin_registro": Decimal("9.05"),
        "notas_debito_transito": Decimal("2.03"),
        "creditos_banco": Decimal("50.07"),
        "notas_credito_banco": Decimal("5.02"),
        "debitos_banco": Decimal("7.04"),
        "depositos_transito": Decimal("20.06"),
        "saldo_conciliado": Decimal("1000.37"),
        "saldo_banco": Decimal("1000.37"),
        "diferencia": Decimal("0.00"),
    }


def test_pdf_agrega_resumen_y_detalle_en_paginas_verticales(tmp_path):
    destino = tmp_path / "conciliacion.pdf"

    with patch("conciliador.printing.abrir_pdf"), patch(
        "conciliador.printing._tabla_pdf", wraps=printing._tabla_pdf
    ) as crear_tabla:
        printing.exportar_conciliacion_pdf(_resultado_base(), destino)

    paginas, tamanos = _paginas_y_tamanos(destino.read_bytes())
    assert paginas == 2
    assert tamanos == [(612.0, 792.0), (612.0, 792.0)]
    tabla_cheques = crear_tabla.call_args_list[0].args[0]
    assert tabla_cheques[-1][0].getPlainText() == "TOTAL CHEQUES EN CIRCULACIÓN"
    assert tabla_cheques[-1][-1].getPlainText() == "Q 100.11"


def test_pdf_sin_saldo_bancario_degrada_a_no_disponible(tmp_path):
    resultado = _resultado_base()
    resultado["estado_cuenta"].pop("saldo_final")
    destino = tmp_path / "sin-saldo.pdf"

    resumen = printing.calcular_resumen_conciliacion(resultado)
    with patch("conciliador.printing.abrir_pdf"):
        printing.exportar_conciliacion_pdf(resultado, destino)

    assert resumen["saldo_libros"] is None
    assert resumen["saldo_conciliado"] is None
    assert resumen["saldo_banco"] is None
    assert resumen["diferencia"] is None
    assert destino.read_bytes().startswith(b"%PDF")


def test_pdf_incrusta_fuentes_truetype_con_metricas(tmp_path):
    destino = tmp_path / "fuentes-incrustadas.pdf"

    with patch("conciliador.printing.abrir_pdf"):
        printing.exportar_conciliacion_pdf(_resultado_base(), destino)

    contenido = destino.read_bytes()
    assert b"/FontDescriptor" in contenido
    assert b"/FontFile2" in contenido
    assert b"/Widths" in contenido
    assert b"/FirstChar" in contenido
    assert b"/LastChar" in contenido
    assert b"/ToUnicode" in contenido


def test_detalle_extenso_pagina_sin_cambiar_orientacion(tmp_path):
    resultado = _resultado_base()
    resultado["cheques_transito"] = [
        {
            "num": str(numero),
            "fecha": "2026-06-03",
            "nombre": f"Beneficiario {numero}",
            "monto_nuestro": Decimal("1.01"),
            "mensaje": "Pendiente en compensación bancaria",
        }
        for numero in range(1, 91)
    ]
    destino = tmp_path / "conciliacion-extensa.pdf"

    with patch("conciliador.printing.abrir_pdf"):
        printing.exportar_conciliacion_pdf(resultado, destino)

    paginas, tamanos = _paginas_y_tamanos(destino.read_bytes())
    assert paginas > 2
    assert len(tamanos) == paginas
    assert all(ancho < alto for ancho, alto in tamanos)
