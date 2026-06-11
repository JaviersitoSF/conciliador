"""Prueba rapida de la impresion de cheques sin registrar movimientos."""

from datetime import date
from decimal import Decimal

from main import imprimir_cheque_pdf


DATOS_CHEQUE_PRUEBA = {
    "num": "999999",
    "fecha": date.today().isoformat(),
    "nombre": "CHEQUE DE PRUEBA - NO PAGAR",
    "monto": Decimal("1234.56"),
    "descripcion": "PRUEBA DE IMPRESION - SIN VALOR",
}


def main():
    print("--- PRUEBA DE IMPRESION DE CHEQUE ---")
    print("Se usara la impresora predeterminada de Windows.")

    impresion_enviada = imprimir_cheque_pdf(
        **DATOS_CHEQUE_PRUEBA,
        archivo_salida="cheque_prueba.pdf",
    )

    if impresion_enviada:
        print("✅ Prueba enviada correctamente.")
    else:
        print("⚠️ No se pudo enviar la prueba. Revisa el mensaje anterior.")


if __name__ == "__main__":
    main()
