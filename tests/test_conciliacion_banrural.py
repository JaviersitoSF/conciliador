from decimal import Decimal
from pathlib import Path

import pytest

from conciliador import analytics, operations as main
from conciliador.errors import ErrorOperacion
from conciliador.printing import calcular_resumen_conciliacion


def crear_estado_banrural(ruta):
    contenido = "\n".join([
        "Movimientos de la Cuenta",
        "Del 01/06/2026 al 30/06/2026",
        "Cuenta: XXXXXX6768-Monetario-BENISA-GTQ",
        "",
        "Fecha,Oficina,Descripción,Referencia,Secuencial,Cheque Propio / Local / Efectivo,Débito (-),Crédito (+),Saldo Contable,Saldo Disponible",
        "04/06/2026,948,PAGO CHEQUE,1912759098,1,1234,2550.0,0,100,100",
        "05/06/2026,669,DEPOSITO COMPLETO,49518610,2,EFECTIVO,0,361.0,461,461",
        "12/06/2026,9755,N/DEBITO TRANSFERENCIA,55086606,3,,7600.0,0,-7139,-7139",
        "13/06/2026,9755,FILA INVALIDA,55086607,4,,malo,0,-7139,-7139",
        "Confidencial",
    ])
    Path(ruta).write_bytes(contenido.encode("latin-1"))


def test_lector_banrural_clasifica_movimientos_y_metadatos(tmp_path):
    archivo = tmp_path / "banrural.csv"
    crear_estado_banrural(archivo)

    estado = analytics._leer_csv_banrural(archivo)

    assert estado["cuenta_numero"] == "XXXXXX6768"
    assert estado["cuenta_nombre"] == "BENISA"
    assert estado["fecha_inicio"] == "2026-06-01"
    assert estado["fecha_fin"] == "2026-06-30"
    assert estado["moneda"] == "GTQ"
    assert estado["saldo_inicial"] == Decimal("2650.00")
    assert estado["saldo_final"] == Decimal("-7139.00")
    assert estado["cheques"].iloc[0]["Num_cheque"] == "1234"
    assert estado["cheques"].iloc[0]["Monto"] == Decimal("2550.00")
    assert estado["depositos"][0]["Num_cheque"] == "49518610"
    assert estado["notas_debito"][0]["Num_cheque"] == "55086606"
    assert estado["filas_invalidas"][0]["numero"] == "55086607"
    assert estado["filas_invalidas"][0]["detalle"] == (
        "Monto inválido o igual a cero"
    )


def test_cuenta_acepta_formato_banrural_y_numero_enmascarado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cuenta_id = main.crear_cuenta_bancaria(
        "BANRURAL", "Rural", "3-409-01676-8", "Banrural"
    )
    archivo = tmp_path / "banrural.csv"
    crear_estado_banrural(archivo)

    resultado = main.obtener_conciliacion(cuenta_id, archivo, "2026-06-30")

    assert resultado["estado_cuenta"]["numero"] == "XXXXXX6768"
    assert resultado["estado_cuenta"]["saldo_inicial"] == Decimal("2650.00")
    assert resultado["saldos_libros"] is not None
    assert resultado["diferencia_movimientos_periodo"] == Decimal("9789.00")
    assert resultado["resumen"]["diferencias_depositos"]["cantidad"] == 1
    assert resultado["resumen"]["notas_debito_no_ingresadas"]["cantidad"] == 1


def test_banrural_muestra_diferencia_del_mes_si_falta_un_deposito_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cuenta_id = main.crear_cuenta_bancaria(
        "BANRURAL", "Rural", "3-409-01676-8", "Banrural"
    )
    archivo = tmp_path / "banrural.csv"
    archivo.write_text("\n".join([
        "Movimientos de la Cuenta",
        "Del 01/06/2026 al 30/06/2026",
        "Cuenta: XXXXXX6768-Monetario-BENISA-GTQ",
        "Fecha,Oficina,Descripción,Referencia,Secuencial,Cheque Propio / Local / Efectivo,Débito (-),Crédito (+),Saldo Contable,Saldo Disponible",
        "04/06/2026,948,DEPOSITO,900,1,EFECTIVO,0,50,1050,1050",
    ]), encoding="latin-1")

    resultado = main.obtener_conciliacion(cuenta_id, archivo, "2026-06-30")
    resumen = calcular_resumen_conciliacion(resultado)

    assert resultado["saldos_libros"]["saldo_inicial"] == Decimal("1000.00")
    assert resultado["saldo_libros"] == Decimal("1000.00")
    assert resultado["diferencia_movimientos_periodo"] == Decimal("-50.00")
    assert resultado["diferencias_depositos"][0]["monto"] == Decimal("50.00")
    assert resumen["creditos_banco"] == Decimal("50.00")
    assert resumen["diferencia"] == Decimal("0.00")


def test_banrural_rechaza_saldo_acumulado_inconsistente(tmp_path):
    archivo = tmp_path / "banrural.csv"
    crear_estado_banrural(archivo)
    contenido = archivo.read_text(encoding="latin-1").replace(
        "0,361.0,461,461", "0,361.0,462,462"
    )
    archivo.write_text(contenido, encoding="latin-1")

    with pytest.raises(ErrorOperacion, match="no cuadra en la fila 7"):
        analytics._leer_csv_banrural(archivo)
