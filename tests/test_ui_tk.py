from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

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

    def insert(self, _indice, valor):
        self.valor = valor


class VariableFalsa:
    def __init__(self, valor):
        self.valor = valor

    def get(self):
        return self.valor


def test_dialogo_movimiento_espera_ser_visible_antes_del_grab():
    fuente = Path(ui_tk.__file__).read_text(encoding="utf-8")
    inicio = fuente.index("class DialogoMovimiento")
    fin = fuente.index("\nclass ", inicio + 1)
    dialogo = fuente[inicio:fin]

    assert dialogo.index("self.wait_visibility()") < dialogo.index(
        "self.grab_set()"
    )


def test_emitir_cheque_incluye_descripcion_y_opcion_de_impresion():
    entradas = [
        EntradaFalsa("12"),
        EntradaFalsa("Proveedor"),
        EntradaFalsa("Compra de inventario"),
        EntradaFalsa("150.25"),
        EntradaFalsa("2026-05-31"),
    ]
    app = SimpleNamespace(
        cheque_num=entradas[0],
        cheque_nombre=entradas[1],
        cheque_descripcion=entradas[2],
        cheque_monto=entradas[3],
        cheque_fecha=entradas[4],
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
        fecha="2026-05-31",
        descripcion="Compra de inventario",
        cuenta_id=7,
        imprimir=False,
    )
    assert all(entrada.eliminada for entrada in entradas)
    app.refrescar_todo.assert_called_once_with()
    informar.assert_called_once_with("Cheque emitido", "Cheque registrado")


def test_imprimir_conciliacion_pide_destino_y_exporta_resultado():
    resultado = {"cuenta": {"id": 7}, "fecha_corte": "2026-06-30"}
    app = SimpleNamespace(resultado_conciliacion=resultado)

    with patch.object(
        ui_tk.filedialog, "asksaveasfilename", return_value="reporte.pdf"
    ) as seleccionar, patch.object(
        ui_tk.service, "exportar_conciliacion"
    ) as exportar:
        ui_tk.ConciliadorApp.imprimir_conciliacion(app)

    assert seleccionar.call_args.kwargs["initialfile"] == "conciliacion_7_2026-06-30.pdf"
    exportar.assert_called_once_with(resultado, "reporte.pdf")


def test_fin_de_mes_usa_el_ultimo_dia_del_periodo():
    assert ui_tk.ConciliadorApp._fin_de_mes("2024-02") == "2024-02-29"
    assert ui_tk.ConciliadorApp._fin_de_mes("2026-06") == "2026-06-30"


def test_conciliacion_muestra_cheques_sin_registro_y_filas_invalidas():
    tablas = [Mock() for _ in range(6)]
    resumen = {
        clave: {"cantidad": 0, "total": 0}
        for clave in (
            "cheques_cobrados", "cheques_transito", "diferencias_depositos",
            "diferencias_notas_debito", "cheques_banco_sin_registro",
        )
    }
    resumen["cheques_banco_sin_registro"] = {"cantidad": 1, "total": 25}
    resumen["filas_invalidas"] = {"cantidad": 1, "total": 0}
    resultado = {
        "cheques_cobrados": [],
        "cheques_transito": [],
        "diferencias_depositos": [],
        "diferencias_notas_debito": [],
        "cheques_banco_sin_registro": [{
            "num": "99", "fecha": "2026-06-03", "descripcion": "CHEQUE",
            "monto": 25, "diferencia": "Cobrado sin registro local",
        }],
        "filas_invalidas": [{
            "num": "Fila 8", "fecha": "fecha mala", "descripcion": "ERROR",
            "monto": None, "diferencia": "Fecha inválida",
        }],
        "resumen": resumen,
        "estado_cuenta": {"moneda": "GTQ"},
    }
    app = SimpleNamespace(
        tabla_cheques_cobrados=tablas[0],
        tabla_cheques_transito=tablas[1],
        tabla_depositos_no_ingresados=tablas[2],
        tabla_notas_debito_no_ingresadas=tablas[3],
        tabla_cheques_banco_sin_registro=tablas[4],
        tabla_filas_invalidas=tablas[5],
        conciliacion_mes=VariableFalsa("2026-06"),
        cuenta_id_actual=Mock(return_value=4),
        _fin_de_mes=Mock(return_value="2026-06-30"),
        _limpiar_tabla=Mock(),
        _mostrar_estado_vacio=Mock(),
        resumen_conciliacion=Mock(),
        boton_imprimir_conciliacion=Mock(),
    )

    with patch.object(ui_tk.service, "conciliar", return_value=resultado):
        ui_tk.ConciliadorApp._conciliar_archivo(app, "estado.csv")

    tablas[4].insert.assert_called_once_with(
        "", ui_tk.tk.END,
        values=("99", "2026-06-03", "CHEQUE", "25.00", "Cobrado sin registro local"),
    )
    tablas[5].insert.assert_called_once_with(
        "", ui_tk.tk.END,
        values=("Fila 8", "fecha mala", "ERROR", "N/D", "Fecha inválida"),
    )


