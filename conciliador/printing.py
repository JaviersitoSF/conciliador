import os
import platform
import subprocess
from datetime import datetime
from decimal import Decimal

from num2words import num2words
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .domain import convertir_monto
from .errors import ErrorOperacion

FORMATO_IMPRESION_DEFAULT = {
    "ancho": 22.0,
    "alto": 14.0,
    "fecha_x": 1.8,
    "fecha_y": 13.0,
    "nombre_x": 1.9,
    "nombre_y": 12.1,
    "monto_x": 15.0,
    "monto_y": 13.0,
    "no_negociable_x": 2.5,
    "no_negociable_y": 10.0,
    "monto_letras_x": 1.0,
    "monto_letras_y": 11.2,
    "descripcion_x": 2.5,
    "descripcion_y": 5.9,
}


def validar_formato_impresion(valores):
    formato = {}
    for campo in FORMATO_IMPRESION_DEFAULT:
        try:
            valor = float(valores[campo])
        except (KeyError, TypeError, ValueError) as exc:
            raise ErrorOperacion(
                f"⚠️ El valor de {campo.replace('_', ' ')} debe ser numérico."
            ) from exc
        if valor < 0:
            raise ErrorOperacion("⚠️ Los valores del formato no pueden ser negativos.")
        formato[campo] = valor
    if formato["ancho"] <= 0 or formato["alto"] <= 0:
        raise ErrorOperacion("⚠️ El ancho y el alto deben ser mayores que cero.")
    for campo, valor in formato.items():
        if campo.endswith("_x") and valor > formato["ancho"]:
            raise ErrorOperacion(f"⚠️ {campo.replace('_', ' ')} queda fuera del cheque.")
        if campo.endswith("_y") and valor > formato["alto"]:
            raise ErrorOperacion(f"⚠️ {campo.replace('_', ' ')} queda fuera del cheque.")
    return formato


def formatear_monto(valor):
    monto = convertir_monto(valor)
    if monto is None:
        raise ValueError("Monto invalido")
    return f"{monto:.2f}"


def formatear_monto_impresion(valor):
    monto = convertir_monto(valor)
    if monto is None:
        raise ValueError("Monto invalido")
    return f"{monto:,.2f}"


def formatear_fecha_cheque(fecha):
    texto = str(fecha).strip()
    try:
        fecha_dt = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return texto
    meses = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    return f"{fecha_dt.day} de {meses[fecha_dt.month - 1]} del {fecha_dt.year}"


def abrir_pdf_silenciosamente(comando):
    try:
        subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detalle = (exc.stderr or exc.stdout or "").strip()
        if detalle:
            raise RuntimeError(detalle) from exc
        raise RuntimeError(f"el comando fallo con codigo {exc.returncode}") from exc


def imprimir_cheque_pdf(
    num, fecha, nombre, monto, descripcion="", archivo_salida=None, formato=None
):
    formato = validar_formato_impresion(formato or FORMATO_IMPRESION_DEFAULT)
    alto_cheque = formato["alto"] * cm
    ancho_cheque = formato["ancho"] * cm
    nombre_pdf = archivo_salida or f"cheque_{num}.pdf"
    sistema = platform.system()
    pdf = canvas.Canvas(nombre_pdf, pagesize=(ancho_cheque, alto_cheque))
    monto_formateado = formatear_monto_impresion(monto)
    entero, centavos = formatear_monto(monto).split(".")
    monto_en_letras = num2words(int(entero), lang="es").upper()
    texto_oficial = f"{monto_en_letras} QUETZALES CON {centavos}/100"
    pdf.drawString(
        formato["fecha_x"] * cm,
        formato["fecha_y"] * cm,
        f"Guatemala {formatear_fecha_cheque(fecha)}",
    )
    pdf.drawString(formato["nombre_x"] * cm, formato["nombre_y"] * cm, nombre)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(formato["monto_x"] * cm, formato["monto_y"] * cm, monto_formateado)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        formato["no_negociable_x"] * cm,
        formato["no_negociable_y"] * cm,
        "NO NEGOCIABLE",
    )
    ancho = max(1 * cm, ancho_cheque - formato["monto_letras_x"] * cm - 1 * cm)
    tamano = min(10, ancho * 10 / stringWidth(texto_oficial, "Helvetica", 10))
    pdf.setFont("Helvetica", max(7, tamano))
    pdf.drawString(
        formato["monto_letras_x"] * cm,
        formato["monto_letras_y"] * cm,
        texto_oficial,
    )
    pdf.setFont("Helvetica", 10)
    if descripcion:
        pdf.drawString(
            formato["descripcion_x"] * cm,
            formato["descripcion_y"] * cm,
            descripcion,
        )
    pdf.save()
    print(f"🖨️  PDF generado: {nombre_pdf}")
    try:
        if sistema == "Windows":
            startfile = getattr(os, "startfile", None)
            if not callable(startfile):
                raise AttributeError("os.startfile no esta disponible en este entorno")
            startfile(nombre_pdf, "print")
        elif sistema == "Darwin":
            abrir_pdf_silenciosamente([
                "lp", "-o",
                f"media=Custom.{formato['ancho'] * 10:g}x{formato['alto'] * 10:g}mm",
                "-o", "scaling=100", "-o", "position=top-left", nombre_pdf,
            ])
        else:
            abrir_pdf_silenciosamente(["xdg-open", nombre_pdf])
    except Exception as exc:
        print(f"⚠️ Abre el PDF manual. Error: {exc}")
        return False
    return True


def probar_formato_impresion(valores, archivo_salida="prueba_formato_cheque.pdf"):
    return imprimir_cheque_pdf(
        "0001",
        datetime.now().strftime("%Y-%m-%d"),
        "NOMBRE DE BENEFICIARIO",
        Decimal("1234.56"),
        "DESCRIPCION DE PRUEBA",
        archivo_salida=archivo_salida,
        formato=validar_formato_impresion(valores),
    )
