import os
from datetime import datetime
from decimal import Decimal

import pandas as pd

from .domain import convertir_monto, normalizar_fecha, normalizar_numero_cheque
from .errors import ErrorOperacion
from .movements import cargar_cheques_registrados, cargar_depositos_registrados, formatear_monto
from .storage import obtener_cuenta

ARCHIVO_BANCO = "estado_cuenta.xlsx"


def obtener_conciliacion(cuenta_id=None, archivo_banco=None, fecha_corte=None):
    cuenta = obtener_cuenta(cuenta_id)
    archivo_banco = archivo_banco or ARCHIVO_BANCO
    if not os.path.exists(archivo_banco):
        raise ErrorOperacion("⚠️ Faltan archivos. Asegúrate de tener registros y estado de cuenta.")

    try:
        df_nuestro = cargar_cheques_registrados(cuenta["id"])
        if fecha_corte is not None:
            fecha_corte = normalizar_fecha(fecha_corte)
            corte = pd.Timestamp(fecha_corte)
            df_nuestro = df_nuestro[
                df_nuestro["Fecha_dt"].notna()
                & (df_nuestro["Fecha_dt"] <= corte)
            ].copy()
        if df_nuestro.empty:
            raise ErrorOperacion("⚠️ No hay cheques registrados hasta la fecha de corte.")
        df_banco = pd.read_excel(archivo_banco)

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
                cheques.append({"num": num, "estado": estado, "resultado": resultado, "mensaje": mensaje})
                continue

            if cobrado.empty:
                mensaje = f"⏳ Cheque {num} en TRÁNSITO."
                cheques.append({"num": num, "estado": estado, "resultado": "TRANSITO", "mensaje": mensaje})
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
                    f"por un total de Q {formatear_monto(total_banco)}."
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
                    f"⚠️ ¡Ojo! Cheque {num} diferencia: Nuestro Q {formatear_monto(monto_nuestro)} | "
                    f"Banco Q {formatear_monto(monto_banco)}"
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

        no_registrados = []
        lista_nuestros_nums = set(df_nuestro["Num_norm"].dropna().tolist())
        for _, fila_banco in df_banco.iterrows():
            num_bco = fila_banco["Num_norm"]
            if num_bco not in lista_nuestros_nums:
                monto_banco = fila_banco["Monto_valor"]
                monto_texto = formatear_monto(monto_banco) if monto_banco is not None else "N/D"
                mensaje = (
                    f"❓ Cheque {num_bco} por Q {monto_texto} cobrado por el banco, "
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
                f"({num_texto}) y monto Q {monto_texto}."
            )
            no_registrados.append(
                {
                    "num": num_texto,
                    "monto": monto_banco,
                    "resultado": "INVALIDO",
                    "mensaje": mensaje,
                }
            )

        return {
            "cuenta": cuenta,
            "fecha_corte": fecha_corte,
            "cheques": cheques,
            "no_registrados": no_registrados,
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

    saldo = total_depositos - total_cheques

    return {
        "periodo": str(periodo_actual),
        "cuenta": cuenta,
        "cheques": df_cheques_mes,
        "depositos": df_depositos_mes,
        "total_cheques": total_cheques,
        "total_depositos": total_depositos,
        "saldo": saldo,
    }
