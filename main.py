import csv
import os
import platform
import subprocess
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd
from num2words import num2words
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

ARCHIVO_CHEQUES = "cheques_emitidos.csv"
ARCHIVO_BANCO = "estado_cuenta.xlsx"
ARCHIVO_DEPOSITOS = "depositos.csv"


def crear_dataframe_vacio(columnas):
    df = pd.DataFrame(columns=columnas + ["Monto_valor", "Fecha_dt"])
    df["Monto_valor"] = pd.Series(dtype=object)
    df["Fecha_dt"] = pd.to_datetime(pd.Series(dtype=object))
    return df


def convertir_monto(valor):
    if valor is None:
        return None

    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    try:
        if pd.isna(valor):
            return None
    except TypeError:
        pass

    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None

    negativo = texto.startswith("(") and texto.endswith(")")
    if negativo:
        texto = texto[1:-1]

    texto = (
        texto.replace("Q", "")
        .replace("q", "")
        .replace("$", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace(",", "")
        .replace("−", "-")
    )

    if texto in {"", "-", ".", "-.", "--"}:
        return None

    try:
        monto = Decimal(texto)
    except InvalidOperation:
        return None

    if negativo:
        monto = -monto

    return monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def formatear_monto(valor):
    monto = convertir_monto(valor)
    if monto is None:
        raise ValueError("Monto invalido")
    return f"{monto:.2f}"


def normalizar_numero_cheque(valor):
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except TypeError:
        pass

    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return None

    if texto.endswith(".0"):
        texto = texto[:-2]

    if texto.isdigit():
        numero = int(texto)
        return str(numero) if numero > 0 else None

    try:
        numero_decimal = Decimal(texto)
    except InvalidOperation:
        return None

    if numero_decimal != numero_decimal.to_integral_value(rounding=ROUND_HALF_UP):
        return None

    numero = int(numero_decimal)
    return str(numero) if numero > 0 else None


def pedir_texto_no_vacio(mensaje):
    while True:
        texto = input(mensaje).strip()
        if texto:
            return texto
        print("⚠️ Error: el campo no puede quedar vacío.")


def pedir_monto_positivo(mensaje):
    while True:
        texto = input(mensaje).strip()
        monto = convertir_monto(texto)
        if monto is None:
            print("⚠️ Error: Solo usar números y punto decimal.")
            continue
        if monto <= 0:
            print("⚠️ Error: El monto debe ser mayor que cero.")
            continue
        return monto


def pedir_numero_cheque(mensaje):
    while True:
        texto = input(mensaje).strip()
        if not texto:
            print("⚠️ Error: el número de cheque no puede quedar vacío.")
            continue
        if not texto.isdigit():
            print("⚠️ Error: el número de cheque debe contener solo dígitos.")
            continue

        numero = int(texto)
        if numero <= 0:
            print("⚠️ Error: el número de cheque debe ser mayor que cero.")
            continue

        return str(numero)


def cargar_cheques_registrados():
    columnas = ["Num", "Fecha", "Nombre", "Monto", "Estado"]
    vacio = crear_dataframe_vacio(columnas)
    vacio["Num_norm"] = pd.Series(dtype=object)

    if not os.path.exists(ARCHIVO_CHEQUES):
        return vacio

    try:
        df = pd.read_csv(
            ARCHIVO_CHEQUES,
            names=columnas,
            header=None,
            dtype=str,
            keep_default_na=False,
        )
    except pd.errors.EmptyDataError:
        return vacio

    if df.empty:
        return vacio

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = ""

    df = df.fillna("")
    df = df[df[columnas].apply(lambda fila: any(str(valor).strip() for valor in fila), axis=1)].copy()

    for columna in columnas:
        df[columna] = df[columna].astype(str).str.strip()

    df["Estado"] = df["Estado"].str.upper()
    df.loc[df["Estado"].isin(["", "NAN"]), "Estado"] = "TRANSITO"
    df["Num_norm"] = df["Num"].map(normalizar_numero_cheque)
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df


def cargar_depositos_registrados():
    columnas = ["Fecha", "Descripcion", "Monto"]
    vacio = crear_dataframe_vacio(columnas)

    if not os.path.exists(ARCHIVO_DEPOSITOS):
        return vacio

    try:
        df = pd.read_csv(
            ARCHIVO_DEPOSITOS,
            names=columnas,
            header=None,
            dtype=str,
            keep_default_na=False,
        )
    except pd.errors.EmptyDataError:
        return vacio

    if df.empty:
        return vacio

    for columna in columnas:
        if columna not in df.columns:
            df[columna] = ""

    df = df.fillna("")
    df = df[df[columnas].apply(lambda fila: any(str(valor).strip() for valor in fila), axis=1)].copy()

    for columna in columnas:
        df[columna] = df[columna].astype(str).str.strip()

    df["Descripcion"] = df["Descripcion"].str.upper()
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df


def cheque_ya_registrado(numero):
    df = cargar_cheques_registrados()
    if df.empty or "Num_norm" not in df.columns:
        return False
    return df["Num_norm"].eq(numero).any()


def registrar_deposito():
    print("\n--- REGISTRO DE DEPÓSITO ---")
    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    monto = pedir_monto_positivo("Monto del depósito (ej. 5000.00): ")
    descripcion = pedir_texto_no_vacio("Descripción (ej. Venta mostrador, Eukanuba): ").upper()

    with open(ARCHIVO_DEPOSITOS, mode="a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow([fecha_actual, descripcion, formatear_monto(monto)])

    print(f"✅ Depósito de Q {formatear_monto(monto)} registrado con éxito.")


def imprimir_cheque_pdf(num, fecha, nombre, monto):
    ancho_papel = 21.5 * cm
    alto_papel = 14.0 * cm
    nombre_pdf = f"cheque_{num}.pdf"

    pdf = canvas.Canvas(nombre_pdf, pagesize=(ancho_papel, alto_papel))

    monto_formateado = formatear_monto(monto)
    entero, centavos = monto_formateado.split(".")
    monto_en_letras = num2words(int(entero), lang="es").upper()
    texto_oficial = f"La suma de: {monto_en_letras} QUETZALES CON {centavos}/100"

    pdf.drawString(15 * cm, 12 * cm, f"Fecha: {fecha}")
    pdf.drawString(2 * cm, 11 * cm, f"Páguese a: {nombre}")
    pdf.drawString(16 * cm, 11 * cm, f"Q {monto_formateado}")
    pdf.drawString(2 * cm, 10 * cm, texto_oficial)

    pdf.save()

    print(f"🖨️  PDF generado: {nombre_pdf}")

    try:
        if platform.system() == "Windows":
            startfile = getattr(os, "startfile", None)
            if callable(startfile):
                startfile(nombre_pdf, "print")
            else:
                raise AttributeError("os.startfile no esta disponible en este entorno")
        elif platform.system() == "Darwin":
            abrir_pdf_silenciosamente(["open", nombre_pdf])
        else:
            print("🐧 Abriendo en Chrome OS...")
            abrir_pdf_silenciosamente(["xdg-open", nombre_pdf])
    except Exception as e:
        print(f"⚠️ Abre el PDF manual. Error: {e}")


def abrir_pdf_silenciosamente(comando):
    try:
        subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        detalle = (e.stderr or e.stdout or "").strip()
        if detalle:
            raise RuntimeError(detalle) from e
        raise RuntimeError(f"el comando fallo con codigo {e.returncode}") from e


def guardar_en_archivo(num, fecha, nombre, monto):
    with open(ARCHIVO_CHEQUES, mode="a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow([num, fecha, nombre, formatear_monto(monto), "TRANSITO"])
    print("💾 Datos guardados en el historial (CSV).")


def registrar_e_imprimir():
    print("\n--- EMISIÓN DE CHEQUE ---")

    monto = pedir_monto_positivo("Monto del cheque (ej. 1500.50): ")
    nombre = pedir_texto_no_vacio("Páguese a la orden de: ").upper()
    num_cheque = pedir_numero_cheque("Número de cheque: ")
    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    if cheque_ya_registrado(num_cheque):
        print(f"⚠️ El cheque {num_cheque} ya existe en el historial.")
        return

    try:
        imprimir_cheque_pdf(num_cheque, fecha_actual, nombre, monto)
        guardar_en_archivo(num_cheque, fecha_actual, nombre, monto)
    except Exception as e:
        print(f"⚠️ No se pudo completar la emisión del cheque: {e}")
        return

    print("✅ Cheque registrado y listo para imprimir con éxito.")


def anular_cheque():
    print("\n--- ANULAR CHEQUE ---")

    if not os.path.exists(ARCHIVO_CHEQUES):
        print("⚠️ No hay registro de cheques aún.")
        return

    num_anular = pedir_numero_cheque("Ingresa el número de cheque que deseas anular: ")
    df = cargar_cheques_registrados()

    if df.empty:
        print("⚠️ No hay registro de cheques aún.")
        return

    coincidencias = df["Num_norm"].eq(num_anular)
    if not coincidencias.any():
        print(f"⚠️ El cheque {num_anular} no existe en los registros.")
        return

    df.loc[coincidencias, "Estado"] = "ANULADO"
    df[["Num", "Fecha", "Nombre", "Monto", "Estado"]].to_csv(
        ARCHIVO_CHEQUES,
        index=False,
        header=False,
    )

    cantidad = int(coincidencias.sum())
    if cantidad > 1:
        print(f"⚠️ El número {num_anular} aparecía {cantidad} veces y quedó marcado como ANULADO.")
    else:
        print(f"🚫 ¡Hecho! El cheque {num_anular} ha sido marcado como ANULADO.")


def conciliar_cuentas():
    print("\n--- CONCILIACIÓN BANCARIA ---")

    if not os.path.exists(ARCHIVO_CHEQUES) or not os.path.exists(ARCHIVO_BANCO):
        print("⚠️ Faltan archivos. Asegúrate de tener registros y estado de cuenta.")
        return

    try:
        df_nuestro = cargar_cheques_registrados()
        df_banco = pd.read_excel(ARCHIVO_BANCO)

        columnas_banco = {str(col).strip().lower(): col for col in df_banco.columns}
        col_num = columnas_banco.get("num_cheque")
        col_monto = columnas_banco.get("monto")

        if not col_num or not col_monto:
            print("⚠️ El archivo del banco debe incluir las columnas 'Num_cheque' y 'Monto'.")
            return

        df_banco = df_banco.copy()
        df_banco["Num_norm"] = df_banco[col_num].map(normalizar_numero_cheque)
        df_banco["Monto_valor"] = df_banco[col_monto].map(convertir_monto)
        df_banco = df_banco[df_banco["Num_norm"].notna()].copy()

        print("\n--- Resultados de Cheques Emitidos ---")
        for _, fila in df_nuestro.iterrows():
            num = fila["Num_norm"]
            if not num:
                continue

            cobrado = df_banco[df_banco["Num_norm"] == num]
            estado = str(fila.get("Estado", "")).upper()

            if estado == "ANULADO":
                if cobrado.empty:
                    print(f"🚫 Cheque {num} está ANULADO y no aparece cobrado en el banco.")
                else:
                    print(f"🚨 Cheque {num} está ANULADO pero el banco sí lo cobró.")
                continue

            if cobrado.empty:
                print(f"⏳ Cheque {num} en TRÁNSITO.")
                continue

            monto_nuestro = fila["Monto_valor"]
            monto_banco = cobrado.iloc[0]["Monto_valor"]

            if monto_nuestro is None or monto_banco is None:
                print(f"⚠️ No pude comparar el monto del cheque {num} por datos inválidos.")
            elif monto_nuestro == monto_banco:
                print(f"✅ Cheque {num} cobrado perfectamente.")
            else:
                print(
                    f"⚠️ ¡Ojo! Cheque {num} diferencia: Nuestro Q {formatear_monto(monto_nuestro)} | "
                    f"Banco Q {formatear_monto(monto_banco)}"
                )

        print("\n--- Cargos del Banco No Registrados por Nosotros ---")
        lista_nuestros_nums = set(df_nuestro["Num_norm"].dropna().tolist())
        for _, fila_banco in df_banco.iterrows():
            num_bco = fila_banco["Num_norm"]
            if num_bco not in lista_nuestros_nums:
                monto_banco = fila_banco["Monto_valor"]
                monto_texto = formatear_monto(monto_banco) if monto_banco is not None else "N/D"
                print(
                    f"❓ Cheque {num_bco} por Q {monto_texto} cobrado por el banco, "
                    "pero NO está en nuestro sistema."
                )

    except Exception as e:
        print(f"⚠️ Ocurrió un error leyendo los archivos: {e}")


def clear_ide_terminal():
    """Pushes old text out of view using standard line breaks."""
    print("\n" * 45)


def reporte_movimientos():
    print("\n" + "=" * 40)
    print(" 📊 CORTE DE CAJA MENSUAL 📊")
    print("=" * 40)

    periodo_actual = pd.Timestamp(datetime.now().date()).to_period("M")
    total_cheques = Decimal("0.00")
    total_depositos = Decimal("0.00")

    df_cheques = cargar_cheques_registrados()
    df_cheques = df_cheques[df_cheques["Monto_valor"].notna() & df_cheques["Fecha_dt"].notna()].copy()
    df_cheques_mes = df_cheques[df_cheques["Fecha_dt"].dt.to_period("M") == periodo_actual].copy()

    if not df_cheques_mes.empty:
        df_cheques_mes["Monto"] = df_cheques_mes["Monto_valor"].map(formatear_monto)
        total_cheques = sum(
            (fila["Monto_valor"] for _, fila in df_cheques_mes.iterrows() if str(fila["Estado"]).upper() != "ANULADO"),
            Decimal("0.00"),
        )
        print("\n--- CHEQUES EMITIDOS DEL MES ---")
        print(df_cheques_mes[["Num", "Fecha", "Nombre", "Monto", "Estado"]].to_string(index=False))
    else:
        print("\n--- CHEQUES EMITIDOS DEL MES ---")
        print("No hay cheques registrados en el mes actual.")

    df_depositos = cargar_depositos_registrados()
    df_depositos = df_depositos[df_depositos["Monto_valor"].notna() & df_depositos["Fecha_dt"].notna()].copy()
    df_depositos_mes = df_depositos[df_depositos["Fecha_dt"].dt.to_period("M") == periodo_actual].copy()

    if not df_depositos_mes.empty:
        df_depositos_mes["Monto"] = df_depositos_mes["Monto_valor"].map(formatear_monto)
        total_depositos = sum(
            (fila["Monto_valor"] for _, fila in df_depositos_mes.iterrows()),
            Decimal("0.00"),
        )
        print("\n--- DEPÓSITOS RECIBIDOS DEL MES ---")
        print(df_depositos_mes[["Fecha", "Descripcion", "Monto"]].to_string(index=False))
    else:
        print("\n--- DEPÓSITOS RECIBIDOS DEL MES ---")
        print("No hay depósitos registrados en el mes actual.")

    saldo = total_depositos - total_cheques

    print("\n" + "-" * 40)
    print(f"📈 TOTAL INGRESOS (Depósitos): Q {formatear_monto(total_depositos)}")
    print(f"📉 TOTAL EGRESOS (Cheques):  Q {formatear_monto(total_cheques)}")
    print("-" * 40)
    print(f"💵 SALDO EN BÓVEDA:          Q {formatear_monto(saldo)}")
    print("-" * 40)

    input("\nPresiona ENTER para volver al menú...")


def mostrar_menu():
    print("\n" + "=" * 40)
    print(" 💼 SISTEMA DE CONTROL BANCARIO 💼")
    print("=" * 40)
    print("1. Emitir nuevo cheque")
    print("2. Registrar un depósito")
    print("3. Conciliar banco")
    print("4. Anular un cheque con error")
    print("5. Ver corte de caja (Reporte)")
    print("6. Salir")
    print("=" * 40)


def main():
    while True:
        mostrar_menu()
        opcion = input("Elige una opción (1-6): ").strip()

        if opcion == "1":
            registrar_e_imprimir()
        elif opcion == "2":
            registrar_deposito()
        elif opcion == "3":
            conciliar_cuentas()
        elif opcion == "4":
            anular_cheque()
        elif opcion == "5":
            reporte_movimientos()
        elif opcion == "6":
            print("\nCerrando la bóveda... ¡Buenas noches y éxito en los negocios, Javier!")
            sys.exit()
        else:
            print("⚠️ Opción inválida. Intenta un número del 1 al 6.")


if __name__ == "__main__":  # pragma: no cover
    main()
