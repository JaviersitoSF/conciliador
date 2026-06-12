from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from conciliador import operations as main


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize(
    "valor",
    ["1e3", "+1", "-1", "Infinity", "-Infinity", "12.5", "abc", ""],
)
def test_normalizar_numero_cheque_rechaza_formatos_no_decimales(valor):
    assert main.normalizar_numero_cheque(valor) is None


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("0012", "12"),
        ("12.0", "12"),
        ("13.00", "13"),
        (35.0, "35"),
        (Decimal("36.0"), "36"),
    ],
)
def test_normalizar_numero_cheque_acepta_enteros_de_excel(valor, esperado):
    assert main.normalizar_numero_cheque(valor) == esperado


@pytest.mark.parametrize(
    "fecha",
    ["2026/06/01", "01-06-2026", "2026-02-30", "2026-6-1", "", "no-fecha"],
)
def test_operaciones_rechazan_fechas_invalidas(fecha):
    with pytest.raises(main.ErrorOperacion, match="fecha"):
        main.registrar_deposito_datos("10", "VENTA", fecha=fecha)

    with patch("conciliador.operations.imprimir_cheque_pdf") as imprimir, \
            pytest.raises(main.ErrorOperacion, match="fecha"):
        main.emitir_cheque_datos("1", "PROVEEDOR", "10", fecha=fecha)

    imprimir.assert_not_called()
    assert main.cargar_cheques_registrados().empty
    assert main.cargar_depositos_registrados().empty


def test_normalizar_fecha_acepta_fecha_iso_y_objetos_fecha():
    assert main.normalizar_fecha("2024-02-29") == "2024-02-29"
    assert main.normalizar_fecha(date(2026, 6, 8)) == "2026-06-08"
    assert main.normalizar_fecha(datetime(2026, 6, 8, 12, 30)) == "2026-06-08"


def test_cuentas_validan_obligatorios_duplicados_e_inactivas():
    with pytest.raises(main.ErrorOperacion, match="obligatorios"):
        main.crear_cuenta_bancaria("", "Operativa")
    with pytest.raises(main.ErrorOperacion, match="obligatorios"):
        main.crear_cuenta_bancaria("BANCO", "")

    cuenta_id = main.crear_cuenta_bancaria(" banco ", " Operativa ", " 001 ")
    cuenta = main.obtener_cuenta(cuenta_id)
    assert cuenta["banco"] == "BANCO"
    assert cuenta["nombre"] == "Operativa"
    assert cuenta["numero"] == "001"

    with pytest.raises(main.ErrorOperacion, match="ya está registrada"):
        main.crear_cuenta_bancaria("BANCO", "Operativa", "001")

    with main.conectar_db() as conexion:
        conexion.execute(
            "UPDATE cuentas_bancarias SET activa = 0 WHERE id = ?",
            (cuenta_id,),
        )

    assert cuenta_id not in {
        cuenta["id"] for cuenta in main.listar_cuentas_bancarias()
    }
    with pytest.raises(main.ErrorOperacion, match="inactiva"):
        main.obtener_cuenta(cuenta_id)


def test_cuentas_tienen_formatos_de_impresion_independientes():
    cuenta_a = main.crear_cuenta_bancaria("BANCO A", "Operativa")
    cuenta_b = main.crear_cuenta_bancaria("BANCO B", "Operativa")
    formato_a = dict(main.FORMATO_IMPRESION_DEFAULT, fecha_x=3.25, ancho=23)

    guardado = main.guardar_formato_impresion(cuenta_a, formato_a)

    assert guardado["fecha_x"] == 3.25
    assert main.obtener_formato_impresion(cuenta_a)["ancho"] == 23
    assert main.obtener_formato_impresion(cuenta_b) == main.FORMATO_IMPRESION_DEFAULT


def test_formato_rechaza_coordenadas_fuera_del_cheque():
    formato = dict(main.FORMATO_IMPRESION_DEFAULT, nombre_x=23)

    with pytest.raises(main.ErrorOperacion, match="fuera del cheque"):
        main.guardar_formato_impresion(1, formato)


