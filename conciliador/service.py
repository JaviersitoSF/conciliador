class ConciliadorService:
    """Fachada de casos de uso consumida por la interfaz gráfica."""

    def __init__(self, operations):
        self.operations = operations

    def listar_cuentas(self):
        return self.operations.listar_cuentas_bancarias()

    def crear_cuenta(self, banco, nombre, numero="", formato_conciliacion=None):
        if formato_conciliacion is None:
            return self.operations.crear_cuenta_bancaria(banco, nombre, numero)
        return self.operations.crear_cuenta_bancaria(
            banco, nombre, numero, formato_conciliacion
        )

    def actualizar_cuenta(
        self, cuenta_id, banco, nombre, numero="", formato_conciliacion=None
    ):
        return self.operations.actualizar_cuenta_bancaria(
            cuenta_id, banco, nombre, numero, formato_conciliacion
        )

    def emitir_cheque(self, *args, **kwargs):
        return self.operations.emitir_cheque_datos(*args, **kwargs)

    def actualizar_cheque(self, *args, **kwargs):
        return self.operations.actualizar_cheque(*args, **kwargs)

    def eliminar_cheque(self, cheque_id, cuenta_id=None):
        return self.operations.eliminar_cheque(cheque_id, cuenta_id)

    def anular_cheque(self, numero, cuenta_id=None):
        return self.operations.anular_cheque_numero(numero, cuenta_id)

    def reimprimir_cheque(self, numero, cuenta_id=None):
        return self.operations.reimprimir_cheque_numero(numero, cuenta_id)

    def registrar_deposito(self, *args, **kwargs):
        return self.operations.registrar_deposito_datos(*args, **kwargs)

    def actualizar_deposito(self, *args, **kwargs):
        return self.operations.actualizar_deposito(*args, **kwargs)

    def eliminar_deposito(self, deposito_id, cuenta_id=None):
        return self.operations.eliminar_deposito(deposito_id, cuenta_id)

    def anular_deposito(self, numero, cuenta_id=None):
        return self.operations.anular_deposito_numero(numero, cuenta_id)

    def registrar_nota_debito(self, *args, **kwargs):
        return self.operations.registrar_nota_debito_datos(*args, **kwargs)

    def actualizar_nota_debito(self, *args, **kwargs):
        return self.operations.actualizar_nota_debito(*args, **kwargs)

    def eliminar_nota_debito(self, nota_id, cuenta_id=None):
        return self.operations.eliminar_nota_debito(nota_id, cuenta_id)

    def anular_nota_debito(self, numero, cuenta_id=None):
        return self.operations.anular_nota_debito_numero(numero, cuenta_id)

    def obtener_cheques(self, cuenta_id=None):
        return self.operations.cargar_cheques_registrados(cuenta_id)

    def obtener_depositos(self, cuenta_id=None):
        return self.operations.cargar_depositos_registrados(cuenta_id)

    def obtener_notas_debito(self, cuenta_id=None):
        return self.operations.cargar_notas_debito_registradas(cuenta_id)

    def obtener_reporte(self, fecha=None, cuenta_id=None):
        return self.operations.obtener_reporte_movimientos(fecha, cuenta_id)

    def conciliar(self, cuenta_id=None, archivo_banco=None, fecha_corte=None):
        return self.operations.obtener_conciliacion(
            cuenta_id, archivo_banco, fecha_corte
        )

    def obtener_formato(self, cuenta_id=None):
        return self.operations.obtener_formato_impresion(cuenta_id)

    def guardar_formato(self, cuenta_id, valores):
        return self.operations.guardar_formato_impresion(cuenta_id, valores)
