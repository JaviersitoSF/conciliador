from decimal import Decimal
from pathlib import Path

from conciliador import analytics, operations as main


def crear_estado_bac(ruta):
    contenido = "\n".join([
        "Número de Clientes, Nombre, Producto, Moneda, Saldo Inicial, Saldo en Libros, Retenidos y Diferidos, Saldo Disponible, Fecha",
        "2755, BENISA S.A., 900016874, QTZ, 100.00, 125.00, 0.00, 125.00, 30/06/2026",
        "",
        "Detalle de Estado Bancario",
        "Fecha de Transacción, Referencia de Transacción, Código de Transacción, Descripción de Transacción, Débito de Transacción, Crédito de Transacción, Balance de Transacción",
        "01/06/2026, 437706449, DP, DEPOSITO EN EFECTIVO, 0.00, 50.00, 150.00",
        "02/06/2026, 900477799, MD, TF:ACH PERSONAS, 20.00, 0.00, 130.00",
        "03/06/2026, 1466, CK, PAGO CHEQUE 1466, 5.00, 0.00, 125.00",
    ])
    Path(ruta).write_bytes(contenido.encode("latin-1"))


def test_lector_bac_clasifica_movimientos_y_metadatos(tmp_path):
    archivo = tmp_path / "bac.csv"
    crear_estado_bac(archivo)

    estado = analytics._leer_csv_bac(archivo)

    assert estado["cuenta_numero"] == "900016874"
    assert estado["cuenta_nombre"] == "BENISA S.A."
    assert estado["fecha_inicio"] == "2026-06-01"
    assert estado["fecha_fin"] == "2026-06-30"
    assert estado["moneda"] == "GTQ"
    assert estado["depositos"][0]["Monto"] == Decimal("50.00")
    assert estado["notas_debito"][0]["Monto"] == Decimal("20.00")
    assert estado["cheques"].iloc[0]["Num_cheque"] == "1466"


def test_cuenta_acepta_formato_bac(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cuenta_id = main.crear_cuenta_bancaria("BAC", "Operativa", "90-001687-4", "BAC")
    archivo = tmp_path / "bac.csv"
    crear_estado_bac(archivo)

    resultado = main.obtener_conciliacion(cuenta_id, archivo, "2026-06-30")

    assert resultado["estado_cuenta"]["numero"] == "900016874"
    assert resultado["resumen"]["diferencias_depositos"]["cantidad"] == 1
    assert resultado["resumen"]["notas_debito_no_ingresadas"]["cantidad"] == 1
