import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
        self.bind_all("<Control-r>", lambda _evento: self.refrescar_todo())
        self.refrescar_todo()
        self.cheque_num.focus_set()

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
        ttk.Button(
            encabezado, text="Actualizar", command=self.refrescar_todo
        ).pack(side="right")
        ttk.Button(encabezado, text="Nueva cuenta", command=self.crear_cuenta).pack(side="right", padx=8)
        ttk.Button(
            encabezado, text="Editar cuenta", command=self.editar_cuenta
        ).pack(side="right")
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
        self.cheque_monto.bind("<Return>", lambda _evento: self.emitir_cheque())

        self.deposito_desc = self._campo(deposito, "Descripción", 0)
        self.deposito_monto = self._campo(deposito, "Monto", 1)
        self.boton_registrar_deposito = ttk.Button(
            deposito,
            text="Registrar depósito",
            command=self.registrar_deposito,
        )
        self.boton_registrar_deposito.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.deposito_monto.bind(
            "<Return>", lambda _evento: self.registrar_deposito()
        )

        acciones_cheque = ttk.Frame(contenedor)
        acciones_cheque.grid(row=1, column=0, sticky="new", padx=(0, 8))
        acciones_cheque.columnconfigure(0, weight=1)

        anular = ttk.LabelFrame(acciones_cheque, text="Anular cheque", padding=14)
        anular.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.anular_num = self._campo(anular, "Número de cheque", 0)
        self.boton_anular_cheque = ttk.Button(
            anular, text="Marcar como anulado", command=self.anular_cheque
        )
        self.boton_anular_cheque.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.anular_num.bind("<Return>", lambda _evento: self.anular_cheque())

        reimprimir = ttk.LabelFrame(
            acciones_cheque, text="Volver a imprimir un cheque", padding=14
        )
        reimprimir.grid(row=1, column=0, sticky="ew")
        self.reimprimir_num = self._campo(reimprimir, "Número de cheque", 0)
        self.boton_reimprimir_cheque = ttk.Button(
            reimprimir,
            text="Generar e imprimir otra copia",
            command=self.reimprimir_cheque,
        )
        self.boton_reimprimir_cheque.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.reimprimir_num.bind(
            "<Return>", lambda _evento: self.reimprimir_cheque()
        )

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
        self.boton_conciliar = ttk.Button(
            acciones,
            text="Seleccionar estado y conciliar",
            command=self.conciliar,
        )
        self.boton_conciliar.pack(side="left")

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
        barra_horizontal = ttk.Scrollbar(
            padre, orient="horizontal", command=tabla.xview
        )
        tabla.configure(
            yscrollcommand=barra.set,
            xscrollcommand=barra_horizontal.set,
        )
        tabla.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        barra_horizontal.grid(row=1, column=0, sticky="ew")
        tabla._orden_descendente = {}
        for columna in columnas:
            tabla.heading(
                columna,
                text=columna,
                command=lambda c=columna, t=tabla: self._ordenar_tabla(t, c),
            )
            ancho = 260 if columna in {"Nombre", "Mensaje", "Descripcion"} else 110
            tabla.column(columna, width=ancho, minwidth=80, anchor="w")
        tabla.bind("<Control-c>", lambda _evento, t=tabla: self._copiar_tabla(t))
        tabla.bind("<Control-C>", lambda _evento, t=tabla: self._copiar_tabla(t))
        return tabla

    def _ordenar_tabla(self, tabla, columna):
        filas = [
            (tabla.set(item, columna), item)
            for item in tabla.get_children()
            if "vacio" not in tabla.item(item, "tags")
        ]
        descendente = tabla._orden_descendente.get(columna, False)

        def clave(fila):
            valor = fila[0].replace(",", "").replace("Q", "").strip()
            try:
                return 0, float(valor)
            except ValueError:
                return 1, valor.casefold()

        filas.sort(key=clave, reverse=descendente)
        for posicion, (_, item) in enumerate(filas):
            tabla.move(item, "", posicion)
        tabla._orden_descendente[columna] = not descendente

    def _copiar_tabla(self, tabla):
        seleccion = tabla.selection()
        if not seleccion:
            return "break"
        lineas = []
        for item in seleccion:
            if "vacio" not in tabla.item(item, "tags"):
                lineas.append("\t".join(map(str, tabla.item(item, "values"))))
        if lineas:
            self.clipboard_clear()
            self.clipboard_append("\n".join(lineas))
        return "break"

    def _mostrar_estado_vacio(self, tabla, mensaje="Sin registros"):
        if not tabla.get_children():
            valores = [mensaje] + [""] * (len(tabla["columns"]) - 1)
            tabla.insert("", tk.END, values=valores, tags=("vacio",))

    def _ejecutar_bloqueado(self, boton, accion):
        if str(boton.cget("state")) == "disabled":
            return None
        boton.configure(state="disabled")
        self.update_idletasks()
        try:
            return accion()
        finally:
            boton.configure(state="normal")

    def _actualizar_boton_cheque(self):
        texto = (
            "Emitir e imprimir"
            if self.imprimir_cheque.get()
            else "Emitir sin imprimir"
        )
        self.boton_emitir_cheque.configure(text=texto)

    def emitir_cheque(self):
        return self._ejecutar_bloqueado(
            self.boton_emitir_cheque, self._emitir_cheque
        )

    def _emitir_cheque(self):
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
        return self._ejecutar_bloqueado(
            self.boton_registrar_deposito, self._registrar_deposito
        )

    def _registrar_deposito(self):
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
        numero = self.anular_num.get().strip()
        if not numero:
            messagebox.showerror(
                "No se pudo anular",
                "Ingrese el número de cheque que desea anular.",
                parent=self,
            )
            self.anular_num.focus_set()
            return
        confirmar = messagebox.askyesno(
            "Confirmar anulación",
            f"¿Desea marcar como anulado el cheque {numero}?\n\n"
            "Esta acción cambia su estado en el registro.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        return self._ejecutar_bloqueado(
            self.boton_anular_cheque, self._anular_cheque
        )

    def _anular_cheque(self):
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
        return self._ejecutar_bloqueado(
            self.boton_reimprimir_cheque, self._reimprimir_cheque
        )

    def _reimprimir_cheque(self):
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
        archivo = filedialog.askopenfilename(
            title="Seleccionar estado de cuenta",
            filetypes=[("Archivos Excel", "*.xlsx *.xls")],
        )
        if not archivo:
            return
        return self._ejecutar_bloqueado(
            self.boton_conciliar, lambda: self._conciliar_archivo(archivo)
        )

    def _conciliar_archivo(self, archivo):
        self._limpiar_tabla(self.tabla_conciliacion)
        self._limpiar_tabla(self.tabla_no_registrados)
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
        self._mostrar_estado_vacio(
            self.tabla_conciliacion, "No se encontraron cheques"
        )
        self._mostrar_estado_vacio(
            self.tabla_no_registrados, "No se encontraron cargos"
        )

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
        DialogoNuevaCuenta(self, self._registrar_cuenta)

    def editar_cuenta(self):
        try:
            cuenta_id = self.cuenta_id_actual()
            cuenta = next(
                cuenta for cuenta in self.cuentas if cuenta["id"] == cuenta_id
            )
        except (Exception, StopIteration) as e:
            messagebox.showerror("Editar cuenta", str(e))
            return
        DialogoNuevaCuenta(
            self,
            lambda banco, nombre, numero: self._actualizar_cuenta(
                cuenta_id, banco, nombre, numero
            ),
            cuenta=cuenta,
        )

    def _registrar_cuenta(self, banco, nombre, numero):
        try:
            cuenta_id = service.crear_cuenta(banco, nombre, numero)
        except Exception as e:
            messagebox.showerror("No se pudo crear", str(e))
            return False
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
        return True

    def _actualizar_cuenta(self, cuenta_id, banco, nombre, numero):
        try:
            service.actualizar_cuenta(cuenta_id, banco, nombre, numero)
        except Exception as e:
            messagebox.showerror("No se pudo actualizar", str(e))
            return False
        self.refrescar_todo()
        messagebox.showinfo(
            "Cuenta actualizada",
            "La información de la cuenta bancaria fue actualizada.",
        )
        return True

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
            self._mostrar_estado_vacio(
                self.tabla_cheques, "No hay cheques registrados"
            )
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            self.tabla_cheques.insert(
                "",
                tk.END,
                values=(fila["Num"], fila["Fecha"], fila["Nombre"], fila["Monto"], fila["Estado"]),
            )
        self._mostrar_estado_vacio(self.tabla_cheques, "No hay cheques registrados")

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
        self._mostrar_estado_vacio(
            self.tabla_reporte_cheques, "No hay cheques en el período"
        )
        self._mostrar_estado_vacio(
            self.tabla_reporte_depositos, "No hay depósitos en el período"
        )

    def _limpiar_tabla(self, tabla):
        for item in tabla.get_children():
            tabla.delete(item)

    def _limpiar_conciliacion(self):
        self._limpiar_tabla(self.tabla_conciliacion)
        self._limpiar_tabla(self.tabla_no_registrados)
        self._mostrar_estado_vacio(
            self.tabla_conciliacion, "Seleccione un estado de cuenta"
        )
        self._mostrar_estado_vacio(
            self.tabla_no_registrados, "Seleccione un estado de cuenta"
        )


