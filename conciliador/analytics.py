import csv
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .domain import convertir_monto, normalizar_fecha, normalizar_numero_cheque
from .errors import ErrorOperacion
from .movements import cargar_cheques_registrados, cargar_depositos_registrados, cargar_notas_debito_registradas, formatear_monto
from .storage import obtener_cuenta

PATRON_CUENTA_BI = re.compile(r"^Cuenta:\s*([0-9]+)\s*-\s*(.+)$", re.IGNORECASE)
PATRON_PERIODO_BI = re.compile(
    r"^Del\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})$",
    re.IGNORECASE,
)
PATRON_MONEDA_BI = re.compile(r"\((GTQ|USD)\)", re.IGNORECASE)
PATRON_PERIODO_BANRURAL = re.compile(
    r"^Del\s+(\d{2}/\d{2}/\d{4})\s+al\s+(\d{2}/\d{2}/\d{4})$",
    re.IGNORECASE,
)
PATRON_CUENTA_BANRURAL = re.compile(
    r"^Cuenta:\s*([^-]+)-(.*?)-(.*?)-(GTQ|USD)\s*$", re.IGNORECASE
)


def _texto_celda(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _normalizar_numero_cuenta(valor):
    """Normaliza la presentación del número sin alterar su valor bancario."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    if not digitos:
        return ""
    return digitos.lstrip("0") or "0"


def _leer_csv_banco_industrial(archivo):
    """Convierte el CSV exportado por BI a cheques y otros cargos bancarios."""
    contenido = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            contenido = Path(archivo).read_text(encoding=codificacion)
            break
        except UnicodeDecodeError:
            continue
    if contenido is None:
        raise ErrorOperacion(
            "⚠️ No se pudo reconocer la codificación del archivo de Banco Industrial."
        )

    filas = list(csv.reader(contenido.splitlines()))
    cuenta_numero = None
    cuenta_nombre = None
    fecha_inicio = None
    fecha_fin = None
    moneda = None
    saldo_inicial = None
    saldo_final = None
    indice_cabecera = None

    for indice, fila in enumerate(filas):
        primera = str(fila[0] if fila else "").strip()
        cuenta = PATRON_CUENTA_BI.match(primera)
        if cuenta:
            cuenta_numero, cuenta_nombre = cuenta.groups()
        periodo = PATRON_PERIODO_BI.match(primera)
        if periodo:
            fecha_inicio = (
                datetime.strptime(periodo.group(1), "%d/%m/%Y")
                .date()
                .isoformat()
            )
            fecha_fin = (
                datetime.strptime(periodo.group(2), "%d/%m/%Y")
                .date()
                .isoformat()
            )
        if primera.casefold().startswith("saldo inicial"):
            _etiqueta, separador, valor = primera.partition(":")
            if separador:
                saldo_inicial = convertir_monto(valor)
        if primera.lower() == "fecha":
            indice_cabecera = indice
            moneda_en_cabecera = PATRON_MONEDA_BI.search(",".join(fila))
            moneda = moneda_en_cabecera.group(1).upper() if moneda_en_cabecera else None
            break

    if indice_cabecera is None:
        raise ErrorOperacion(
            "⚠️ El archivo no contiene la cabecera de movimientos de Banco Industrial."
        )

    cabecera = [str(valor).strip() for valor in filas[indice_cabecera]]
    columnas = {
        nombre.split(" (", 1)[0].lower(): indice
        for indice, nombre in enumerate(cabecera)
    }
    requeridas = ("fecha", "tt", "descripción", "no. doc", "debe", "haber", "saldo")
    if any(nombre not in columnas for nombre in requeridas):
        raise ErrorOperacion(
            "⚠️ El estado de Banco Industrial no contiene todas las columnas esperadas."
        )

    cheques = []
    depositos = []
    notas_credito = []
    notas_debito = []
    otros_cargos = []
    for fila in filas[indice_cabecera + 1:]:
        if not fila or not any(str(valor).strip() for valor in fila):
            continue
        if len(fila) > len(cabecera):
            # BI no siempre encierra entre comillas las comas de la descripción.
            fila = fila[:2] + [", ".join(fila[2:-4])] + fila[-4:]
        fila += [""] * (len(cabecera) - len(fila))
        tipo = fila[columnas["tt"]].strip().upper()
        debe_original = fila[columnas["debe"]].strip()
        haber_original = fila[columnas["haber"]].strip()
        saldo_fila = convertir_monto(fila[columnas["saldo"]].strip())
        if saldo_fila is not None:
            saldo_final = saldo_fila
        if not debe_original and not haber_original:
            continue
        monto = convertir_monto(debe_original or haber_original)
        if monto is None and tipo != "CQ":
            continue
        movimiento = {
            "Num_cheque": fila[columnas["no. doc"]].strip(),
            "Monto": monto,
            "fecha": fila[columnas["fecha"]].strip(),
            "tipo": tipo,
            "descripcion": fila[columnas["descripción"]].strip(),
        }
        if tipo == "CQ":
            cheques.append(movimiento)
        elif tipo in {"DE", "DP"}:
            depositos.append(movimiento)
        elif tipo == "NC":
            notas_credito.append(movimiento)
        elif tipo == "ND":
            notas_debito.append(movimiento)
        elif debe_original:
            otros_cargos.append(movimiento)

    return {
        "cheques": pd.DataFrame(
            cheques,
            columns=["Num_cheque", "Monto", "fecha", "tipo", "descripcion"],
        ),
        "otros_cargos": otros_cargos,
        "depositos": depositos,
        "notas_credito": notas_credito,
        "notas_debito": notas_debito,
        "cuenta_numero": cuenta_numero,
        "cuenta_nombre": cuenta_nombre,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "moneda": moneda or "GTQ",
        "saldo_inicial": saldo_inicial,
        "saldo_final": saldo_final,
    }


def _leer_xls_gt_continental(archivo):
    """Convierte el estado por rango de fechas exportado por G&T."""
    tabla = pd.read_excel(archivo, header=None, dtype=object, engine="xlrd")
    cuenta_numero = None
    cuenta_nombre = None
    fecha_inicio = None
    fecha_fin = None
    moneda = "GTQ"
    saldo_inicial = None
    saldo_final = None
    indice_cabecera = None

    for indice, fila in tabla.iterrows():
        valores = [_texto_celda(valor) for valor in fila]
        for posicion, valor in enumerate(valores):
            etiqueta = valor.casefold()
            siguiente = next(
                (item for item in valores[posicion + 1:] if item), ""
            )
            if etiqueta == "#cuenta":
                cuenta_numero = siguiente
            elif etiqueta == "nombre de la cuenta":
                cuenta_nombre = siguiente
            elif etiqueta == "fecha inicial":
                fecha_inicio = _fecha_bancaria(siguiente)
            elif etiqueta == "fecha final":
                fecha_fin = _fecha_bancaria(siguiente)
            elif etiqueta == "saldo inicial":
                saldo_inicial = convertir_monto(siguiente)
        if "monetario (usd)" in " ".join(valores).casefold():
            moneda = "USD"
        normalizados = {valor.casefold() for valor in valores}
        if {"fecha", "referencia", "descripción", "débito", "crédito"} <= normalizados:
            indice_cabecera = indice
            break

    if indice_cabecera is None:
        raise ErrorOperacion(
            "⚠️ El estado de G&T Continental no contiene las columnas esperadas."
        )

    cabecera = [_texto_celda(valor).casefold() for valor in tabla.iloc[indice_cabecera]]
    columnas = {nombre: indice for indice, nombre in enumerate(cabecera) if nombre}
    indice_saldo = columnas.get("saldo")
    cheques = []
    depositos = []
    notas_debito = []
    for _, fila in tabla.iloc[indice_cabecera + 1:].iterrows():
        fecha = _texto_celda(fila.iloc[columnas["fecha"]])
        referencia = _texto_celda(fila.iloc[columnas["referencia"]])
        descripcion = _texto_celda(fila.iloc[columnas["descripción"]])
        debito = convertir_monto(fila.iloc[columnas["débito"]])
        credito = convertir_monto(fila.iloc[columnas["crédito"]])
        saldo_fila = (
            convertir_monto(fila.iloc[indice_saldo])
            if indice_saldo is not None
            else None
        )
        if saldo_fila is not None:
            saldo_final = saldo_fila
        if not fecha or (debito is None and credito is None):
            continue
        descripcion_norm = descripcion.casefold()
        movimiento = {
            "Num_cheque": referencia,
            "Monto": abs(debito if debito is not None else credito),
            "fecha": fecha,
            "descripcion": descripcion,
        }
        if debito is not None and (
            "pago de cheque" in descripcion_norm
            or "cheque propio en consignacion" in descripcion_norm
        ):
            movimiento["tipo"] = "CQ"
            cheques.append(movimiento)
        elif credito is not None:
            movimiento["tipo"] = "DP"
            depositos.append(movimiento)
        else:
            movimiento["tipo"] = "ND"
            notas_debito.append(movimiento)

    return {
        "cheques": pd.DataFrame(
            cheques,
            columns=["Num_cheque", "Monto", "fecha", "tipo", "descripcion"],
        ),
        "otros_cargos": [],
        "depositos": depositos,
        "notas_credito": [],
        "notas_debito": notas_debito,
        "cuenta_numero": cuenta_numero,
        "cuenta_nombre": cuenta_nombre,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "moneda": moneda,
        "saldo_inicial": saldo_inicial,
        "saldo_final": saldo_final,
    }


def _leer_csv_banrural(archivo):
    """Convierte el CSV de movimientos de cuenta exportado por Banrural."""
    contenido = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            contenido = Path(archivo).read_text(encoding=codificacion)
            break
        except UnicodeDecodeError:
            continue
    if contenido is None:
        raise ErrorOperacion(
            "⚠️ No se pudo reconocer la codificación del archivo de Banrural."
        )

    filas = list(csv.reader(contenido.splitlines()))
    cuenta_numero = cuenta_nombre = fecha_inicio = fecha_fin = moneda = None
    saldo_final = None
    indice_cabecera = None
    for indice, fila in enumerate(filas):
        primera = str(fila[0] if fila else "").strip()
        periodo = PATRON_PERIODO_BANRURAL.match(primera)
        if periodo:
            fecha_inicio = _fecha_bancaria(periodo.group(1))
            fecha_fin = _fecha_bancaria(periodo.group(2))
        cuenta = PATRON_CUENTA_BANRURAL.match(primera)
        if cuenta:
            cuenta_numero, _tipo_cuenta, cuenta_nombre, moneda = cuenta.groups()
        if primera.casefold() == "fecha":
            indice_cabecera = indice
            break

    if indice_cabecera is None:
        raise ErrorOperacion(
            "⚠️ El archivo no contiene la cabecera de movimientos de Banrural."
        )

    cabecera = [str(valor).strip().casefold() for valor in filas[indice_cabecera]]
    columnas = {nombre: indice for indice, nombre in enumerate(cabecera)}
    requeridas = {
        "fecha", "descripción", "referencia",
        "cheque propio / local / efectivo", "débito (-)", "crédito (+)",
    }
    if not requeridas <= columnas.keys():
        raise ErrorOperacion(
            "⚠️ El estado de Banrural no contiene todas las columnas esperadas."
        )

    cheques, depositos, notas_debito = [], [], []
    for fila in filas[indice_cabecera + 1:]:
        fila += [""] * (len(cabecera) - len(fila))
        fecha = fila[columnas["fecha"]].strip()
        if not fecha or _fecha_bancaria(fecha) is None:
            continue
        indice_saldo = columnas.get("saldo contable")
        if indice_saldo is not None:
            saldo_fila = convertir_monto(fila[indice_saldo])
            if saldo_fila is not None:
                saldo_final = saldo_fila
        descripcion = fila[columnas["descripción"]].strip()
        referencia = fila[columnas["referencia"]].strip()
        cheque = fila[columnas["cheque propio / local / efectivo"]].strip()
        debito = convertir_monto(fila[columnas["débito (-)"]])
        credito = convertir_monto(fila[columnas["crédito (+)"]])
        if debito is not None and debito != 0:
            movimiento = {
                "Num_cheque": cheque or referencia,
                "Monto": abs(debito), "fecha": fecha,
                "descripcion": descripcion,
            }
            if normalizar_numero_cheque(cheque):
                movimiento["tipo"] = "CQ"
                cheques.append(movimiento)
            else:
                movimiento["tipo"] = "ND"
                notas_debito.append(movimiento)
        elif credito is not None and credito != 0:
            depositos.append({
                "Num_cheque": referencia, "Monto": abs(credito),
                "fecha": fecha, "tipo": "DP", "descripcion": descripcion,
            })

    return {
        "cheques": pd.DataFrame(
            cheques, columns=["Num_cheque", "Monto", "fecha", "tipo", "descripcion"]
        ),
        "otros_cargos": [],
        "depositos": depositos,
        "notas_credito": [],
        "notas_debito": notas_debito,
        "cuenta_numero": cuenta_numero,
        "cuenta_nombre": cuenta_nombre,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "moneda": (moneda or "GTQ").upper(),
        "saldo_inicial": None,
        "saldo_final": saldo_final,
    }


def _leer_csv_bac(archivo):
    """Convierte el CSV de detalle de estado bancario exportado por BAC."""
    contenido = None
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            contenido = Path(archivo).read_text(encoding=codificacion)
            break
        except UnicodeDecodeError:
            continue
    if contenido is None:
        raise ErrorOperacion("⚠️ No se pudo reconocer la codificación del archivo de BAC.")

    filas = list(csv.reader(contenido.splitlines()))
    if len(filas) < 2:
        raise ErrorOperacion("⚠️ El estado de BAC no contiene los datos de la cuenta.")

    cabecera_cuenta = {
        nombre.strip().casefold(): indice
        for indice, nombre in enumerate(filas[0])
    }
    requeridas_cuenta = {"producto", "moneda", "fecha"}
    if not requeridas_cuenta <= cabecera_cuenta.keys():
        raise ErrorOperacion("⚠️ El estado de BAC no contiene los datos esperados de la cuenta.")
    datos_cuenta = filas[1] + [""] * (len(filas[0]) - len(filas[1]))
    cuenta_numero = datos_cuenta[cabecera_cuenta["producto"]].strip()
    cuenta_nombre = datos_cuenta[cabecera_cuenta.get("nombre", 1)].strip()
    moneda_bac = datos_cuenta[cabecera_cuenta["moneda"]].strip().upper()
    fecha_fin = _fecha_bancaria(datos_cuenta[cabecera_cuenta["fecha"]])
    indice_saldo_inicial = cabecera_cuenta.get("saldo inicial")
    saldo_inicial = (
        convertir_monto(datos_cuenta[indice_saldo_inicial])
        if indice_saldo_inicial is not None
        else None
    )
    indice_saldo_final = cabecera_cuenta.get("saldo en libros")
    saldo_final = (
        convertir_monto(datos_cuenta[indice_saldo_final])
        if indice_saldo_final is not None
        else None
    )
    saldo_final_movimientos = None

    indice_cabecera = None
    for indice, fila in enumerate(filas):
        nombres = {valor.strip().casefold() for valor in fila}
        if {
            "fecha de transacción", "referencia de transacción",
            "código de transacción", "descripción de transacción",
            "débito de transacción", "crédito de transacción",
        } <= nombres:
            indice_cabecera = indice
            break
    if indice_cabecera is None:
        raise ErrorOperacion("⚠️ El estado de BAC no contiene la cabecera de movimientos.")

    cabecera = [valor.strip().casefold() for valor in filas[indice_cabecera]]
    columnas = {nombre: indice for indice, nombre in enumerate(cabecera)}
    cheques, depositos, notas_debito = [], [], []
    fechas = []
    for fila in filas[indice_cabecera + 1:]:
        fila += [""] * (len(cabecera) - len(fila))
        fecha = fila[columnas["fecha de transacción"]].strip()
        fecha_normalizada = _fecha_bancaria(fecha)
        if fecha_normalizada is None:
            continue
        fechas.append(fecha_normalizada)
        referencia = fila[columnas["referencia de transacción"]].strip()
        codigo = fila[columnas["código de transacción"]].strip().upper()
        descripcion = fila[columnas["descripción de transacción"]].strip()
        debito = convertir_monto(fila[columnas["débito de transacción"]])
        credito = convertir_monto(fila[columnas["crédito de transacción"]])
        indice_balance = columnas.get("balance de transacción")
        saldo_movimiento = (
            convertir_monto(fila[indice_balance])
            if indice_balance is not None
            else None
        )
        if saldo_movimiento is not None:
            saldo_final_movimientos = saldo_movimiento
        movimiento = {
            "Num_cheque": referencia,
            "fecha": fecha,
            "descripcion": descripcion,
        }
        es_cheque = codigo in {"CH", "CQ", "CK"} or "CHEQUE" in descripcion.upper()
        if debito is not None and debito != 0:
            movimiento["Monto"] = abs(debito)
            movimiento["tipo"] = "CQ" if es_cheque else "ND"
            (cheques if es_cheque else notas_debito).append(movimiento)
        elif credito is not None and credito != 0:
            movimiento["Monto"] = abs(credito)
            movimiento["tipo"] = "DP"
            depositos.append(movimiento)

    return {
        "cheques": pd.DataFrame(
            cheques, columns=["Num_cheque", "Monto", "fecha", "tipo", "descripcion"]
        ),
        "otros_cargos": [],
        "depositos": depositos,
        "notas_credito": [],
        "notas_debito": notas_debito,
        "cuenta_numero": cuenta_numero,
        "cuenta_nombre": cuenta_nombre,
        "fecha_inicio": min(fechas) if fechas else None,
        "fecha_fin": fecha_fin or (max(fechas) if fechas else None),
        "moneda": "GTQ" if moneda_bac in {"QTZ", "GTQ"} else moneda_bac,
        "saldo_inicial": saldo_inicial,
        "saldo_final": saldo_final if saldo_final is not None else saldo_final_movimientos,
    }


LECTORES_ESTADO_CUENTA = {
    "Banco Industrial": {
        ".csv": _leer_csv_banco_industrial,
    },
    "G&T Continental": {
        ".xls": _leer_xls_gt_continental,
    },
    "Banrural": {
        ".csv": _leer_csv_banrural,
    },
    "BAC": {
        ".csv": _leer_csv_bac,
    },
}


def _fecha_bancaria(valor):
    """Devuelve una fecha comparable para las fechas dd-mm-AAAA de BI."""
    fecha = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    return None if pd.isna(fecha) else fecha.date().isoformat()


def _cuentas_coinciden(numero_archivo, numero_configurado):
    archivo = _normalizar_numero_cuenta(numero_archivo)
    configurado = _normalizar_numero_cuenta(numero_configurado)
    if "x" in str(numero_archivo).casefold():
        return bool(archivo) and configurado.endswith(archivo)
    return archivo == configurado


VENTANA_CONCILIACION_MOVIMIENTOS_DIAS = 7


def _separar_movimientos_no_ingresados(locales, bancarios, fecha_inicio, fecha_corte):
    """Hace un cotejo uno-a-uno y devuelve movimientos sin contraparte.

    Primero se reserva cada coincidencia de documento+monto. Para referencias
    distintas se usa monto+fecha dentro de una ventana inclusiva de siete días,
    pero solo cuando la relación es única en ambos sentidos. Ninguna fila se
    reutiliza y las coincidencias ambiguas permanecen como diferencias.
    """
    bancarios_preparados = []
    for movimiento in bancarios:
        fecha_norm = _fecha_bancaria(movimiento["fecha"])
        bancarios_preparados.append(
            {
                **movimiento,
                "numero_norm": normalizar_numero_cheque(movimiento["Num_cheque"]),
                "fecha_norm": fecha_norm,
                "fecha_dt": (
                    datetime.fromisoformat(fecha_norm).date()
                    if fecha_norm is not None
                    else None
                ),
            }
        )

    locales_vigentes = locales.copy()
    if fecha_inicio is not None:
        locales_vigentes = locales_vigentes[
            locales_vigentes["Fecha_dt"].notna()
            & (locales_vigentes["Fecha_dt"] >= pd.Timestamp(fecha_inicio))
        ]
    if fecha_corte is not None:
        locales_vigentes = locales_vigentes[
            locales_vigentes["Fecha_dt"].notna()
            & (locales_vigentes["Fecha_dt"] <= pd.Timestamp(fecha_corte))
        ]
    locales_vigentes = locales_vigentes[
        locales_vigentes["Estado"].astype(str).str.upper() != "ANULADO"
    ]

    locales_preparados = list(locales_vigentes.iterrows())
    indices_bancarios_disponibles = set(range(len(bancarios_preparados)))
    indices_locales_con_match = set()

    # Las referencias exactas tienen prioridad global sobre la ventana de
    # fechas. Así, una fila flexible anterior no puede consumir la contraparte
    # exacta de otro movimiento local.
    for indice_local, (_, local) in enumerate(locales_preparados):
        monto = local["Monto_valor"]
        numero = normalizar_numero_cheque(local["Num"])
        indice_bancario = next(
            (
                indice
                for indice in sorted(indices_bancarios_disponibles)
                if numero
                and bancarios_preparados[indice]["numero_norm"] == numero
                and bancarios_preparados[indice]["Monto"] == monto
            ),
            None,
        )
        if indice_bancario is not None:
            indices_locales_con_match.add(indice_local)
            indices_bancarios_disponibles.remove(indice_bancario)

    candidatos_por_local = {}
    locales_por_bancario = {
        indice: [] for indice in indices_bancarios_disponibles
    }
    for indice_local, (_, local) in enumerate(locales_preparados):
        if indice_local in indices_locales_con_match:
            continue

        monto = local["Monto_valor"]
        fecha_local = (
            None if pd.isna(local["Fecha_dt"]) else local["Fecha_dt"].date()
        )
        candidatos = []
        if monto is not None and fecha_local is not None:
            for indice_bancario in sorted(indices_bancarios_disponibles):
                banco = bancarios_preparados[indice_bancario]
                fecha_banco = banco["fecha_dt"]
                if (
                    banco["Monto"] == monto
                    and fecha_banco is not None
                    and abs((fecha_banco - fecha_local).days)
                    <= VENTANA_CONCILIACION_MOVIMIENTOS_DIAS
                ):
                    candidatos.append(indice_bancario)
                    locales_por_bancario[indice_bancario].append(indice_local)
        candidatos_por_local[indice_local] = candidatos

    for indice_local, candidatos in candidatos_por_local.items():
        if len(candidatos) != 1:
            continue
        indice_bancario = candidatos[0]
        if len(locales_por_bancario[indice_bancario]) != 1:
            continue
        indices_locales_con_match.add(indice_local)
        indices_bancarios_disponibles.remove(indice_bancario)

    sin_ingresar = []
    for indice_local, (_, local) in enumerate(locales_preparados):
        if indice_local not in indices_locales_con_match:
            fecha = (
                None
                if pd.isna(local["Fecha_dt"])
                else local["Fecha_dt"].date().isoformat()
            )
            monto = local["Monto_valor"]
            sin_ingresar.append(
                {
                    "num": str(local["Num"] or "S/N"),
                    "fecha": fecha or "N/D",
                    "descripcion": str(local.get("Descripcion", "") or ""),
                    "monto": monto,
                }
            )
    disponibles = [
        movimiento
        for indice, movimiento in enumerate(bancarios_preparados)
        if indice in indices_bancarios_disponibles
    ]
    return sin_ingresar, disponibles


def _leer_estado_cuenta(archivo, formato):
    extension = Path(archivo).suffix.lower()
    lector = LECTORES_ESTADO_CUENTA.get(formato, {}).get(extension)
    if lector is not None:
        return lector(archivo)
    raise ErrorOperacion(
        f"⚠️ El archivo {extension or 'sin extensión'} no es compatible con el formato de conciliación '{formato}'."
    )


def obtener_conciliacion(cuenta_id=None, archivo_banco=None, fecha_corte=None):
    cuenta = obtener_cuenta(cuenta_id)
    if not archivo_banco:
        raise ErrorOperacion("⚠️ Selecciona el estado de cuenta que deseas conciliar.")
    if not Path(archivo_banco).exists():
        raise ErrorOperacion("⚠️ No se encontró el estado de cuenta seleccionado.")

    try:
        df_nuestro = cargar_cheques_registrados(cuenta["id"])
        if fecha_corte is not None:
            fecha_corte = normalizar_fecha(fecha_corte)
            corte = pd.Timestamp(fecha_corte)
            df_nuestro = df_nuestro[
                df_nuestro["Fecha_dt"].notna()
                & (df_nuestro["Fecha_dt"] <= corte)
            ].copy()
        estado_banco = _leer_estado_cuenta(
            archivo_banco, cuenta["formato_conciliacion"]
        )
        numero_archivo = estado_banco["cuenta_numero"]
        numero_configurado = str(cuenta.get("numero") or "").strip()
        if numero_archivo and numero_configurado:
            if not _cuentas_coinciden(numero_archivo, numero_configurado):
                raise ErrorOperacion(
                    f"⚠️ El estado pertenece a la cuenta {numero_archivo}, no a la cuenta seleccionada {numero_configurado}."
                )
        if fecha_corte is not None and estado_banco["fecha_fin"]:
            if estado_banco["fecha_fin"] != fecha_corte:
                raise ErrorOperacion(
                    f"⚠️ El estado termina el {estado_banco['fecha_fin']}, pero seleccionaste un corte al {fecha_corte}."
                )
        df_banco = estado_banco["cheques"]
        moneda = estado_banco["moneda"]
        simbolo = "$" if moneda == "USD" else "Q"

        columnas_banco = {str(col).strip().lower(): col for col in df_banco.columns}
        col_num = columnas_banco.get("num_cheque")
        col_monto = columnas_banco.get("monto")

        if col_num is None or col_monto is None:
            raise ErrorOperacion("⚠️ El archivo del banco debe incluir las columnas 'Num_cheque' y 'Monto'.")

        df_banco = df_banco.copy()
        df_banco["Num_original"] = df_banco[col_num]
        df_banco["Num_norm"] = df_banco[col_num].map(normalizar_numero_cheque)
        df_banco["Monto_valor"] = df_banco[col_monto].map(convertir_monto)
        filas_numero_invalido = df_banco[df_banco["Num_norm"].isna()].copy()
        df_banco = df_banco[df_banco["Num_norm"].notna()].copy()

        cheques = []
        for _, fila in df_nuestro.iterrows():
            num = fila["Num_norm"]
            if not num:
                continue

            cobrado = df_banco[df_banco["Num_norm"] == num]
            estado = str(fila.get("Estado", "")).upper()

            if estado == "ANULADO":
                if cobrado.empty:
                    mensaje = f"🚫 Cheque {num} está ANULADO y no aparece cobrado en el banco."
                    resultado = "ANULADO"
                else:
                    mensaje = f"🚨 Cheque {num} está ANULADO pero el banco sí lo cobró."
                    resultado = "ALERTA"
                cheques.append({"num": num, "estado": estado, "resultado": resultado, "monto_nuestro": fila["Monto_valor"], "mensaje": mensaje})
                continue

            if cobrado.empty:
                mensaje = f"⏳ Cheque {num} en TRÁNSITO."
                cheques.append({"num": num, "estado": estado, "resultado": "TRANSITO", "monto_nuestro": fila["Monto_valor"], "mensaje": mensaje})
                continue

            monto_nuestro = fila["Monto_valor"]
            if len(cobrado) > 1:
                montos = cobrado["Monto_valor"].tolist()
                if any(monto is None for monto in montos):
                    mensaje = (
                        f"🚨 Cheque {num} aparece {len(cobrado)} veces en el banco "
                        "y al menos un monto es inválido."
                    )
                    cheques.append(
                        {
                            "num": num,
                            "estado": estado,
                            "resultado": "DUPLICADO_INVALIDO",
                            "monto_nuestro": monto_nuestro,
                            "monto_banco": None,
                            "mensaje": mensaje,
                        }
                    )
                    continue

                montos_validos = cobrado["Monto_valor"].tolist()
                total_banco = sum(montos_validos, Decimal("0.00"))
                mensaje = (
                    f"🚨 Cheque {num} aparece {len(cobrado)} veces en el banco "
                    f"por un total de {simbolo} {formatear_monto(total_banco)}."
                )
                cheques.append(
                    {
                        "num": num,
                        "estado": estado,
                        "resultado": "DUPLICADO",
                        "monto_nuestro": monto_nuestro,
                        "monto_banco": total_banco,
                        "mensaje": mensaje,
                    }
                )
                continue

            monto_banco = cobrado.iloc[0]["Monto_valor"]

            if monto_nuestro is None or monto_banco is None:
                mensaje = f"⚠️ No pude comparar el monto del cheque {num} por datos inválidos."
                resultado = "INVALIDO"
            elif monto_nuestro == monto_banco:
                mensaje = f"✅ Cheque {num} cobrado perfectamente."
                resultado = "COBRADO"
            else:
                mensaje = (
                    f"⚠️ ¡Ojo! Cheque {num} diferencia: Nuestro {simbolo} {formatear_monto(monto_nuestro)} | "
                    f"Banco {simbolo} {formatear_monto(monto_banco)}"
                )
                resultado = "DIFERENCIA"
            cheques.append(
                {
                    "num": num,
                    "estado": estado,
                    "resultado": resultado,
                    "monto_nuestro": monto_nuestro,
                    "monto_banco": monto_banco,
                    "mensaje": mensaje,
                }
            )

        detalles_cheques = {
            fila["Num_norm"]: {
                "fecha": _texto_celda(fila.get("Fecha", "")),
                "nombre": _texto_celda(fila.get("Nombre", "")),
            }
            for _, fila in df_nuestro.iterrows()
            if fila.get("Num_norm")
        }
        for cheque in cheques:
            cheque.update(detalles_cheques.get(cheque["num"], {}))

        no_registrados = []
        lista_nuestros_nums = set(df_nuestro["Num_norm"].dropna().tolist())
        for _, fila_banco in df_banco.iterrows():
            num_bco = fila_banco["Num_norm"]
            if num_bco not in lista_nuestros_nums:
                monto_banco = fila_banco["Monto_valor"]
                monto_texto = formatear_monto(monto_banco) if monto_banco is not None else "N/D"
                mensaje = (
                    f"❓ Cheque {num_bco} por {simbolo} {monto_texto} cobrado por el banco, "
                    "pero NO está en nuestro sistema."
                )
                no_registrados.append({"num": num_bco, "monto": monto_banco, "mensaje": mensaje})

        for _, fila_banco in filas_numero_invalido.iterrows():
            valor_original = fila_banco["Num_original"]
            try:
                sin_valor = pd.isna(valor_original)
            except TypeError:
                sin_valor = False
            num_texto = (
                "N/D"
                if sin_valor or not str(valor_original).strip()
                else str(valor_original).strip()
            )
            monto_banco = fila_banco["Monto_valor"]
            monto_texto = (
                formatear_monto(monto_banco)
                if monto_banco is not None
                else "N/D"
            )
            mensaje = (
                f"⚠️ Fila del banco con número de cheque inválido "
                f"({num_texto}) y monto {simbolo} {monto_texto}."
            )
            no_registrados.append(
                {
                    "num": num_texto,
                    "monto": monto_banco,
                    "resultado": "INVALIDO",
                    "mensaje": mensaje,
                }
            )

        # Se conserva esta salida histórica para consumidores de la fachada;
        # la interfaz nueva usa la lista específica de notas no ingresadas.
        for cargo in estado_banco["notas_debito"] + estado_banco["otros_cargos"]:
            numero = cargo["Num_cheque"] or "N/D"
            monto = cargo["Monto"]
            descripcion = cargo["descripcion"] or "Sin descripción"
            no_registrados.append(
                {
                    "num": numero,
                    "monto": monto,
                    "resultado": "CARGO_BANCO",
                    "mensaje": (
                        f"❓ {cargo['tipo']} {numero} por {simbolo} {formatear_monto(monto)}: "
                        f"{descripcion}."
                    ),
                }
            )

        # BI reporta varios abonos que corresponden a depósitos locales como
        # notas de crédito (NC). Se cotejan junto con DE/DP; únicamente las NC
        # sin contraparte local conservan su clasificación contable.
        abonos_bancarios = (
            estado_banco["depositos"] + estado_banco.get("notas_credito", [])
        )
        depositos_no_ingresados, abonos_banco_sin_registro = (
            _separar_movimientos_no_ingresados(
                cargar_depositos_registrados(cuenta["id"]),
                abonos_bancarios,
                estado_banco["fecha_inicio"],
                fecha_corte,
            )
        )
        depositos_banco_sin_registro = [
            movimiento
            for movimiento in abonos_banco_sin_registro
            if movimiento.get("tipo") != "NC"
        ]
        notas_credito_sin_deposito = [
            movimiento
            for movimiento in abonos_banco_sin_registro
            if movimiento.get("tipo") == "NC"
        ]
        notas_locales_sin_banco, notas_debito_no_ingresadas = (
            _separar_movimientos_no_ingresados(
                cargar_notas_debito_registradas(cuenta["id"]),
                estado_banco["notas_debito"],
                estado_banco["fecha_inicio"],
                fecha_corte,
            )
        )
        notas_debito_no_ingresadas = [
            {
                "num": movimiento["Num_cheque"] or "S/N",
                "fecha": _fecha_bancaria(movimiento["fecha"]) or "N/D",
                "descripcion": movimiento["descripcion"] or "Sin descripción",
                "monto": movimiento["Monto"],
            }
            for movimiento in notas_debito_no_ingresadas
        ]
        depositos_banco_sin_registro = [
            {
                "num": movimiento["Num_cheque"] or "S/N",
                "fecha": _fecha_bancaria(movimiento["fecha"]) or "N/D",
                "descripcion": movimiento["descripcion"] or "Sin descripción",
                "monto": movimiento["Monto"],
            }
            for movimiento in depositos_banco_sin_registro
        ]
        notas_credito_banco = [
            {
                "num": movimiento["Num_cheque"] or "S/N",
                "fecha": _fecha_bancaria(movimiento["fecha"]) or "N/D",
                "descripcion": movimiento["descripcion"] or "Sin descripción",
                "monto": movimiento["Monto"],
            }
            for movimiento in notas_credito_sin_deposito
        ]
        for fila in depositos_no_ingresados:
            fila["diferencia"] = "Pendiente en banco"
        for fila in depositos_banco_sin_registro:
            fila["diferencia"] = "No registrado localmente"
        diferencias_depositos = depositos_no_ingresados + depositos_banco_sin_registro

        for fila in notas_locales_sin_banco:
            fila["diferencia"] = "No aparece en el banco"
        for fila in notas_debito_no_ingresadas:
            fila["diferencia"] = "No registrada localmente"
        diferencias_notas_debito = notas_locales_sin_banco + notas_debito_no_ingresadas
        cheques_cobrados = [
            cheque for cheque in cheques if cheque["resultado"] not in {"TRANSITO", "ANULADO"}
        ]
        # Un estado mensual no permite saber si un cheque histórico se cobró en
        # un estado anterior. Mostrar todos como pendientes produciría miles de
        # falsos tránsitos después de una importación histórica.
        inicio_estado = estado_banco["fecha_inicio"]
        numeros_emitidos_en_periodo = set(
            df_nuestro.loc[
                df_nuestro["Fecha_dt"].notna()
                & (
                    df_nuestro["Fecha_dt"] >= pd.Timestamp(inicio_estado)
                    if inicio_estado
                    else True
                ),
                "Num_norm",
            ].dropna()
        )
        cheques_transito = [
            cheque
            for cheque in cheques
            if cheque["resultado"] == "TRANSITO"
            and cheque["num"] in numeros_emitidos_en_periodo
        ]

        def resumen(filas):
            return {
                "cantidad": len(filas),
                "total": sum(
                    (fila.get("monto_nuestro", fila.get("monto")) or Decimal("0.00") for fila in filas),
                    Decimal("0.00"),
                ),
            }

        return {
            "cuenta": cuenta,
            "fecha_corte": fecha_corte,
            "estado_cuenta": {
                "numero": estado_banco["cuenta_numero"],
                "nombre": estado_banco["cuenta_nombre"],
                "fecha_inicio": estado_banco["fecha_inicio"],
                "fecha_fin": estado_banco["fecha_fin"],
                "moneda": moneda,
                "saldo_inicial": estado_banco.get("saldo_inicial"),
                "saldo_final": estado_banco.get("saldo_final"),
            },
            "cheques": cheques,
            "no_registrados": no_registrados,
            "cheques_cobrados": cheques_cobrados,
            "cheques_transito": cheques_transito,
            "depositos_no_ingresados": depositos_no_ingresados,
            "notas_debito_no_ingresadas": notas_debito_no_ingresadas,
            "depositos_banco_sin_registro": depositos_banco_sin_registro,
            "notas_credito_banco": notas_credito_banco,
            "notas_debito_locales_sin_banco": notas_locales_sin_banco,
            "diferencias_depositos": diferencias_depositos,
            "diferencias_notas_debito": diferencias_notas_debito,
            "resumen": {
                "cheques_cobrados": resumen(cheques_cobrados),
                "cheques_transito": resumen(cheques_transito),
                "depositos_no_ingresados": resumen(depositos_no_ingresados),
                "depositos_banco_sin_registro": resumen(depositos_banco_sin_registro),
                "notas_credito_banco": resumen(notas_credito_banco),
                "notas_debito_no_ingresadas": resumen(notas_debito_no_ingresadas),
                "notas_debito_locales_sin_banco": resumen(notas_locales_sin_banco),
                "diferencias_depositos": resumen(diferencias_depositos),
                "diferencias_notas_debito": resumen(diferencias_notas_debito),
            },
        }

    except ErrorOperacion:
        raise
    except Exception as e:
        raise ErrorOperacion(f"⚠️ Ocurrió un error leyendo los archivos: {e}") from e

def obtener_reporte_movimientos(fecha=None, cuenta_id=None):
    if fecha is None:
        fecha = datetime.now().date()
    fecha = normalizar_fecha(fecha)
    periodo_actual = pd.Timestamp(fecha).to_period("M")
    total_cheques = Decimal("0.00")
    total_notas_debito = Decimal("0.00")
    total_depositos = Decimal("0.00")

    cuenta = obtener_cuenta(cuenta_id) if cuenta_id is not None else None
    df_cheques = cargar_cheques_registrados(cuenta_id)
    df_cheques = df_cheques[df_cheques["Monto_valor"].notna() & df_cheques["Fecha_dt"].notna()].copy()
    df_cheques_mes = df_cheques[df_cheques["Fecha_dt"].dt.to_period("M") == periodo_actual].copy()

    if not df_cheques_mes.empty:
        df_cheques_mes["Monto"] = df_cheques_mes["Monto_valor"].map(formatear_monto)
        total_cheques = sum(
            (fila["Monto_valor"] for _, fila in df_cheques_mes.iterrows() if str(fila["Estado"]).upper() != "ANULADO"),
            Decimal("0.00"),
        )
    else:
        df_cheques_mes = pd.DataFrame(columns=["Num", "Fecha", "Nombre", "Monto", "Estado"])

    df_depositos = cargar_depositos_registrados(cuenta_id)
    df_depositos = df_depositos[df_depositos["Monto_valor"].notna() & df_depositos["Fecha_dt"].notna()].copy()
    df_depositos_mes = df_depositos[df_depositos["Fecha_dt"].dt.to_period("M") == periodo_actual].copy()

    if not df_depositos_mes.empty:
        df_depositos_mes["Monto"] = df_depositos_mes["Monto_valor"].map(formatear_monto)
        total_depositos = sum(
            (
                fila["Monto_valor"]
                for _, fila in df_depositos_mes.iterrows()
                if str(fila["Estado"]).upper() != "ANULADO"
            ),
            Decimal("0.00"),
        )
    else:
        df_depositos_mes = pd.DataFrame(
            columns=["Num", "Fecha", "Descripcion", "Monto", "Estado"]
        )

    df_notas_debito = cargar_notas_debito_registradas(cuenta_id)
    df_notas_debito = df_notas_debito[df_notas_debito["Monto_valor"].notna() & df_notas_debito["Fecha_dt"].notna()].copy()
    df_notas_debito_mes = df_notas_debito[df_notas_debito["Fecha_dt"].dt.to_period("M") == periodo_actual].copy()

    if not df_notas_debito_mes.empty:
        df_notas_debito_mes["Monto"] = df_notas_debito_mes["Monto_valor"].map(formatear_monto)
        total_notas_debito = sum(
            (
                fila["Monto_valor"]
                for _, fila in df_notas_debito_mes.iterrows()
                if str(fila["Estado"]).upper() != "ANULADO"
            ),
            Decimal("0.00"),
        )
    else:
        df_notas_debito_mes = pd.DataFrame(
            columns=["Num", "Fecha", "Descripcion", "Monto", "Estado"]
        )

    total_egresos = total_cheques + total_notas_debito
    saldo = total_depositos - total_egresos

    return {
        "periodo": str(periodo_actual),
        "cuenta": cuenta,
        "cheques": df_cheques_mes,
        "depositos": df_depositos_mes,
        "notas_debito": df_notas_debito_mes,
        "total_cheques": total_cheques,
        "total_notas_debito": total_notas_debito,
        "total_egresos": total_egresos,
        "total_depositos": total_depositos,
        "saldo": saldo,
    }
