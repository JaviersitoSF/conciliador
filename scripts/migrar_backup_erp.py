#!/usr/bin/env python3
"""Migra chequeras y cheques de un dump MariaDB del ERP a Conciliador."""

import argparse
import re
import sqlite3
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


TABLAS = {"erp_chequera", "erp_cheque_cab"}
INSERT_RE = re.compile(r"^INSERT INTO `([^`]+)` VALUES ")


def leer_inserts(ruta):
    with ruta.open("r", encoding="utf-8", errors="replace") as archivo:
        sentencia = ""
        tabla = None
        for linea in archivo:
            if not sentencia:
                coincidencia = INSERT_RE.match(linea)
                if not coincidencia or coincidencia.group(1) not in TABLAS:
                    continue
                tabla = coincidencia.group(1)
            sentencia += linea
            if sentencia.rstrip().endswith(";"):
                prefijo = f"INSERT INTO `{tabla}` VALUES "
                yield tabla, sentencia[len(prefijo):].rstrip()[:-1]
                sentencia = ""
                tabla = None


def convertir_campo(texto, entre_comillas):
    if entre_comillas:
        return texto
    texto = texto.strip()
    if texto.upper() == "NULL":
        return None
    return texto


def parsear_filas(valores):
    filas = []
    fila = []
    campo = []
    entre_comillas = False
    escape = False
    profundidad = 0

    for caracter in valores:
        if entre_comillas:
            if escape:
                equivalencias = {"n": "\n", "r": "\r", "t": "\t", "0": "\0"}
                campo.append(equivalencias.get(caracter, caracter))
                escape = False
            elif caracter == "\\":
                escape = True
            elif caracter == "'":
                entre_comillas = False
            else:
                campo.append(caracter)
            continue

        if caracter == "'":
            entre_comillas = True
        elif caracter == "(":
            profundidad += 1
            if profundidad > 1:
                campo.append(caracter)
        elif caracter == ")" and profundidad:
            if profundidad == 1:
                fila.append(convertir_campo("".join(campo), False))
                filas.append(fila)
                fila = []
                campo = []
            else:
                campo.append(caracter)
            profundidad -= 1
        elif caracter == "," and profundidad == 1:
            fila.append(convertir_campo("".join(campo), False))
            campo = []
        elif profundidad:
            campo.append(caracter)

    if entre_comillas or profundidad:
        raise ValueError("Sentencia INSERT incompleta")
    return filas


def banco_desde_descripcion(descripcion):
    texto = descripcion.upper()
    if "INDUSTRIAL" in texto:
        return "BANCO INDUSTRIAL"
    if "AMERICA CENTRAL" in texto or " BAC" in f" {texto}":
        return "BAC"
    if "G&T" in texto or "GYT" in texto or "G & T" in texto:
        return "BANCO G&T CONTINENTAL"
    if "INTERNACIONAL" in texto:
        return "BANCO INTERNACIONAL"
    if "RURAL" in texto:
        return "BANRURAL"
    return descripcion.upper()


def monto_dos_decimales(valor):
    try:
        monto = Decimal(str(valor)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"Monto inválido: {valor!r}") from error
    return f"{monto:.2f}"


def crear_esquema(conexion):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import main

    main.ARCHIVO_DATOS = str(Path(conexion.execute("PRAGMA database_list").fetchone()[2]))
    conexion.close()
    main.inicializar_db()
    return sqlite3.connect(main.ARCHIVO_DATOS)


def migrar(origen, destino):
    if destino.exists():
        raise FileExistsError(f"El destino ya existe: {destino}")

    chequeras = {}
    cheques = []
    for tabla, valores in leer_inserts(origen):
        filas = parsear_filas(valores)
        if tabla == "erp_chequera":
            for fila in filas:
                chequeras[int(fila[0])] = fila
        else:
            cheques.extend(filas)

    destino.parent.mkdir(parents=True, exist_ok=True)
    conexion_inicial = sqlite3.connect(destino)
    conexion = crear_esquema(conexion_inicial)
    duplicados = 0
    invalidos = 0

    try:
        conexion.execute("DELETE FROM formatos_impresion")
        conexion.execute("DELETE FROM cuentas_bancarias")
        for chequera_id, fila in sorted(chequeras.items()):
            descripcion = fila[5].strip()
            conexion.execute(
                """
                INSERT INTO cuentas_bancarias
                    (id, banco, nombre, numero, activa)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    chequera_id,
                    banco_desde_descripcion(descripcion),
                    descripcion,
                    fila[2] or "",
                    1 if int(fila[7]) else 0,
                ),
            )

        formato_default = {
            "ancho": 22.0, "alto": 14.0, "fecha_x": 1.8, "fecha_y": 13.0,
            "nombre_x": 1.9, "nombre_y": 12.1, "monto_x": 15.0,
            "monto_y": 13.0, "no_negociable_x": 2.5,
            "no_negociable_y": 10.0, "monto_letras_x": 1.0,
            "monto_letras_y": 11.2, "descripcion_x": 2.5,
            "descripcion_y": 5.9,
        }
        campos = ", ".join(formato_default)
        marcas = ", ".join("?" for _ in formato_default)
        for chequera_id in chequeras:
            conexion.execute(
                f"INSERT INTO formatos_impresion (cuenta_id, {campos}) "
                f"VALUES (?, {marcas})",
                (chequera_id, *formato_default.values()),
            )

        for fila in cheques:
            chequera_id = int(fila[1])
            numero = int(fila[3])
            if chequera_id not in chequeras or numero <= 0:
                invalidos += 1
                continue
            razon_anula = (fila[24] or "").strip()
            estado = "ANULADO" if int(fila[8]) == 0 or razon_anula else "TRANSITO"
            descripcion = (fila[5] or fila[9] or "").strip()
            if razon_anula:
                descripcion = f"{descripcion} [ANULADO: {razon_anula}]".strip()
            try:
                conexion.execute(
                    """
                    INSERT INTO cheques
                        (cuenta_id, numero, fecha, nombre, monto, estado,
                         descripcion, creado_en, actualizado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chequera_id,
                        str(numero),
                        str(fila[6])[:10],
                        (fila[12] or "").strip() or "SIN BENEFICIARIO",
                        monto_dos_decimales(fila[7]),
                        estado,
                        descripcion,
                        fila[22] or str(fila[6]),
                        fila[22] or str(fila[6]),
                    ),
                )
            except sqlite3.IntegrityError:
                duplicados += 1

        conexion.execute(
            """
            INSERT INTO auditoria (accion, entidad, entidad_id, detalle)
            VALUES ('MIGRAR', 'backup_erp', NULL, ?)
            """,
            (
                f"Origen: {origen.name}; cuentas: {len(chequeras)}; "
                f"cheques: {len(cheques) - duplicados - invalidos}; "
                f"duplicados omitidos: {duplicados}; inválidos omitidos: {invalidos}",
            ),
        )
        conexion.commit()
    finally:
        conexion.close()

    return len(chequeras), len(cheques) - duplicados - invalidos, duplicados, invalidos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("origen", type=Path)
    parser.add_argument("destino", type=Path)
    args = parser.parse_args()
    resultado = migrar(args.origen, args.destino)
    print(
        f"Cuentas: {resultado[0]}; cheques: {resultado[1]}; "
        f"duplicados: {resultado[2]}; inválidos: {resultado[3]}"
    )


if __name__ == "__main__":
    main()
