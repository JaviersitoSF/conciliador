from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from conciliador import analytics, operations as main


def _locales(*movimientos):
    filas = [
        {
            "Num": numero,
            "Fecha": fecha,
            "Descripcion": "MOVIMIENTO LOCAL",
            "Monto_valor": Decimal(monto),
            "Estado": estado,
        }
        for numero, fecha, monto, estado in movimientos
    ]
    locales = pd.DataFrame(filas)
    locales["Fecha_dt"] = pd.to_datetime(locales["Fecha"], errors="coerce")
    return locales


def _bancario(numero, fecha, monto):
    return {
        "Num_cheque": numero,
        "fecha": fecha,
        "descripcion": "MOVIMIENTO BANCARIO",
        "Monto": Decimal(monto),
    }


def _separar(locales, bancarios):
    return analytics._separar_movimientos_no_ingresados(
        locales, bancarios, fecha_inicio=None, fecha_corte=None
    )


@pytest.mark.parametrize(
    ("fecha_banco", "coincide"),
    [
        ("24-05-2026", False),
        ("25-05-2026", True),
        ("08-06-2026", True),
        ("09-06-2026", False),
    ],
)
def test_match_por_monto_usa_ventana_inclusiva_de_mas_menos_siete_dias(
    fecha_banco, coincide
):
    locales = _locales(("100", "2026-06-01", "25.00", "REGISTRADO"))
    bancarios = [_bancario("900", fecha_banco, "25.00")]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert bool(locales_sin_banco) is not coincide
    assert bool(banco_sin_local) is not coincide


def test_match_temporal_requiere_un_solo_candidato_bancario():
    locales = _locales(("100", "2026-06-10", "25.00", "REGISTRADO"))
    bancarios = [
        _bancario("900", "05-06-2026", "25.00"),
        _bancario("901", "17-06-2026", "25.00"),
    ]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert [fila["num"] for fila in locales_sin_banco] == ["100"]
    assert [fila["Num_cheque"] for fila in banco_sin_local] == ["900", "901"]


def test_match_temporal_no_asigna_un_bancario_disputado_por_dos_locales():
    locales = _locales(
        ("100", "2026-06-10", "25.00", "REGISTRADO"),
        ("101", "2026-06-11", "25.00", "REGISTRADO"),
    )
    bancarios = [_bancario("900", "10-06-2026", "25.00")]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert [fila["num"] for fila in locales_sin_banco] == ["100", "101"]
    assert [fila["Num_cheque"] for fila in banco_sin_local] == ["900"]


def test_match_exacto_tiene_prioridad_y_no_reutiliza_el_bancario():
    locales = _locales(
        ("100", "2026-06-01", "25.00", "REGISTRADO"),
        ("900", "2026-06-30", "25.00", "REGISTRADO"),
    )
    bancarios = [_bancario("900", "05-06-2026", "25.00")]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert [fila["num"] for fila in locales_sin_banco] == ["100"]
    assert banco_sin_local == []


def test_match_exacto_por_numero_y_monto_no_depende_de_la_ventana():
    locales = _locales(("900", "2026-06-01", "25.00", "REGISTRADO"))
    bancarios = [_bancario("900", "30-06-2026", "25.00")]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert locales_sin_banco == []
    assert banco_sin_local == []


def test_movimientos_anulados_no_participan_en_el_match_temporal():
    locales = _locales(
        ("100", "2026-06-10", "25.00", "ANULADO"),
        ("101", "2026-06-10", "25.00", "REGISTRADO"),
    )
    bancarios = [_bancario("900", "12-06-2026", "25.00")]

    locales_sin_banco, banco_sin_local = _separar(locales, bancarios)

    assert locales_sin_banco == []
    assert banco_sin_local == []


def _crear_estado_bi(ruta):
    contenido = "\r\n".join(
        [
            "Tipo de Transacciones,",
            "Cuenta: 0480003228 - BENISA S A",
            "Saldo inicial (GTQ): 1000.00",
            "Del 01/06/2026 al 30/06/2026",
            "",
            "Fecha,TT,Descripción,No. Doc,Debe (GTQ),Haber (GTQ),Saldo (GTQ)",
            "08-06-2026,DE,DEPÓSITO BANCO,900,,50.00,1050.00",
            "13-06-2026,ND,NOTA BANCO,901,20.00,,1030.00",
            "07-06-2026,CQ,CHEQUE CON OTRO NÚMERO,999,100.00,,930.00",
            "",
        ]
    )
    Path(ruta).write_bytes(contenido.encode("latin-1"))


def test_conciliacion_aplica_ventana_a_depositos_y_notas_pero_no_a_cheques(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    cuenta_id = main.crear_cuenta_bancaria(
        "BANCO INDUSTRIAL", "Monetaria", "0480003228"
    )
    main.registrar_deposito_datos(
        "50", "Depósito local", "2026-06-01", cuenta_id, "100"
    )
    main.registrar_nota_debito_datos(
        "20", "Nota local", "2026-06-20", cuenta_id, "101"
    )
    main.guardar_cheque_en_archivo(
        "1", "2026-06-01", "Cheque local", "100", cuenta_id=cuenta_id
    )
    estado = tmp_path / "estado.csv"
    _crear_estado_bi(estado)

    resultado = main.obtener_conciliacion(cuenta_id, estado, "2026-06-30")

    assert resultado["diferencias_depositos"] == []
    assert resultado["diferencias_notas_debito"] == []
    assert resultado["cheques"][0]["resultado"] == "TRANSITO"
    assert resultado["no_registrados"][0]["num"] == "999"
