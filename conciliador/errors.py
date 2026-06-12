class ErrorOperacion(ValueError):
    """Error esperado que puede mostrarse directamente al usuario."""


class ErrorValidacion(ErrorOperacion):
    """Los datos de entrada no cumplen las reglas del dominio."""


class ConflictoOperacion(ErrorOperacion):
    """La operacion entra en conflicto con el estado almacenado."""


class ErrorPersistencia(ErrorOperacion):
    """La operacion no pudo completarse en la base de datos."""
