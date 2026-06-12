import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from conciliador import operations as core
from conciliador.runtime import prepare_application
from conciliador.service import ConciliadorService

service = ConciliadorService(core)


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
        ttk.Button(encabezado, text="Nueva cuenta", command=self.crear_cuenta).pack(side="right", padx=8)
        ttk.Button(
            encabezado,
            text="Formato de impresión",
            command=self.configurar_formato_impresion,
        ).pack(side="right")
        self.selector_cuenta = ttk.Combobox(encabezado, state="readonly", width=36)
        self.selector_cuenta.pack(side="right", padx=8)
        self.selector_cuenta.bind("<<ComboboxSelected>>", lambda _evento: self.refrescar_todo())
        ttk.Label(encabezado, text="Cuenta:").pack(side="right")

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

        self.cheque_num = self._campo(cheque, "Número de cheque", 0)
        self.cheque_nombre = self._campo(cheque, "Páguese a", 1)
        self.cheque_descripcion = self._campo(cheque, "Descripción", 2)
        self.cheque_monto = self._campo(cheque, "Monto", 3)
        self.imprimir_cheque = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            cheque,
            text="Imprimir cheque",
            variable=self.imprimir_cheque,
            command=self._actualizar_boton_cheque,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.boton_emitir_cheque = ttk.Button(
            cheque, text="Emitir e imprimir", command=self.emitir_cheque
        )
        self.boton_emitir_cheque.grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        self.deposito_desc = self._campo(deposito, "Descripción", 0)
        self.deposito_monto = self._campo(deposito, "Monto", 1)
        ttk.Button(deposito, text="Registrar depósito", command=self.registrar_deposito).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        acciones_cheque = ttk.Frame(contenedor)
        acciones_cheque.grid(row=1, column=0, sticky="new", padx=(0, 8))
        acciones_cheque.columnconfigure(0, weight=1)

        anular = ttk.LabelFrame(acciones_cheque, text="Anular cheque", padding=14)
        anular.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.anular_num = self._campo(anular, "Número de cheque", 0)
        ttk.Button(anular, text="Marcar como anulado", command=self.anular_cheque).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        reimprimir = ttk.LabelFrame(
            acciones_cheque, text="Volver a imprimir un cheque", padding=14
        )
        reimprimir.grid(row=1, column=0, sticky="ew")
        self.reimprimir_num = self._campo(reimprimir, "Número de cheque", 0)
        ttk.Button(
            reimprimir,
            text="Generar e imprimir otra copia",
            command=self.reimprimir_cheque,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))

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
        ttk.Button(acciones, text="Seleccionar estado y conciliar", command=self.conciliar).pack(side="left")

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

    def _actualizar_boton_cheque(self):
        texto = (
            "Emitir e imprimir"
            if self.imprimir_cheque.get()
            else "Emitir sin imprimir"
        )
        self.boton_emitir_cheque.configure(text=texto)

    def emitir_cheque(self):
        descripcion = self.cheque_descripcion.get().strip()
        if not descripcion:
            messagebox.showerror(
                "No se pudo emitir",
                "⚠️ Error: el campo no puede quedar vacío.",
            )
            return
        try:
            resultado = service.emitir_cheque(
                self.cheque_num.get(),
                self.cheque_nombre.get(),
                self.cheque_monto.get(),
                descripcion=descripcion,
                cuenta_id=self.cuenta_id_actual(),
                imprimir=self.imprimir_cheque.get(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo emitir", str(e))
            return
        self.cheque_num.delete(0, tk.END)
        self.cheque_nombre.delete(0, tk.END)
        self.cheque_descripcion.delete(0, tk.END)
        self.cheque_monto.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Cheque emitido", resultado["mensaje"])

    def registrar_deposito(self):
        try:
            resultado = service.registrar_deposito(
                self.deposito_monto.get(),
                self.deposito_desc.get(),
                cuenta_id=self.cuenta_id_actual(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo registrar", str(e))
            return
        self.deposito_desc.delete(0, tk.END)
        self.deposito_monto.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Depósito registrado", resultado["mensaje"])

    def anular_cheque(self):
        try:
            resultado = service.anular_cheque(
                self.anular_num.get(), self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo anular", str(e))
            return
        self.anular_num.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Cheque anulado", resultado["mensaje"])

    def reimprimir_cheque(self):
        try:
            mensaje = service.reimprimir_cheque(
                self.reimprimir_num.get(), self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo reimprimir", str(e))
            return
        self.reimprimir_num.delete(0, tk.END)
        messagebox.showinfo("Cheque listo", mensaje)

    def conciliar(self):
        self._limpiar_tabla(self.tabla_conciliacion)
        self._limpiar_tabla(self.tabla_no_registrados)
        archivo = filedialog.askopenfilename(
            title="Seleccionar estado de cuenta",
            filetypes=[("Archivos Excel", "*.xlsx *.xls")],
        )
        if not archivo:
            return
        try:
            resultado = service.conciliar(
                self.cuenta_id_actual(), archivo
            )
        except Exception as e:
            messagebox.showerror("Conciliación", str(e))
            return
        for fila in resultado["cheques"]:
            self.tabla_conciliacion.insert("", tk.END, values=(fila["num"], fila["resultado"], fila["mensaje"]))
        for fila in resultado["no_registrados"]:
            monto = core.formatear_monto(fila["monto"]) if fila["monto"] is not None else "N/D"
            self.tabla_no_registrados.insert("", tk.END, values=(fila["num"], monto, fila["mensaje"]))

    def refrescar_todo(self):
        self._cargar_selector_cuentas()
        self._cargar_cheques()
        self._cargar_reporte()
        self._limpiar_conciliacion()

    def _cargar_selector_cuentas(self):
        cuenta_actual = self.cuenta_id_actual(requerida=False)
        self.cuentas = service.listar_cuentas()
        valores = [
            f"{cuenta['id']} | {cuenta['banco']} | {cuenta['nombre']}"
            for cuenta in self.cuentas
        ]
        self.selector_cuenta["values"] = valores
        if not valores:
            self.selector_cuenta.set("")
            return
        indice = next(
            (
                posicion
                for posicion, cuenta in enumerate(self.cuentas)
                if cuenta["id"] == cuenta_actual
            ),
            0,
        )
        self.selector_cuenta.current(indice)

    def cuenta_id_actual(self, requerida=True):
        valor = self.selector_cuenta.get()
        if valor:
            return int(valor.split("|", 1)[0].strip())
        if requerida:
            raise core.ErrorOperacion("No hay una cuenta bancaria seleccionada.")
        return None

    def crear_cuenta(self):
        banco = simpledialog.askstring("Nueva cuenta", "Nombre del banco:", parent=self)
        if banco is None:
            return
        nombre = simpledialog.askstring(
            "Nueva cuenta", "Nombre interno de la cuenta:", parent=self
        )
        if nombre is None:
            return
        numero = simpledialog.askstring(
            "Nueva cuenta", "Número de cuenta (opcional):", parent=self
        )
        if numero is None:
            return
        try:
            cuenta_id = service.crear_cuenta(banco, nombre, numero)
        except Exception as e:
            messagebox.showerror("No se pudo crear", str(e))
            return
        self._cargar_selector_cuentas()
        for indice, cuenta in enumerate(self.cuentas):
            if cuenta["id"] == cuenta_id:
                self.selector_cuenta.current(indice)
                break
        self.refrescar_todo()
        messagebox.showinfo(
            "Cuenta registrada",
            f"✅ Cuenta bancaria registrada con identificador {cuenta_id}.",
        )

    def configurar_formato_impresion(self):
        try:
            cuenta_id = self.cuenta_id_actual()
            formato = service.obtener_formato(cuenta_id)
        except Exception as e:
            messagebox.showerror("Formato de impresión", str(e))
            return
        DialogoFormatoImpresion(self, cuenta_id, formato)

    def _cargar_cheques(self):
        self._limpiar_tabla(self.tabla_cheques)
        df = service.obtener_cheques(self.cuenta_id_actual())
        if df.empty:
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            self.tabla_cheques.insert(
                "",
                tk.END,
                values=(fila["Num"], fila["Fecha"], fila["Nombre"], fila["Monto"], fila["Estado"]),
            )

    def _cargar_reporte(self):
        reporte = service.obtener_reporte(
            cuenta_id=self.cuenta_id_actual()
        )
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

    def _limpiar_conciliacion(self):
        self._limpiar_tabla(self.tabla_conciliacion)
        self._limpiar_tabla(self.tabla_no_registrados)


class DialogoFormatoImpresion(tk.Toplevel):
    CAMPOS = (
        ("ancho", "Ancho del cheque"),
        ("alto", "Alto del cheque"),
        ("fecha_x", "Fecha X"),
        ("fecha_y", "Fecha Y"),
        ("nombre_x", "Beneficiario X"),
        ("nombre_y", "Beneficiario Y"),
        ("monto_x", "Monto X"),
        ("monto_y", "Monto Y"),
        ("no_negociable_x", "No negociable X"),
        ("no_negociable_y", "No negociable Y"),
        ("monto_letras_x", "Monto en letras X"),
        ("monto_letras_y", "Monto en letras Y"),
        ("descripcion_x", "Descripción X"),
        ("descripcion_y", "Descripción Y"),
    )

    def __init__(self, padre, cuenta_id, formato):
        super().__init__(padre)
        self.cuenta_id = cuenta_id
        self.title("Formato de impresión")
        self.resizable(False, False)
        self.transient(padre)
        self.grab_set()

        ttk.Label(
            self,
            text="Medidas y posiciones en centímetros",
            style="Title.TLabel",
        ).grid(row=0, column=0, columnspan=4, padx=18, pady=(16, 10))

        self.entradas = {}
        for posicion, (campo, etiqueta) in enumerate(self.CAMPOS):
            columna = 0 if posicion < 7 else 2
            fila = posicion + 1 if posicion < 7 else posicion - 6
            ttk.Label(self, text=etiqueta).grid(
                row=fila, column=columna, sticky="w", padx=(18, 8), pady=5
            )
            entrada = ttk.Entry(self, width=12)
            entrada.grid(
                row=fila, column=columna + 1, sticky="ew", padx=(0, 18), pady=5
            )
            self.entradas[campo] = entrada

        acciones = ttk.Frame(self)
        acciones.grid(row=8, column=0, columnspan=4, sticky="ew", padx=18, pady=16)
        ttk.Button(
            acciones, text="Restaurar defaults", command=self.restaurar_defaults
        ).pack(side="left")
        ttk.Button(
            acciones, text="Probar impresión", command=self.probar_impresion
        ).pack(side="left", padx=8)
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(acciones, text="Guardar", command=self.guardar).pack(
            side="right", padx=8
        )
        self._cargar(formato)

    def _cargar(self, formato):
        for campo, entrada in self.entradas.items():
            entrada.delete(0, tk.END)
            entrada.insert(0, f"{formato[campo]:g}")

    def _valores(self):
        return {
            campo: entrada.get().strip()
            for campo, entrada in self.entradas.items()
        }

    def restaurar_defaults(self):
        self._cargar(core.FORMATO_IMPRESION_DEFAULT)

    def probar_impresion(self):
        try:
            enviada = core.probar_formato_impresion(self._valores())
        except Exception as e:
            messagebox.showerror("Prueba de impresión", str(e), parent=self)
            return
        if enviada:
            mensaje = "La prueba fue enviada a impresión."
        else:
            mensaje = "Se generó el PDF, pero no se pudo enviar a impresión."
        messagebox.showinfo("Prueba de impresión", mensaje, parent=self)

    def guardar(self):
        try:
            service.guardar_formato(self.cuenta_id, self._valores())
        except Exception as e:
            messagebox.showerror("Formato de impresión", str(e), parent=self)
            return
        messagebox.showinfo(
            "Formato de impresión",
            "Formato guardado para la cuenta seleccionada.",
            parent=self,
        )
        self.destroy()


def main(base_dir=None):
    try:
        paths, logger, _version = prepare_application(base_dir)
    except Exception as e:
        messagebox.showerror(
            "Conciliador no pudo iniciar",
            f"No se pudo preparar la base de datos:\n{e}",
        )
        return 1

    app = ConciliadorApp()

    def report_callback_exception(exc_type, exc_value, exc_traceback):
        logger.error(
            "Excepcion no controlada en Tkinter",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        messagebox.showerror(
            "Error inesperado",
            "Ocurrió un error inesperado. El detalle está en:\n"
            f"{paths.log_file}",
            parent=app,
        )

    app.report_callback_exception = report_callback_exception
    app.mainloop()
    return 0


if __name__ == "__main__":
    main()
