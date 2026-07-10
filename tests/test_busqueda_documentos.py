from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from conciliador import operations as main
from conciliador.service import ConciliadorService
import ui_tk


class EntradaFalsa:
    def __init__(self, valor):
        self.valor = valor
        self.enfocada = False

    def get(self):
        return self.valor

    def delete(self, _inicio, _fin):
        self.valor = ""

    def focus_set(self):
        self.enfocada = True


class WidgetFalso:
    def __init__(self, *_args, **kwargs):
        self.bindings = {}
        self.command = kwargs.get("command")

    def grid(self, **_kwargs):
        return self

    def columnconfigure(self, *_args, **_kwargs):
        return None

    def rowconfigure(self, *_args, **_kwargs):
        return None

    def bind(self, evento, callback):
        self.bindings[evento] = callback


@pytest.fixture(autouse=True)
def cwd_temporal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_busqueda_de_cheques_cubre_campos_y_respeta_la_cuenta():
    cuenta_a = main.crear_cuenta_bancaria("BANCO A", "Operativa", "001")
    cuenta_b = main.crear_cuenta_bancaria("BANCO B", "Operativa", "002")
    main.guardar_cheque_en_archivo(
        "101",
        "2025-01-02",
        "Proveedor Antiguo",
        "123.45",
        "Compra anual",
        cuenta_a,
    )
    main.guardar_cheque_en_archivo(
        "202", "2025-02-03", "Otro proveedor", "67.89", "Servicio", cuenta_a
    )
    main.anular_cheque_numero("202", cuenta_a)
    main.guardar_cheque_en_archivo(
        "101", "2026-01-02", "Misma referencia", "999.00", "Otra cuenta", cuenta_b
    )

    casos = {
        "101": "101",
        "2025-01-02": "101",
        "proveedor antiguo": "101",
        "compra anual": "101",
        "123.45": "101",
        "anulado": "202",
    }
    for termino, numero_esperado in casos.items():
        encontrados = main.cargar_cheques_registrados(cuenta_a, termino)
        assert encontrados["Num"].tolist() == [numero_esperado]
        assert encontrados["Cuenta_id"].tolist() == [cuenta_a]

    assert len(main.cargar_cheques_registrados(None, "101")) == 2
    assert len(main.cargar_cheques_registrados(cuenta_a, "   ")) == 2


def test_busqueda_de_depositos_y_notas_no_mezcla_tipos():
    cuenta = main.crear_cuenta_bancaria("BANCO", "Operativa", "001")
    main.registrar_deposito_datos(
        "876.54",
        "Ingreso extraordinario por depósito",
        fecha="2024-03-04",
        numero="DOC-COMUN",
        cuenta_id=cuenta,
    )
    main.registrar_nota_debito_datos(
        "19.25",
        "Cargo extraordinario",
        fecha="2024-04-05",
        numero="DOC-COMUN",
        cuenta_id=cuenta,
    )

    assert main.cargar_depositos_registrados(
        cuenta, "ingreso extraordinario"
    )["Num"].tolist() == ["DOC-COMUN"]
    assert main.cargar_depositos_registrados(cuenta, "DOC-COMUN")[
        "Num"
    ].tolist() == ["DOC-COMUN"]
    assert main.cargar_depositos_registrados(cuenta, "deposito")[
        "Num"
    ].tolist() == ["DOC-COMUN"]
    assert main.cargar_depositos_registrados(cuenta, "876.54")[
        "Num"
    ].tolist() == ["DOC-COMUN"]
    assert main.cargar_notas_debito_registradas(
        cuenta, "cargo extraordinario"
    )["Num"].tolist() == ["DOC-COMUN"]
    assert main.cargar_notas_debito_registradas(cuenta, "2024-04-05")[
        "Num"
    ].tolist() == ["DOC-COMUN"]
    assert main.cargar_notas_debito_registradas(cuenta, "19.25")[
        "Num"
    ].tolist() == ["DOC-COMUN"]
    assert main.cargar_notas_debito_registradas(cuenta, "registrado")[
        "Num"
    ].tolist() == ["DOC-COMUN"]

    assert main.cargar_depositos_registrados(
        cuenta, "cargo extraordinario"
    ).empty
    assert main.cargar_notas_debito_registradas(
        cuenta, "ingreso extraordinario"
    ).empty


def test_busqueda_trata_los_comodines_como_texto_literal_y_admite_vacio():
    cuenta = main.crear_cuenta_bancaria("BANCO", "Operativa", "001")
    main.registrar_deposito_datos(
        "10",
        r"Tasa 25%_real\caja O'Brien",
        fecha="2024-01-01",
        numero="LITERAL",
        cuenta_id=cuenta,
    )
    main.registrar_deposito_datos(
        "20",
        "Tasa 250Xreal caja",
        fecha="2024-01-02",
        numero="NORMAL",
        cuenta_id=cuenta,
    )

    for termino in ("%", "_", "\\", "o'brien"):
        encontrados = main.cargar_depositos_registrados(cuenta, termino)
        assert encontrados["Num"].tolist() == ["LITERAL"]

    assert len(main.cargar_depositos_registrados(cuenta, None)) == 2
    assert len(main.cargar_depositos_registrados(cuenta, "")) == 2
    sin_resultados = main.cargar_depositos_registrados(cuenta, "no existe")
    assert sin_resultados.empty
    assert {"Id", "Num", "Monto_valor", "Fecha_dt"} <= set(
        sin_resultados.columns
    )


