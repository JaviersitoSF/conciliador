from types import SimpleNamespace
from unittest.mock import Mock, patch

import ui_tk


class EntradaFalsa:
    def __init__(self, valor):
        self.valor = valor
        self.eliminada = False

    def get(self):
        return self.valor

    def delete(self, _inicio, _fin):
        self.eliminada = True
        self.valor = ""


class VariableFalsa:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor


def test_emitir_cheque_incluye_descripcion_y_opcion_de_impresion():
    entradas = [
        EntradaFalsa("12"),
        EntradaFalsa("Proveedor"),
        EntradaFalsa("Compra de inventario"),
        EntradaFalsa("150.25"),
    ]
    app = SimpleNamespace(
        cheque_num=entradas[0],
        cheque_nombre=entradas[1],
        cheque_descripcion=entradas[2],
        cheque_monto=entradas[3],
        imprimir_cheque=VariableFalsa(False),
        cuenta_id_actual=Mock(return_value=7),
        refrescar_todo=Mock(),
    )

    with patch.object(
        ui_tk.service,
        "emitir_cheque",
        return_value={"mensaje": "Cheque registrado"},
    ) as emitir, patch.object(ui_tk.messagebox, "showinfo") as informar:
        ui_tk.ConciliadorApp._emitir_cheque(app)

    emitir.assert_called_once_with(
        "12",
        "Proveedor",
        "150.25",
        descripcion="Compra de inventario",
        cuenta_id=7,
        imprimir=False,
    )
    assert all(entrada.eliminada for entrada in entradas)
    app.refrescar_todo.assert_called_once_with()
    informar.assert_called_once_with("Cheque emitido", "Cheque registrado")


def test_emitir_cheque_rechaza_descripcion_vacia_como_la_tui():
    app = SimpleNamespace(
        cheque_descripcion=EntradaFalsa("   "),
    )

    with patch.object(
        ui_tk.service, "emitir_cheque"
    ) as emitir, patch.object(ui_tk.messagebox, "showerror") as informar:
        ui_tk.ConciliadorApp._emitir_cheque(app)

    emitir.assert_not_called()
    informar.assert_called_once_with(
        "No se pudo emitir",
        "⚠️ Error: el campo no puede quedar vacío.",
    )


def test_reimprimir_cheque_usa_la_cuenta_seleccionada():
    numero = EntradaFalsa("35")
    app = SimpleNamespace(
        reimprimir_num=numero,
        cuenta_id_actual=Mock(return_value=4),
    )

    with patch.object(
        ui_tk.service,
        "reimprimir_cheque",
        return_value="Cheque listo para imprimir",
    ) as reimprimir, patch.object(ui_tk.messagebox, "showinfo") as informar:
        ui_tk.ConciliadorApp._reimprimir_cheque(app)

    reimprimir.assert_called_once_with("35", 4)
    assert numero.eliminada
    informar.assert_called_once_with("Cheque listo", "Cheque listo para imprimir")


def test_crear_cuenta_abre_un_unico_formulario():
    app = SimpleNamespace(_registrar_cuenta=Mock())

    with patch.object(ui_tk, "DialogoNuevaCuenta") as dialogo:
        ui_tk.ConciliadorApp.crear_cuenta(app)

    dialogo.assert_called_once_with(app, app._registrar_cuenta)


def test_anular_cheque_cancelado_no_ejecuta_la_operacion():
    app = SimpleNamespace(
        anular_num=EntradaFalsa("42"),
        boton_anular_cheque=Mock(),
        _ejecutar_bloqueado=Mock(),
    )

    with patch.object(ui_tk.messagebox, "askyesno", return_value=False):
        ui_tk.ConciliadorApp.anular_cheque(app)

    app._ejecutar_bloqueado.assert_not_called()


def test_configurar_formato_abre_dialogo_para_cuenta_seleccionada():
    app = SimpleNamespace(cuenta_id_actual=Mock(return_value=9))
    formato = dict(ui_tk.core.FORMATO_IMPRESION_DEFAULT)

    with patch.object(
        ui_tk.core, "obtener_formato_impresion", return_value=formato
    ) as obtener, patch.object(ui_tk, "DialogoFormatoImpresion") as dialogo:
        ui_tk.ConciliadorApp.configurar_formato_impresion(app)

    obtener.assert_called_once_with(9)
    dialogo.assert_called_once_with(app, 9, formato)


def test_refrescar_invalida_resultados_de_conciliacion_anteriores():
    app = SimpleNamespace(
        _cargar_selector_cuentas=Mock(),
        _cargar_cheques=Mock(),
        _cargar_reporte=Mock(),
        _limpiar_conciliacion=Mock(),
    )

    ui_tk.ConciliadorApp.refrescar_todo(app)

    app._cargar_selector_cuentas.assert_called_once_with()
    app._cargar_cheques.assert_called_once_with()
    app._cargar_reporte.assert_called_once_with()
    app._limpiar_conciliacion.assert_called_once_with()


def test_main_registra_error_si_falla_construccion_inicial():
    paths = SimpleNamespace(log_file="logs/conciliador.log")
    logger = Mock()

    with patch.object(
        ui_tk,
        "prepare_application",
        return_value=(paths, logger, 1),
    ), patch.object(
        ui_tk, "ConciliadorApp", side_effect=RuntimeError("fallo inicial")
    ), patch.object(ui_tk.messagebox, "showerror") as informar:
        resultado = ui_tk.main()

    assert resultado == 1
    logger.exception.assert_called_once_with(
        "No se pudo construir la interfaz grafica"
    )
    informar.assert_called_once()
    assert "logs/conciliador.log" in informar.call_args.args[1]
    assert "fallo inicial" in informar.call_args.args[1]
