import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd


DEFAULT_BANCO = "extracto_banco.csv"
DEFAULT_LIBRO = "mi_libro.csv"
DEFAULT_SALIDA = "reporte.xlsx"
DEFAULT_VENTANA_DIAS = 2
DEFAULT_SIMILITUD_MINIMA = 0.35
TIPOS_MATCH_SECUNDARIO = {"deposito", "movimiento"}
CLAVES_GENERICAS = {
    "abono",
    "abonos",
    "cargo",
    "cargos",
    "cheque",
    "cheques",
    "credito",
    "creditos",
    "debito",
    "debitos",
    "deposito",
    "depositos",
    "egreso",
    "egresos",
    "ingreso",
    "ingresos",
    "movimiento",
    "movimientos",
    "retiro",
    "retiros",
    "transferencia",
    "transferencias",
}
PALABRAS_VACIAS_BUSQUEDA = {
    "a",
    "al",
    "banco",
    "con",
    "cargo",
    "cargos",
    "cheque",
    "cheques",
    "de",
    "del",
    "deposito",
    "depositos",
    "descripcion",
    "el",
    "en",
    "ingreso",
    "ingresos",
    "la",
    "las",
    "los",
    "movimiento",
    "movimientos",
    "nota",
    "por",
    "para",
    "pago",
    "pagos",
    "ref",
    "referencia",
    "transferencia",
    "transferencias",
    "una",
    "uno",
    "y",
    "q",
}


def normalizar_texto(valor):
    """Normaliza texto para comparaciones sin perder el original."""
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def normalizar_columna(nombre):
    texto = normalizar_texto(nombre)
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto.strip("_")


def normalizar_columnas(df):
    df = df.copy()
    df.columns = [normalizar_columna(col) for col in df.columns]
    return df


def limpiar_monto(valor):
    """Convierte montos tipo 'Q 1,250.50' o '(250.00)' a float."""
    if pd.isna(valor):
        return 0.0

    texto = str(valor).strip()
    if not texto:
        return 0.0

    negativo = texto.startswith("(") and texto.endswith(")")
    texto = texto.strip("()")
    texto = texto.replace("Q", "").replace("q", "").replace("$", "")
    texto = texto.replace("\xa0", "").replace(" ", "").replace("−", "-")
    texto = re.sub(r"[^0-9,.\-]", "", texto)

    if texto.count("-") > 1:
        texto = texto.replace("-", "")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        if len(partes[-1]) in (1, 2):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")

    if negativo and not texto.startswith("-"):
        texto = "-" + texto

    if texto in {"", "-", ".", "-.", "--"}:
        return 0.0

    try:
        return round(float(texto), 2)
    except ValueError as exc:
        raise ValueError(f"No pude convertir el monto '{valor}'") from exc


def canonizar_tipo(valor):
    texto = normalizar_texto(valor)
    if not texto:
        return ""

    alias = {
        "chq": "cheque",
        "chk": "cheque",
        "cheque": "cheque",
        "cheques": "cheque",
        "dep": "deposito",
        "deposit": "deposito",
        "deposito": "deposito",
        "depositos": "deposito",
        "abono": "deposito",
        "abonos": "deposito",
        "ingreso": "deposito",
        "ingresos": "deposito",
        "credito": "deposito",
        "creditos": "deposito",
        "transferencia": "deposito",
        "cargo": "cargo",
        "cargos": "cargo",
        "debito": "cargo",
        "debitos": "cargo",
        "comision": "cargo",
        "comisiones": "cargo",
        "retiro": "cargo",
        "retiros": "cargo",
        "movimiento": "movimiento",
        "movimientos": "movimiento",
    }

    for clave, canonico in alias.items():
        if clave in texto:
            return canonico

    return texto


def primer_no_vacio(*valores):
    for valor in valores:
        texto = str(valor).strip()
        if texto and texto.lower() != "nan":
            return texto
    return ""


