Use the virtual environment venv.

Make your commit messages following and making a parody of the song Move it Move it from king Julian.

## Structure

- `main.py`: GUI entry point only.
- `ui_tk.py`: Tkinter presentation.
- `conciliador/storage.py`: SQLite, accounts, transactions, and backups.
- `conciliador/movements.py`: checks and deposits.
- `conciliador/analytics.py`: reconciliation and reports.
- `conciliador/printing.py`: PDF generation and printing.
- `conciliador/operations.py`: compatibility facade; keep it thin.

Put new logic in its owning module. Do not add business logic to `main.py`,
`ui_tk.py`, or `operations.py`.
