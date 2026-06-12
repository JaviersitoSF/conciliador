"""Nucleo de la aplicacion Conciliador."""

from .errors import (
    ConflictoOperacion,
    ErrorOperacion,
    ErrorPersistencia,
    ErrorValidacion,
)
from .paths import AppPaths

__all__ = [
    "AppPaths",
    "ConflictoOperacion",
    "ErrorOperacion",
    "ErrorPersistencia",
    "ErrorValidacion",
]