def test_emitir_y_reimprimir_usan_formato_de_la_cuenta():
    cuenta_id = main.crear_cuenta_bancaria("BANCO", "Cheques")
    formato = dict(main.FORMATO_IMPRESION_DEFAULT, monto_x=16.5)
    main.guardar_formato_impresion(cuenta_id, formato)

    with patch("conciliador.movements.printing.imprimir_cheque_pdf", return_value=True) as imprimir:
        main.emitir_cheque_datos(
            "8", "PROVEEDOR", "50", fecha="2026-06-01",
            descripcion="COMPRA", cuenta_id=cuenta_id,
        )
        main.reimprimir_cheque_numero("8", cuenta_id)

    assert imprimir.call_count == 2
    assert imprimir.call_args_list[0].kwargs["formato"]["monto_x"] == 16.5
    assert imprimir.call_args_list[1].kwargs["formato"]["monto_x"] == 16.5


def test_prueba_de_formato_no_registra_movimientos_ni_auditoria():
    formato = dict(main.FORMATO_IMPRESION_DEFAULT, descripcion_y=6.5)

    with patch("conciliador.printing.imprimir_cheque_pdf", return_value=True) as imprimir:
        assert main.probar_formato_impresion(formato) is True

    assert imprimir.call_args.kwargs["formato"]["descripcion_y"] == 6.5
    assert main.cargar_cheques_registrados().empty
    with main.conectar_db() as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("monto", "descripcion"),
    [("malo", "VENTA"), ("0", "VENTA"), ("-1", "VENTA"), ("10", "")],
)
def test_depositos_invalidos_no_escriben_datos_ni_auditoria(monto, descripcion):
    with pytest.raises(main.ErrorOperacion):
        main.registrar_deposito_datos(
            monto, descripcion, fecha="2026-06-01"
        )

    assert main.cargar_depositos_registrados().empty
    with main.conectar_db() as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM auditoria").fetchone()[0] == 0


def test_falla_de_respaldo_informa_que_la_operacion_si_se_guardo():
    with patch("conciliador.storage.crear_respaldo", side_effect=OSError("sin espacio")), \
            pytest.raises(main.ErrorOperacion, match="sí se guardó.*respaldo"):
        main.registrar_deposito_datos(
            "10", "VENTA", fecha="2026-06-01"
        )

    depositos = main.cargar_depositos_registrados()
    assert depositos["Monto"].tolist() == ["10.00"]


def test_guardar_cheque_aplica_invariantes_aunque_se_use_directamente():
    casos = [
        ("x", "2026-06-01", "A", "10"),
        ("1", "fecha-mala", "A", "10"),
        ("1", "2026-06-01", "", "10"),
        ("1", "2026-06-01", "A", "0"),
        ("1", "2026-06-01", "A", "-1"),
    ]

    for numero, fecha, nombre, monto in casos:
        with pytest.raises(main.ErrorOperacion):
            main.guardar_cheque_en_archivo(numero, fecha, nombre, monto)

    assert main.cargar_cheques_registrados().empty


def test_busqueda_de_cheque_usa_la_misma_normalizacion_que_el_registro():
    main.guardar_cheque_en_archivo("001", "2026-06-01", "A", "10")

    assert main.cheque_ya_registrado("1")
    assert main.cheque_ya_registrado("001.00")
    assert not main.cheque_ya_registrado("1e0")


def test_emitir_informa_que_el_cheque_quedo_registrado_si_falla_el_pdf():
    with patch("conciliador.movements.printing.imprimir_cheque_pdf", side_effect=OSError("disco lleno")):
        with pytest.raises(main.ErrorOperacion, match="fue registrado"):
            main.emitir_cheque_datos(
                "15", "PROVEEDOR", "100", fecha="2026-06-01"
            )

    cheques = main.cargar_cheques_registrados()
    assert cheques["Num"].tolist() == ["15"]


def test_emitir_advierte_si_pdf_existe_pero_no_se_pudo_abrir_o_imprimir():
    with patch("conciliador.movements.printing.imprimir_cheque_pdf", return_value=False):
        resultado = main.emitir_cheque_datos(
            "16", "PROVEEDOR", "100", fecha="2026-06-01"
        )

    assert resultado["impresion_enviada"] is False
    assert "manualmente" in resultado["mensaje"]
    assert main.cheque_ya_registrado("16")