def es_clave_usable(valor):
    """Devuelve una clave normalizada solo si parece un identificador real."""
    texto = normalizar_clave_busqueda(valor)
    if not texto:
        return ""
    return texto


def normalizar_clave_busqueda(valor):
    """Convierte referencias tipo CH-001 y 001 en una misma clave comparable."""
    texto = normalizar_texto(valor)
    if not texto:
        return ""

    if re.fullmatch(r"\d+\.0+", texto):
        return str(int(texto.split(".")[0]))

    digitos = re.findall(r"\d+", texto)
    if digitos:
        return str(int(digitos[-1]))

    tokens = re.findall(r"[a-z0-9]+", texto)
    if len(tokens) != 1:
        return ""

    token = tokens[0]
    if token in CLAVES_GENERICAS or len(token) < 3:
        return ""

    return token


def tokens_relevantes(texto):
    texto = normalizar_texto(texto)
    if not texto:
        return []

    tokens = re.findall(r"[a-z0-9]+", texto)
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in PALABRAS_VACIAS_BUSQUEDA
    ]


def similitud_textual(texto_a, texto_b):
    """Calcula una similitud simple basada en solapamiento y contencion parcial."""
    a = normalizar_texto(texto_a)
    b = normalizar_texto(texto_b)
    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a in b or b in a:
        return 0.95 if min(len(a), len(b)) >= 6 else 0.8

    tokens_a = tokens_relevantes(a)
    tokens_b = tokens_relevantes(b)
    if not tokens_a or not tokens_b:
        return 0.0

    set_a = set(tokens_a)
    set_b = set(tokens_b)
    interseccion_exacta = set_a & set_b
    jaccard = len(interseccion_exacta) / len(set_a | set_b)
    cobertura = len(interseccion_exacta) / max(1, min(len(set_a), len(set_b)))

    coincidencias_parciales = 0
    usados_b = set()
    for token_a in tokens_a:
        for indice_b, token_b in enumerate(tokens_b):
            if indice_b in usados_b:
                continue
            if token_a == token_b:
                coincidencias_parciales += 1
                usados_b.add(indice_b)
                break
            if len(token_a) >= 4 and len(token_b) >= 4 and (
                token_a.startswith(token_b) or token_b.startswith(token_a)
            ):
                coincidencias_parciales += 1
                usados_b.add(indice_b)
                break

    parcial = coincidencias_parciales / max(1, min(len(tokens_a), len(tokens_b)))
    return round(max(jaccard, cobertura, parcial), 3)


def elegir_clave_banco(fila):
    return primer_no_vacio(fila["referencia"], fila["descripcion"])


def elegir_clave_libro_match(fila):
    if fila["tipo"] == "cheque":
        return primer_no_vacio(fila["numero_cheque"], fila["referencia"])
    if fila["tipo"] == "deposito":
        return primer_no_vacio(fila["numero_deposito"], fila["referencia"])
    return primer_no_vacio(fila["referencia"], fila["numero_deposito"], fila["numero_cheque"])


def obtener_texto_fila(fila, opciones):
    partes = []
    for opcion in opciones:
        valor = fila.get(opcion, "")
        if pd.isna(valor):
            continue
        texto = str(valor).strip()
        if texto and texto.lower() != "nan":
            partes.append(texto)
    return " ".join(partes)


def construir_texto_banco(fila):
    return obtener_texto_fila(
        fila,
        (
            "descripcion_norm_banco",
            "descripcion_norm",
            "referencia_norm_banco",
            "referencia_norm",
        ),
    )


def construir_texto_libro(fila):
    return obtener_texto_fila(
        fila,
        (
            "beneficiario_norm_libro",
            "beneficiario_norm",
            "referencia_norm_libro",
            "referencia_norm",
            "numero_cheque_norm_libro",
            "numero_cheque_norm",
            "numero_deposito_norm_libro",
            "numero_deposito_norm",
        ),
    )


