import pandas as pd
from datetime import datetime, timedelta


# =============================================================================
# 1. CARGA Y LIMPIEZA (donde mueren los errores del usuario)
# =============================================================================

def cargar_csv(ruta, columnas_esperadas):
    """Lee un CSV y verifica que no falten columnas clave."""
    try:
        df = pd.read_csv(ruta)
    except FileNotFoundError:
        raise ValueError(f"No encontré el archivo: {ruta}")

    faltantes = [col for col in columnas_esperadas if col not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas: {faltantes}")

    return df


def limpiar_monto(valor):
    """Convierte 'Q 1,250.50' o '(250.00)' en float."""
    if pd.isna(valor):
        return 0.0
    texto = str(valor).replace("Q", "").replace(",", "").strip()
    if texto.startswith("(") and texto.endswith(")"):
        texto = "-" + texto[1:-1]
    return float(texto)


def normalizar_banco(df):
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["monto"] = df["monto"].apply(limpiar_monto)
    df["referencia"] = df["referencia"].astype(str).str.strip().str.lower()
    df = df.drop_duplicates()
    return df


def normalizar_libro(df):
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["monto"] = df["monto"].apply(limpiar_monto)
    df["numero_cheque"] = df["numero_cheque"].astype(str).str.strip().str.lower()
    df = df.drop_duplicates()
    return df


# =============================================================================
# 2. CONCILIACIÓN (el corazón del asunto)
# =============================================================================

def match_exacto(df_banco, df_libro):
    """Empareja por referencia y monto perfectos."""
    merge = pd.merge(
        df_banco,
        df_libro,
        left_on=["referencia", "monto"],
        right_on=["numero_cheque", "monto"],
        how="inner",
        suffixes=("_banco", "_libro"),
        indicator=True,
    )

    ids_banco = merge.index if not merge.empty else []
    # Para obtener los índices originales correctamente en merges complejos,
    # usamos reset_index; aquí lo simplifico para que sea legible:
    return merge


def separar_pendientes(df_original, df_conciliado, lado="banco"):
    """Devuelve lo que NO apareció en la conciliación."""
    # Usamos un identificador temporal para no perder filas
    temp = df_original.copy()
    temp["_id"] = temp.index

    if lado == "banco":
        clave = "referencia"
        merge_clave = "referencia"
    else:
        clave = "numero_cheque"
        merge_clave = "numero_cheque"

    # Anti-merge: filas del original que no están en el conciliado
    pendientes = temp[~temp[clave].isin(df_conciliado[merge_clave])]
    return pendientes.drop(columns=["_id"], errors="ignore")


# =============================================================================
# 3. CLASIFICACIÓN DE DIFERENCIAS (el detective contable)
# =============================================================================

def clasificar_diferencias(pend_libro, pend_banco):
    resultado = {
        "cheques_transito": pend_libro.copy(),  # Emití, banco no los ve
        "cargos_ocultos": pend_banco.copy(),    # Banco cobró, yo no lo anoté
        "depositos_pendientes": pd.DataFrame(), # Opcional, si maneja depósitos
        "errores": pd.DataFrame(),              # Montos que no cuadran ni por fecha
    }
    return resultado


# =============================================================================
# 4. REPORTE (donde todo se ve bonito)
# =============================================================================

def generar_reporte(conciliados, clasificacion, nombre_salida="reporte.xlsx"):
    with pd.ExcelWriter(nombre_salida, engine="openpyxl") as writer:
        conciliados.to_excel(writer, sheet_name="Conciliados", index=False)
        clasificacion["cheques_transito"].to_excel(
            writer, sheet_name="Cheques_Transito", index=False
        )
        clasificacion["cargos_ocultos"].to_excel(
            writer, sheet_name="Cargos_Ocultos", index=False
        )
    print(f"Reporte guardado como: {nombre_salida}")


# =============================================================================
# 5. MAIN (el jefe que da órdenes)
# =============================================================================

def main():
    try:
        # ---------- Entrada ----------
        banco = cargar_csv("extracto_banco.csv", ["fecha", "descripcion", "referencia", "monto"])
        libro = cargar_csv("mi_libro.csv", ["fecha", "numero_cheque", "beneficiario", "monto"])

        # ---------- Limpieza ----------
        banco = normalizar_banco(banco)
        libro = normalizar_libro(libro)

        # ---------- Fase 1: Exacto ----------
        exactos = match_exacto(banco, libro)

        # ---------- Fase 2: Pendientes ----------
        pend_banco = separar_pendientes(banco, exactos, lado="banco")
        pend_libro = separar_pendientes(libro, exactos, lado="libro")

        # ---------- Fase 3: Clasificar ----------
        diffs = clasificar_diferencias(pend_libro, pend_banco)

        # ---------- Salida ----------
        generar_reporte(exactos, diffs)

    except ValueError as e:
        print(f"Error controlado: {e}")
    except Exception as e:
        print(f"Algo inesperado ocurrió: {e}")


if __name__ == "__main__":
    main()