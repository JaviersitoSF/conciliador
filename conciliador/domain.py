import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .errors import ErrorValidacion

PATRON_MONTO = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")
PATRON_NUMERO_CHEQUE = re.compile(r"^\d+(?:\.0+)?$")
PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class CuentaBancaria:
    id: int
    banco: str
    nombre: str
    numero: str = ""
    activa: bool = True


@dataclass(frozen=True)
class Cheque:
    cuenta_id: int
    numero: str
    fecha: str
    nombre: str
    monto: Decimal
    estado: str = "TRANSITO"
    descripcion: str = ""


@dataclass(frozen=True)
class Deposito:
    cuenta_id: int
    numero: str
    fecha: str
    descripcion: str
    monto: Decimal


@dataclass(frozen=True)
class FormatoImpresion:
    ancho: float
    alto: float
    fecha_x: float
    fecha_y: float
    nombre_x: float
    nombre_y: float
    monto_x: float
    monto_y: float
    no_negociable_x: float
    no_negociable_y: float
    monto_letras_x: float
    monto_letras_y: float
    descripcion_x: float
    descripcion_y: float


def convertir_monto(valor):
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    try:
        if valor != valor:
            return None
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None
    negativo = texto.startswith("(") and texto.endswith(")")
    if negativo:
        texto = texto[1:-1].strip()
        if texto.startswith(("+", "-", "−")):
            return None
    texto = (
        texto.replace("Q", "")
        .replace("q", "")
        .replace("$", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("−", "-")
    )
    if not PATRON_MONTO.fullmatch(texto):
        return None
    try:
        monto = Decimal(texto.replace(",", ""))
    except InvalidOperation:
        return None
    if negativo:
        monto = -monto
    return monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalizar_numero_cheque(valor):
    if valor is None:
        return None
    try:
        if valor != valor:
            return None
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan" or not PATRON_NUMERO_CHEQUE.fullmatch(texto):
        return None
    numero = int(texto.split(".", 1)[0])
    return str(numero) if numero > 0 else None


def normalizar_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor or "").strip()
    if not PATRON_FECHA.fullmatch(texto):
        raise ErrorValidacion("⚠️ La fecha debe usar el formato AAAA-MM-DD.")
    try:
        datetime.strptime(texto, "%Y-%m-%d")
    except ValueError as exc:
        raise ErrorValidacion("⚠️ La fecha indicada no es válida.") from exc
    return texto
