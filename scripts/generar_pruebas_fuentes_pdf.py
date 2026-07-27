"""Genera controles para diagnosticar fuentes y posicionamiento en impresión PDF."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


SALIDA = Path(__file__).resolve().parents[1] / "diagnostics" / "pdf_fonts"
SANS = Path("/usr/share/fonts/liberation/LiberationSans-Regular.ttf")
MONO = Path("/usr/share/fonts/liberation/LiberationMono-Regular.ttf")
TEXTO = "AVATAR 0123456789 — ÁÉÍÓÚ Ñ / ancho horizontal"


def _fila_normal(pdf, fuente, tamano, x, y, etiqueta):
    pdf.setFont(fuente, tamano)
    pdf.drawString(x, y, f"{etiqueta}: {TEXTO}")


def _fila_caracteres(pdf, fuente, tamano, x, y, etiqueta):
    pdf.setFont(fuente, tamano)
    prefijo = f"{etiqueta}: "
    pdf.drawString(x, y, prefijo)
    cursor = x + pdfmetrics.stringWidth(prefijo, fuente, tamano)
    for caracter in TEXTO:
        pdf.drawString(cursor, y, caracter)
        cursor += pdfmetrics.stringWidth(caracter, fuente, tamano)


def _crear_vectorial(ruta, fuentes, fuente_inicial="Helvetica"):
    pdf = canvas.Canvas(
        str(ruta),
        pagesize=LETTER,
        pageCompression=0,
        initialFontName=fuente_inicial,
    )
    y = 750
    for etiqueta, fuente in fuentes:
        for tamano in (10, 12, 18):
            _fila_normal(pdf, fuente, tamano, 36, y, f"{etiqueta} normal {tamano} pt")
            y -= 28
            _fila_caracteres(
                pdf, fuente, tamano, 36, y, f"{etiqueta} carácter {tamano} pt"
            )
            y -= 38
    pdf.save()


def _crear_imagen(ruta):
    imagen = Image.new("L", (2400, 1500), "white")
    dibujo = ImageDraw.Draw(imagen)
    y = 40
    for archivo, etiqueta in ((SANS, "Liberation Sans"), (MONO, "Liberation Mono")):
        for puntos in (10, 12, 18):
            fuente = ImageFont.truetype(str(archivo), puntos * 4)
            dibujo.text(
                (40, y),
                f"{etiqueta} imagen {puntos} pt: {TEXTO}",
                font=fuente,
                fill="black",
            )
            y += puntos * 6
    imagen.convert("RGB").save(ruta, "PDF", resolution=300)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("LiberationSansAudit", str(SANS)))
    pdfmetrics.registerFont(TTFont("LiberationMonoAudit", str(MONO)))
    _crear_vectorial(
        SALIDA / "prueba_antes_sin_incrustar.pdf",
        (("Helvetica", "Helvetica"), ("Courier", "Courier")),
    )
    _crear_vectorial(
        SALIDA / "prueba_despues_incrustada.pdf",
        (
            ("Liberation Sans", "LiberationSansAudit"),
            ("Liberation Mono", "LiberationMonoAudit"),
        ),
        fuente_inicial="LiberationSansAudit",
    )
    _crear_imagen(SALIDA / "prueba_texto_como_imagen.pdf")


if __name__ == "__main__":
    main()