def test_emitir_puede_registrar_sin_imprimir():
    with patch("conciliador.movements.printing.imprimir_cheque_pdf") as imprimir:
        resultado = main.emitir_cheque_datos(
            "17",
            "PROVEEDOR",
            "100",
            fecha="2026-06-01",
            imprimir=False,
        )

    imprimir.assert_not_called()
    assert resultado["pdf"] is None
    assert resultado["impresion_enviada"] is False
    assert resultado["mensaje"] == "✅ Cheque registrado sin imprimir."
    assert main.cheque_ya_registrado("17")


def test_cheques_de_cuentas_distintas_generan_nombres_pdf_distintos():
    cuenta_a = main.crear_cuenta_bancaria("BANCO A", "Operativa", "001")
    cuenta_b = main.crear_cuenta_bancaria("BANCO B", "Operativa", "002")

    with patch("conciliador.movements.printing.imprimir_cheque_pdf") as imprimir:
        resultado_a = main.emitir_cheque_datos(
            "10", "A", "10", fecha="2026-06-01", cuenta_id=cuenta_a
        )
        resultado_b = main.emitir_cheque_datos(
            "10", "B", "20", fecha="2026-06-01", cuenta_id=cuenta_b
        )

    assert resultado_a["pdf"] != resultado_b["pdf"]
    assert resultado_a["pdf"].endswith(f"cheque_{cuenta_a}_10.pdf")
    assert resultado_b["pdf"].endswith(f"cheque_{cuenta_b}_10.pdf")
    assert imprimir.call_count == 2


def test_no_se_puede_reimprimir_un_cheque_anulado():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")
    main.anular_cheque_numero("1")

    with patch("conciliador.movements.printing.imprimir_cheque_pdf") as imprimir, \
            pytest.raises(main.ErrorOperacion, match="anulado"):
        main.reimprimir_cheque_numero("1")

    imprimir.assert_not_called()
    with main.conectar_db() as conexion:
        acciones = [
            fila[0]
            for fila in conexion.execute("SELECT accion FROM auditoria ORDER BY id")
        ]
    assert acciones == ["CREAR", "ANULAR"]


def test_anular_dos_veces_no_duplica_la_auditoria():
    main.guardar_cheque_en_archivo("1", "2026-06-01", "A", "10")
    main.anular_cheque_numero("1")

    with pytest.raises(main.ErrorOperacion, match="ya esta anulado|ya está anulado"):
        main.anular_cheque_numero("1")

    with main.conectar_db() as conexion:
        acciones = [
            fila[0]
            for fila in conexion.execute("SELECT accion FROM auditoria ORDER BY id")
        ]
    assert acciones == ["CREAR", "ANULAR"]


def test_anular_busca_existencia_solo_en_la_cuenta_seleccionada():
    cuenta_sin_cheques = main.crear_cuenta_bancaria("BANCO A", "Sin cheques")
    cuenta_con_cheques = main.crear_cuenta_bancaria("BANCO B", "Con cheques")
    main.guardar_cheque_en_archivo(
        "1", "2026-06-01", "A", "10", cuenta_id=cuenta_con_cheques
    )

    with pytest.raises(main.ErrorOperacion, match="No hay registro"):
        main.anular_cheque_numero("1", cuenta_id=cuenta_sin_cheques)


def test_reporte_rechaza_fecha_de_corte_invalida():
    with pytest.raises(main.ErrorOperacion, match="fecha"):
        main.obtener_reporte_movimientos("no-fecha")


def test_reporte_sin_movimientos_devuelve_totales_cero_y_dataframes_validos():
    reporte = main.obtener_reporte_movimientos("2026-06-08")

    assert reporte["periodo"] == "2026-06"
    assert reporte["total_cheques"] == Decimal("0.00")
    assert reporte["total_depositos"] == Decimal("0.00")
    assert reporte["saldo"] == Decimal("0.00")
    assert reporte["cheques"].empty
    assert reporte["depositos"].empty