def test_registrar_deposito_incluye_numero():
    entradas = [
        EntradaFalsa("DEP-18"),
        EntradaFalsa("Venta"),
        EntradaFalsa("100.50"),
        EntradaFalsa("2026-06-15"),
    ]
    app = SimpleNamespace(
        deposito_num=entradas[0],
        deposito_desc=entradas[1],
        deposito_monto=entradas[2],
        deposito_fecha=entradas[3],
        cuenta_id_actual=Mock(return_value=7),
        refrescar_todo=Mock(),
    )
    app._confirmar_posible_duplicado_deposito = (
        lambda fecha, monto, deposito_id=None:
        ui_tk.ConciliadorApp._confirmar_posible_duplicado_deposito(
            app, fecha, monto, deposito_id
        )
    )

    with patch.object(
        ui_tk.service,
        "buscar_posibles_duplicados_deposito",
        return_value=[],
    ), patch.object(
        ui_tk.service,
        "registrar_deposito",
        return_value={"mensaje": "Depósito registrado"},
    ) as registrar, patch.object(ui_tk.messagebox, "showinfo"):
        ui_tk.ConciliadorApp._registrar_deposito(app)

    registrar.assert_called_once_with(
        "100.50",
        "Venta",
        fecha="2026-06-15",
        cuenta_id=7,
        numero="DEP-18",
    )
    assert entradas[0].eliminada


def test_registrar_deposito_advierte_y_respeta_cancelacion_por_duplicado():
    entradas = [
        EntradaFalsa("DEP-19"),
        EntradaFalsa("Venta"),
        EntradaFalsa("400.95"),
        EntradaFalsa("2026-06-01"),
    ]
    app = SimpleNamespace(
        deposito_num=entradas[0],
        deposito_desc=entradas[1],
        deposito_monto=entradas[2],
        deposito_fecha=entradas[3],
        cuenta_id_actual=Mock(return_value=7),
    )
    app._confirmar_posible_duplicado_deposito = (
        lambda fecha, monto, deposito_id=None:
        ui_tk.ConciliadorApp._confirmar_posible_duplicado_deposito(
            app, fecha, monto, deposito_id
        )
    )
    existente = {
        "id": 32762,
        "numero": "1134566",
        "fecha": "2026-06-01",
        "descripcion": "VISTARES 30/5/2026",
        "monto": "400.95",
        "estado": "REGISTRADO",
    }

    with patch.object(
        ui_tk.service,
        "buscar_posibles_duplicados_deposito",
        return_value=[existente],
    ) as buscar, patch.object(
        ui_tk.messagebox, "askyesno", return_value=False
    ) as confirmar, patch.object(
        ui_tk.service, "registrar_deposito"
    ) as registrar:
        ui_tk.ConciliadorApp._registrar_deposito(app)

    buscar.assert_called_once_with(
        "2026-06-01", "400.95", 7, excluir_id=None
    )
    assert "1134566 (registro 32762)" in confirmar.call_args.args[1]
    registrar.assert_not_called()
    assert all(not entrada.eliminada for entrada in entradas)


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


def test_editar_cuenta_abre_formulario_con_datos_seleccionados():
    cuenta = {
        "id": 7,
        "banco": "BANCO",
        "nombre": "Operativa",
        "numero": "001",
    }
    app = SimpleNamespace(
        cuenta_id_actual=Mock(return_value=7),
        cuentas=[cuenta],
        _actualizar_cuenta=Mock(),
    )

    with patch.object(ui_tk, "DialogoNuevaCuenta") as dialogo:
        ui_tk.ConciliadorApp.editar_cuenta(app)

    dialogo.assert_called_once()
    assert dialogo.call_args.kwargs["cuenta"] == cuenta


