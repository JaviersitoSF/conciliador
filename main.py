import os
import platform
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from num2words import num2words
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

ARCHIVO_DATOS = "conciliador.db"
ARCHIVO_BANCO = "estado_cuenta.xlsx"
DIRECTORIO_RESPALDOS = "respaldos"
COLUMNAS_CHEQUES = [
    "Cuenta_id", "Banco", "Cuenta", "Num", "Fecha", "Nombre", "Monto",
    "Estado", "Descripcion",
]
PATRON_MONTO = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")
MAX_RESPALDOS = 10


class ErrorOperacion(ValueError):
    """Error esperado en operaciones del sistema."""


def conectar_db():
    conexion = sqlite3.connect(ARCHIVO_DATOS, timeout=10)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA busy_timeout = 10000")
    return conexion


def inicializar_db():
    with conectar_db() as conexion:
        tabla_cheques = conexion.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'cheques'
            """
        ).fetchone()
        if tabla_cheques:
            columnas = {
                fila["name"]
                for fila in conexion.execute("PRAGMA table_info(cheques)").fetchall()
            }
            if "cuenta_id" not in columnas:
                conexion.executescript(
                    """
                    DROP TABLE IF EXISTS cheques;
                    DROP TABLE IF EXISTS depositos;
                    DROP TABLE IF EXISTS auditoria;
                    DROP TABLE IF EXISTS cuentas_bancarias;
                    """
                )

        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS cheques (
                id INTEGER PRIMARY KEY,
                cuenta_id INTEGER NOT NULL,
                numero TEXT NOT NULL,
                fecha TEXT NOT NULL,
                nombre TEXT NOT NULL,
                monto TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'TRANSITO'
                    CHECK (estado IN ('TRANSITO', 'ANULADO')),
                descripcion TEXT NOT NULL DEFAULT '',
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cuenta_id, numero),
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );

            CREATE TABLE IF NOT EXISTS depositos (
                id INTEGER PRIMARY KEY,
                cuenta_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto TEXT NOT NULL,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cuenta_id) REFERENCES cuentas_bancarias(id)
            );

            CREATE TABLE IF NOT EXISTS cuentas_bancarias (
                id INTEGER PRIMARY KEY,
                banco TEXT NOT NULL,
                nombre TEXT NOT NULL,
                numero TEXT NOT NULL DEFAULT '',
                activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1)),
                creada_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (banco, nombre, numero)
            );

            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY,
                fecha_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                accion TEXT NOT NULL,
                entidad TEXT NOT NULL,
                entidad_id TEXT,
                detalle TEXT NOT NULL
            );
            """
        )
        conexion.execute(
            """
            INSERT OR IGNORE INTO cuentas_bancarias (id, banco, nombre, numero)
            VALUES (1, 'SIN CONFIGURAR', 'Cuenta principal', '')
            """
        )


def listar_cuentas_bancarias(solo_activas=True):
    inicializar_db()
    consulta = """
        SELECT id, banco, nombre, numero, activa
        FROM cuentas_bancarias
    """
    if solo_activas:
        consulta += " WHERE activa = 1"
    consulta += " ORDER BY banco, nombre"
    with conectar_db() as conexion:
        return [dict(fila) for fila in conexion.execute(consulta).fetchall()]


def crear_cuenta_bancaria(banco, nombre, numero=""):
    banco = str(banco or "").strip().upper()
    nombre = str(nombre or "").strip()
    numero = str(numero or "").strip()
    if not banco or not nombre:
        raise ErrorOperacion("⚠️ Banco y nombre de cuenta son obligatorios.")

    try:
        with transaccion() as conexion:
            cursor = conexion.execute(
                """
                INSERT INTO cuentas_bancarias (banco, nombre, numero)
                VALUES (?, ?, ?)
                """,
                (banco, nombre, numero),
            )
            cuenta_id = cursor.lastrowid
            registrar_auditoria(
                conexion,
                "CREAR",
                "CUENTA_BANCARIA",
                cuenta_id,
                f"{banco} - {nombre} - {numero or 'sin número'}",
            )
    except sqlite3.IntegrityError as e:
        raise ErrorOperacion("⚠️ Esa cuenta bancaria ya está registrada.") from e
    crear_respaldo()
    return cuenta_id


