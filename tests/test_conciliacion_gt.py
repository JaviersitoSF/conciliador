from decimal import Decimal

import pandas as pd
import pytest

from conciliador import analytics, operations as main


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_lector_gt_clasifica_cheques_depositos_y_notas(monkeypatch):
    tabla = pd.DataFrame(
        [
            ["ESTADO DE CUENTA POR RANGO DE FECHAS - MONETARIO (QTZ)"],
            ["#Cuenta", None, "08050003210", None, "Nombre de la Cuenta", "BENISA, S.A."],
            ["Fecha Inicial", None, "01/06/2026", None, "Fecha Final", "30/06/2026"],
            ["#", "Fecha", "Referencia", "Descripción", "Débito", "Crédito", "Saldo", "Agencia"],
            [1, "02/06/2026", 93808165, "PAGO DE CHEQUE", -4919.06, None, 100, "AGENCIA"],
            [2, "03/06/2026", 1234, "DEPOSITO EN EFECTIVO", None, 25, 125, "AGENCIA"],
            [3, "04/06/2026", 99, "NOTA DEBITO POR ISR", -0.28, None, 124.72, "AGENCIA"],
            [4, "05/06/2026", 100, "FILA INVÁLIDA", "malo", None, 124.72, "AGENCIA"],
            ["No Débitos:", None, 2, None, "Total Débitos:", 4919.34, None, None],
        ]
    )
    monkeypatch.setattr(analytics.pd, "read_excel", lambda *args, **kwargs: tabla)

    estado = analytics._leer_xls_gt_continental("estado.xls")

    assert estado["cuenta_numero"] == "08050003210"
    assert estado["fecha_inicio"] == "2026-06-01"
    assert estado["fecha_fin"] == "2026-06-30"
    assert estado["saldo_inicial"] is None
    assert estado["saldo_final"] == Decimal("124.72")
    assert estado["cheques"].iloc[0]["Num_cheque"] == "93808165"
    assert estado["cheques"].iloc[0]["Monto"] == Decimal("4919.06")
    assert estado["depositos"][0]["Monto"] == Decimal("25.00")
    assert estado["notas_debito"][0]["Monto"] == Decimal("0.28")
    assert estado["filas_invalidas"] == [
        {
            "fila": 8,
            "fecha": "05/06/2026",
            "tipo": "",
            "numero": "100",
            "descripcion": "FILA INVÁLIDA",
            "monto": None,
            "detalle": "Monto inválido o igual a cero",
        }
    ]


def test_cuenta_acepta_formato_gt_continental():
    cuenta_id = main.crear_cuenta_bancaria(
        "G&T", "Monetaria", "08050003210", "G&T Continental"
    )

    assert main.obtener_cuenta(cuenta_id)["formato_conciliacion"] == "G&T Continental"