def test_actualizar_cheque_envia_datos_del_dialogo():
    app = SimpleNamespace(
        cuenta_id_actual=Mock(return_value=7),
        refrescar_todo=Mock(),
    )
    valores = {
        "numero": "12",
        "fecha": "2026-06-15",
        "nombre": "Proveedor",
        "descripcion": "Compra",
        "monto": "100",
    }

    with patch.object(
        ui_tk.service,
        "actualizar_cheque",
        return_value={"mensaje": "Cheque actualizado"},
    ) as actualizar, patch.object(ui_tk.messagebox, "showinfo"):
        assert ui_tk.ConciliadorApp._actualizar_cheque(app, 3, valores)

    actualizar.assert_called_once_with(
        3, "12", "2026-06-15", "Proveedor", "100", "Compra", 7
    )
    app.refrescar_todo.assert_called_once_with()


def test_actualizar_deposito_envia_datos_del_dialogo():
    app = SimpleNamespace(
        cuenta_id_actual=Mock(return_value=7),
        refrescar_todo=Mock(),
    )
    app._confirmar_posible_duplicado_deposito = (
        lambda fecha, monto, deposito_id=None:
        ui_tk.ConciliadorApp._confirmar_posible_duplicado_deposito(
            app, fecha, monto, deposito_id
        )
    )
    valores = {
        "numero": "DEP-2",
        "fecha": "2026-06-15",
        "descripcion": "Venta",
        "monto": "100",
    }

    with patch.object(
        ui_tk.service,
        "buscar_posibles_duplicados_deposito",
        return_value=[],
    ) as buscar, patch.object(
        ui_tk.service,
        "actualizar_deposito",
        return_value={"mensaje": "Depósito actualizado"},
    ) as actualizar, patch.object(ui_tk.messagebox, "showinfo"):
        assert ui_tk.ConciliadorApp._actualizar_deposito(app, 4, valores)

    actualizar.assert_called_once_with(
        4, "DEP-2", "2026-06-15", "Venta", "100", 7
    )
    buscar.assert_called_once_with(
        "2026-06-15", "100", 7, excluir_id=4
    )
    app.refrescar_todo.assert_called_once_with()


def test_anular_cheque_cancelado_no_ejecuta_la_operacion():
    app = SimpleNamespace(
        anular_num=EntradaFalsa("42"),
        boton_anular_cheque=Mock(),
        _ejecutar_bloqueado=Mock(),
    )

    with patch.object(ui_tk.messagebox, "askyesno", return_value=False):
        ui_tk.ConciliadorApp.anular_cheque(app)

    app._ejecutar_bloqueado.assert_not_called()

def test_eliminar_cheque_confirmado_usa_id_y_cuenta_seleccionada():
    tabla = Mock()
    tabla.selection.return_value = ("3",)
    tabla.item.return_value = {"tags": ()}
    app = SimpleNamespace(
        tabla_cheques=tabla,
        cheques_por_id={
            3: {"id": 3, "numero": "12", "monto": "100.00"}
        },
        cuenta_id_actual=Mock(return_value=7),
        refrescar_todo=Mock(),
    )
    app._movimiento_seleccionado = (
        lambda tabla, titulo: ui_tk.ConciliadorApp._movimiento_seleccionado(
            app, tabla, titulo
        )
    )

    with patch.object(
        ui_tk.messagebox, "askyesno", return_value=True
    ), patch.object(
        ui_tk.service,
        "eliminar_cheque",
        return_value={"mensaje": "Cheque eliminado"},
    ) as eliminar, patch.object(ui_tk.messagebox, "showinfo"):
        ui_tk.ConciliadorApp.eliminar_cheque(app)

    eliminar.assert_called_once_with(3, 7)
    app.refrescar_todo.assert_called_once_with()


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
        _cargar_depositos=Mock(),
        _cargar_reporte=Mock(),
        _limpiar_conciliacion=Mock(),
    )

    ui_tk.ConciliadorApp.refrescar_todo(app)

    app._cargar_selector_cuentas.assert_called_once_with()
    app._cargar_cheques.assert_called_once_with()
    app._cargar_depositos.assert_called_once_with()
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
