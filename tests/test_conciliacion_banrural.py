from decimal import Decimal
from pathlib import Path

from conciliador import analytics, operations as main


def crear_estado_banrural(ruta):
    contenido = "\n".join([
        "Movimientos de la Cuenta",
        "Del 01/06/2026 al 30/06/2026",
        "Cuenta: XXXXXX6768-Monetario-BENISA-GTQ",
        "",
        "Fecha,Oficina,Descripción,Referencia,Secuencial,Cheque Propio / Local / Efectivo,Débito (-),Crédito (+),Saldo Contable,Saldo Disponible",
        "04/06/2026,948,PAGO CHEQUE,1912759098,1,1234,2550.0,0,100,100",
        "05/06/2026,669,DEPOSITO COMPLETO,49518610,2,EFECTIVO,0,361.0,461,461",
        "12/06/2026,9755,N/DEBITO TRANSFERENCIA,55086606,3,,7600.0,0,0,0",
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
    assert estado["cheques"].iloc[0]["Num_cheque"] == "1234"
    assert estado["cheques"].iloc[0]["Monto"] == Decimal("2550.00")
    assert estado["depositos"][0]["Num_cheque"] == "49518610"
    assert estado["notas_debito"][0]["Num_cheque"] == "55086606"


def test_cuenta_acepta_formato_banrural_y_numero_enmascarado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cuenta_id = main.crear_cuenta_bancaria(
        "BANRURAL", "Rural", "3-409-01676-8", "Banrural"
    )
    archivo = tmp_path / "banrural.csv"
    crear_estado_banrural(archivo)

    resultado = main.obtener_conciliacion(cuenta_id, archivo, "2026-06-30")

    assert resultado["estado_cuenta"]["numero"] == "XXXXXX6768"
    assert resultado["resumen"]["diferencias_depositos"]["cantidad"] == 1
    assert resultado["resumen"]["notas_debito_no_ingresadas"]["cantidad"] == 1
