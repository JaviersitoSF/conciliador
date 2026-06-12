# Distribución y operación de Conciliador

## Opción recomendada: ejecutable de Windows

El proyecto incluye una acción de GitHub que crea `Conciliador-UI.exe`, la
única interfaz soportada.

`main.py` es solamente el punto de entrada gráfico. La interfaz vive en
`ui_tk.py` y los casos de uso se consumen mediante `conciliador.service`.
El paquete separa persistencia (`storage`), movimientos (`movements`),
conciliación y reportes (`analytics`) e impresión (`printing`).

1. Sube el repositorio a GitHub.
2. Abre la pestaña **Actions**.
3. Selecciona **Construir ejecutable de Windows**.
4. Pulsa **Run workflow**.
5. Al terminar, descarga el artefacto **Conciliador-Windows**.

El ejecutable se puede copiar a una carpeta estable y escribible sin instalar
Python. Sus datos se resuelven desde la ubicación real del ejecutable, aunque
se abra mediante un acceso directo o desde otra carpeta:

- `data/conciliador.db`: base de datos.
- `data/migration_backups/`: últimos cinco respaldos previos a migraciones.
- `logs/conciliador.log`: diagnóstico con rotación automática.
- `exports/`: archivos generados por la aplicación.

La carpeta portable completa debe incluirse en los respaldos corporativos.

## Construcción manual en Windows

Con Python 3.12 instalado:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
python -m pytest
python -m PyInstaller --clean --noconfirm Conciliador-UI.spec
```

El resultado queda en `dist\Conciliador-UI.exe`.

## Actualización

1. Cierra Conciliador.
2. Confirma que el respaldo corporativo de la carpeta portable terminó.
3. Sustituye únicamente `Conciliador-UI.exe` por la versión nueva.
4. Abre la aplicación. Las migraciones se ejecutan antes de mostrar la UI.
5. Si el arranque falla, conserva el ejecutable y revisa el log antes de
   intentar otra actualización.

No se implementan downgrades. Para volver a una versión anterior, cierra la
aplicación, restaura el respaldo de `data/conciliador.db` creado antes de la
actualización y usa el ejecutable anterior.

## Restauración

1. Cierra Conciliador.
2. Renombra la base dañada para conservarla para diagnóstico.
3. Copia el respaldo elegido como `data/conciliador.db`.
4. Abre Conciliador y confirma cuentas, movimientos y reporte mensual.

Los archivos de `data/migration_backups/` sirven para revertir una migración.
Los respaldos cotidianos dependen del sistema corporativo.

## Diagnóstico

Ante un error inesperado, anota la operación realizada y entrega
`logs/conciliador.log` al mantenedor. Si la UI no abre, no reemplaces ni borres
la base: el fallo de migración hace rollback y conserva su respaldo previo.

## Otras opciones

- **Carpeta portable (`--onedir`)**: inicia más rápido y algunos antivirus
  generan menos alertas, pero se distribuye una carpeta completa.
- **Instalador de Windows**: envolver los ejecutables con Inno Setup permite
  crear accesos directos, desinstalador y una ubicación estable para la app.
- **Código Python y entorno virtual**: solo para desarrollo, con Python 3.12.
- **Aplicación web**: facilita el acceso desde varios equipos, pero requiere
  autenticación, servidor, copias de seguridad y una revisión de seguridad por
  tratarse de información financiera.