def test_servicio_propaga_el_termino_a_cada_tipo_de_documento():
    operaciones = Mock()
    servicio = ConciliadorService(operaciones)

    servicio.obtener_cheques(7, "cheque viejo")
    servicio.obtener_depositos(7, "depósito viejo")
    servicio.obtener_notas_debito(7, "nota vieja")

    operaciones.cargar_cheques_registrados.assert_called_once_with(
        7, "cheque viejo"
    )
    operaciones.cargar_depositos_registrados.assert_called_once_with(
        7, "depósito viejo"
    )
    operaciones.cargar_notas_debito_registradas.assert_called_once_with(
        7, "nota vieja"
    )


def test_buscador_ejecuta_con_enter_y_limpia_con_escape():
    entrada = WidgetFalso()
    cargar = Mock()
    app = SimpleNamespace(_limpiar_busqueda=Mock())

    with patch.object(ui_tk.ttk, "Frame", side_effect=WidgetFalso), \
            patch.object(ui_tk.ttk, "Label", side_effect=WidgetFalso), \
            patch.object(ui_tk.ttk, "Entry", return_value=entrada), \
            patch.object(ui_tk.ttk, "Button", side_effect=WidgetFalso):
        ui_tk.ConciliadorApp._buscador_historial(app, WidgetFalso(), cargar)

    entrada.bindings["<Return>"](None)
    cargar.assert_called_once_with()
    entrada.bindings["<Escape>"](None)
    app._limpiar_busqueda.assert_called_once_with(entrada, cargar)


def test_limpiar_busqueda_vuelve_a_cargar_recientes_y_conserva_el_foco():
    entrada = EntradaFalsa("documento anterior")
    cargar = Mock()

    ui_tk.ConciliadorApp._limpiar_busqueda(
        SimpleNamespace(), entrada, cargar
    )

    assert entrada.get() == ""
    assert entrada.enfocada
    cargar.assert_called_once_with()


def _dataframe_cheques(cantidad):
    return pd.DataFrame(
        [
            {
                "Id": indice,
                "Num": str(indice),
                "Fecha": "2024-01-01",
                "Nombre": f"Proveedor {indice}",
                "Descripcion": "Documento histórico",
                "Monto": "10.00",
                "Estado": "TRANSITO",
            }
            for indice in range(1, cantidad + 1)
        ]
    )


def test_busqueda_en_ui_recorre_historial_completo_y_vista_normal_sigue_reciente():
    app = SimpleNamespace(
        tabla_cheques=Mock(),
        busqueda_cheques=EntradaFalsa("histórico"),
        cuenta_id_actual=Mock(return_value=7),
        _limpiar_tabla=Mock(),
        _mostrar_estado_vacio=Mock(),
    )
    encontrados = _dataframe_cheques(35)

    with patch.object(
        ui_tk.service, "obtener_cheques", return_value=encontrados
    ) as buscar:
        ui_tk.ConciliadorApp._cargar_cheques(app)

    buscar.assert_called_once_with(7, "histórico")
    assert app.tabla_cheques.insert.call_count == 35
    assert len(app.cheques_por_id) == 35
    assert app.tabla_cheques.insert.call_args_list[0].kwargs["iid"] == "35"

    app.tabla_cheques.reset_mock()
    app.busqueda_cheques = EntradaFalsa("   ")
    with patch.object(
        ui_tk.service, "obtener_cheques", return_value=encontrados
    ) as cargar_recientes:
        ui_tk.ConciliadorApp._cargar_cheques(app)

    cargar_recientes.assert_called_once_with(7, None)
    assert app.tabla_cheques.insert.call_count == 30


@pytest.mark.parametrize(
    ("metodo", "atributo_entrada", "atributo_tabla", "atributo_resultados", "servicio"),
    [
        (
            ui_tk.ConciliadorApp._cargar_depositos,
            "busqueda_depositos",
            "tabla_depositos",
            "depositos_por_id",
            "obtener_depositos",
        ),
        (
            ui_tk.ConciliadorApp._cargar_notas_debito,
            "busqueda_notas_debito",
            "tabla_notas_debito",
            "notas_debito_por_id",
            "obtener_notas_debito",
        ),
    ],
)
def test_busqueda_en_ui_tambien_cubre_depositos_y_notas(
    metodo,
    atributo_entrada,
    atributo_tabla,
    atributo_resultados,
    servicio,
):
    tabla = Mock()
    app = SimpleNamespace(
        cuenta_id_actual=Mock(return_value=9),
        _limpiar_tabla=Mock(),
        _mostrar_estado_vacio=Mock(),
    )
    setattr(app, atributo_entrada, EntradaFalsa("documento anterior"))
    setattr(app, atributo_tabla, tabla)
    encontrados = pd.DataFrame(
        [
            {
                "Id": 41,
                "Num": "ANT-41",
                "Fecha": "2023-01-02",
                "Descripcion": "Documento anterior",
                "Monto": "50.00",
                "Estado": "REGISTRADO",
            }
        ]
    )

    with patch.object(
        ui_tk.service, servicio, return_value=encontrados
    ) as buscar:
        metodo(app)

    buscar.assert_called_once_with(9, "documento anterior")
    assert getattr(app, atributo_resultados)[41]["numero"] == "ANT-41"
    tabla.insert.assert_called_once()
