import sqlite3
import unicodedata
from datetime import datetime

import pandas as pd

from .domain import convertir_monto, normalizar_fecha, normalizar_numero_cheque
from .errors import ErrorOperacion
from . import printing
from .storage import (conectar_db, crear_respaldo_posterior, inicializar_db,
    obtener_cuenta, obtener_formato_impresion, registrar_auditoria, transaccion)

COLUMNAS_CHEQUES = ["Id", "Cuenta_id", "Banco", "Cuenta", "Num", "Fecha", "Nombre", "Monto", "Estado", "Descripcion"]
COLUMNAS_MOVIMIENTOS = [
    "Id", "Cuenta_id", "Banco", "Cuenta", "Num", "Fecha", "Descripcion",
    "Monto", "Estado",
]

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

def _normalizar_texto_busqueda(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).casefold()
    return "".join(
        caracter for caracter in texto
        if not unicodedata.combining(caracter)
    )


def _patron_busqueda(termino):
    termino = _normalizar_texto_busqueda(str(termino or "").strip())
    if not termino:
        return None
    termino = (
        termino.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{termino}%"


def _condicion_busqueda(columnas):
    return "(" + " OR ".join(
        f"NORMALIZAR_BUSQUEDA(COALESCE({columna}, '')) LIKE ? ESCAPE '\\'"
        for columna in columnas
    ) + ")"


def cargar_cheques_registrados(cuenta_id=None, busqueda=None):
    columnas = COLUMNAS_CHEQUES
    vacio = crear_dataframe_vacio(columnas)
    vacio["Num_norm"] = pd.Series(dtype=object)
    patron = _patron_busqueda(busqueda)

    inicializar_db()
    with conectar_db() as conexion:
        if patron is not None:
            conexion.create_function(
                "NORMALIZAR_BUSQUEDA", 1, _normalizar_texto_busqueda,
                deterministic=True,
            )
        consulta = """
            SELECT c.id AS Id, c.cuenta_id AS Cuenta_id, cb.banco AS Banco,
                   cb.nombre AS Cuenta, c.numero AS Num, c.fecha AS Fecha,
                   c.nombre AS Nombre, c.monto AS Monto, c.estado AS Estado,
                   c.descripcion AS Descripcion
            FROM cheques c
            JOIN cuentas_bancarias cb ON cb.id = c.cuenta_id
        """
        condiciones = []
        parametros = []
        if cuenta_id is not None:
            condiciones.append("c.cuenta_id = ?")
            parametros.append(obtener_cuenta(cuenta_id)["id"])
        if patron is not None:
            columnas_busqueda = (
                "c.numero", "c.fecha", "c.nombre", "c.descripcion",
                "c.monto", "c.estado",
            )
            condiciones.append(_condicion_busqueda(columnas_busqueda))
            parametros.extend([patron] * len(columnas_busqueda))
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += " ORDER BY c.id"
        filas = conexion.execute(consulta, parametros).fetchall()
    if not filas:
        return vacio

    df = pd.DataFrame([dict(fila) for fila in filas], columns=columnas)
    df["Num_norm"] = df["Num"].map(normalizar_numero_cheque)
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")

    return df

def _cargar_movimientos_registrados(tabla, alias, cuenta_id=None, busqueda=None):
    vacio = crear_dataframe_vacio(COLUMNAS_MOVIMIENTOS)
    patron = _patron_busqueda(busqueda)

    inicializar_db()
    with conectar_db() as conexion:
        if patron is not None:
            conexion.create_function(
                "NORMALIZAR_BUSQUEDA", 1, _normalizar_texto_busqueda,
                deterministic=True,
            )
        consulta = f"""
            SELECT {alias}.id AS Id, {alias}.cuenta_id AS Cuenta_id,
                   cb.banco AS Banco, cb.nombre AS Cuenta,
                   {alias}.numero AS Num, {alias}.fecha AS Fecha,
                   {alias}.descripcion AS Descripcion, {alias}.monto AS Monto,
                   {alias}.estado AS Estado
            FROM {tabla} {alias}
            JOIN cuentas_bancarias cb ON cb.id = {alias}.cuenta_id
        """
        condiciones = []
        parametros = []
        if cuenta_id is not None:
            condiciones.append(f"{alias}.cuenta_id = ?")
            parametros.append(obtener_cuenta(cuenta_id)["id"])
        if patron is not None:
            columnas_busqueda = (
                f"{alias}.numero", f"{alias}.fecha",
                f"{alias}.descripcion", f"{alias}.monto", f"{alias}.estado",
            )
            condiciones.append(_condicion_busqueda(columnas_busqueda))
            parametros.extend([patron] * len(columnas_busqueda))
        if condiciones:
            consulta += " WHERE " + " AND ".join(condiciones)
        consulta += f" ORDER BY {alias}.id"
        filas = conexion.execute(consulta, parametros).fetchall()
    if not filas:
        return vacio

    df = pd.DataFrame([dict(fila) for fila in filas], columns=COLUMNAS_MOVIMIENTOS)
    df["Monto_valor"] = df["Monto"].map(convertir_monto)
    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce")
    return df


def cargar_depositos_registrados(cuenta_id=None, busqueda=None):
    return _cargar_movimientos_registrados(
        "depositos", "d", cuenta_id, busqueda
    )


def cargar_notas_debito_registradas(cuenta_id=None, busqueda=None):
    return _cargar_movimientos_registrados(
        "notas_debito", "n", cuenta_id, busqueda
    )

def registrar_nota_debito_datos(monto, descripcion, fecha=None, cuenta_id=None, numero=None):
    cuenta = obtener_cuenta(cuenta_id)
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion("⚠️ Error: el número de nota de débito no puede quedar vacío.")
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
            INSERT INTO notas_debito
                (cuenta_id, numero, fecha, descripcion, monto, actualizado_en)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (cuenta["id"], numero, fecha, descripcion, formatear_monto(monto)),
        )
        registrar_auditoria(conexion, "CREAR", "NOTA_DEBITO", cursor.lastrowid,
            f"{cuenta['banco']} / {cuenta['nombre']}: nota de débito {numero} Q {formatear_monto(monto)}: {descripcion}")
    crear_respaldo_posterior()
    return {"fecha": fecha, "numero": numero, "descripcion": descripcion, "cuenta_id": cuenta["id"], "monto": monto,
            "mensaje": f"✅ Nota de débito de Q {formatear_monto(monto)} registrada con éxito."}

