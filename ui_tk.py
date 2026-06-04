import tkinter as tk
from tkinter import messagebox, ttk

import main as core


class ConciliadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Control Bancario")
        self.geometry("1080x720")
        self.minsize(900, 620)

        self._configurar_estilo()
        self._crear_layout()
        self.refrescar_todo()

    def _configurar_estilo(self):
        self.configure(bg="#f6f7f9")
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background="#f6f7f9")
        estilo.configure("Panel.TFrame", background="#ffffff", relief="flat")
        estilo.configure("TLabel", background="#f6f7f9", foreground="#1f2937")
        estilo.configure("Panel.TLabel", background="#ffffff", foreground="#1f2937")
        estilo.configure("Title.TLabel", font=("Arial", 18, "bold"), background="#f6f7f9")
        estilo.configure("Metric.TLabel", font=("Arial", 14, "bold"), background="#ffffff")
        estilo.configure("TButton", padding=(12, 7))
        estilo.configure("Treeview", rowheight=28, fieldbackground="#ffffff", background="#ffffff")
        estilo.configure("Treeview.Heading", font=("Arial", 10, "bold"))

    def _crear_layout(self):
        encabezado = ttk.Frame(self, padding=(18, 14, 18, 8))
        encabezado.pack(fill="x")
        ttk.Label(encabezado, text="Sistema de Control Bancario", style="Title.TLabel").pack(side="left")
        ttk.Button(encabezado, text="Actualizar", command=self.refrescar_todo).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        self.tab_operaciones = ttk.Frame(self.notebook, padding=14)
        self.tab_reporte = ttk.Frame(self.notebook, padding=14)
        self.tab_conciliacion = ttk.Frame(self.notebook, padding=14)

        self.notebook.add(self.tab_operaciones, text="Operaciones")
        self.notebook.add(self.tab_reporte, text="Corte de caja")
        self.notebook.add(self.tab_conciliacion, text="Conciliación")

        self._crear_operaciones()
        self._crear_reporte()
        self._crear_conciliacion()

    def _crear_operaciones(self):
        contenedor = ttk.Frame(self.tab_operaciones)
        contenedor.pack(fill="both", expand=True)
        contenedor.columnconfigure((0, 1), weight=1, uniform="ops")
        contenedor.rowconfigure(1, weight=1)

        cheque = ttk.LabelFrame(contenedor, text="Emitir cheque", padding=14)
        cheque.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        deposito = ttk.LabelFrame(contenedor, text="Registrar depósito", padding=14)
        deposito.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))
        anular = ttk.LabelFrame(contenedor, text="Anular cheque", padding=14)
        anular.grid(row=1, column=0, sticky="new", padx=(0, 8))

        self.cheque_num = self._campo(cheque, "Número de cheque", 0)
        self.cheque_nombre = self._campo(cheque, "Páguese a", 1)
        self.cheque_monto = self._campo(cheque, "Monto", 2)
        ttk.Button(cheque, text="Emitir e imprimir", command=self.emitir_cheque).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        self.deposito_desc = self._campo(deposito, "Descripción", 0)
        self.deposito_monto = self._campo(deposito, "Monto", 1)
        ttk.Button(deposito, text="Registrar depósito", command=self.registrar_deposito).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        self.anular_num = self._campo(anular, "Número de cheque", 0)
        ttk.Button(anular, text="Marcar como anulado", command=self.anular_cheque).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        historial = ttk.LabelFrame(contenedor, text="Cheques recientes", padding=10)
        historial.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        historial.rowconfigure(0, weight=1)
        historial.columnconfigure(0, weight=1)
        self.tabla_cheques = self._tabla(historial, ("Num", "Fecha", "Nombre", "Monto", "Estado"))

    def _crear_reporte(self):
        metricas = ttk.Frame(self.tab_reporte, style="Panel.TFrame", padding=12)
        metricas.pack(fill="x", pady=(0, 12))
        metricas.columnconfigure((0, 1, 2), weight=1)
        self.lbl_ingresos = ttk.Label(metricas, text="Ingresos: Q 0.00", style="Metric.TLabel")
        self.lbl_egresos = ttk.Label(metricas, text="Egresos: Q 0.00", style="Metric.TLabel")
        self.lbl_saldo = ttk.Label(metricas, text="Saldo: Q 0.00", style="Metric.TLabel")
        self.lbl_ingresos.grid(row=0, column=0, sticky="w")
        self.lbl_egresos.grid(row=0, column=1, sticky="w")
        self.lbl_saldo.grid(row=0, column=2, sticky="w")

        cuerpo = ttk.Frame(self.tab_reporte)
        cuerpo.pack(fill="both", expand=True)
        cuerpo.columnconfigure((0, 1), weight=1, uniform="report")
        cuerpo.rowconfigure(0, weight=1)

        cheques = ttk.LabelFrame(cuerpo, text="Cheques del mes", padding=10)
        cheques.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cheques.rowconfigure(0, weight=1)
        cheques.columnconfigure(0, weight=1)
        self.tabla_reporte_cheques = self._tabla(cheques, ("Num", "Fecha", "Nombre", "Monto", "Estado"))

        depositos = ttk.LabelFrame(cuerpo, text="Depósitos del mes", padding=10)
        depositos.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        depositos.rowconfigure(0, weight=1)
        depositos.columnconfigure(0, weight=1)
        self.tabla_reporte_depositos = self._tabla(depositos, ("Fecha", "Descripcion", "Monto"))

    def _crear_conciliacion(self):
        acciones = ttk.Frame(self.tab_conciliacion)
        acciones.pack(fill="x", pady=(0, 12))
        ttk.Button(acciones, text="Conciliar con estado_cuenta.xlsx", command=self.conciliar).pack(side="left")

        panel = ttk.Frame(self.tab_conciliacion)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure((0, 1), weight=1, uniform="conc")
        panel.rowconfigure(0, weight=1)

        cheques = ttk.LabelFrame(panel, text="Resultados de cheques emitidos", padding=10)
        cheques.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cheques.rowconfigure(0, weight=1)
        cheques.columnconfigure(0, weight=1)
        self.tabla_conciliacion = self._tabla(cheques, ("Num", "Resultado", "Mensaje"))

        banco = ttk.LabelFrame(panel, text="Cargos no registrados", padding=10)
        banco.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        banco.rowconfigure(0, weight=1)
        banco.columnconfigure(0, weight=1)
        self.tabla_no_registrados = self._tabla(banco, ("Num", "Monto", "Mensaje"))

    def _campo(self, padre, etiqueta, fila):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=5)
        entrada = ttk.Entry(padre)
        entrada.grid(row=fila, column=1, sticky="ew", pady=5)
        padre.columnconfigure(1, weight=1)
        return entrada

    def _tabla(self, padre, columnas):
        tabla = ttk.Treeview(padre, columns=columnas, show="headings")
        barra = ttk.Scrollbar(padre, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=barra.set)
        tabla.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        for columna in columnas:
            tabla.heading(columna, text=columna)
            ancho = 260 if columna in {"Nombre", "Mensaje", "Descripcion"} else 110
            tabla.column(columna, width=ancho, minwidth=80, anchor="w")
        return tabla

    def emitir_cheque(self):
        try:
            resultado = core.emitir_cheque_datos(
                self.cheque_num.get(),
                self.cheque_nombre.get(),
                self.cheque_monto.get(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo emitir", str(e))
            return
        self.cheque_num.delete(0, tk.END)
        self.cheque_nombre.delete(0, tk.END)
        self.cheque_monto.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Cheque emitido", resultado["mensaje"])

    def registrar_deposito(self):
        try:
            resultado = core.registrar_deposito_datos(self.deposito_monto.get(), self.deposito_desc.get())
        except Exception as e:
            messagebox.showerror("No se pudo registrar", str(e))
            return
        self.deposito_desc.delete(0, tk.END)
        self.deposito_monto.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Depósito registrado", resultado["mensaje"])

    def anular_cheque(self):
        try:
            resultado = core.anular_cheque_numero(self.anular_num.get())
        except Exception as e:
            messagebox.showerror("No se pudo anular", str(e))
            return
        self.anular_num.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Cheque anulado", resultado["mensaje"])

    def conciliar(self):
        self._limpiar_tabla(self.tabla_conciliacion)
        self._limpiar_tabla(self.tabla_no_registrados)
        try:
            resultado = core.obtener_conciliacion()
        except Exception as e:
            messagebox.showerror("Conciliación", str(e))
            return
        for fila in resultado["cheques"]:
            self.tabla_conciliacion.insert("", tk.END, values=(fila["num"], fila["resultado"], fila["mensaje"]))
        for fila in resultado["no_registrados"]:
            monto = core.formatear_monto(fila["monto"]) if fila["monto"] is not None else "N/D"
            self.tabla_no_registrados.insert("", tk.END, values=(fila["num"], monto, fila["mensaje"]))

    def refrescar_todo(self):
        self._cargar_cheques()
        self._cargar_reporte()

    def _cargar_cheques(self):
        self._limpiar_tabla(self.tabla_cheques)
        df = core.cargar_cheques_registrados()
        if df.empty:
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            self.tabla_cheques.insert(
                "",
                tk.END,
                values=(fila["Num"], fila["Fecha"], fila["Nombre"], fila["Monto"], fila["Estado"]),
            )

    def _cargar_reporte(self):
        reporte = core.obtener_reporte_movimientos()
        self.lbl_ingresos.configure(text=f"Ingresos: Q {core.formatear_monto(reporte['total_depositos'])}")
        self.lbl_egresos.configure(text=f"Egresos: Q {core.formatear_monto(reporte['total_cheques'])}")
        self.lbl_saldo.configure(text=f"Saldo: Q {core.formatear_monto(reporte['saldo'])}")

        self._limpiar_tabla(self.tabla_reporte_cheques)
        for _, fila in reporte["cheques"].iterrows():
            self.tabla_reporte_cheques.insert(
                "",
                tk.END,
                values=(fila["Num"], fila["Fecha"], fila["Nombre"], fila["Monto"], fila["Estado"]),
            )

        self._limpiar_tabla(self.tabla_reporte_depositos)
        for _, fila in reporte["depositos"].iterrows():
            self.tabla_reporte_depositos.insert(
                "",
                tk.END,
                values=(fila["Fecha"], fila["Descripcion"], fila["Monto"]),
            )

    def _limpiar_tabla(self, tabla):
        for item in tabla.get_children():
            tabla.delete(item)


def main():
    app = ConciliadorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
