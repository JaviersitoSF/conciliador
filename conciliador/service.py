class ConciliadorService:
    """Fachada de casos de uso consumida por la interfaz gráfica."""

    def __init__(self, operations):
        self.operations = operations

    def listar_cuentas(self):
        return self.operations.listar_cuentas_bancarias()

    def crear_cuenta(self, banco, nombre, numero=""):
        return self.operations.crear_cuenta_bancaria(banco, nombre, numero)

    def emitir_cheque(self, *args, **kwargs):
        return self.operations.emitir_cheque_datos(*args, **kwargs)

    def anular_cheque(self, numero, cuenta_id=None):
        return self.operations.anular_cheque_numero(numero, cuenta_id)

    def reimprimir_cheque(self, numero, cuenta_id=None):
        return self.operations.reimprimir_cheque_numero(numero, cuenta_id)

    def registrar_deposito(self, *args, **kwargs):
        return self.operations.registrar_deposito_datos(*args, **kwargs)

    def obtener_cheques(self, cuenta_id=None):
        return self.operations.cargar_cheques_registrados(cuenta_id)

    def obtener_reporte(self, fecha=None, cuenta_id=None):
        return self.operations.obtener_reporte_movimientos(fecha, cuenta_id)

    def conciliar(self, cuenta_id=None, archivo_banco=None):
        return self.operations.obtener_conciliacion(cuenta_id, archivo_banco)

    def obtener_formato(self, cuenta_id=None):
        return self.operations.obtener_formato_impresion(cuenta_id)

    def guardar_formato(self, cuenta_id, valores):
        return self.operations.guardar_formato_impresion(cuenta_id, valores)
