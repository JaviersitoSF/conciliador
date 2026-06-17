# Conciliador

Aplicación de escritorio para control bancario: emisión de cheques,
registro de depósitos, notas de débito, conciliación y reportes de corte de
caja.

## Requisitos

- Python 3.12
- Dependencias listadas en `requirements.txt` o `pyproject.toml`

## Desarrollo

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest
```

## Ejecución

```bash
source venv/bin/activate
python main.py
```

La aplicación guarda datos locales en SQLite y crea respaldos automáticos
antes/después de operaciones importantes.

## Empaquetado

Ver `DISTRIBUCION.md` y `Conciliador-UI.spec` para generar distribuibles con
PyInstaller.