class DialogoNuevaCuenta(tk.Toplevel):
    def __init__(self, padre, al_guardar, cuenta=None):
        super().__init__(padre)
        self.al_guardar = al_guardar
        self.title("Editar cuenta" if cuenta else "Nueva cuenta")
        self.resizable(False, False)
        self.transient(padre)
        self.grab_set()

        contenido = ttk.Frame(self, padding=18)
        contenido.pack(fill="both", expand=True)
        contenido.columnconfigure(1, weight=1)

        self.banco = self._campo(contenido, "Nombre del banco", 0)
        self.nombre = self._campo(contenido, "Nombre interno", 1)
        self.numero = self._campo(contenido, "Número de cuenta (opcional)", 2)
        if cuenta:
            self.banco.insert(0, cuenta["banco"])
            self.nombre.insert(0, cuenta["nombre"])
            self.numero.insert(0, cuenta["numero"])

        acciones = ttk.Frame(contenido)
        acciones.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(
            side="right"
        )
        self.boton_guardar = ttk.Button(
            acciones,
            text="Guardar cambios" if cuenta else "Guardar cuenta",
            command=self.guardar,
        )
        self.boton_guardar.pack(side="right", padx=8)

        self.bind("<Escape>", lambda _evento: self.destroy())
        self.bind("<Return>", lambda _evento: self.guardar())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.banco.focus_set()

    def _campo(self, padre, etiqueta, fila):
        ttk.Label(padre, text=etiqueta).grid(
            row=fila, column=0, sticky="w", padx=(0, 12), pady=6
        )
        entrada = ttk.Entry(padre, width=36)
        entrada.grid(row=fila, column=1, sticky="ew", pady=6)
        return entrada

    def guardar(self):
        if str(self.boton_guardar.cget("state")) == "disabled":
            return
        banco = self.banco.get().strip()
        nombre = self.nombre.get().strip()
        if not banco:
            messagebox.showerror(
                "Datos incompletos",
                "Ingrese el nombre del banco.",
                parent=self,
            )
            self.banco.focus_set()
            return
        if not nombre:
            messagebox.showerror(
                "Datos incompletos",
                "Ingrese el nombre interno de la cuenta.",
                parent=self,
            )
            self.nombre.focus_set()
            return

        self.boton_guardar.configure(state="disabled")
        self.update_idletasks()
        try:
            guardada = self.al_guardar(banco, nombre, self.numero.get().strip())
        finally:
            if self.winfo_exists():
                self.boton_guardar.configure(state="normal")
        if guardada:
            self.destroy()


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
        self.boton_probar = ttk.Button(
            acciones, text="Probar impresión", command=self.probar_impresion
        )
        self.boton_probar.pack(side="left", padx=8)
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(side="right")
        self.boton_guardar = ttk.Button(
            acciones, text="Guardar", command=self.guardar
        )
        self.boton_guardar.pack(side="right", padx=8)
        self._cargar(formato)
        self.bind("<Escape>", lambda _evento: self.destroy())
        self.bind("<Control-s>", lambda _evento: self.guardar())
        self.entradas["ancho"].focus_set()

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
        if str(self.boton_probar.cget("state")) == "disabled":
            return
        self.boton_probar.configure(state="disabled")
        self.update_idletasks()
        try:
            enviada = core.probar_formato_impresion(self._valores())
        except Exception as e:
            messagebox.showerror("Prueba de impresión", str(e), parent=self)
            return
        finally:
            self.boton_probar.configure(state="normal")
        if enviada:
            mensaje = "La prueba fue enviada a impresión."
        else:
            mensaje = "Se generó el PDF, pero no se pudo enviar a impresión."
        messagebox.showinfo("Prueba de impresión", mensaje, parent=self)

    def guardar(self):
        if str(self.boton_guardar.cget("state")) == "disabled":
            return
        self.boton_guardar.configure(state="disabled")
        self.update_idletasks()
        try:
            service.guardar_formato(self.cuenta_id, self._valores())
        except Exception as e:
            messagebox.showerror("Formato de impresión", str(e), parent=self)
            return
        finally:
            if self.winfo_exists():
                self.boton_guardar.configure(state="normal")
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

    try:
        app = ConciliadorApp()
    except Exception as e:
        logger.exception("No se pudo construir la interfaz grafica")
        messagebox.showerror(
            "Conciliador no pudo iniciar",
            "No se pudo cargar la interfaz. El detalle está en:\n"
            f"{paths.log_file}\n\n{e}",
        )
        return 1

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
