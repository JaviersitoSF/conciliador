import os
import platform
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .domain import convertir_monto
from .errors import ErrorOperacion

DIRECTORIO_EXPORTACIONES = Path(".")

# Se reemplazan también los nombres base que algunos Flowables seleccionan para
# fragmentos vacíos; así ningún recurso Helvetica queda sin incrustar.
FUENTE_REGULAR = "Helvetica"
FUENTE_NEGRITA = "Helvetica-Bold"


def _registrar_fuentes_pdf():
    """Registra fuentes TrueType que ReportLab incrusta dentro de cada PDF."""
    directorio_fuentes = Path(__import__("reportlab").__file__).parent / "fonts"
    pdfmetrics.registerFont(
        TTFont(FUENTE_REGULAR, str(directorio_fuentes / "Vera.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont(FUENTE_NEGRITA, str(directorio_fuentes / "VeraBd.ttf"))
    )
    pdfmetrics.registerFontFamily(
        FUENTE_REGULAR,
        normal=FUENTE_REGULAR,
        bold=FUENTE_NEGRITA,
    )


_registrar_fuentes_pdf()


def _crear_canvas_pdf(*args, **kwargs):
    kwargs.setdefault("initialFontName", FUENTE_REGULAR)
    return canvas.Canvas(*args, **kwargs)


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


def configure_paths(paths):
    global DIRECTORIO_EXPORTACIONES
    DIRECTORIO_EXPORTACIONES = paths.exports_dir


def resolver_archivo_salida(archivo_salida):
    ruta = Path(archivo_salida)
    if not ruta.is_absolute():
        ruta = DIRECTORIO_EXPORTACIONES / ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


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
        detalle_error = getattr(exc, "stderr", "")
        detalle = str(detalle_error).strip() if detalle_error else ""
        if detalle:
            raise RuntimeError(detalle) from exc
        raise RuntimeError("No se pudo completar el comando de impresión.") from exc


def abrir_pdf(ruta):
    """Abre un PDF en el visor predeterminado, sin enviarlo a impresión."""
    ruta = str(Path(ruta).resolve())
    sistema = platform.system()
    if sistema == "Windows":
        startfile = getattr(os, "startfile", None)
        if not callable(startfile):
            raise RuntimeError("No se encontró una aplicación para abrir el PDF.")
        startfile(ruta)
    elif sistema == "Darwin":
        abrir_pdf_silenciosamente(["open", ruta])
    else:
        abrir_pdf_silenciosamente(["xdg-open", ruta])


def _monto_o_cero(valor):
    monto = convertir_monto(valor)
    return monto if monto is not None else Decimal("0.00")


def _total_movimientos(filas, campo="monto"):
    return sum(
        (_monto_o_cero(fila.get(campo)) for fila in filas),
        Decimal("0.00"),
    )


def _filas_compatibles(resultado, clave, clave_diferencias, descripciones):
    """Obtiene una categoría nueva o la reconstruye de resultados anteriores."""
    if clave in resultado:
        return resultado.get(clave) or []
    descripciones = tuple(texto.casefold() for texto in descripciones)
    return [
        fila
        for fila in resultado.get(clave_diferencias, []) or []
        if str(fila.get("diferencia", "")).casefold() in descripciones
    ]


def calcular_resumen_conciliacion(resultado):
    """Calcula los ajustes que llevan del saldo en libros al saldo bancario.

    Los cheques y notas de débito locales pendientes, así como los créditos
    bancarios aún no registrados, se suman al saldo en libros. Los depósitos
    en tránsito y débitos bancarios aún no registrados se restan.
    """
    cheques_transito = resultado.get("cheques_transito", []) or []
    depositos_transito = _filas_compatibles(
        resultado,
        "depositos_no_ingresados",
        "diferencias_depositos",
        ("Pendiente en banco",),
    )
    creditos_banco = _filas_compatibles(
        resultado,
        "depositos_banco_sin_registro",
        "diferencias_depositos",
        ("No registrado localmente", "No registrada localmente"),
    )
    notas_debito_transito = _filas_compatibles(
        resultado,
        "notas_debito_locales_sin_banco",
        "diferencias_notas_debito",
        ("No aparece en el banco",),
    )
    debitos_banco = _filas_compatibles(
        resultado,
        "notas_debito_no_ingresadas",
        "diferencias_notas_debito",
        ("No registrada localmente", "No registrado localmente"),
    )
    notas_credito_banco = resultado.get("notas_credito_banco", []) or []

    ajustes = {
        "cheques_transito": _total_movimientos(
            cheques_transito, "monto_nuestro"
        ),
        "notas_debito_transito": _total_movimientos(notas_debito_transito),
        "creditos_banco": _total_movimientos(creditos_banco),
        "notas_credito_banco": _total_movimientos(notas_credito_banco),
        "debitos_banco": _total_movimientos(debitos_banco),
        "depositos_transito": _total_movimientos(depositos_transito),
    }

    estado = resultado.get("estado_cuenta", {}) or {}
    saldo_banco = convertir_monto(estado.get("saldo_final"))
    saldo_libros = convertir_monto(
        resultado.get("saldo_libros", estado.get("saldo_libros"))
    )
    saldo_libros_calculado = False
    if saldo_libros is None and saldo_banco is not None:
        saldo_libros = (
            saldo_banco
            - ajustes["cheques_transito"]
            - ajustes["notas_debito_transito"]
            - ajustes["creditos_banco"]
            - ajustes["notas_credito_banco"]
            + ajustes["debitos_banco"]
            + ajustes["depositos_transito"]
        )
        saldo_libros_calculado = True

    saldo_conciliado = None
    if saldo_libros is not None:
        saldo_conciliado = (
            saldo_libros
            + ajustes["cheques_transito"]
            + ajustes["notas_debito_transito"]
            + ajustes["creditos_banco"]
            + ajustes["notas_credito_banco"]
            - ajustes["debitos_banco"]
            - ajustes["depositos_transito"]
        )
    diferencia = (
        saldo_conciliado - saldo_banco
        if saldo_conciliado is not None and saldo_banco is not None
        else None
    )
    return {
        "saldo_libros": saldo_libros,
        "saldo_libros_calculado": saldo_libros_calculado,
        **ajustes,
        "saldo_conciliado": saldo_conciliado,
        "saldo_banco": saldo_banco,
        "diferencia": diferencia,
    }


def _parrafo(valor, estilo):
    texto = "" if valor is None else str(valor)
    return Paragraph(escape(texto), estilo)


def _monto_resumen(valor, simbolo):
    if valor is None:
        return "N/D"
    return f"{simbolo} {formatear_monto_impresion(valor)}"


def _fecha_resumen(valor):
    texto = str(valor or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha = datetime.strptime(texto, formato)
            break
        except ValueError:
            fecha = None
    if fecha is None:
        return texto or "N/D"
    meses = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
        "Diciembre",
    )
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


def _tabla_pdf(datos, anchos, filas_vacias=False):
    tabla = Table(datos, colWidths=anchos, repeatRows=1, hAlign="LEFT")
    instrucciones = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")),
        ("FONTNAME", (0, 0), (-1, 0), FUENTE_NEGRITA),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#808080")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if filas_vacias:
        instrucciones.append(("SPAN", (0, 1), (-1, 1)))
    tabla.setStyle(TableStyle(instrucciones))
    return tabla


def _pie_pagina(lienzo, documento, incluir_firmas=False):
    lienzo.saveState()
    lienzo.setStrokeColor(colors.HexColor("#808080"))
    lienzo.setFillColor(colors.HexColor("#404040"))
    if incluir_firmas:
        ancho_util = LETTER[0] - 3 * cm
        ancho_firma = 4.6 * cm
        separacion = (ancho_util - 3 * ancho_firma) / 2
        x = 1.5 * cm
        for etiqueta in ("Elaborado por", "Revisado por", "Autorizado por"):
            lienzo.line(x, 1.65 * cm, x + ancho_firma, 1.65 * cm)
            lienzo.setFont(FUENTE_REGULAR, 7.5)
            lienzo.drawCentredString(x + ancho_firma / 2, 1.3 * cm, etiqueta)
            x += ancho_firma + separacion
    lienzo.setFont(FUENTE_REGULAR, 7.5)
    lienzo.drawString(1.5 * cm, 0.65 * cm, "Conciliación bancaria")
    lienzo.drawRightString(
        LETTER[0] - 1.5 * cm,
        0.65 * cm,
        f"Página {documento.page}",
    )
    lienzo.restoreState()


def _pie_resumen(lienzo, documento):
    _pie_pagina(lienzo, documento, incluir_firmas=True)


def _pie_detalle(lienzo, documento):
    _pie_pagina(lienzo, documento)


def exportar_conciliacion_pdf(resultado, archivo_salida):
    """Exporta un resumen contable y el detalle, en páginas carta verticales."""
    nombre_pdf = resolver_archivo_salida(archivo_salida)
    estilos = getSampleStyleSheet()
    documento = SimpleDocTemplate(
        str(nombre_pdf),
        pagesize=LETTER,
        rightMargin=1.35 * cm,
        leftMargin=1.35 * cm,
        topMargin=1.1 * cm,
        bottomMargin=2.25 * cm,
        title="Conciliación bancaria",
    )
    cuenta = resultado.get("cuenta", {}) or {}
    estado = resultado.get("estado_cuenta", {}) or {}
    moneda = estado.get("moneda", "GTQ")
    simbolo = "$" if moneda == "USD" else "Q"
    corte = resultado.get("fecha_corte") or estado.get("fecha_fin") or "N/D"
    estilo_titulo = ParagraphStyle(
        "TituloConciliacion",
        parent=estilos["Title"],
        fontName=FUENTE_NEGRITA,
        fontSize=17,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=3,
    )
    estilo_centrado = ParagraphStyle(
        "CentradoConciliacion",
        parent=estilos["Normal"],
        fontName=FUENTE_REGULAR,
        alignment=TA_CENTER,
        fontSize=9,
        leading=11,
    )
    estilo_celda = ParagraphStyle(
        "CeldaConciliacion",
        parent=estilos["BodyText"],
        fontName=FUENTE_REGULAR,
        fontSize=7.5,
        leading=9,
    )
    estilo_celda_derecha = ParagraphStyle(
        "CeldaDerechaConciliacion",
        parent=estilo_celda,
        alignment=TA_RIGHT,
    )
    estilo_seccion = ParagraphStyle(
        "SeccionConciliacion",
        parent=estilos["Heading2"],
        fontName=FUENTE_NEGRITA,
        fontSize=11,
        leading=13,
        spaceBefore=5,
        spaceAfter=3,
        keepWithNext=True,
    )

    nombre_cuenta = cuenta.get("nombre") or estado.get("nombre") or "N/D"
    numero_cuenta = cuenta.get("numero") or estado.get("numero") or "N/D"
    moneda_nombre = "DÓLARES" if moneda == "USD" else "QUETZALES"
    resumen = calcular_resumen_conciliacion(resultado)
    elementos = [
        _parrafo(cuenta.get("banco", ""), estilo_centrado),
        _parrafo("CONCILIACIÓN BANCARIA", estilo_titulo),
        _parrafo(f"AL {_fecha_resumen(corte)}", estilo_centrado),
        _parrafo(
            f"Cantidades expresadas en: {simbolo} · {moneda_nombre}",
            estilo_centrado,
        ),
        Spacer(1, 0.25 * cm),
    ]

    datos_cuenta = [
        [_parrafo("No. de cuenta", estilo_celda), _parrafo(numero_cuenta, estilo_celda)],
        [_parrafo("Nombre de cuenta", estilo_celda), _parrafo(nombre_cuenta, estilo_celda)],
    ]
    tabla_cuenta = Table(datos_cuenta, colWidths=(3.6 * cm, 11.8 * cm), hAlign="CENTER")
    tabla_cuenta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), FUENTE_NEGRITA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    elementos.extend((tabla_cuenta, Spacer(1, 0.3 * cm)))

    etiqueta_libros = "Saldo según libros"
    if resumen["saldo_libros_calculado"]:
        etiqueta_libros += " (calculado)"
    filas_resumen = (
        (etiqueta_libros, resumen["saldo_libros"]),
        ("(+) Cheques en circulación", resumen["cheques_transito"]),
        ("(+) Notas de débito en tránsito", resumen["notas_debito_transito"]),
        ("(+) Créditos bancarios no registrados", resumen["creditos_banco"]),
        ("(+) Notas de crédito operadas por el banco", resumen["notas_credito_banco"]),
        ("(-) Débitos bancarios no registrados", resumen["debitos_banco"]),
        ("(-) Depósitos en tránsito", resumen["depositos_transito"]),
        ("Saldo conciliado", resumen["saldo_conciliado"]),
        ("Saldo según estado de cuenta", resumen["saldo_banco"]),
        ("Diferencia", resumen["diferencia"]),
    )
    datos_resumen = [
        [_parrafo(etiqueta, estilo_celda), _parrafo(_monto_resumen(valor, simbolo), estilo_celda_derecha)]
        for etiqueta, valor in filas_resumen
    ]
    tabla_resumen = Table(
        datos_resumen,
        colWidths=(13.2 * cm, 5.1 * cm),
        hAlign="CENTER",
    )
    tabla_resumen.setStyle(TableStyle([
        ("LINEABOVE", (0, 7), (-1, 7), 0.8, colors.HexColor("#404040")),
        ("LINEABOVE", (0, 9), (-1, 9), 0.8, colors.HexColor("#404040")),
        ("FONTNAME", (0, 0), (-1, 0), FUENTE_NEGRITA),
        ("FONTNAME", (0, 7), (-1, -1), FUENTE_NEGRITA),
        ("BACKGROUND", (0, 8), (-1, 8), colors.HexColor("#EDF3F8")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    elementos.extend((tabla_resumen, Spacer(1, 0.18 * cm)))
    if resumen["saldo_libros_calculado"]:
        elementos.append(_parrafo(
            "El saldo según libros se despejó del saldo bancario y de los ajustes "
            "pendientes; no corresponde al saldo neto de un reporte mensual.",
            ParagraphStyle(
                "NotaSaldoCalculado",
                parent=estilo_celda,
                fontSize=6.8,
                leading=8,
                textColor=colors.HexColor("#505050"),
            ),
        ))
    elif resumen["saldo_banco"] is None:
        elementos.append(_parrafo(
            "El archivo importado no proporcionó saldo final. Los ajustes se "
            "muestran, pero los saldos y la diferencia quedan como N/D.",
            ParagraphStyle(
                "NotaSaldoNoDisponible",
                parent=estilo_celda,
                fontSize=6.8,
                leading=8,
                textColor=colors.HexColor("#8A3B12"),
            ),
        ))

    elementos.append(_parrafo("CHEQUES EN CIRCULACIÓN", estilo_seccion))
    cheques_resumen = resultado.get("cheques_transito", []) or []
    limite_cheques_resumen = 10
    encabezados_cheques = ("# Docto.", "Fecha", "Beneficiario", "Valor")
    datos_cheques = [[_parrafo(valor, estilo_celda) for valor in encabezados_cheques]]
    for fila in cheques_resumen[:limite_cheques_resumen]:
        datos_cheques.append([
            _parrafo(fila.get("num", "S/N"), estilo_celda),
            _parrafo(fila.get("fecha") or "N/D", estilo_celda),
            _parrafo(fila.get("nombre") or "N/D", estilo_celda),
            _parrafo(
                _monto_resumen(_monto_o_cero(fila.get("monto_nuestro")), simbolo),
                estilo_celda_derecha,
            ),
        ])
    sin_cheques = not cheques_resumen
    if sin_cheques:
        datos_cheques.append([
            _parrafo("Sin cheques en circulación", estilo_celda),
            _parrafo("", estilo_celda),
            _parrafo("", estilo_celda),
            _parrafo("", estilo_celda),
        ])
    datos_cheques.append([
        _parrafo("TOTAL CHEQUES EN CIRCULACIÓN", estilo_celda_derecha),
        _parrafo("", estilo_celda),
        _parrafo("", estilo_celda),
        _parrafo(
            _monto_resumen(resumen["cheques_transito"], simbolo),
            estilo_celda_derecha,
        ),
    ])
    tabla_cheques_resumen = _tabla_pdf(
        datos_cheques,
        (2.5 * cm, 3.0 * cm, 9.5 * cm, 3.3 * cm),
        filas_vacias=sin_cheques,
    )
    tabla_cheques_resumen.setStyle(TableStyle([
        ("SPAN", (0, -1), (2, -1)),
        ("FONTNAME", (0, -1), (-1, -1), FUENTE_NEGRITA),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#404040")),
        ("ALIGN", (0, -1), (-1, -1), "RIGHT"),
    ]))
    elementos.append(tabla_cheques_resumen)
    if len(cheques_resumen) > limite_cheques_resumen:
        elementos.append(_parrafo(
            f"Se muestran {limite_cheques_resumen} de {len(cheques_resumen)} "
            "cheques; el detalle completo continúa en las páginas siguientes.",
            estilo_celda,
        ))
    elementos.append(PageBreak())
    elementos.extend((
        _parrafo("DETALLE DE CONCILIACIÓN", estilo_titulo),
        _parrafo(
            f"{cuenta.get('banco', '')} · {nombre_cuenta} · Cuenta {numero_cuenta} · "
            f"Corte {_fecha_resumen(corte)} · Moneda {moneda}",
            estilo_centrado,
        ),
        Spacer(1, 0.25 * cm),
    ))

    secciones = (
        (
            "Cheques en tránsito",
            ("Número", "Monto", "Detalle"),
            resultado["cheques_transito"],
            lambda fila: (
                fila.get("num", "S/N"),
                f"{simbolo} {formatear_monto_impresion(fila.get('monto_nuestro') or 0)}",
                fila.get("mensaje", ""),
            ),
            (2.5 * cm, 3.3 * cm, 12.5 * cm),
        ),
        (
            "Diferencias de depósitos",
            ("Número", "Fecha", "Descripción", "Monto", "Diferencia"),
            resultado.get("diferencias_depositos", []),
            lambda fila: (
                fila.get("num", "S/N"), fila.get("fecha", "N/D"), fila.get("descripcion", ""),
                f"{simbolo} {formatear_monto_impresion(fila.get('monto') or 0)}",
                fila.get("diferencia", ""),
            ),
            (2.2 * cm, 2.6 * cm, 5.5 * cm, 3.0 * cm, 5.0 * cm),
        ),
        (
            "Diferencias de notas de débito",
            ("Número", "Fecha", "Descripción", "Monto", "Diferencia"),
            resultado.get("diferencias_notas_debito", []),
            lambda fila: (
                fila.get("num", "S/N"), fila.get("fecha", "N/D"), fila.get("descripcion", ""),
                f"{simbolo} {formatear_monto_impresion(fila.get('monto') or 0)}",
                fila.get("diferencia", ""),
            ),
            (2.2 * cm, 2.6 * cm, 5.5 * cm, 3.0 * cm, 5.0 * cm),
        ),
    )
    for titulo, encabezados, filas, convertir, anchos in secciones:
        elementos.append(_parrafo(titulo, estilo_seccion))
        datos = [[_parrafo(valor, estilo_celda) for valor in encabezados]]
        datos.extend(
            [_parrafo(valor, estilo_celda) for valor in convertir(fila)]
            for fila in filas
        )
        if not filas:
            datos.append([
                _parrafo("Sin registros" if indice == 0 else "", estilo_celda)
                for indice in range(len(encabezados))
            ])
        tabla = _tabla_pdf(datos, anchos, filas_vacias=not filas)
        elementos.extend((tabla, Spacer(1, 0.25 * cm)))

    documento.build(
        elementos,
        onFirstPage=_pie_resumen,
        onLaterPages=_pie_detalle,
        canvasmaker=_crear_canvas_pdf,
    )
    abrir_pdf(nombre_pdf)
    return nombre_pdf


def imprimir_cheque_pdf(
    num, fecha, nombre, monto, descripcion="", archivo_salida=None, formato=None
):
    formato = validar_formato_impresion(formato or FORMATO_IMPRESION_DEFAULT)
    alto_cheque = formato["alto"] * cm
    ancho_cheque = formato["ancho"] * cm
    nombre_pdf = resolver_archivo_salida(archivo_salida or f"cheque_{num}.pdf")
    sistema = platform.system()
    if sistema == "Windows":
        pdf = _crear_canvas_pdf(str(nombre_pdf), pagesize=LETTER)
        pdf.translate(0, LETTER[1] - alto_cheque)
    else:
        pdf = _crear_canvas_pdf(
            str(nombre_pdf), pagesize=(ancho_cheque, alto_cheque)
        )
    monto_formateado = formatear_monto_impresion(monto)
    entero, centavos = formatear_monto(monto).split(".")
    try:
        monto_entero = int(entero)
    except (TypeError, ValueError) as exc:
        raise ErrorOperacion("El monto del cheque no es válido.") from exc
    monto_en_letras = num2words(monto_entero, lang="es").upper()
    texto_oficial = f"{monto_en_letras} QUETZALES CON {centavos}/100"
    pdf.setFont(FUENTE_REGULAR, 10)
    pdf.drawString(
        formato["fecha_x"] * cm,
        formato["fecha_y"] * cm,
        f"Guatemala {formatear_fecha_cheque(fecha)}",
    )
    pdf.drawString(formato["nombre_x"] * cm, formato["nombre_y"] * cm, nombre)
    pdf.setFont(FUENTE_NEGRITA, 12)
    pdf.drawString(formato["monto_x"] * cm, formato["monto_y"] * cm, monto_formateado)
    pdf.setFont(FUENTE_REGULAR, 10)
    pdf.drawString(
        formato["no_negociable_x"] * cm,
        formato["no_negociable_y"] * cm,
        "NO NEGOCIABLE",
    )
    ancho = max(1 * cm, ancho_cheque - formato["monto_letras_x"] * cm - 1 * cm)
    tamano = min(10, ancho * 10 / stringWidth(texto_oficial, FUENTE_REGULAR, 10))
    pdf.setFont(FUENTE_REGULAR, max(7, tamano))
    pdf.drawString(
        formato["monto_letras_x"] * cm,
        formato["monto_letras_y"] * cm,
        texto_oficial,
    )
    pdf.setFont(FUENTE_REGULAR, 10)
    if descripcion:
        texto_descripcion = pdf.beginText(
            formato["descripcion_x"] * cm,
            formato["descripcion_y"] * cm,
        )
        texto_descripcion.setFont(FUENTE_REGULAR, 10)
        texto_descripcion.setLeading(12)
        for linea in str(descripcion).splitlines() or [""]:
            texto_descripcion.textLine(linea)
        pdf.drawText(texto_descripcion)
    pdf.save()
    print(f"🖨️  PDF generado: {nombre_pdf}")
    impresion_enviada = True
    try:
        if sistema == "Windows":
            startfile = getattr(os, "startfile", None)
            if not callable(startfile):
                raise AttributeError("os.startfile no esta disponible en este entorno")
            try:
                startfile(str(nombre_pdf), "print")
            except Exception:
                abrir_pdf(nombre_pdf)
                impresion_enviada = False
        elif sistema == "Darwin":
            abrir_pdf_silenciosamente([
                "lp", "-o",
                f"media=Custom.{formato['ancho'] * 10:g}x{formato['alto'] * 10:g}mm",
                "-o", "scaling=100", "-o", "position=top-left", str(nombre_pdf),
            ])
        else:
            abrir_pdf_silenciosamente(["xdg-open", str(nombre_pdf)])
    except Exception as exc:
        print(f"⚠️ Abre el PDF manual. Error: {exc}")
        return False
    return impresion_enviada


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