def actualizar_nota_debito(nota_id, numero, fecha, descripcion, monto, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        nota_id = int(nota_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Nota de débito inválida.") from e
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion("⚠️ Error: el número de nota de débito no puede quedar vacío.")
    fecha = normalizar_fecha(fecha)
    descripcion = str(descripcion or "").strip()
    if not descripcion:
        raise ErrorOperacion("⚠️ Error: el campo no puede quedar vacío.")
    monto = convertir_monto(monto)
    if monto is None:
        raise ErrorOperacion("⚠️ Error: Solo usar números y punto decimal.")
    if monto <= 0:
        raise ErrorOperacion("⚠️ Error: El monto debe ser mayor que cero.")
    descripcion = descripcion.upper()
    with transaccion() as conexion:
        nota = conexion.execute("SELECT estado FROM notas_debito WHERE id = ? AND cuenta_id = ?", (nota_id, cuenta["id"])).fetchone()
        if nota is None:
            raise ErrorOperacion("⚠️ La nota de débito no existe en esta cuenta.")
        if nota["estado"] == "ANULADO":
            raise ErrorOperacion("⚠️ Una nota de débito anulada no se puede editar.")
        conexion.execute("""UPDATE notas_debito SET numero = ?, fecha = ?, descripcion = ?, monto = ?, actualizado_en = CURRENT_TIMESTAMP WHERE id = ?""",
            (numero, fecha, descripcion, formatear_monto(monto), nota_id))
        registrar_auditoria(conexion, "ACTUALIZAR", "NOTA_DEBITO", nota_id, f"{cuenta['banco']} / {cuenta['nombre']}: nota de débito {numero} actualizada")
    crear_respaldo_posterior()
    return {"id": nota_id, "mensaje": f"✅ Nota de débito {numero} actualizada."}

def eliminar_nota_debito(nota_id, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        nota_id = int(nota_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Nota de débito inválida.") from e
    with transaccion() as conexion:
        nota = conexion.execute("SELECT numero, monto, descripcion FROM notas_debito WHERE id = ? AND cuenta_id = ?", (nota_id, cuenta["id"])).fetchone()
        if nota is None:
            raise ErrorOperacion("⚠️ La nota de débito no existe en esta cuenta.")
        registrar_auditoria(conexion, "ELIMINAR", "NOTA_DEBITO", nota_id, f"{cuenta['banco']} / {cuenta['nombre']}: nota de débito {nota['numero']} eliminada")
        conexion.execute("DELETE FROM notas_debito WHERE id = ? AND cuenta_id = ?", (nota_id, cuenta["id"]))
    crear_respaldo_posterior()
    return {"id": nota_id, "mensaje": f"✅ Nota de débito {nota['numero']} eliminada."}

def anular_nota_debito_numero(numero, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion("⚠️ Error: el número de nota de débito no puede quedar vacío.")
    with transaccion() as conexion:
        notas = conexion.execute("SELECT id, estado FROM notas_debito WHERE cuenta_id = ? AND numero = ? ORDER BY id", (cuenta["id"], numero)).fetchall()
        if not notas:
            raise ErrorOperacion(f"⚠️ La nota de débito {numero} no existe en los registros.")
        if len(notas) > 1:
            raise ErrorOperacion(f"⚠️ Hay más de una nota de débito con el número {numero}; no se puede determinar cuál anular.")
        nota = notas[0]
        if nota["estado"] == "ANULADO":
            raise ErrorOperacion(f"⚠️ La nota de débito {numero} ya está anulada.")
        conexion.execute("UPDATE notas_debito SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP WHERE id = ?", (nota["id"],))
        registrar_auditoria(conexion, "ANULAR", "NOTA_DEBITO", nota["id"], f"{cuenta['banco']} / {cuenta['nombre']}: nota de débito {numero} cambiada a ANULADO.")
    crear_respaldo_posterior()
    return {"numero": numero, "cantidad": 1, "mensaje": f"🚫 La nota de débito {numero} ha sido marcada como ANULADO."}

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

def registrar_deposito_datos(
    monto, descripcion, fecha=None, cuenta_id=None, numero=None
):
    cuenta = obtener_cuenta(cuenta_id)
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion(
            "⚠️ Error: el número de depósito no puede quedar vacío."
        )
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
            INSERT INTO depositos
                (cuenta_id, numero, fecha, descripcion, monto, actualizado_en)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                cuenta["id"], numero, fecha, descripcion,
                formatear_monto(monto),
            ),
        )
        registrar_auditoria(
            conexion,
            "CREAR",
            "DEPOSITO",
            cursor.lastrowid,
            f"{cuenta['banco']} / {cuenta['nombre']}: depósito {numero} "
            f"Q {formatear_monto(monto)}: {descripcion}",
        )
    crear_respaldo_posterior()

    return {
        "fecha": fecha,
        "numero": numero,
        "descripcion": descripcion,
        "cuenta_id": cuenta["id"],
        "monto": monto,
        "mensaje": f"✅ Depósito de Q {formatear_monto(monto)} registrado con éxito.",
    }

def actualizar_deposito(
    deposito_id, numero, fecha, descripcion, monto, cuenta_id=None
):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        deposito_id = int(deposito_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Depósito inválido.") from e
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion(
            "⚠️ Error: el número de depósito no puede quedar vacío."
        )
    fecha = normalizar_fecha(fecha)
    descripcion = str(descripcion or "").strip()
    if not descripcion:
        raise ErrorOperacion("⚠️ Error: el campo no puede quedar vacío.")
    monto = convertir_monto(monto)
    if monto is None:
        raise ErrorOperacion("⚠️ Error: Solo usar números y punto decimal.")
    if monto <= 0:
        raise ErrorOperacion("⚠️ Error: El monto debe ser mayor que cero.")
    descripcion = descripcion.upper()

    with transaccion() as conexion:
        deposito = conexion.execute(
            """
            SELECT estado FROM depositos
            WHERE id = ? AND cuenta_id = ?
            """,
            (deposito_id, cuenta["id"]),
        ).fetchone()
        if deposito is None:
            raise ErrorOperacion("⚠️ El depósito no existe en esta cuenta.")
        if deposito["estado"] == "ANULADO":
            raise ErrorOperacion("⚠️ Un depósito anulado no se puede editar.")
        conexion.execute(
            """
            UPDATE depositos
            SET numero = ?, fecha = ?, descripcion = ?, monto = ?,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                numero, fecha, descripcion, formatear_monto(monto),
                deposito_id,
            ),
        )
        registrar_auditoria(
            conexion,
            "ACTUALIZAR",
            "DEPOSITO",
            deposito_id,
            f"{cuenta['banco']} / {cuenta['nombre']}: depósito {numero} "
            f"actualizado a Q {formatear_monto(monto)}: {descripcion}",
        )
    crear_respaldo_posterior()
    return {"id": deposito_id, "mensaje": f"✅ Depósito {numero} actualizado."}

def eliminar_deposito(deposito_id, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        deposito_id = int(deposito_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Depósito inválido.") from e

    with transaccion() as conexion:
        deposito = conexion.execute(
            """
            SELECT numero, monto, descripcion FROM depositos
            WHERE id = ? AND cuenta_id = ?
            """,
            (deposito_id, cuenta["id"]),
        ).fetchone()
        if deposito is None:
            raise ErrorOperacion("⚠️ El depósito no existe en esta cuenta.")
        registrar_auditoria(
            conexion,
            "ELIMINAR",
            "DEPOSITO",
            deposito_id,
            f"{cuenta['banco']} / {cuenta['nombre']}: depósito "
            f"{deposito['numero']} Q {deposito['monto']} eliminado: "
            f"{deposito['descripcion']}",
        )
        conexion.execute(
            "DELETE FROM depositos WHERE id = ? AND cuenta_id = ?",
            (deposito_id, cuenta["id"]),
        )
    crear_respaldo_posterior()
    return {
        "id": deposito_id,
        "mensaje": f"✅ Depósito {deposito['numero']} eliminado.",
    }

def anular_deposito_numero(numero, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    numero = str(numero or "").strip()
    if not numero:
        raise ErrorOperacion(
            "⚠️ Error: el número de depósito no puede quedar vacío."
        )

    with transaccion() as conexion:
        depositos = conexion.execute(
            """
            SELECT id, estado FROM depositos
            WHERE cuenta_id = ? AND numero = ?
            ORDER BY id
            """,
            (cuenta["id"], numero),
        ).fetchall()
        if not depositos:
            total = conexion.execute(
                "SELECT COUNT(*) FROM depositos WHERE cuenta_id = ?",
                (cuenta["id"],),
            ).fetchone()[0]
            if total == 0:
                raise ErrorOperacion("⚠️ No hay registro de depósitos aún.")
            raise ErrorOperacion(
                f"⚠️ El depósito {numero} no existe en los registros."
            )
        if len(depositos) > 1:
            raise ErrorOperacion(
                f"⚠️ Hay más de un depósito con el número {numero}; "
                "no se puede determinar cuál anular."
            )
        deposito = depositos[0]
        if deposito["estado"] == "ANULADO":
            raise ErrorOperacion(f"⚠️ El depósito {numero} ya está anulado.")

        conexion.execute(
            """
            UPDATE depositos
            SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (deposito["id"],),
        )
        registrar_auditoria(
            conexion,
            "ANULAR",
            "DEPOSITO",
            deposito["id"],
            f"{cuenta['banco']} / {cuenta['nombre']}: depósito {numero} "
            "cambiado a ANULADO.",
        )
    crear_respaldo_posterior()

    return {
        "numero": numero,
        "cantidad": 1,
        "mensaje": f"🚫 El depósito {numero} ha sido marcado como ANULADO.",
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

def actualizar_cheque(
    cheque_id, numero, fecha, nombre, monto, descripcion="", cuenta_id=None
):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        cheque_id = int(cheque_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Cheque inválido.") from e
    numero = normalizar_numero_cheque(numero)
    if not numero:
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
    nombre = nombre.upper()
    descripcion = str(descripcion or "").strip().upper()

    try:
        with transaccion() as conexion:
            cheque = conexion.execute(
                """
                SELECT estado FROM cheques
                WHERE id = ? AND cuenta_id = ?
                """,
                (cheque_id, cuenta["id"]),
            ).fetchone()
            if cheque is None:
                raise ErrorOperacion("⚠️ El cheque no existe en esta cuenta.")
            if cheque["estado"] == "ANULADO":
                raise ErrorOperacion("⚠️ Un cheque anulado no se puede editar.")
            conexion.execute(
                """
                UPDATE cheques
                SET numero = ?, fecha = ?, nombre = ?, monto = ?,
                    descripcion = ?, actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    numero, fecha, nombre, formatear_monto(monto),
                    descripcion, cheque_id,
                ),
            )
            registrar_auditoria(
                conexion,
                "ACTUALIZAR",
                "CHEQUE",
                cheque_id,
                f"{cuenta['banco']} / {cuenta['nombre']}: cheque {numero} "
                f"actualizado a Q {formatear_monto(monto)} para {nombre}",
            )
    except sqlite3.IntegrityError as e:
        raise ErrorOperacion(
            f"⚠️ El cheque {numero} ya existe en el historial."
        ) from e
    crear_respaldo_posterior()
    return {"id": cheque_id, "mensaje": f"✅ Cheque {numero} actualizado."}

def eliminar_cheque(cheque_id, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    try:
        cheque_id = int(cheque_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Cheque inválido.") from e

    with transaccion() as conexion:
        cheque = conexion.execute(
            """
            SELECT numero, monto, nombre FROM cheques
            WHERE id = ? AND cuenta_id = ?
            """,
            (cheque_id, cuenta["id"]),
        ).fetchone()
        if cheque is None:
            raise ErrorOperacion("⚠️ El cheque no existe en esta cuenta.")
        registrar_auditoria(
            conexion,
            "ELIMINAR",
            "CHEQUE",
            cheque_id,
            f"{cuenta['banco']} / {cuenta['nombre']}: cheque "
            f"{cheque['numero']} Q {cheque['monto']} para "
            f"{cheque['nombre']} eliminado.",
        )
        conexion.execute(
            "DELETE FROM cheques WHERE id = ? AND cuenta_id = ?",
            (cheque_id, cuenta["id"]),
        )
    crear_respaldo_posterior()
    return {
        "id": cheque_id,
        "mensaje": f"✅ Cheque {cheque['numero']} eliminado.",
    }

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
            moneda=cuenta["moneda"],
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
        moneda=cuenta["moneda"],
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
