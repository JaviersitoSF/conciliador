import sqlite3
from datetime import datetime

import pandas as pd

from .domain import convertir_monto, normalizar_fecha, normalizar_numero_cheque
from .errors import ErrorOperacion
from . import printing
from .storage import (conectar_db, crear_respaldo_posterior, inicializar_db,
    obtener_cuenta, obtener_formato_impresion, registrar_auditoria, transaccion)

COLUMNAS_CHEQUES = ["Cuenta_id", "Banco", "Cuenta", "Num", "Fecha", "Nombre", "Monto", "Estado", "Descripcion"]

def formatear_monto(valor):
    monto = convertir_monto(valor)
    if monto is None:
        raise ValueError("Monto invalido")
    return f"{monto:.2f}"
def crear_dataframe_vacio(columnas):
    df = pd.DataFrame(columns=columnas + ["Monto_valor", "Fecha_dt"])
    df["Monto_valor"] = pd.Series(dtype=object)
    df["Fecha_dt"] = pd.to_datetime(pd.Series(dtype=object))
    return df

def cargar_cheques_registrados(cuenta_id=None):
    columnas = COLUMNAS_CHEQUES
    vacio = crear_dataframe_vacio(columnas)
    vacio["Num_norm"] = pd.Series(dtype=object)

    inicializar_db()
    with conectar_db() as conexion:
        consulta = """
            SELECT c.cuenta_id AS Cuenta_id, cb.banco AS Banco,
                   cb.nombre AS Cuenta, c.numero AS Num, c.fecha AS Fecha,
                   c.nombre AS Nombre, c.monto AS Monto, c.estado AS Estado,
                   c.descripcion AS Descripcion
            FROM cheques c
            JOIN cuentas_bancarias cb ON cb.id = c.cuenta_id
        """
        parametros = ()
        if cuenta_id is not None:
            consulta += " WHERE c.cuenta_id = ?"
            parametros = (obtener_cuenta(cuenta_id)["id"],)
        consulta += " ORDER BY c.id"
        filas = conexion.execute(consulta, parametros).fetchall()
    if not filas:
        return vacio

    df = pd.DataFrame([dict(fila) for fila in filas], columns=columnas)
    df["Num_norm"] = df["Num"].map(normalizar_numero_cheque)
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df

def cargar_depositos_registrados(cuenta_id=None):
    columnas = ["Cuenta_id", "Banco", "Cuenta", "Fecha", "Descripcion", "Monto"]
    vacio = crear_dataframe_vacio(columnas)

    inicializar_db()
    with conectar_db() as conexion:
        consulta = """
            SELECT d.cuenta_id AS Cuenta_id, cb.banco AS Banco,
                   cb.nombre AS Cuenta, d.fecha AS Fecha,
                   d.descripcion AS Descripcion, d.monto AS Monto
            FROM depositos d
            JOIN cuentas_bancarias cb ON cb.id = d.cuenta_id
        """
        parametros = ()
        if cuenta_id is not None:
            consulta += " WHERE d.cuenta_id = ?"
            parametros = (obtener_cuenta(cuenta_id)["id"],)
        consulta += " ORDER BY d.id"
        filas = conexion.execute(consulta, parametros).fetchall()
    if not filas:
        return vacio

    df = pd.DataFrame([dict(fila) for fila in filas], columns=columnas)
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df

