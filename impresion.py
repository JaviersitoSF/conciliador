from datetime import datetime

from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def probar_impresion_cheque_media_carta():
    print("--- Generando PDF a la medida del cheque ---")
    
    # medimos el cheque (Ancho x Alto)
    ancho_papel = 21.5 * cm
    alto_papel = 14.0 * cm
    
    # Le pasamos nuestras medidas exactas entre paréntesis (tupla)
    pdf = canvas.Canvas("cheque_media_carta.pdf", pagesize=(ancho_papel, alto_papel))
    
    # OJO: Como el papel ahora es más bajo (14cm), las coordenadas en "Y" 
    # no deben pasar de 14. Si pones 25 * cm, se imprimirá en el aire.
    
    pdf.drawString(15 * cm, 12 * cm, f"Fecha: {datetime.now().strftime('%Y-%m-%d')}")
    pdf.drawString(2 * cm, 10 * cm, "Páguese a: JAVIER SANCHEZ")
    pdf.drawString(16 * cm, 10 * cm, "$ 1,500.00")
    
    pdf.save()
    print("PDF de media carta generado.")

if __name__ == "__main__":
    probar_impresion_cheque_media_carta()
