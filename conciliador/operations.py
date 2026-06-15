"""Fachada temporal de compatibilidad para los casos de uso públicos."""

from .analytics import ARCHIVO_BANCO, obtener_conciliacion, obtener_reporte_movimientos
from .domain import convertir_monto, normalizar_fecha, normalizar_numero_cheque
from .errors import ErrorOperacion
from .movements import (
    actualizar_cheque,
    actualizar_deposito,
    anular_cheque_numero,
    anular_deposito_numero,
    cargar_cheques_registrados,
    cargar_depositos_registrados,
    cheque_ya_registrado,
    emitir_cheque_datos,
    formatear_monto,
    guardar_cheque_en_archivo,
    registrar_deposito_datos,
    reimprimir_cheque_numero,
)
from .printing import (
    FORMATO_IMPRESION_DEFAULT,
    abrir_pdf_silenciosamente,
    formatear_fecha_cheque,
    formatear_monto_impresion,
    imprimir_cheque_pdf,
    probar_formato_impresion,
    validar_formato_impresion,
)
from .storage import (
    actualizar_cuenta_bancaria,
    crear_cuenta_bancaria,
    crear_respaldo,
    crear_respaldo_posterior,
    guardar_formato_impresion,
    inicializar_db,
    listar_cuentas_bancarias,
    obtener_cuenta,
    obtener_formato_impresion,
    registrar_auditoria,
    transaccion,
)
from . import storage


def configure_paths(paths):
    storage.configure_paths(paths)


def conectar_db():
    return storage.conectar_db()


def guardar_en_archivo(num, fecha, nombre, monto, descripcion="", cuenta_id=None):
    guardar_cheque_en_archivo(num, fecha, nombre, monto, descripcion, cuenta_id)


def __getattr__(name):
    if name in {"ARCHIVO_DATOS", "DIRECTORIO_RESPALDOS", "MAX_RESPALDOS"}:
        return getattr(storage, name)
    raise AttributeError(name)