def cheque_ya_registrado(numero, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    numero = normalizar_numero_cheque(numero)
    if not numero:
        return False

    inicializar_db()
    with conectar_db() as conexion:
        fila = conexion.execute(
            "SELECT 1 FROM cheques WHERE cuenta_id = ? AND numero = ?",
            (cuenta["id"], numero),
        ).fetchone()
    return fila is not None

def registrar_deposito_datos(monto, descripcion, fecha=None, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    monto = convertir_monto(monto)
    if monto is None:
        raise ErrorOperacion("⚠️ Error: Solo usar números y punto decimal.")
    if monto <= 0:
        raise ErrorOperacion("⚠️ Error: El monto debe ser mayor que cero.")

    descripcion = str(descripcion or "").strip()
    if not descripcion:
        raise ErrorOperacion("⚠️ Error: el campo no puede quedar vacío.")

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")
    fecha = normalizar_fecha(fecha)
    descripcion = descripcion.upper()

    with transaccion() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO depositos (cuenta_id, fecha, descripcion, monto)
            VALUES (?, ?, ?, ?)
            """,
            (cuenta["id"], fecha, descripcion, formatear_monto(monto)),
        )
        registrar_auditoria(
            conexion,
            "CREAR",
            "DEPOSITO",
            cursor.lastrowid,
            f"{cuenta['banco']} / {cuenta['nombre']}: depósito "
            f"Q {formatear_monto(monto)}: {descripcion}",
        )
    crear_respaldo_posterior()

    return {
        "fecha": fecha,
        "descripcion": descripcion,
        "cuenta_id": cuenta["id"],
        "monto": monto,
        "mensaje": f"✅ Depósito de Q {formatear_monto(monto)} registrado con éxito.",
    }

def guardar_cheque_en_archivo(num, fecha, nombre, monto, descripcion="", cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    num = normalizar_numero_cheque(num)
    if not num:
        raise ErrorOperacion("⚠️ Error: el número de cheque debe ser mayor que cero.")

    fecha = normalizar_fecha(fecha)
    nombre = str(nombre or "").strip()
    if not nombre:
        raise ErrorOperacion("⚠️ Error: el campo no puede quedar vacío.")

    monto = convertir_monto(monto)
    if monto is None:
        raise ErrorOperacion("⚠️ Error: Solo usar números y punto decimal.")
    if monto <= 0:
        raise ErrorOperacion("⚠️ Error: El monto debe ser mayor que cero.")

    descripcion = str(descripcion or "").strip()
    try:
        with transaccion() as conexion:
            conexion.execute(
                """
                INSERT INTO cheques
                    (cuenta_id, numero, fecha, nombre, monto, estado, descripcion)
                VALUES (?, ?, ?, ?, ?, 'TRANSITO', ?)
                """,
                (
                    cuenta["id"], num, fecha, nombre,
                    formatear_monto(monto), descripcion,
                ),
            )
            registrar_auditoria(
                conexion,
                "CREAR",
                "CHEQUE",
                num,
                f"{cuenta['banco']} / {cuenta['nombre']}: cheque "
                f"Q {formatear_monto(monto)} para {nombre}",
            )
    except sqlite3.IntegrityError as e:
        raise ErrorOperacion(f"⚠️ El cheque {num} ya existe en el historial.") from e
    crear_respaldo_posterior()

def emitir_cheque_datos(
    num_cheque, nombre, monto, fecha=None, descripcion="", cuenta_id=None,
    imprimir=True,
):
    cuenta = obtener_cuenta(cuenta_id)
    num_cheque = normalizar_numero_cheque(num_cheque)
    if not num_cheque:
        raise ErrorOperacion("⚠️ Error: el número de cheque debe ser mayor que cero.")

    nombre = str(nombre or "").strip()
    if not nombre:
        raise ErrorOperacion("⚠️ Error: el campo no puede quedar vacío.")

    monto = convertir_monto(monto)
    if monto is None:
        raise ErrorOperacion("⚠️ Error: Solo usar números y punto decimal.")
    if monto <= 0:
        raise ErrorOperacion("⚠️ Error: El monto debe ser mayor que cero.")

    if cheque_ya_registrado(num_cheque, cuenta["id"]):
        raise ErrorOperacion(f"⚠️ El cheque {num_cheque} ya existe en el historial.")

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")
    fecha = normalizar_fecha(fecha)
    nombre = nombre.upper()
    descripcion = str(descripcion or "").strip().upper()
    nombre_pdf = printing.resolver_archivo_salida(
        f"cheque_{cuenta['id']}_{num_cheque}.pdf"
    )

    guardar_cheque_en_archivo(
        num_cheque, fecha, nombre, monto, descripcion, cuenta["id"]
    )
    if not imprimir:
        return {
            "num": num_cheque,
            "fecha": fecha,
            "nombre": nombre,
            "descripcion": descripcion,
            "cuenta_id": cuenta["id"],
            "monto": monto,
            "pdf": None,
            "impresion_enviada": False,
            "mensaje": "✅ Cheque registrado sin imprimir.",
        }

    try:
        impresion_enviada = printing.imprimir_cheque_pdf(
            num_cheque,
            fecha,
            nombre,
            monto,
            descripcion,
            archivo_salida=nombre_pdf,
            formato=obtener_formato_impresion(cuenta["id"]),
        )
    except Exception as e:
        raise ErrorOperacion(
            f"⚠️ El cheque {num_cheque} fue registrado, pero no se pudo generar "
            "el PDF. Usa la opción de reimpresión."
        ) from e

    if impresion_enviada:
        mensaje = "✅ Cheque registrado y listo para imprimir con éxito."
    else:
        mensaje = (
            "⚠️ Cheque registrado y PDF generado, pero no se pudo abrir o enviar "
            "a impresión. Abre el archivo manualmente."
        )

    return {
        "num": num_cheque,
        "fecha": fecha,
        "nombre": nombre,
        "descripcion": descripcion,
        "cuenta_id": cuenta["id"],
        "monto": monto,
        "pdf": str(nombre_pdf),
        "impresion_enviada": impresion_enviada,
        "mensaje": mensaje,
    }

def reimprimir_cheque_numero(num_cheque, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    num_cheque = normalizar_numero_cheque(num_cheque)
    if not num_cheque:
        raise ErrorOperacion("⚠️ Error: el número de cheque debe ser mayor que cero.")

    df = cargar_cheques_registrados(cuenta["id"])
    if df.empty:
        raise ErrorOperacion("⚠️ No hay registro de cheques aún.")

    coincidencias = df[df["Num_norm"].eq(num_cheque)]
    if coincidencias.empty:
        raise ErrorOperacion(f"⚠️ El cheque {num_cheque} no existe en los registros.")

    cheque = coincidencias.iloc[-1]
    if str(cheque["Estado"]).upper() == "ANULADO":
        raise ErrorOperacion(
            f"⚠️ El cheque {num_cheque} está anulado y no se puede reimprimir."
        )

    monto = convertir_monto(cheque["Monto"])
    if monto is None:
        raise ErrorOperacion(f"⚠️ El cheque {num_cheque} tiene un monto inválido.")

    nombre_pdf = printing.resolver_archivo_salida(
        f"cheque_{cuenta['id']}_{num_cheque}.pdf"
    )
    impresion_enviada = printing.imprimir_cheque_pdf(
        num_cheque,
        cheque["Fecha"],
        cheque["Nombre"],
        monto,
        cheque["Descripcion"],
        archivo_salida=nombre_pdf,
        formato=obtener_formato_impresion(cuenta["id"]),
    )
    with transaccion() as conexion:
        registrar_auditoria(
            conexion,
            "REIMPRIMIR",
            "CHEQUE",
            num_cheque,
            f"{cuenta['banco']} / {cuenta['nombre']}: se generó una nueva copia.",
        )
    crear_respaldo_posterior()
    if impresion_enviada:
        return f"✅ Cheque {num_cheque} listo para volver a imprimir."
    return (
        f"⚠️ Se generó el PDF del cheque {num_cheque}, pero no se pudo abrir o "
        "enviar a impresión. Abre el archivo manualmente."
    )

def anular_cheque_numero(num_anular, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    num_anular = normalizar_numero_cheque(num_anular)
    if not num_anular:
        raise ErrorOperacion("⚠️ Error: el número de cheque debe ser mayor que cero.")

    with transaccion() as conexion:
        cheque = conexion.execute(
            """
            SELECT estado FROM cheques
            WHERE cuenta_id = ? AND numero = ?
            """,
            (cuenta["id"], num_anular),
        ).fetchone()
        if cheque is None:
            total = conexion.execute(
                "SELECT COUNT(*) FROM cheques WHERE cuenta_id = ?",
                (cuenta["id"],),
            ).fetchone()[0]
            if total == 0:
                raise ErrorOperacion("⚠️ No hay registro de cheques aún.")
            raise ErrorOperacion(f"⚠️ El cheque {num_anular} no existe en los registros.")
        if cheque["estado"] == "ANULADO":
            raise ErrorOperacion(f"⚠️ El cheque {num_anular} ya está anulado.")

        conexion.execute(
            """
            UPDATE cheques
            SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
            WHERE cuenta_id = ? AND numero = ?
            """,
            (cuenta["id"], num_anular),
        )
        registrar_auditoria(
            conexion,
            "ANULAR",
            "CHEQUE",
            num_anular,
            "Estado cambiado a ANULADO.",
        )
    crear_respaldo_posterior()

    mensaje = f"🚫 ¡Hecho! El cheque {num_anular} ha sido marcado como ANULADO."
    return {"num": num_anular, "cantidad": 1, "mensaje": mensaje}