def obtener_cuenta(cuenta_id=None):
    cuenta_id = 1 if cuenta_id is None else cuenta_id
    try:
        cuenta_id = int(cuenta_id)
    except (TypeError, ValueError) as e:
        raise ErrorOperacion("⚠️ Cuenta bancaria inválida.") from e

    inicializar_db()
    with conectar_db() as conexion:
        cuenta = conexion.execute(
            """
            SELECT id, banco, nombre, numero, activa
            FROM cuentas_bancarias
            WHERE id = ? AND activa = 1
            """,
            (cuenta_id,),
        ).fetchone()
    if cuenta is None:
        raise ErrorOperacion("⚠️ La cuenta bancaria no existe o está inactiva.")
    return dict(cuenta)


@contextmanager
def transaccion():
    inicializar_db()
    conexion = conectar_db()
    try:
        conexion.execute("BEGIN IMMEDIATE")
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def registrar_auditoria(conexion, accion, entidad, entidad_id, detalle):
    conexion.execute(
        """
        INSERT INTO auditoria (accion, entidad, entidad_id, detalle)
        VALUES (?, ?, ?, ?)
        """,
        (accion, entidad, str(entidad_id) if entidad_id is not None else None, detalle),
    )


def crear_respaldo():
    if not os.path.exists(ARCHIVO_DATOS):
        return None

    directorio = Path(DIRECTORIO_RESPALDOS)
    directorio.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = directorio / f"conciliador_{marca}.db"

    origen = conectar_db()
    copia = sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()

    respaldos = sorted(directorio.glob("conciliador_*.db"), reverse=True)
    for respaldo_antiguo in respaldos[MAX_RESPALDOS:]:
        respaldo_antiguo.unlink()
    return str(destino)


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
        texto = texto[1:-1].strip()
        if texto.startswith(("+", "-", "−")):
            return None

    texto = (
        texto.replace("Q", "")
        .replace("q", "")
        .replace("$", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("−", "-")
    )

    if not PATRON_MONTO.fullmatch(texto):
        return None

    try:
        monto = Decimal(texto.replace(",", ""))
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


def formatear_monto_impresion(valor):
    monto = convertir_monto(valor)
    if monto is None:
        raise ValueError("Monto invalido")
    return f"{monto:,.2f}"


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


def etiqueta_cuenta(cuenta):
    numero = cuenta["numero"]
    referencia = f" terminada en {numero[-4:]}" if numero else ""
    return f"{cuenta['banco']} - {cuenta['nombre']}{referencia}"


def pedir_cuenta_bancaria():
    cuentas = listar_cuentas_bancarias()
    if not cuentas:
        raise ErrorOperacion("⚠️ No hay cuentas bancarias registradas.")

    print("\n--- SELECCIONAR CUENTA BANCARIA ---")
    for posicion, cuenta in enumerate(cuentas, start=1):
        print(f"{posicion}. {etiqueta_cuenta(cuenta)}")

    while True:
        opcion = input("Elige la cuenta bancaria: ").strip()
        if opcion.isdigit() and 1 <= int(opcion) <= len(cuentas):
            cuenta = cuentas[int(opcion) - 1]
            print(f"Cuenta seleccionada: {etiqueta_cuenta(cuenta)}")
            return cuenta
        print("⚠️ Selecciona una cuenta de la lista.")


def registrar_cuenta_bancaria():
    print("\n--- REGISTRAR CUENTA BANCARIA ---")
    banco = pedir_texto_no_vacio("Banco: ")
    nombre = pedir_texto_no_vacio("Nombre interno de la cuenta: ")
    numero = input("Número de cuenta (opcional): ").strip()
    try:
        cuenta_id = crear_cuenta_bancaria(banco, nombre, numero)
    except ErrorOperacion as e:
        print(e)
        return
    print(f"✅ Cuenta bancaria registrada con identificador {cuenta_id}.")


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

    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
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
    crear_respaldo()

    return {
        "fecha": fecha,
        "descripcion": descripcion,
        "cuenta_id": cuenta["id"],
        "monto": monto,
        "mensaje": f"✅ Depósito de Q {formatear_monto(monto)} registrado con éxito.",
    }


def registrar_deposito():
    print("\n--- REGISTRO DE DEPÓSITO ---")
    try:
        cuenta = pedir_cuenta_bancaria()
    except ErrorOperacion as e:
        print(e)
        return
    monto = pedir_monto_positivo("Monto del depósito (ej. 5000.00): ")
    descripcion = pedir_texto_no_vacio("Descripción (ej. Venta mostrador, Eukanuba): ").upper()
    resultado = registrar_deposito_datos(
        monto, descripcion, cuenta_id=cuenta["id"]
    )
    print(resultado["mensaje"])


def formatear_fecha_cheque(fecha):
    texto = str(fecha).strip()
    try:
        fecha_dt = datetime.strptime(texto, "%Y-%m-%d")
    except ValueError:
        return texto
    meses = (
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    )
    return f"{fecha_dt.day} de {meses[fecha_dt.month - 1]} del {fecha_dt.year}"


def imprimir_cheque_pdf(num, fecha, nombre, monto, descripcion=""):
    alto_cheque = 14 * cm
    ancho_cheque = 22 * cm
    nombre_pdf = f"cheque_{num}.pdf"

    pdf = canvas.Canvas(nombre_pdf, pagesize=(ancho_cheque, alto_cheque))

    monto_formateado = formatear_monto_impresion(monto)
    entero, centavos = formatear_monto(monto).split(".")
    monto_en_letras = num2words(int(entero), lang="es").upper()
    texto_oficial = f"{monto_en_letras} QUETZALES CON {centavos}/100"

    pdf.drawString(5 * cm, 11.5 * cm, f"Guatemala {formatear_fecha_cheque(fecha)}")
    pdf.drawString(4.3 * cm, 10.8 * cm, nombre)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(16.5 * cm, 11.5 * cm, monto_formateado)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(4.5 * cm, 8.5 * cm, "NO NEGOCIABLE")

    ancho_disponible = ancho_cheque - 4.3 * cm - 1 * cm
    tamano_texto = min(
        10,
        ancho_disponible * 10 / stringWidth(texto_oficial, "Helvetica", 10),
    )
    pdf.setFont("Helvetica", max(7, tamano_texto))
    pdf.drawString(4.3 * cm, 10 * cm, texto_oficial)
    pdf.setFont("Helvetica", 10)
    if descripcion:
        pdf.drawString(4.5 * cm, alto_cheque - 9.6 * cm, descripcion)

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
            abrir_pdf_silenciosamente([
                "lp",
                "-o", "media=Custom.220x140mm",
                "-o", "scaling=100",
                "-o", "position=top-left",
                nombre_pdf,
            ])
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


def guardar_en_archivo(num, fecha, nombre, monto, descripcion="", cuenta_id=None):
    guardar_cheque_en_archivo(num, fecha, nombre, monto, descripcion, cuenta_id)
    print("💾 Datos guardados en el historial.")


def guardar_cheque_en_archivo(num, fecha, nombre, monto, descripcion="", cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
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
    crear_respaldo()


def emitir_cheque_datos(
    num_cheque, nombre, monto, fecha=None, descripcion="", cuenta_id=None
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

    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
    nombre = nombre.upper()
    descripcion = str(descripcion or "").strip().upper()

    guardar_cheque_en_archivo(
        num_cheque, fecha, nombre, monto, descripcion, cuenta["id"]
    )
    imprimir_cheque_pdf(num_cheque, fecha, nombre, monto, descripcion)

    return {
        "num": num_cheque,
        "fecha": fecha,
        "nombre": nombre,
        "descripcion": descripcion,
        "cuenta_id": cuenta["id"],
        "monto": monto,
        "pdf": f"cheque_{num_cheque}.pdf",
        "mensaje": "✅ Cheque registrado y listo para imprimir con éxito.",
    }


def registrar_e_imprimir():
    print("\n--- EMISIÓN DE CHEQUE ---")

    try:
        cuenta = pedir_cuenta_bancaria()
    except ErrorOperacion as e:
        print(e)
        return
    monto = pedir_monto_positivo("Monto del cheque (ej. 1500.50): ")
    nombre = pedir_texto_no_vacio("Páguese a la orden de: ").upper()
    descripcion = pedir_texto_no_vacio("Descripción del cheque: ").upper()

    while True:
        num_cheque = pedir_numero_cheque("Número de cheque: ")
        if not cheque_ya_registrado(num_cheque, cuenta["id"]):
            break

        print(f"⚠️ El cheque {num_cheque} ya existe en el historial.")
        input("\nPresiona ENTER para ingresar otro número de cheque...")

    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    try:
        guardar_en_archivo(
            num_cheque,
            fecha_actual,
            nombre,
            monto,
            descripcion,
            cuenta["id"],
        )
        imprimir_cheque_pdf(num_cheque, fecha_actual, nombre, monto, descripcion)
    except Exception as e:
        print(f"⚠️ No se pudo completar la emisión del cheque: {e}")
        return

    print("✅ Cheque registrado y listo para imprimir con éxito.")


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
    monto = convertir_monto(cheque["Monto"])
    if monto is None:
        raise ErrorOperacion(f"⚠️ El cheque {num_cheque} tiene un monto inválido.")

    imprimir_cheque_pdf(
        num_cheque,
        cheque["Fecha"],
        cheque["Nombre"],
        monto,
        cheque["Descripcion"],
    )
    with transaccion() as conexion:
        registrar_auditoria(
            conexion,
            "REIMPRIMIR",
            "CHEQUE",
            num_cheque,
            "Se generó una nueva copia del cheque.",
        )
    return f"✅ Cheque {num_cheque} listo para volver a imprimir."


def reimprimir_cheque():
    print("\n--- REIMPRESIÓN DE CHEQUE ---")
    try:
        cuenta = pedir_cuenta_bancaria()
    except ErrorOperacion as e:
        print(e)
        return
    num_cheque = pedir_numero_cheque("Número de cheque a reimprimir: ")

    try:
        mensaje = reimprimir_cheque_numero(num_cheque, cuenta["id"])
    except ErrorOperacion as e:
        print(e)
        return

    print(mensaje)


def anular_cheque_numero(num_anular, cuenta_id=None):
    cuenta = obtener_cuenta(cuenta_id)
    num_anular = normalizar_numero_cheque(num_anular)
    if not num_anular:
        raise ErrorOperacion("⚠️ Error: el número de cheque debe ser mayor que cero.")

    with transaccion() as conexion:
        cursor = conexion.execute(
            """
            UPDATE cheques
            SET estado = 'ANULADO', actualizado_en = CURRENT_TIMESTAMP
            WHERE cuenta_id = ? AND numero = ?
            """,
            (cuenta["id"], num_anular),
        )
        if cursor.rowcount == 0:
            total = conexion.execute("SELECT COUNT(*) FROM cheques").fetchone()[0]
            if total == 0:
                raise ErrorOperacion("⚠️ No hay registro de cheques aún.")
            raise ErrorOperacion(f"⚠️ El cheque {num_anular} no existe en los registros.")
        registrar_auditoria(
            conexion,
            "ANULAR",
            "CHEQUE",
            num_anular,
            "Estado cambiado a ANULADO.",
        )
    crear_respaldo()

    mensaje = f"🚫 ¡Hecho! El cheque {num_anular} ha sido marcado como ANULADO."
    return {"num": num_anular, "cantidad": 1, "mensaje": mensaje}


def anular_cheque():
    print("\n--- ANULAR CHEQUE ---")

    try:
        cuenta = pedir_cuenta_bancaria()
    except ErrorOperacion as e:
        print(e)
        return
    num_anular = pedir_numero_cheque("Ingresa el número de cheque que deseas anular: ")
    try:
        resultado = anular_cheque_numero(num_anular, cuenta["id"])
    except ErrorOperacion as e:
        print(e)
        return
    print(resultado["mensaje"])


def obtener_conciliacion(cuenta_id=None, archivo_banco=None):
    cuenta = obtener_cuenta(cuenta_id)
    archivo_banco = archivo_banco or ARCHIVO_BANCO
    if not os.path.exists(archivo_banco):
        raise ErrorOperacion("⚠️ Faltan archivos. Asegúrate de tener registros y estado de cuenta.")

    try:
        df_nuestro = cargar_cheques_registrados(cuenta["id"])
        if df_nuestro.empty:
            raise ErrorOperacion("⚠️ No hay registro de cheques aún.")
        df_banco = pd.read_excel(archivo_banco)

        columnas_banco = {str(col).strip().lower(): col for col in df_banco.columns}
        col_num = columnas_banco.get("num_cheque")
        col_monto = columnas_banco.get("monto")

        if not col_num or not col_monto:
            raise ErrorOperacion("⚠️ El archivo del banco debe incluir las columnas 'Num_cheque' y 'Monto'.")

        df_banco = df_banco.copy()
        df_banco["Num_norm"] = df_banco[col_num].map(normalizar_numero_cheque)
        df_banco["Monto_valor"] = df_banco[col_monto].map(convertir_monto)
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
                montos_validos = cobrado["Monto_valor"].dropna().tolist()
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

        return {
            "cuenta": cuenta,
            "cheques": cheques,
            "no_registrados": no_registrados,
        }

    except ErrorOperacion:
        raise
    except Exception as e:
        raise ErrorOperacion(f"⚠️ Ocurrió un error leyendo los archivos: {e}") from e


def conciliar_cuentas():
    print("\n--- CONCILIACIÓN BANCARIA ---")

    try:
        cuenta = pedir_cuenta_bancaria()
        resultado = obtener_conciliacion(cuenta["id"])
    except ErrorOperacion as e:
        print(e)
        return

    print("\n--- Resultados de Cheques Emitidos ---")
    for fila in resultado["cheques"]:
        print(fila["mensaje"])

    print("\n--- Cargos del Banco No Registrados por Nosotros ---")
    for fila in resultado["no_registrados"]:
        print(fila["mensaje"])


def clear_ide_terminal():
    """Pushes old text out of view using standard line breaks."""
    print("\n" * 45)


def obtener_reporte_movimientos(fecha=None, cuenta_id=None):
    fecha = fecha or datetime.now().date()
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
            (fila["Monto_valor"] for _, fila in df_depositos_mes.iterrows()),
            Decimal("0.00"),
        )
    else:
        df_depositos_mes = pd.DataFrame(columns=["Fecha", "Descripcion", "Monto"])

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


def reporte_movimientos():
    print("\n" + "=" * 40)
    print(" 📊 CORTE DE CAJA MENSUAL 📊")
    print("=" * 40)

    try:
        cuenta = pedir_cuenta_bancaria()
    except ErrorOperacion as e:
        print(e)
        return
    reporte = obtener_reporte_movimientos(cuenta_id=cuenta["id"])
    df_cheques_mes = reporte["cheques"]

    if not df_cheques_mes.empty:
        print("\n--- CHEQUES EMITIDOS DEL MES ---")
        print(df_cheques_mes[["Num", "Fecha", "Nombre", "Monto", "Estado"]].to_string(index=False))
    else:
        print("\n--- CHEQUES EMITIDOS DEL MES ---")
        print("No hay cheques registrados en el mes actual.")

    df_depositos_mes = reporte["depositos"]

    if not df_depositos_mes.empty:
        print("\n--- DEPÓSITOS RECIBIDOS DEL MES ---")
        print(df_depositos_mes[["Fecha", "Descripcion", "Monto"]].to_string(index=False))
    else:
        print("\n--- DEPÓSITOS RECIBIDOS DEL MES ---")
        print("No hay depósitos registrados en el mes actual.")

    print("\n" + "-" * 40)
    print(f"📈 TOTAL INGRESOS (Depósitos): Q {formatear_monto(reporte['total_depositos'])}")
    print(f"📉 TOTAL EGRESOS (Cheques):  Q {formatear_monto(reporte['total_cheques'])}")
    print("-" * 40)
    print(f"💵 SALDO EN BÓVEDA:          Q {formatear_monto(reporte['saldo'])}")
    print("-" * 40)

    input("\nPresiona ENTER para volver al menú...")


def mostrar_menu():
    print("\n"*45)
    print("\n" + "=" * 40)
    print(" 💼 SISTEMA DE CONTROL BANCARIO 💼")
    print("=" * 40)
    print("1. Emitir nuevo cheque")
    print("2. Registrar un depósito")
    print("3. Conciliar banco")
    print("4. Anular un cheque con error")
    print("5. Ver corte de caja (Reporte)")
    print("6. Volver a imprimir un cheque")
    print("7. Registrar cuenta bancaria")
    print("8. Salir")
    print("=" * 40)


def main():
    while True:
        mostrar_menu()
        opcion = input("Elige una opción (1-8): ").strip()

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
            reimprimir_cheque()
        elif opcion == "7":
            registrar_cuenta_bancaria()
        elif opcion == "8":
            print("\nCerrando la bóveda... ¡Buenas noches y éxito en los negocios, Javier!")
            sys.exit()
        else:
            print("⚠️ Opción inválida. Intenta un número del 1 al 8.")


if __name__ == "__main__":  # pragma: no cover
    main()
