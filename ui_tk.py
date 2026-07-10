import tkinter as tk
from calendar import monthrange
from datetime import date
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

        self._orden_descendente_tablas = {}
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

        self.tab_cheques = ttk.Frame(self.notebook, padding=14)
        self.tab_depositos = ttk.Frame(self.notebook, padding=14)
        self.tab_notas_debito = ttk.Frame(self.notebook, padding=14)
        self.tab_reporte = ttk.Frame(self.notebook, padding=14)
        self.tab_conciliacion = ttk.Frame(self.notebook, padding=14)

        self.notebook.add(self.tab_cheques, text="Cheques")
        self.notebook.add(self.tab_depositos, text="Depósitos")
        self.notebook.add(self.tab_notas_debito, text="Notas de débito")
        self.notebook.add(self.tab_reporte, text="Corte de caja")
        self.notebook.add(self.tab_conciliacion, text="Conciliación")

        self._crear_cheques()
        self._crear_depositos()
        self._crear_notas_debito()
        self._crear_reporte()
        self._crear_conciliacion()

    def _crear_cheques(self):
        contenedor = ttk.Frame(self.tab_cheques)
        contenedor.pack(fill="both", expand=True)
        contenedor.columnconfigure((0, 1), weight=1, uniform="cheques")
        contenedor.rowconfigure(0, weight=1)

        controles = ttk.Frame(contenedor)
        controles.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        controles.columnconfigure(0, weight=1)
        cheque = ttk.LabelFrame(controles, text="Emitir cheque", padding=14)
        cheque.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.cheque_num = self._campo(cheque, "Número de cheque", 0)
        self.cheque_nombre = self._campo(cheque, "Páguese a", 1)
        self.cheque_descripcion = self._campo(cheque, "Descripción", 2)
        self.cheque_monto = self._campo(cheque, "Monto", 3)
        self.cheque_fecha = self._campo(cheque, "Fecha (AAAA-MM-DD)", 4)
        self.cheque_fecha.insert(0, date.today().isoformat())
        self.imprimir_cheque = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            cheque,
            text="Imprimir cheque",
            variable=self.imprimir_cheque,
            command=self._actualizar_boton_cheque,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.boton_emitir_cheque = ttk.Button(
            cheque, text="Emitir e imprimir", command=self.emitir_cheque
        )
        self.boton_emitir_cheque.grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        self.cheque_monto.bind("<Return>", lambda _evento: self.emitir_cheque())

        acciones_cheque = ttk.Frame(controles)
        acciones_cheque.grid(row=1, column=0, sticky="ew")
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
        historial.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        historial.rowconfigure(0, weight=1)
        historial.columnconfigure(0, weight=1)
        self.tabla_cheques = self._tabla(historial, ("Num", "Fecha", "Nombre", "Monto", "Estado"))
        acciones = ttk.Frame(historial)
        acciones.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        acciones.columnconfigure((0, 1), weight=1)
        ttk.Button(
            acciones, text="Editar seleccionado", command=self.editar_cheque
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            acciones, text="Borrar seleccionado", command=self.eliminar_cheque
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.tabla_cheques.bind("<Double-1>", lambda _evento: self.editar_cheque())

    def _crear_depositos(self):
        contenedor = ttk.Frame(self.tab_depositos)
        contenedor.pack(fill="both", expand=True)
        contenedor.columnconfigure((0, 1), weight=1, uniform="depositos")
        contenedor.rowconfigure(0, weight=1)

        controles = ttk.Frame(contenedor)
        controles.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        controles.columnconfigure(0, weight=1)

        deposito = ttk.LabelFrame(controles, text="Registrar depósito", padding=14)
        deposito.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.deposito_num = self._campo(deposito, "Número de depósito", 0)
        self.deposito_desc = self._campo(deposito, "Descripción", 1)
        self.deposito_monto = self._campo(deposito, "Monto", 2)
        self.deposito_fecha = self._campo(deposito, "Fecha (AAAA-MM-DD)", 3)
        self.deposito_fecha.insert(0, date.today().isoformat())
        self.boton_registrar_deposito = ttk.Button(
            deposito, text="Registrar depósito", command=self.registrar_deposito
        )
        self.boton_registrar_deposito.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.deposito_monto.bind(
            "<Return>", lambda _evento: self.registrar_deposito()
        )

        anular = ttk.LabelFrame(controles, text="Anular depósito", padding=14)
        anular.grid(row=1, column=0, sticky="ew")
        self.anular_deposito_num = self._campo(
            anular, "Número de depósito", 0
        )
        self.boton_anular_deposito = ttk.Button(
            anular, text="Marcar como anulado", command=self.anular_deposito
        )
        self.boton_anular_deposito.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.anular_deposito_num.bind(
            "<Return>", lambda _evento: self.anular_deposito()
        )

        historial = ttk.LabelFrame(
            contenedor, text="Depósitos recientes", padding=10
        )
        historial.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        historial.rowconfigure(0, weight=1)
        historial.columnconfigure(0, weight=1)
        self.tabla_depositos = self._tabla(
            historial, ("Num", "Fecha", "Descripcion", "Monto", "Estado")
        )
        acciones = ttk.Frame(historial)
        acciones.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        acciones.columnconfigure((0, 1), weight=1)
        ttk.Button(
            acciones, text="Editar seleccionado", command=self.editar_deposito
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            acciones, text="Borrar seleccionado", command=self.eliminar_deposito
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.tabla_depositos.bind(
            "<Double-1>", lambda _evento: self.editar_deposito()
        )

    def _crear_notas_debito(self):
        contenedor = ttk.Frame(self.tab_notas_debito)
        contenedor.pack(fill="both", expand=True)
        contenedor.columnconfigure((0, 1), weight=1, uniform="notas_debito")
        contenedor.rowconfigure(0, weight=1)

        controles = ttk.Frame(contenedor)
        controles.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        controles.columnconfigure(0, weight=1)

        nota = ttk.LabelFrame(controles, text="Registrar nota de débito", padding=14)
        nota.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.nota_debito_num = self._campo(nota, "Número de nota de débito", 0)
        self.nota_debito_desc = self._campo(nota, "Descripción", 1)
        self.nota_debito_monto = self._campo(nota, "Monto", 2)
        self.nota_debito_fecha = self._campo(nota, "Fecha (AAAA-MM-DD)", 3)
        self.nota_debito_fecha.insert(0, date.today().isoformat())
        self.boton_registrar_nota_debito = ttk.Button(
            nota, text="Registrar nota de débito", command=self.registrar_nota_debito
        )
        self.boton_registrar_nota_debito.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.nota_debito_monto.bind(
            "<Return>", lambda _evento: self.registrar_nota_debito()
        )

        anular = ttk.LabelFrame(controles, text="Anular nota de débito", padding=14)
        anular.grid(row=1, column=0, sticky="ew")
        self.anular_nota_debito_num = self._campo(anular, "Número de nota de débito", 0)
        self.boton_anular_nota_debito = ttk.Button(
            anular, text="Marcar como anulado", command=self.anular_nota_debito
        )
        self.boton_anular_nota_debito.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )
        self.anular_nota_debito_num.bind(
            "<Return>", lambda _evento: self.anular_nota_debito()
        )

        historial = ttk.LabelFrame(contenedor, text="Notas de débito recientes", padding=10)
        historial.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        historial.rowconfigure(0, weight=1)
        historial.columnconfigure(0, weight=1)
        self.tabla_notas_debito = self._tabla(
            historial, ("Num", "Fecha", "Descripcion", "Monto", "Estado")
        )
        acciones = ttk.Frame(historial)
        acciones.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        acciones.columnconfigure((0, 1), weight=1)
        ttk.Button(
            acciones, text="Editar seleccionado", command=self.editar_nota_debito
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(
            acciones, text="Borrar seleccionado", command=self.eliminar_nota_debito
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.tabla_notas_debito.bind(
            "<Double-1>", lambda _evento: self.editar_nota_debito()
        )

    def _crear_reporte(self):
        acciones = ttk.Frame(self.tab_reporte)
        acciones.pack(fill="x", pady=(0, 12))
        ttk.Label(acciones, text="Mes del corte:").pack(side="left")
        self.reporte_mes = self._selector_mes(acciones)
        self.reporte_mes.pack(side="left", padx=8)
        ttk.Button(
            acciones, text="Ver mes", command=self._cargar_reporte
        ).pack(side="left")

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
        cuerpo.columnconfigure((0, 1, 2), weight=1, uniform="report")
        cuerpo.rowconfigure(0, weight=1)

        cheques = ttk.LabelFrame(cuerpo, text="Cheques del mes", padding=10)
        cheques.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cheques.rowconfigure(0, weight=1)
        cheques.columnconfigure(0, weight=1)
        self.tabla_reporte_cheques = self._tabla(cheques, ("Num", "Fecha", "Nombre", "Monto", "Estado"))

        depositos = ttk.LabelFrame(cuerpo, text="Depósitos del mes", padding=10)
        depositos.grid(row=0, column=1, sticky="nsew", padx=8)
        depositos.rowconfigure(0, weight=1)
        depositos.columnconfigure(0, weight=1)
        self.tabla_reporte_depositos = self._tabla(
            depositos, ("Numero", "Fecha", "Descripcion", "Monto", "Estado")
        )

        notas_debito = ttk.LabelFrame(cuerpo, text="Notas de débito del mes", padding=10)
        notas_debito.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        notas_debito.rowconfigure(0, weight=1)
        notas_debito.columnconfigure(0, weight=1)
        self.tabla_reporte_notas_debito = self._tabla(
            notas_debito, ("Numero", "Fecha", "Descripcion", "Monto", "Estado")
        )

    def _crear_conciliacion(self):
        acciones = ttk.Frame(self.tab_conciliacion)
        acciones.pack(fill="x", pady=(0, 12))
        ttk.Label(acciones, text="Mes del estado:").pack(side="left")
        self.conciliacion_mes = self._selector_mes(acciones)
        self.conciliacion_mes.pack(side="left", padx=(8, 12))
        self.boton_conciliar = ttk.Button(
            acciones,
            text="Seleccionar estado y conciliar",
            command=self.conciliar,
        )
        self.boton_conciliar.pack(side="left")
        self.boton_imprimir_conciliacion = ttk.Button(
            acciones,
            text="Exportar PDF para imprimir",
            command=self.imprimir_conciliacion,
            state="disabled",
        )
        self.boton_imprimir_conciliacion.pack(side="left", padx=(8, 0))

        self.resumen_conciliacion = ttk.Label(
            self.tab_conciliacion,
            text="Seleccione un estado de cuenta para ver la conciliación.",
            anchor="w",
        )
        self.resumen_conciliacion.pack(fill="x", pady=(0, 12))

        panel = ttk.Frame(self.tab_conciliacion)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure((0, 1), weight=1, uniform="conc")
        panel.rowconfigure((0, 1), weight=1, uniform="conc")

        cobrados = ttk.LabelFrame(panel, text="Cheques cobrados", padding=10)
        cobrados.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        cobrados.rowconfigure(0, weight=1)
        cobrados.columnconfigure(0, weight=1)
        self.tabla_cheques_cobrados = self._tabla(
            cobrados, ("Numero", "Monto", "Resultado")
        )

        transito = ttk.LabelFrame(panel, text="Cheques en tránsito", padding=10)
        transito.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        transito.rowconfigure(0, weight=1)
        transito.columnconfigure(0, weight=1)
        self.tabla_cheques_transito = self._tabla(
            transito, ("Numero", "Monto", "Detalle")
        )

        depositos = ttk.LabelFrame(panel, text="Diferencias de depósitos", padding=10)
        depositos.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(6, 0))
        depositos.rowconfigure(0, weight=1)
        depositos.columnconfigure(0, weight=1)
        self.tabla_depositos_no_ingresados = self._tabla(
            depositos, ("Numero", "Fecha", "Descripcion", "Monto", "Diferencia")
        )

        notas = ttk.LabelFrame(panel, text="Diferencias de notas de débito", padding=10)
        notas.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(6, 0))
        notas.rowconfigure(0, weight=1)
        notas.columnconfigure(0, weight=1)
        self.tabla_notas_debito_no_ingresadas = self._tabla(
            notas, ("Numero", "Fecha", "Descripcion", "Monto", "Diferencia")
        )

    def _campo(self, padre, etiqueta, fila):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=5)
        entrada = ttk.Entry(padre)
        entrada.grid(row=fila, column=1, sticky="ew", pady=5)
        padre.columnconfigure(1, weight=1)
        return entrada

    def _selector_mes(self, padre):
        hoy = date.today()
        valores = []
        anio, mes = hoy.year, hoy.month
        for _ in range(60):
            valores.append(f"{anio:04d}-{mes:02d}")
            mes -= 1
            if mes == 0:
                anio -= 1
                mes = 12
        selector = ttk.Combobox(padre, width=9, values=valores)
        selector.current(0)
        return selector

    @staticmethod
    def _fin_de_mes(valor):
        try:
            anio_texto, mes_texto = valor.split("-")
            anio, mes = int(anio_texto), int(mes_texto)
            return f"{anio:04d}-{mes:02d}-{monthrange(anio, mes)[1]:02d}"
        except (AttributeError, TypeError, ValueError) as e:
            raise core.ErrorOperacion(
                "⚠️ Seleccione un mes válido en formato AAAA-MM."
            ) from e

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
        self._orden_descendente_tablas[id(tabla)] = {}
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
        orden_tabla = self._orden_descendente_tablas.setdefault(id(tabla), {})
        descendente = orden_tabla.get(columna, False)

        def clave(fila):
            valor = fila[0].replace(",", "").replace("Q", "").strip()
            try:
                return 0, float(valor)
            except ValueError:
                return 1, valor.casefold()

        filas.sort(key=clave, reverse=descendente)
        for posicion, (_, item) in enumerate(filas):
            tabla.move(item, "", posicion)
        orden_tabla[columna] = not descendente

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
                fecha=self.cheque_fecha.get(),
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
        self.cheque_fecha.delete(0, tk.END)
        self.cheque_fecha.insert(0, date.today().isoformat())
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
                fecha=self.deposito_fecha.get(),
                cuenta_id=self.cuenta_id_actual(),
                numero=self.deposito_num.get(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo registrar", str(e))
            return
        self.deposito_num.delete(0, tk.END)
        self.deposito_desc.delete(0, tk.END)
        self.deposito_monto.delete(0, tk.END)
        self.deposito_fecha.delete(0, tk.END)
        self.deposito_fecha.insert(0, date.today().isoformat())
        self.refrescar_todo()
        messagebox.showinfo("Depósito registrado", resultado["mensaje"])

    def registrar_nota_debito(self):
        return self._ejecutar_bloqueado(
            self.boton_registrar_nota_debito, self._registrar_nota_debito
        )

    def _registrar_nota_debito(self):
        try:
            resultado = service.registrar_nota_debito(
                self.nota_debito_monto.get(),
                self.nota_debito_desc.get(),
                fecha=self.nota_debito_fecha.get(),
                cuenta_id=self.cuenta_id_actual(),
                numero=self.nota_debito_num.get(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo registrar", str(e))
            return
        self.nota_debito_num.delete(0, tk.END)
        self.nota_debito_desc.delete(0, tk.END)
        self.nota_debito_monto.delete(0, tk.END)
        self.nota_debito_fecha.delete(0, tk.END)
        self.nota_debito_fecha.insert(0, date.today().isoformat())
        self.refrescar_todo()
        messagebox.showinfo("Nota de débito registrada", resultado["mensaje"])

    def _movimiento_seleccionado(self, tabla, titulo):
        seleccion = tabla.selection()
        if not seleccion or "vacio" in tabla.item(seleccion[0], "tags"):
            messagebox.showerror(
                titulo,
                "Seleccione un movimiento del historial.",
                parent=self,
            )
            return None
        return seleccion[0]

    def editar_cheque(self):
        item = self._movimiento_seleccionado(
            self.tabla_cheques, "Editar cheque"
        )
        if item is None:
            return
        cheque = self.cheques_por_id[int(item)]
        DialogoMovimiento(
            self,
            "Editar cheque",
            (
                ("numero", "Número de cheque"),
                ("fecha", "Fecha (AAAA-MM-DD)"),
                ("nombre", "Páguese a"),
                ("descripcion", "Descripción"),
                ("monto", "Monto"),
            ),
            cheque,
            lambda valores: self._actualizar_cheque(cheque["id"], valores),
        )

    def _actualizar_cheque(self, cheque_id, valores):
        try:
            resultado = service.actualizar_cheque(
                cheque_id,
                valores["numero"],
                valores["fecha"],
                valores["nombre"],
                valores["monto"],
                valores["descripcion"],
                self.cuenta_id_actual(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo actualizar", str(e))
            return False
        self.refrescar_todo()
        messagebox.showinfo("Cheque actualizado", resultado["mensaje"])
        return True

    def editar_deposito(self):
        item = self._movimiento_seleccionado(
            self.tabla_depositos, "Editar depósito"
        )
        if item is None:
            return
        deposito = self.depositos_por_id[int(item)]
        DialogoMovimiento(
            self,
            "Editar depósito",
            (
                ("numero", "Número de depósito"),
                ("fecha", "Fecha (AAAA-MM-DD)"),
                ("descripcion", "Descripción"),
                ("monto", "Monto"),
            ),
            deposito,
            lambda valores: self._actualizar_deposito(
                deposito["id"], valores
            ),
        )

    def _actualizar_deposito(self, deposito_id, valores):
        try:
            resultado = service.actualizar_deposito(
                deposito_id,
                valores["numero"],
                valores["fecha"],
                valores["descripcion"],
                valores["monto"],
                self.cuenta_id_actual(),
            )
        except Exception as e:
            messagebox.showerror("No se pudo actualizar", str(e))
            return False
        self.refrescar_todo()
        messagebox.showinfo("Depósito actualizado", resultado["mensaje"])
        return True

    def editar_nota_debito(self):
        item = self._movimiento_seleccionado(self.tabla_notas_debito, "Editar nota de débito")
        if item is None:
            return
        nota = self.notas_debito_por_id[int(item)]
        DialogoMovimiento(
            self,
            "Editar nota de débito",
            (("numero", "Número de nota de débito"), ("fecha", "Fecha (AAAA-MM-DD)"), ("descripcion", "Descripción"), ("monto", "Monto")),
            nota,
            lambda valores: self._actualizar_nota_debito(nota["id"], valores),
        )

    def _actualizar_nota_debito(self, nota_id, valores):
        try:
            resultado = service.actualizar_nota_debito(
                nota_id, valores["numero"], valores["fecha"], valores["descripcion"], valores["monto"], self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo actualizar", str(e))
            return False
        self.refrescar_todo()
        messagebox.showinfo("Nota de débito actualizada", resultado["mensaje"])
        return True

    def eliminar_cheque(self):
        item = self._movimiento_seleccionado(
            self.tabla_cheques, "Borrar cheque"
        )
        if item is None:
            return
        cheque = self.cheques_por_id[int(item)]
        confirmar = messagebox.askyesno(
            "Confirmar borrado",
            f"¿Desea borrar permanentemente el cheque {cheque['numero']} "
            f"por Q {cheque['monto']}?\n\nEsta acción no se puede deshacer.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        try:
            resultado = service.eliminar_cheque(
                cheque["id"], self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo borrar", str(e))
            return
        self.refrescar_todo()
        messagebox.showinfo("Cheque eliminado", resultado["mensaje"])

    def eliminar_deposito(self):
        item = self._movimiento_seleccionado(
            self.tabla_depositos, "Borrar depósito"
        )
        if item is None:
            return
        deposito = self.depositos_por_id[int(item)]
        confirmar = messagebox.askyesno(
            "Confirmar borrado",
            f"¿Desea borrar permanentemente el depósito {deposito['numero']} "
            f"por Q {deposito['monto']}?\n\nEsta acción no se puede deshacer.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        try:
            resultado = service.eliminar_deposito(
                deposito["id"], self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo borrar", str(e))
            return
        self.refrescar_todo()
        messagebox.showinfo("Depósito eliminado", resultado["mensaje"])

    def eliminar_nota_debito(self):
        item = self._movimiento_seleccionado(self.tabla_notas_debito, "Borrar nota de débito")
        if item is None:
            return
        nota = self.notas_debito_por_id[int(item)]
        confirmar = messagebox.askyesno(
            "Confirmar borrado",
            f"¿Desea borrar permanentemente la nota de débito {nota['numero']} por Q {nota['monto']}?\n\nEsta acción no se puede deshacer.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        try:
            resultado = service.eliminar_nota_debito(nota["id"], self.cuenta_id_actual())
        except Exception as e:
            messagebox.showerror("No se pudo borrar", str(e))
            return
        self.refrescar_todo()
        messagebox.showinfo("Nota de débito eliminada", resultado["mensaje"])

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

    def anular_deposito(self):
        numero = self.anular_deposito_num.get().strip()
        if not numero:
            messagebox.showerror(
                "No se pudo anular",
                "Ingrese el número de depósito que desea anular.",
                parent=self,
            )
            self.anular_deposito_num.focus_set()
            return
        confirmar = messagebox.askyesno(
            "Confirmar anulación",
            f"¿Desea marcar como anulado el depósito {numero}?\n\n"
            "Esta acción cambia su estado en el registro.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        return self._ejecutar_bloqueado(
            self.boton_anular_deposito, self._anular_deposito
        )

    def _anular_deposito(self):
        try:
            resultado = service.anular_deposito(
                self.anular_deposito_num.get(), self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("No se pudo anular", str(e))
            return
        self.anular_deposito_num.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Depósito anulado", resultado["mensaje"])

    def anular_nota_debito(self):
        numero = self.anular_nota_debito_num.get().strip()
        if not numero:
            messagebox.showerror("No se pudo anular", "Ingrese el número de nota de débito que desea anular.", parent=self)
            self.anular_nota_debito_num.focus_set()
            return
        confirmar = messagebox.askyesno(
            "Confirmar anulación",
            f"¿Desea marcar como anulada la nota de débito {numero}?\n\nEsta acción cambia su estado en el registro.",
            icon="warning",
            parent=self,
        )
        if not confirmar:
            return
        return self._ejecutar_bloqueado(self.boton_anular_nota_debito, self._anular_nota_debito)

    def _anular_nota_debito(self):
        try:
            resultado = service.anular_nota_debito(self.anular_nota_debito_num.get(), self.cuenta_id_actual())
        except Exception as e:
            messagebox.showerror("No se pudo anular", str(e))
            return
        self.anular_nota_debito_num.delete(0, tk.END)
        self.refrescar_todo()
        messagebox.showinfo("Nota de débito anulada", resultado["mensaje"])

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
            filetypes=[
                ("Banco Industrial CSV", "*.csv"),
                ("G&T Continental XLS", "*.xls"),
            ],
        )
        if not archivo:
            return
        return self._ejecutar_bloqueado(
            self.boton_conciliar, lambda: self._conciliar_archivo(archivo)
        )

    def _conciliar_archivo(self, archivo):
        tablas = (
            self.tabla_cheques_cobrados,
            self.tabla_cheques_transito,
            self.tabla_depositos_no_ingresados,
            self.tabla_notas_debito_no_ingresadas,
        )
        for tabla in tablas:
            self._limpiar_tabla(tabla)
        try:
            resultado = service.conciliar(
                self.cuenta_id_actual(),
                archivo,
                self._fin_de_mes(self.conciliacion_mes.get()),
            )
        except Exception as e:
            messagebox.showerror("Conciliación", str(e))
            return
        for fila in resultado["cheques_cobrados"]:
            monto = fila.get("monto_nuestro")
            self.tabla_cheques_cobrados.insert(
                "", tk.END, values=(fila["num"], core.formatear_monto(monto), fila["resultado"])
            )
        for fila in resultado["cheques_transito"]:
            monto = fila.get("monto_nuestro")
            self.tabla_cheques_transito.insert(
                "", tk.END, values=(fila["num"], core.formatear_monto(monto), fila["mensaje"])
            )
        for clave, tabla in (
            ("diferencias_depositos", self.tabla_depositos_no_ingresados),
            ("diferencias_notas_debito", self.tabla_notas_debito_no_ingresadas),
        ):
            for fila in resultado[clave]:
                tabla.insert(
                    "", tk.END,
                    values=(fila["num"], fila["fecha"], fila["descripcion"], core.formatear_monto(fila["monto"]), fila["diferencia"]),
                )

        resumen = resultado["resumen"]
        simbolo = "$" if resultado["estado_cuenta"]["moneda"] == "USD" else "Q"
        etiquetas = (
            ("cheques_cobrados", "Cobrados"),
            ("cheques_transito", "En tránsito"),
            ("diferencias_depositos", "Diferencias de depósitos"),
            ("diferencias_notas_debito", "Diferencias de notas de débito"),
        )
        self.resumen_conciliacion.configure(
            text="   |   ".join(
                f"{titulo}: {resumen[clave]['cantidad']} · {simbolo} {core.formatear_monto(resumen[clave]['total'])}"
                for clave, titulo in etiquetas
            )
        )
        self.resultado_conciliacion = resultado
        self.boton_imprimir_conciliacion.configure(state="normal")
        mensajes_vacios = (
            "No hay cheques cobrados",
            "No hay cheques en tránsito",
            "No hay diferencias de depósitos",
            "No hay diferencias de notas de débito",
        )
        for tabla, mensaje in zip(tablas, mensajes_vacios):
            self._mostrar_estado_vacio(tabla, mensaje)

    def imprimir_conciliacion(self):
        resultado = getattr(self, "resultado_conciliacion", None)
        if not resultado:
            messagebox.showwarning(
                "Imprimir conciliación", "Primero debe generar una conciliación."
            )
            return
        corte = resultado.get("fecha_corte") or "sin_fecha"
        cuenta_id = resultado["cuenta"]["id"]
        archivo = filedialog.asksaveasfilename(
            title="Exportar conciliación",
            defaultextension=".pdf",
            initialfile=f"conciliacion_{cuenta_id}_{corte}.pdf",
            filetypes=[("Documento PDF", "*.pdf")],
        )
        if not archivo:
            return
        try:
            service.exportar_conciliacion(resultado, archivo)
        except Exception as e:
            messagebox.showerror("Imprimir conciliación", str(e))

    def refrescar_todo(self):
        self._cargar_selector_cuentas()
        self._cargar_cheques()
        self._cargar_depositos()
        if hasattr(self, "_cargar_notas_debito"):
            self._cargar_notas_debito()
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
            lambda banco, nombre, numero, formato: self._actualizar_cuenta(
                cuenta_id, banco, nombre, numero, formato
            ),
            cuenta=cuenta,
        )

    def _registrar_cuenta(self, banco, nombre, numero, formato_conciliacion):
        try:
            cuenta_id = service.crear_cuenta(
                banco, nombre, numero, formato_conciliacion
            )
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

    def _actualizar_cuenta(
        self, cuenta_id, banco, nombre, numero, formato_conciliacion
    ):
        try:
            service.actualizar_cuenta(
                cuenta_id, banco, nombre, numero, formato_conciliacion
            )
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
        self.cheques_por_id = {}
        if df.empty:
            self._mostrar_estado_vacio(
                self.tabla_cheques, "No hay cheques registrados"
            )
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            cheque_id = int(fila["Id"])
            self.cheques_por_id[cheque_id] = {
                "id": cheque_id,
                "numero": fila["Num"],
                "fecha": fila["Fecha"],
                "nombre": fila["Nombre"],
                "descripcion": fila["Descripcion"],
                "monto": fila["Monto"],
            }
            self.tabla_cheques.insert(
                "",
                tk.END,
                iid=str(cheque_id),
                values=(fila["Num"], fila["Fecha"], fila["Nombre"], fila["Monto"], fila["Estado"]),
            )
        self._mostrar_estado_vacio(self.tabla_cheques, "No hay cheques registrados")

    def _cargar_depositos(self):
        self._limpiar_tabla(self.tabla_depositos)
        df = service.obtener_depositos(self.cuenta_id_actual())
        self.depositos_por_id = {}
        if df.empty:
            self._mostrar_estado_vacio(
                self.tabla_depositos, "No hay depósitos registrados"
            )
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            deposito_id = int(fila["Id"])
            self.depositos_por_id[deposito_id] = {
                "id": deposito_id,
                "numero": fila["Num"],
                "fecha": fila["Fecha"],
                "descripcion": fila["Descripcion"],
                "monto": fila["Monto"],
            }
            self.tabla_depositos.insert(
                "",
                tk.END,
                iid=str(deposito_id),
                values=(
                    fila["Num"], fila["Fecha"], fila["Descripcion"],
                    fila["Monto"], fila["Estado"],
                ),
            )
        self._mostrar_estado_vacio(
            self.tabla_depositos, "No hay depósitos registrados"
        )

    def _cargar_notas_debito(self):
        self._limpiar_tabla(self.tabla_notas_debito)
        df = service.obtener_notas_debito(self.cuenta_id_actual())
        self.notas_debito_por_id = {}
        if df.empty:
            self._mostrar_estado_vacio(self.tabla_notas_debito, "No hay notas de débito registradas")
            return
        for _, fila in df.tail(30).iloc[::-1].iterrows():
            nota_id = int(fila["Id"])
            self.notas_debito_por_id[nota_id] = {
                "id": nota_id,
                "numero": fila["Num"],
                "fecha": fila["Fecha"],
                "descripcion": fila["Descripcion"],
                "monto": fila["Monto"],
            }
            self.tabla_notas_debito.insert(
                "", tk.END, iid=str(nota_id),
                values=(fila["Num"], fila["Fecha"], fila["Descripcion"], fila["Monto"], fila["Estado"]),
            )
        self._mostrar_estado_vacio(self.tabla_notas_debito, "No hay notas de débito registradas")

    def _cargar_reporte(self):
        try:
            fecha_corte = self._fin_de_mes(self.reporte_mes.get())
            reporte = service.obtener_reporte(
                fecha_corte, self.cuenta_id_actual()
            )
        except Exception as e:
            messagebox.showerror("Corte de caja", str(e))
            return
        self.lbl_ingresos.configure(text=f"Ingresos: Q {core.formatear_monto(reporte['total_depositos'])}")
        self.lbl_egresos.configure(text=f"Egresos: Q {core.formatear_monto(reporte.get('total_egresos', reporte['total_cheques']))}")
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
                values=(
                    fila["Num"], fila["Fecha"], fila["Descripcion"],
                    fila["Monto"], fila["Estado"],
                ),
            )
        self._limpiar_tabla(self.tabla_reporte_notas_debito)
        for _, fila in reporte["notas_debito"].iterrows():
            self.tabla_reporte_notas_debito.insert(
                "", tk.END,
                values=(fila["Num"], fila["Fecha"], fila["Descripcion"], fila["Monto"], fila["Estado"]),
            )

        self._mostrar_estado_vacio(
            self.tabla_reporte_cheques, "No hay cheques en el período"
        )
        self._mostrar_estado_vacio(
            self.tabla_reporte_depositos, "No hay depósitos en el período"
        )
        self._mostrar_estado_vacio(
            self.tabla_reporte_notas_debito, "No hay notas de débito en el período"
        )

    def _limpiar_tabla(self, tabla):
        for item in tabla.get_children():
            tabla.delete(item)

    def _limpiar_conciliacion(self):
        self.resultado_conciliacion = None
        self.boton_imprimir_conciliacion.configure(state="disabled")
        self.resumen_conciliacion.configure(
            text="Seleccione un estado de cuenta para ver la conciliación."
        )
        for tabla in (
            self.tabla_cheques_cobrados,
            self.tabla_cheques_transito,
            self.tabla_depositos_no_ingresados,
            self.tabla_notas_debito_no_ingresadas,
        ):
            self._limpiar_tabla(tabla)
            self._mostrar_estado_vacio(tabla, "Seleccione un estado de cuenta")


class DialogoMovimiento(tk.Toplevel):
    def __init__(self, padre, titulo, campos, valores, al_guardar):
        super().__init__(padre)
        self.al_guardar = al_guardar
        self.title(titulo)
        self.resizable(False, False)
        self.transient(padre)

        contenido = ttk.Frame(self, padding=18)
        contenido.pack(fill="both", expand=True)
        contenido.columnconfigure(1, weight=1)
        self.entradas = {}
        for fila, (campo, etiqueta) in enumerate(campos):
            ttk.Label(contenido, text=etiqueta).grid(
                row=fila, column=0, sticky="w", padx=(0, 12), pady=6
            )
            entrada = ttk.Entry(contenido, width=38)
            entrada.grid(row=fila, column=1, sticky="ew", pady=6)
            entrada.insert(0, valores.get(campo, ""))
            self.entradas[campo] = entrada

        acciones = ttk.Frame(contenido)
        acciones.grid(
            row=len(campos), column=0, columnspan=2, sticky="ew", pady=(16, 0)
        )
        ttk.Button(acciones, text="Cancelar", command=self.destroy).pack(
            side="right"
        )
        self.boton_guardar = ttk.Button(
            acciones, text="Guardar cambios", command=self.guardar
        )
        self.boton_guardar.pack(side="right", padx=8)
        self.bind("<Escape>", lambda _evento: self.destroy())
        self.bind("<Control-s>", lambda _evento: self.guardar())
        self.wait_visibility()
        self.grab_set()
        self.entradas[campos[0][0]].focus_set()

    def guardar(self):
        if str(self.boton_guardar.cget("state")) == "disabled":
            return
        valores = {
            campo: entrada.get().strip()
            for campo, entrada in self.entradas.items()
        }
        self.boton_guardar.configure(state="disabled")
        self.update_idletasks()
        try:
            guardado = self.al_guardar(valores)
        finally:
            if self.winfo_exists():
                self.boton_guardar.configure(state="normal")
        if guardado:
            self.destroy()


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
        ttk.Label(contenido, text="Formato de conciliación").grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=6
        )
        self.formato_conciliacion = ttk.Combobox(
            contenido,
            state="readonly",
            width=34,
            values=core.FORMATOS_CONCILIACION,
        )
        self.formato_conciliacion.grid(row=3, column=1, sticky="ew", pady=6)
        self.formato_conciliacion.current(0)
        if cuenta:
            self.banco.insert(0, cuenta["banco"])
            self.nombre.insert(0, cuenta["nombre"])
            self.numero.insert(0, cuenta["numero"])
            self.formato_conciliacion.set(cuenta["formato_conciliacion"])

        acciones = ttk.Frame(contenido)
        acciones.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(16, 0))
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
            guardada = self.al_guardar(
                banco,
                nombre,
                self.numero.get().strip(),
                self.formato_conciliacion.get(),
            )
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