def cargar_csv(ruta, columnas_esperadas):
    """Lee un CSV con delimitador auto-detectado y valida columnas clave."""
    try:
        df = pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValueError(f"No encontre el archivo: {ruta}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"El archivo esta vacio: {ruta}") from exc

    df = normalizar_columnas(df)

    faltantes = [col for col in columnas_esperadas if col not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas en {ruta}: {faltantes}")

    return df


def validar_fechas(df, contexto):
    invalidas = df[df["fecha"].isna()]
    if not invalidas.empty:
        filas = [int(idx) + 2 for idx in invalidas["_origen"].head(5).tolist()]
        raise ValueError(f"Hay fechas invalidas en {contexto}. Revisa las filas: {filas}")


def normalizar_banco(df):
    df = df.copy()

    if "tipo" in df.columns:
        df["tipo_original"] = df["tipo"]
    else:
        df["tipo"] = ""

    if "descripcion" not in df.columns or "referencia" not in df.columns:
        raise ValueError("El extracto del banco debe incluir descripcion y referencia.")

    df["_origen"] = df.index.astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["monto"] = df["monto"].apply(limpiar_monto)

    df["descripcion_norm"] = df["descripcion"].map(normalizar_texto)
    df["referencia_norm"] = df["referencia"].map(normalizar_texto)
    df["tipo"] = df.apply(
        lambda fila: canonizar_tipo(fila["tipo"]) or inferir_tipo_banco(
            fila["descripcion_norm"], fila["referencia_norm"]
        ),
        axis=1,
    )
    df["clave"] = df.apply(
        lambda fila: elegir_clave_banco(fila),
        axis=1,
    )
    df["clave_norm"] = df["clave"].map(normalizar_texto)
    df["clave_match"] = df["clave"].map(es_clave_usable)

    validar_fechas(df, "extracto del banco")
    return df


def inferir_tipo_libro(fila):
    tipo = canonizar_tipo(fila.get("tipo", ""))
    if tipo:
        return tipo
    if fila.get("numero_deposito_norm"):
        return "deposito"
    if fila.get("numero_cheque_norm"):
        return "cheque"
    return "movimiento"


def inferir_tipo_banco(descripcion_norm, referencia_norm):
    texto = f"{descripcion_norm} {referencia_norm}".strip()
    if any(palabra in texto for palabra in ("deposit", "abono", "ingreso", "credito", "transfer")):
        return "deposito"
    if any(palabra in texto for palabra in ("cheque", "chk", "chq")):
        return "cheque"
    if any(palabra in texto for palabra in ("cargo", "debito", "comision", "retiro", "mora", "sobregiro")):
        return "cargo"
    return "movimiento"


def normalizar_libro(df):
    df = df.copy()

    if "tipo" in df.columns:
        df["tipo_original"] = df["tipo"]
    else:
        df["tipo"] = ""

    if "fecha" not in df.columns or "monto" not in df.columns:
        raise ValueError("El libro debe incluir fecha y monto.")

    if not any(col in df.columns for col in ("numero_cheque", "numero_deposito", "referencia")):
        raise ValueError(
            "El libro debe incluir al menos numero_cheque, numero_deposito o referencia."
        )

    for columna in ("numero_cheque", "numero_deposito", "beneficiario", "referencia"):
        if columna not in df.columns:
            df[columna] = ""

    df["_origen"] = df.index.astype(int)
    df["fecha"] = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
    df["monto"] = df["monto"].apply(limpiar_monto)

    df["numero_cheque_norm"] = df["numero_cheque"].map(normalizar_texto)
    df["numero_deposito_norm"] = df["numero_deposito"].map(normalizar_texto)
    df["beneficiario_norm"] = df["beneficiario"].map(normalizar_texto)
    df["referencia_norm"] = df["referencia"].map(normalizar_texto)
    df["tipo"] = df.apply(inferir_tipo_libro, axis=1)
    df["clave"] = df.apply(
        lambda fila: elegir_clave_libro(fila),
        axis=1,
    )
    df["clave_norm"] = df["clave"].map(normalizar_texto)
    df["clave_match"] = df.apply(elegir_clave_libro_match, axis=1).map(es_clave_usable)

    validar_fechas(df, "libro")
    return df


def elegir_clave_libro(fila):
    if fila["tipo"] == "deposito":
        return primer_no_vacio(
            fila.get("numero_deposito"),
            fila.get("referencia"),
            fila.get("beneficiario"),
            fila.get("numero_cheque"),
        )
    if fila["tipo"] == "cheque":
        return primer_no_vacio(
            fila.get("numero_cheque"),
            fila.get("referencia"),
            fila.get("beneficiario"),
            fila.get("numero_deposito"),
        )
    return primer_no_vacio(
        fila.get("numero_cheque"),
        fila.get("numero_deposito"),
        fila.get("referencia"),
        fila.get("beneficiario"),
    )
def match_exacto(df_banco, df_libro):
    """Empareja movimientos por tipo, clave y monto exacto."""
    banco = df_banco[df_banco["clave_match"] != ""].copy()
    libro = df_libro[df_libro["clave_match"] != ""].copy()

    if banco.empty or libro.empty:
        return pd.DataFrame()

    banco = banco.sort_values(["tipo", "clave_match", "monto", "fecha", "_origen"]).copy()
    libro = libro.sort_values(["tipo", "clave_match", "monto", "fecha", "_origen"]).copy()

    banco["_seq"] = banco.groupby(["tipo", "clave_match", "monto"]).cumcount()
    libro["_seq"] = libro.groupby(["tipo", "clave_match", "monto"]).cumcount()

    conciliados = pd.merge(
        banco,
        libro,
        left_on=["tipo", "clave_match", "monto", "_seq"],
        right_on=["tipo", "clave_match", "monto", "_seq"],
        how="inner",
        suffixes=("_banco", "_libro"),
    )
    conciliados["metodo"] = "exacto"
    conciliados["similitud_texto"] = 1.0
    conciliados["delta_dias"] = 0
    return conciliados


def _fusionar_grupo_sin_clave(grupo_banco, grupo_libro, ventana_dias, similitud_minima):
    if grupo_banco.empty or grupo_libro.empty:
        return pd.DataFrame()

    candidatos = grupo_banco.assign(_tmp=1).merge(
        grupo_libro.assign(_tmp=1),
        on="_tmp",
        how="inner",
        suffixes=("_banco", "_libro"),
    )
    candidatos = candidatos.drop(columns=["_tmp"])

    if candidatos.empty:
        return candidatos

    candidatos["_delta_dias"] = (
        candidatos["fecha_banco"] - candidatos["fecha_libro"]
    ).abs().dt.days
    candidatos["_ambos_sin_clave"] = (
        (candidatos["clave_match_banco"] == "") & (candidatos["clave_match_libro"] == "")
    )

    candidatos = candidatos[
        (candidatos["_delta_dias"] <= ventana_dias)
        & (
            (candidatos["clave_match_banco"] == "")
            | (candidatos["clave_match_libro"] == "")
        )
    ].copy()

    if candidatos.empty:
        return candidatos

    candidatos["_texto_banco"] = candidatos.apply(construir_texto_banco, axis=1)
    candidatos["_texto_libro"] = candidatos.apply(construir_texto_libro, axis=1)
    candidatos["_similitud_texto"] = candidatos.apply(
        lambda fila: similitud_textual(fila["_texto_banco"], fila["_texto_libro"]),
        axis=1,
    )
    candidatos = candidatos[candidatos["_similitud_texto"] >= similitud_minima].copy()

    if candidatos.empty:
        return candidatos

    candidatos["_bono_clave"] = candidatos["_ambos_sin_clave"].astype(int)
    candidatos["_score_total"] = (
        (candidatos["_similitud_texto"] * 100)
        + ((ventana_dias - candidatos["_delta_dias"]) * 5)
        + (candidatos["_bono_clave"] * 3)
    )

    candidatos = candidatos.sort_values(
        [
            "_score_total",
            "_similitud_texto",
            "_delta_dias",
            "_ambos_sin_clave",
            "fecha_banco",
            "fecha_libro",
            "_origen_banco",
            "_origen_libro",
        ],
        ascending=[False, False, True, False, True, True, True, True],
    )

    usados_banco = set()
    usados_libro = set()
    seleccionados = []

    for _, fila in candidatos.iterrows():
        id_banco = int(fila["_origen_banco"])
        id_libro = int(fila["_origen_libro"])
        if id_banco in usados_banco or id_libro in usados_libro:
            continue
        usados_banco.add(id_banco)
        usados_libro.add(id_libro)
        fila = fila.copy()
        fila["metodo"] = "monto_fecha_texto"
        fila["similitud_texto"] = round(float(fila["_similitud_texto"]), 3)
        fila["delta_dias"] = int(fila["_delta_dias"])
        seleccionados.append(fila)

    if not seleccionados:
        return pd.DataFrame()

    return pd.DataFrame(seleccionados).drop(
        columns=[
            "_ambos_sin_clave",
            "_bono_clave",
            "_score_total",
            "_texto_banco",
            "_texto_libro",
            "_similitud_texto",
            "_delta_dias",
        ],
        errors="ignore",
    )


def match_sin_clave(df_banco, df_libro, ventana_dias=2, similitud_minima=0.35):
    """Empareja movimientos sin clave usable por tipo, monto y cercania de fecha."""
    banco = df_banco[df_banco["tipo"].isin(TIPOS_MATCH_SECUNDARIO)].copy()
    libro = df_libro[df_libro["tipo"].isin(TIPOS_MATCH_SECUNDARIO)].copy()

    if banco.empty or libro.empty:
        return pd.DataFrame()

    banco = banco.sort_values(["tipo", "monto", "fecha", "_origen"]).copy()
    libro = libro.sort_values(["tipo", "monto", "fecha", "_origen"]).copy()

    grupos = []
    for (tipo, monto), grupo_banco in banco.groupby(["tipo", "monto"], dropna=False):
        grupo_libro = libro[(libro["tipo"] == tipo) & (libro["monto"] == monto)].copy()
        if grupo_libro.empty:
            continue
        candidatos = _fusionar_grupo_sin_clave(
            grupo_banco,
            grupo_libro,
            ventana_dias,
            similitud_minima,
        )
        if not candidatos.empty:
            grupos.append(candidatos)

    if not grupos:
        return pd.DataFrame()

    conciliados = pd.concat(grupos, ignore_index=True, sort=False)
    conciliados["metodo"] = conciliados["metodo"].fillna("monto_fecha_texto")
    return conciliados


def separar_pendientes(df_original, df_conciliado, lado="banco"):
    """Devuelve lo que no aparecio en la conciliacion."""
    if df_conciliado.empty:
        return df_original.copy()

    columna = "_origen_banco" if lado == "banco" else "_origen_libro"
    if columna not in df_conciliado.columns:
        return df_original.copy()

    ids_conciliados = (
        pd.to_numeric(df_conciliado[columna], errors="coerce").dropna().astype(int).tolist()
    )
    return df_original[~df_original["_origen"].isin(ids_conciliados)].copy()


def detectar_errores(pend_libro, pend_banco):
    """Busca el mismo numero de referencia con montos distintos."""
    if pend_libro.empty or pend_banco.empty:
        return pd.DataFrame(), pend_libro.copy(), pend_banco.copy()

    libro = pend_libro[pend_libro["clave_norm"] != ""].copy()
    banco = pend_banco[pend_banco["clave_norm"] != ""].copy()

    if libro.empty or banco.empty:
        return pd.DataFrame(), pend_libro.copy(), pend_banco.copy()

    libro = libro.sort_values(["tipo", "clave_norm", "fecha", "_origen"]).copy()
    banco = banco.sort_values(["tipo", "clave_norm", "fecha", "_origen"]).copy()

    libro["_seq_clave"] = libro.groupby(["tipo", "clave_norm"]).cumcount()
    banco["_seq_clave"] = banco.groupby(["tipo", "clave_norm"]).cumcount()

    comparados = pd.merge(
        banco,
        libro,
        on=["tipo", "clave_norm", "_seq_clave"],
        how="inner",
        suffixes=("_banco", "_libro"),
    )

    errores = comparados[comparados["monto_banco"].round(2) != comparados["monto_libro"].round(2)].copy()
    if errores.empty:
        return errores, pend_libro.copy(), pend_banco.copy()

    ids_libro = set(
        pd.to_numeric(errores["_origen_libro"], errors="coerce").dropna().astype(int).tolist()
    )
    ids_banco = set(
        pd.to_numeric(errores["_origen_banco"], errors="coerce").dropna().astype(int).tolist()
    )

    pend_libro_restante = pend_libro[~pend_libro["_origen"].isin(ids_libro)].copy()
    pend_banco_restante = pend_banco[~pend_banco["_origen"].isin(ids_banco)].copy()
    return errores, pend_libro_restante, pend_banco_restante


def clasificar_diferencias(pend_libro, pend_banco):
    errores, pend_libro_restante, pend_banco_restante = detectar_errores(pend_libro, pend_banco)

    cheques_transito = pend_libro_restante[pend_libro_restante["tipo"] == "cheque"].copy()
    depositos_pendientes = pend_libro_restante[pend_libro_restante["tipo"] == "deposito"].copy()
    otros_pendientes_libro = pend_libro_restante[
        ~pend_libro_restante["tipo"].isin(["cheque", "deposito"])
    ].copy()

    cargos_ocultos = pend_banco_restante[
        pend_banco_restante["tipo"].isin(["cargo", "movimiento"])
    ].copy()
    depositos_no_registrados = pend_banco_restante[
        pend_banco_restante["tipo"] == "deposito"
    ].copy()
    cheques_banco_pendientes = pend_banco_restante[
        pend_banco_restante["tipo"] == "cheque"
    ].copy()
    otros_pendientes_banco = pend_banco_restante[
        ~pend_banco_restante["tipo"].isin(["cargo", "movimiento", "deposito", "cheque"])
    ].copy()

    return {
        "errores": errores,
        "pendientes_libro": pend_libro_restante,
        "pendientes_banco": pend_banco_restante,
        "cheques_transito": cheques_transito,
        "depositos_pendientes": depositos_pendientes,
        "cargos_ocultos": cargos_ocultos,
        "depositos_no_registrados": depositos_no_registrados,
        "cheques_banco_pendientes": cheques_banco_pendientes,
        "otros_pendientes_libro": otros_pendientes_libro,
        "otros_pendientes_banco": otros_pendientes_banco,
    }


def preparar_salida(df):
    if df.empty:
        return df.copy()

    salida = df.copy()
    columnas_drop = [col for col in salida.columns if col.startswith("_") or col.endswith("_norm")]
    salida = salida.drop(columns=columnas_drop, errors="ignore")

    preferidas = [
        col
        for col in (
            "fecha",
            "tipo",
            "clave",
            "clave_match",
            "monto",
            "metodo",
            "similitud_texto",
            "delta_dias",
            "descripcion",
            "referencia",
            "beneficiario",
            "numero_cheque",
            "numero_deposito",
            "tipo_original",
        )
        if col in salida.columns
    ]
    resto = [col for col in salida.columns if col not in preferidas]
    salida = salida.loc[:, preferidas + resto]

    if "fecha" in salida.columns:
        salida = salida.sort_values(["fecha", "tipo", "clave"], na_position="last")

    return salida.reset_index(drop=True)


def sumar_monto(df):
    if df.empty or "monto" not in df.columns:
        return 0.0
    return round(float(df["monto"].sum()), 2)


def contar_duplicados(df):
    columnas = [col for col in ("fecha", "tipo", "clave", "monto") if col in df.columns]
    if not columnas:
        return 0
    return int(df.duplicated(subset=columnas, keep=False).sum())


def construir_resumen(banco, libro, conciliados, clasificacion):
    conciliados_sin_clave = clasificacion.get("conciliados_sin_clave", pd.DataFrame())
    filas = [
        {"concepto": "Registros banco", "cantidad": len(banco), "monto": sumar_monto(banco)},
        {"concepto": "Registros libro", "cantidad": len(libro), "monto": sumar_monto(libro)},
        {
            "concepto": "Conciliados exactos",
            "cantidad": len(clasificacion.get("conciliados_exacto", pd.DataFrame())),
            "monto": sumar_monto(clasificacion.get("conciliados_exacto", pd.DataFrame())),
        },
        {
            "concepto": "Conciliados sin clave",
            "cantidad": len(conciliados_sin_clave),
            "monto": sumar_monto(conciliados_sin_clave),
        },
        {
            "concepto": "Conciliados totales",
            "cantidad": len(conciliados),
            "monto": sumar_monto(conciliados),
        },
        {
            "concepto": "Pendientes libro",
            "cantidad": len(clasificacion["pendientes_libro"]),
            "monto": sumar_monto(clasificacion["pendientes_libro"]),
        },
        {
            "concepto": "Pendientes banco",
            "cantidad": len(clasificacion["pendientes_banco"]),
            "monto": sumar_monto(clasificacion["pendientes_banco"]),
        },
        {
            "concepto": "Cheques en transito",
            "cantidad": len(clasificacion["cheques_transito"]),
            "monto": sumar_monto(clasificacion["cheques_transito"]),
        },
        {
            "concepto": "Depositos pendientes",
            "cantidad": len(clasificacion["depositos_pendientes"]),
            "monto": sumar_monto(clasificacion["depositos_pendientes"]),
        },
        {
            "concepto": "Cargos ocultos",
            "cantidad": len(clasificacion["cargos_ocultos"]),
            "monto": sumar_monto(clasificacion["cargos_ocultos"]),
        },
        {
            "concepto": "Depositos no registrados",
            "cantidad": len(clasificacion["depositos_no_registrados"]),
            "monto": sumar_monto(clasificacion["depositos_no_registrados"]),
        },
        {
            "concepto": "Errores de monto",
            "cantidad": len(clasificacion["errores"]),
            "monto": sumar_monto(clasificacion["errores"]),
        },
        {
            "concepto": "Duplicados banco",
            "cantidad": contar_duplicados(banco),
            "monto": 0.0,
        },
        {
            "concepto": "Duplicados libro",
            "cantidad": contar_duplicados(libro),
            "monto": 0.0,
        },
        {
            "concepto": "Diferencia banco - libro",
            "cantidad": "",
            "monto": round(sumar_monto(banco) - sumar_monto(libro), 2),
        },
    ]
    return pd.DataFrame(filas)


def generar_reporte(conciliados, clasificacion, banco, libro, nombre_salida=DEFAULT_SALIDA):
    """Escribe el reporte final en Excel."""
    hojas = {
        "Conciliados": conciliados,
        "Conciliados_Exactos": clasificacion.get("conciliados_exacto", pd.DataFrame()),
        "Conciliados_Sin_Clave": clasificacion.get("conciliados_sin_clave", pd.DataFrame()),
        "Pendientes_Libro": clasificacion["pendientes_libro"],
        "Pendientes_Banco": clasificacion["pendientes_banco"],
        "Cheques_Transito": clasificacion["cheques_transito"],
        "Depositos_Pendientes": clasificacion["depositos_pendientes"],
        "Cargos_Ocultos": clasificacion["cargos_ocultos"],
        "Depositos_No_Reg": clasificacion["depositos_no_registrados"],
        "Cheques_Banco": clasificacion["cheques_banco_pendientes"],
        "Otros_Libro": clasificacion["otros_pendientes_libro"],
        "Otros_Banco": clasificacion["otros_pendientes_banco"],
        "Errores": clasificacion["errores"],
        "Resumen": construir_resumen(banco, libro, conciliados, clasificacion),
    }

    try:
        with pd.ExcelWriter(nombre_salida, engine="openpyxl") as writer:
            for hoja, df in hojas.items():
                preparar_salida(df).to_excel(writer, sheet_name=hoja, index=False)
        print(f"Reporte guardado como: {nombre_salida}")
    except (ImportError, ModuleNotFoundError, ValueError):
        destino = Path(nombre_salida)
        carpeta = destino.with_suffix("")
        salida_dir = carpeta.parent / f"{carpeta.name}_sheets"
        salida_dir.mkdir(parents=True, exist_ok=True)

        for hoja, df in hojas.items():
            preparar_salida(df).to_csv(salida_dir / f"{hoja}.csv", index=False)

        print(f"Excel no disponible; reporte guardado como CSVs en: {salida_dir}")


def parsear_argumentos():
    parser = argparse.ArgumentParser(
        description="Conciliador de cheques y depositos contra el reporte del banco."
    )
    parser.add_argument("--banco", default=DEFAULT_BANCO, help="CSV del extracto bancario.")
    parser.add_argument("--libro", default=DEFAULT_LIBRO, help="CSV del libro interno.")
    parser.add_argument(
        "--ventana-dias",
        type=int,
        default=DEFAULT_VENTANA_DIAS,
        help="Diferencia maxima de dias para la conciliacion secundaria.",
    )
    parser.add_argument(
        "--similitud-minima",
        type=float,
        default=DEFAULT_SIMILITUD_MINIMA,
        help="Umbral minimo de similitud textual para la conciliacion secundaria.",
    )
    parser.add_argument(
        "--salida", default=DEFAULT_SALIDA, help="Nombre del archivo Excel de salida."
    )
    return parser.parse_args()


def main():
    args = parsear_argumentos()

    try:
        banco = cargar_csv(args.banco, ["fecha", "descripcion", "referencia", "monto"])
        libro = cargar_csv(args.libro, ["fecha", "monto"])

        banco = normalizar_banco(banco)
        libro = normalizar_libro(libro)

        exactos = match_exacto(banco, libro)
        pend_banco = separar_pendientes(banco, exactos, lado="banco")
        pend_libro = separar_pendientes(libro, exactos, lado="libro")

        secundarios = match_sin_clave(
            pend_banco,
            pend_libro,
            ventana_dias=args.ventana_dias,
            similitud_minima=args.similitud_minima,
        )
        if secundarios.empty:
            conciliados = exactos.copy()
            pend_banco_final = pend_banco
            pend_libro_final = pend_libro
        else:
            pend_banco_final = separar_pendientes(pend_banco, secundarios, lado="banco")
            pend_libro_final = separar_pendientes(pend_libro, secundarios, lado="libro")
            conciliados = pd.concat([exactos, secundarios], ignore_index=True, sort=False)

        diffs = clasificar_diferencias(pend_libro_final, pend_banco_final)
        diffs["conciliados_exacto"] = exactos
        diffs["conciliados_sin_clave"] = secundarios

        generar_reporte(conciliados, diffs, banco, libro, nombre_salida=args.salida)

        print("Conciliacion terminada.")
        print(f"Conciliados exactos: {len(exactos)}")
        print(f"Conciliados sin clave: {len(secundarios)}")
        print(f"Conciliados totales: {len(conciliados)}")
        print(f"Pendientes libro: {len(diffs['pendientes_libro'])}")
        print(f"Pendientes banco: {len(diffs['pendientes_banco'])}")
        print(f"Errores detectados: {len(diffs['errores'])}")
    except ValueError as e:
        print(f"Error controlado: {e}")
    except Exception as e:
        print(f"Algo inesperado ocurrio: {e}")


if __name__ == "__main__":
    main()
