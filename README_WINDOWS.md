# Instalación y Uso en Windows

Este documento describe los pasos para instalar y ejecutar la aplicación `conciliador` en una máquina Windows.

## Requisitos Previos

- **Python 3.8 o superior** instalado y agregado a PATH
  - Descargar desde: https://www.python.org/downloads/
  - ✅ Marcar "Add Python to PATH" durante la instalación
- **Git** (opcional, para clonar el repositorio)
  - Descargar desde: https://git-scm.com/download/win

## Pasos de Instalación

### 1. Descargar y Extraer el Proyecto

**Opción A: Desde el ZIP (sin Git)**
- Extrae `conciliador_windows.zip` en la carpeta donde quieras (p. ej. `C:\Users\TuUsuario\Documentos\conciliador`)
- Abre **PowerShell** o **CMD** y navega a la carpeta:
  ```powershell
  cd C:\ruta\del\proyecto\conciliador
  ```

**Opción B: Usar Git (si lo tienes instalado)**
```powershell
git clone https://github.com/JaviersitoSF/conciliador.git
cd conciliador
git checkout ui
```

### 2. Crear Entorno Virtual

En PowerShell o CMD (desde la carpeta del proyecto):

**PowerShell:**
```powershell
python -m venv .\venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\venv\Scripts\Activate.ps1
```

**CMD:**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

Deberías ver `(venv)` al inicio de la línea de comandos.

### 3. Instalar Dependencias

Con el entorno virtual activado:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si esto tarda mucho o falla con errores de compilación, instala las **Build Tools de Visual Studio**:
- Descargar: https://visualstudio.microsoft.com/visual-cpp-build-tools/
- Selecciona "Herramientas de compilación de C++" durante la instalación.

### 4. Ejecutar la Aplicación

Con el entorno virtual activado:
```powershell
python main.py
```

Aparecerá un menú interactivo con opciones como:
- Emitir cheques
- Registrar depósitos
- Anular cheques
- Conciliar cuentas
- Generar reportes

### 5. Generar/Usar Reportes PDF

La aplicación genera archivos PDF automáticamente:
- **Cheques:** `cheque_<numero>.pdf`
- **Conciliación:** `conciliacion_<fecha_hora>.pdf`

Los PDFs se guardan en la carpeta del proyecto y se abren automáticamente si tienes un lector PDF configurado (p. ej. Adobe Reader, Microsoft Edge).

## Ejecutar Tests (Opcional)

Para verificar que todo funcione correctamente:
```powershell
pip install pytest
python -m pytest -q
```

Deberías ver "24 passed" si todo está bien.

## Datos y Archivos CSV

La aplicación genera/usa estos archivos CSV en la carpeta del proyecto:
- `cheques_emitidos.csv` — registro de cheques emitidos
- `depositos.csv` — registro de depósitos
- `estado_cuenta.xlsx` o `estado_cuenta.csv` — estado de cuenta bancario (proporciona tú)

**Nota:** No borres estos archivos a menos que quieras limpiar los datos.

## Solución de Problemas

### Error: "python: command not found"
- Verifica que Python esté en PATH.
- Reinicia PowerShell/CMD después de instalar Python.
- O usa la ruta completa: `C:\Python312\python.exe main.py` (reemplaza la versión).

### Error al instalar dependencias (falta compilador C++)
- Instala las **Build Tools de Visual Studio C++**
- O intenta: `pip install --only-binary :all: -r requirements.txt`

### El PDF no abre automáticamente
- Los PDFs se guardan en la carpeta del proyecto.
- Ábrelos manualmente si es necesario.
- Verifica que tengas un lector PDF predeterminado configurado.

### ImportError: No module named 'reportlab' (u otro)
- Asegúrate de que el entorno virtual esté **activado**.
- Reinstala dependencias: `pip install --force-reinstall -r requirements.txt`

### La aplicación no encuentra los archivos de datos
- Verifica que los CSVs estén en la **misma carpeta** que `main.py`.
- Las rutas son relativas al directorio actual.

## Crear un Ejecutable Independiente (Opcional)

Si quieres distribuir la aplicación sin necesidad de Python instalado:

```powershell
pip install pyinstaller
pyinstaller --onefile main.py
```

El ejecutable quedará en `dist\main.exe`. ⚠️ Pruébalo en otra máquina antes de distribuirlo.

## Desactivar el Entorno Virtual

Cuando termines:
```powershell
deactivate
```

## Notas Finales

- Todas las interacciones son en **español**.
- Los montos se manejan con valores **Decimal** para precisión.
- Usa `/` en las fechas si es necesario (p. ej. `2026-06-04` o `04/06/2026`).
- Para ayuda, verifícalo en `main.py` u abre un issue en el repositorio.

¡Listo! Ya está instalado. Disfruta la aplicación.
