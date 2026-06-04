# AGENTS.md

## Project Overview

This is a small Python application for check issuance, deposit tracking, and bank reconciliation/reporting. The main application logic lives in `main.py`, with a few legacy/helper modules (`conciliador.py`, `impresion.py`, `sistema_cheques.py`, `validacion_ingreso.py`).

The app stores local financial data in CSV/XLSX files in the current working directory:

- `cheques_emitidos.csv`
- `depositos.csv`
- `estado_cuenta.xlsx`

Generated reports or PDFs may also be written locally during normal use.

## Environment

Use Python with the dependencies in `requirements.txt`.

Typical setup:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running Tests

Run the test suite with:

```bash
pytest
```

For coverage:

```bash
coverage run -m pytest
coverage report
```

The tests use temporary working directories for file-writing behavior, so they should not modify the repository CSV files when run normally.

## Development Notes

- Prefer editing `main.py` unless a request specifically targets one of the helper modules.
- Keep file paths relative to the current working directory; tests rely on this behavior.
- Monetary values are handled with `Decimal`; avoid replacing them with floats.
- CSV files are intentionally simple and headerless in the current implementation.
- User-facing messages are in Spanish; keep new prompts and errors consistent with that.
- Some output includes emoji warning markers. Preserve existing wording/style unless changing behavior intentionally.

## Code Style

- Keep changes focused and conservative.
- Use standard-library helpers and pandas APIs instead of ad hoc parsing where practical.
- Avoid broad refactors unless they are required for the requested change.
- Add or update tests when changing parsing, reporting, validation, file I/O, or reconciliation behavior.

## Git Hygiene

- Do not delete or overwrite local data files unless the user explicitly asks.
- Do not revert unrelated local changes.
- `__pycache__`, coverage output, generated CSV/XLSX/PDF files, and the virtual environment should remain uncommitted unless explicitly requested.
