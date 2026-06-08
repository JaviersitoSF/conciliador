# Distribución de Conciliador

## Opción recomendada: ejecutable de Windows

El proyecto incluye una acción de GitHub que crea dos ejecutables en Windows:

- `Conciliador-Terminal.exe`: menú operado desde una consola.
- `Conciliador-UI.exe`: aplicación de escritorio con interfaz gráfica.

1. Sube el repositorio a GitHub.
2. Abre la pestaña **Actions**.
3. Selecciona **Construir ejecutable de Windows**.
4. Pulsa **Run workflow**.
5. Al terminar, descarga el artefacto **Conciliador-Windows**.

Los ejecutables se pueden copiar a una carpeta normal y abrir sin instalar Python.
La base de datos `conciliador.db`, los PDF y la carpeta `respaldos` se crean en
el directorio de trabajo desde el que se inicia la aplicación. Conviene usar
una carpeta con permisos de escritura y respaldarla periódicamente.

## Construcción manual en Windows

Con Python 3.12 instalado:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
python -m pytest
python -m PyInstaller --clean --noconfirm Conciliador-Terminal.spec
python -m PyInstaller --clean --noconfirm Conciliador-UI.spec
```

Los resultados quedan en:

- `dist\Conciliador-Terminal.exe`
- `dist\Conciliador-UI.exe`

## Otras opciones

- **Carpeta portable (`--onedir`)**: inicia más rápido y algunos antivirus
  generan menos alertas, pero se distribuye una carpeta completa.
- **Instalador de Windows**: envolver los ejecutables con Inno Setup permite
  crear accesos directos, desinstalador y una ubicación estable para la app.
- **Código Python y entorno virtual**: útil solo para usuarios técnicos; exige
  instalar Python y las dependencias.
- **Aplicación web**: facilita el acceso desde varios equipos, pero requiere
  autenticación, servidor, copias de seguridad y una revisión de seguridad por
  tratarse de información financiera.
