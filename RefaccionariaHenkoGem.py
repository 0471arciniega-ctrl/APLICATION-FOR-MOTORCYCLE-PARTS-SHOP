#!/usr/bin/env python3
"""
Sistema de inventario y ventas para refaccionaria — versión con interfaz gráfica.
Usa Tkinter (incluido en Python) y SQLite para guardar los datos en
refaccionaria.db, en la misma carpeta donde ejecutes este script.

Uso:
    python3 refaccionaria_gui.py

Si en Linux te da error de que falta tkinter, instalá:
    sudo apt install python3-tk
"""

from enum import auto
from gettext import install
import sqlite3
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
from pathlib import Path

import pip

DB_PATH = Path(__file__).parent / "refaccionaria.db"

ZONAS = {
    "MO": "Mostrador / Más vendidos",
    "EL": "Eléctrico y Tornillería",
    "FF": "Filtros, Fluidos y Consumibles",
    "HE": "Herramientas",
    "DP": "Depósito / Gabinete de Inflamables",
}

BG = "#18181b"
SURFACE = "#27272a"
TEXT = "#f4f4f5"
MUTED = "#a1a1aa"
ACCENT = "#fbbf24"
DANGER = "#f87171"
DANGER_BG = "#3f1d1d"


def money(n):
    return f"${n:,.2f}"


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def conectar():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def inicializar_db():
    con = conectar()
    con.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            zona TEXT NOT NULL,
            cant INTEGER NOT NULL DEFAULT 0,
            cant_min INTEGER NOT NULL DEFAULT 0,
            precio REAL NOT NULL DEFAULT 0,
            notas TEXT DEFAULT ''
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            total REAL NOT NULL,
            fecha TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def siguiente_codigo(con, zona):
    n = con.execute("SELECT COUNT(*) FROM items WHERE zona = ?", (zona,)).fetchone()[0]
    return f"{zona}-{n + 1:03d}"


# ---------------------------------------------------------------------------
# Diálogo: agregar / editar artículo
# ---------------------------------------------------------------------------

class DialogoItem(tk.Toplevel):
    def __init__(self, master, con, on_guardado, item=None):
        super().__init__(master)
        self.con = con
        self.on_guardado = on_guardado
        self.item = item
        self.title("Editar artículo" if item else "Nuevo artículo")
        self.configure(bg=SURFACE, padx=16, pady=16)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        campos = [
            ("Nombre", "nombre", item["nombre"] if item else ""),
            ("Cantidad", "cant", str(item["cant"]) if item else "0"),
            ("Mínimo para alerta", "cant_min", str(item["cant_min"]) if item else "0"),
            ("Precio de venta", "precio", str(item["precio"]) if item else "0"),
            ("Notas (opcional)", "notas", item["notas"] if item else ""),
        ]
        self.vars = {}
        row = 0
        for etiqueta, clave, valor in campos:
            tk.Label(self, text=etiqueta, bg=SURFACE, fg=MUTED, anchor="w").grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
            row += 1
            var = tk.StringVar(value=valor)
            entry = tk.Entry(self, textvariable=var, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", width=32)
            entry.grid(row=row, column=0, columnspan=2, sticky="ew", ipady=4)
            self.vars[clave] = var
            row += 1

        tk.Label(self, text="Zona", bg=SURFACE, fg=MUTED, anchor="w").grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
        row += 1
        self.zona_var = tk.StringVar(value=item["zona"] if item else "MO")
        combo = ttk.Combobox(self, textvariable=self.zona_var, state="readonly",
                              values=[f"{k} · {v}" for k, v in ZONAS.items()])
        for k, v in ZONAS.items():
            if item and item["zona"] == k:
                combo.set(f"{k} · {v}")
        combo.grid(row=row, column=0, columnspan=2, sticky="ew")
        self.combo_zona = combo
        row += 1

        btn = tk.Button(self, text="Guardar cambios" if item else "Agregar al inventario",
                         bg=ACCENT, fg="#1c1917", relief="flat", command=self.guardar, pady=6)
        btn.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def guardar(self):
        nombre = self.vars["nombre"].get().strip()
        if not nombre:
            messagebox.showwarning("Falta el nombre", "Ingresá un nombre para el artículo.")
            return
        try:
            cant = int(self.vars["cant"].get())
            cant_min = int(self.vars["cant_min"].get())
            precio = float(self.vars["precio"].get())
        except ValueError:
            messagebox.showwarning("Datos inválidos", "Cantidad, mínimo y precio deben ser números.")
            return
        notas = self.vars["notas"].get().strip()
        zona = self.combo_zona.get().split(" · ")[0] if self.combo_zona.get() else self.zona_var.get()

        if self.item:
            self.con.execute(
                "UPDATE items SET nombre=?, zona=?, cant=?, cant_min=?, precio=?, notas=? WHERE id=?",
                (nombre, zona, cant, cant_min, precio, notas, self.item["id"]),
            )
        else:
            codigo = siguiente_codigo(self.con, zona)
            self.con.execute(
                "INSERT INTO items (id, codigo, nombre, zona, cant, cant_min, precio, notas) VALUES (?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), codigo, nombre, zona, cant, cant_min, precio, notas),
            )
        self.con.commit()
        self.on_guardado()
        self.destroy()


# ---------------------------------------------------------------------------
# Diálogo: registrar venta
# ---------------------------------------------------------------------------

class DialogoVenta(tk.Toplevel):
    def __init__(self, master, con, on_guardado):
        super().__init__(master)
        self.con = con
        self.on_guardado = on_guardado
        self.item_sel = None
        self.title("Registrar venta")
        self.configure(bg=SURFACE, padx=16, pady=16)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        tk.Label(self, text="Buscar artículo", bg=SURFACE, fg=MUTED, anchor="w").grid(row=0, column=0, sticky="w")
        self.buscar_var = tk.StringVar()
        self.buscar_var.trace_add("write", lambda *a: self.buscar())
        tk.Entry(self, textvariable=self.buscar_var, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", width=36) \
            .grid(row=1, column=0, columnspan=2, sticky="ew", ipady=4)

        self.lista = tk.Listbox(self, bg=BG, fg=TEXT, height=5, relief="flat", selectbackground=ACCENT, selectforeground="#1c1917")
        self.lista.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        self.lista.bind("<<ListboxSelect>>", self.seleccionar)
        self.resultados = []

        self.lbl_sel = tk.Label(self, text="Ningún artículo seleccionado", bg=SURFACE, fg=ACCENT, anchor="w")
        self.lbl_sel.grid(row=3, column=0, columnspan=2, sticky="w")

        tk.Label(self, text="Cantidad", bg=SURFACE, fg=MUTED, anchor="w").grid(row=4, column=0, sticky="w", pady=(8, 0))
        tk.Label(self, text="Precio unitario", bg=SURFACE, fg=MUTED, anchor="w").grid(row=4, column=1, sticky="w", pady=(8, 0))
        self.cant_var = tk.StringVar(value="1")
        self.precio_var = tk.StringVar(value="0")
        tk.Entry(self, textvariable=self.cant_var, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat") \
            .grid(row=5, column=0, sticky="ew", ipady=4, padx=(0, 4))
        tk.Entry(self, textvariable=self.precio_var, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat") \
            .grid(row=5, column=1, sticky="ew", ipady=4, padx=(4, 0))

        self.lbl_total = tk.Label(self, text="Total: $0.00", bg=SURFACE, fg=TEXT, anchor="w")
        self.lbl_total.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.cant_var.trace_add("write", lambda *a: self.actualizar_total())
        self.precio_var.trace_add("write", lambda *a: self.actualizar_total())

        tk.Button(self, text="Registrar venta", bg=ACCENT, fg="#1c1917", relief="flat",
                  command=self.guardar, pady=6).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))

    def buscar(self):
        q = self.buscar_var.get().strip()
        self.lista.delete(0, tk.END)
        if not q:
            self.resultados = []
            return
        self.resultados = self.con.execute(
            "SELECT * FROM items WHERE nombre LIKE ? OR codigo LIKE ? ORDER BY codigo",
            (f"%{q}%", f"%{q}%"),
        ).fetchall()
        for r in self.resultados:
            self.lista.insert(tk.END, f"{r['codigo']} · {r['nombre']} (stock {r['cant']})")

    def seleccionar(self, event):
        sel = self.lista.curselection()
        if not sel:
            return
        self.item_sel = self.resultados[sel[0]]
        self.lbl_sel.config(text=f"Seleccionado: {self.item_sel['codigo']} · {self.item_sel['nombre']}")
        self.precio_var.set(str(self.item_sel["precio"]))

    def actualizar_total(self):
        try:
            total = float(self.cant_var.get()) * float(self.precio_var.get())
            self.lbl_total.config(text=f"Total: {money(total)}")
        except ValueError:
            self.lbl_total.config(text="Total: —")

    def guardar(self):
        if not self.item_sel:
            messagebox.showwarning("Falta el artículo", "Buscá y seleccioná un artículo de la lista.")
            return
        try:
            cantidad = int(self.cant_var.get())
            precio = float(self.precio_var.get())
        except ValueError:
            messagebox.showwarning("Datos inválidos", "Cantidad y precio deben ser números.")
            return
        total = cantidad * precio
        self.con.execute(
            "INSERT INTO ventas (id, item_id, codigo, nombre, cantidad, precio_unitario, total, fecha) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), self.item_sel["id"], self.item_sel["codigo"], self.item_sel["nombre"],
             cantidad, precio, total, datetime.now().isoformat()),
        )
        nueva_cant = max(0, self.item_sel["cant"] - cantidad)
        self.con.execute("UPDATE items SET cant=? WHERE id=?", (nueva_cant, self.item_sel["id"]))
        self.con.commit()
        self.on_guardado()
        self.destroy()


# ---------------------------------------------------------------------------
# App principal
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Refaccionaria")
        self.geometry("820x560")
        self.configure(bg=BG)
        self.con = conectar()

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                         rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED, relief="flat")
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#1c1917")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        notebook.bind("<<NotebookTabChanged>>", lambda e: self.refrescar_todo())

        self.tab_inv = tk.Frame(notebook, bg=BG)
        self.tab_ventas = tk.Frame(notebook, bg=BG)
        self.tab_resumen = tk.Frame(notebook, bg=BG)
        notebook.add(self.tab_inv, text="Inventario")
        notebook.add(self.tab_ventas, text="Ventas")
        notebook.add(self.tab_resumen, text="Resumen")

        self.construir_tab_inventario()
        self.construir_tab_ventas()
        self.construir_tab_resumen()
        self.refrescar_todo()

    # ---------------- Inventario ----------------

    def construir_tab_inventario(self):
        top = tk.Frame(self.tab_inv, bg=BG, pady=8, padx=8)
        top.pack(fill="x")

        self.busqueda_var = tk.StringVar()
        self.busqueda_var.trace_add("write", lambda *a: self.refrescar_inventario())
        tk.Entry(top, textvariable=self.busqueda_var, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                 relief="flat", width=30).pack(side="left", ipady=4)
        tk.Label(top, text="  Buscar por nombre o código", bg=BG, fg=MUTED).pack(side="left")

        tk.Button(top, text="+ Artículo", bg=ACCENT, fg="#1c1917", relief="flat",
                  command=self.abrir_agregar_item).pack(side="right")
        tk.Button(top, text="Eliminar", bg=SURFACE, fg=DANGER, relief="flat",
                  command=self.eliminar_item_seleccionado).pack(side="right", padx=6)
        tk.Button(top, text="Editar", bg=SURFACE, fg=ACCENT, relief="flat",
                  command=self.editar_item_seleccionado).pack(side="right")

        cols = ("codigo", "nombre", "zona", "cant", "min", "precio")
        self.tree_inv = ttk.Treeview(self.tab_inv, columns=cols, show="headings", selectmode="browse")
        encabezados = {"codigo": "Código", "nombre": "Nombre", "zona": "Zona", "cant": "Cant.", "min": "Mín.", "precio": "Precio"}
        anchos = {"codigo": 80, "nombre": 260, "zona": 160, "cant": 60, "min": 60, "precio": 90}
        for c in cols:
            self.tree_inv.heading(c, text=encabezados[c])
            self.tree_inv.column(c, width=anchos[c], anchor="w")
        self.tree_inv.tag_configure("bajo", background=DANGER_BG, foreground=DANGER)
        self.tree_inv.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.lbl_alerta_inv = tk.Label(self.tab_inv, text="", bg=BG, fg=DANGER, anchor="w")
        self.lbl_alerta_inv.pack(fill="x", padx=8, pady=(0, 8))

    def refrescar_inventario(self):
        q = self.busqueda_var.get().strip()
        for row in self.tree_inv.get_children():
            self.tree_inv.delete(row)
        if q:
            filas = self.con.execute(
                "SELECT * FROM items WHERE nombre LIKE ? OR codigo LIKE ? ORDER BY zona, codigo",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            filas = self.con.execute("SELECT * FROM items ORDER BY zona, codigo").fetchall()

        for f in filas:
            tags = ("bajo",) if f["cant"] <= f["cant_min"] else ()
            self.tree_inv.insert("", "end", iid=f["id"], values=(
                f["codigo"], f["nombre"], ZONAS.get(f["zona"], f["zona"]),
                f["cant"], f["cant_min"], money(f["precio"]),
            ), tags=tags)

        total_bajo = self.con.execute("SELECT COUNT(*) FROM items WHERE cant <= cant_min").fetchone()[0]
        self.lbl_alerta_inv.config(
            text=f"⚠ {total_bajo} artículo(s) para reponer" if total_bajo else "Todo el stock por encima del mínimo."
        )

    def abrir_agregar_item(self):
        DialogoItem(self, self.con, self.refrescar_todo)

    def _item_seleccionado(self):
        sel = self.tree_inv.selection()
        if not sel:
            messagebox.showinfo("Nada seleccionado", "Elegí un artículo de la lista primero.")
            return None
        return self.con.execute("SELECT * FROM items WHERE id=?", (sel[0],)).fetchone()

    def editar_item_seleccionado(self):
        item = self._item_seleccionado()
        if item:
            DialogoItem(self, self.con, self.refrescar_todo, item=item)

    def eliminar_item_seleccionado(self):
        item = self._item_seleccionado()
        if not item:
            return
        if messagebox.askyesno("Confirmar", f"¿Borrar {item['codigo']} · {item['nombre']}?"):
            self.con.execute("DELETE FROM items WHERE id=?", (item["id"],))
            self.con.commit()
            self.refrescar_todo()

    # ---------------- Ventas ----------------

    def construir_tab_ventas(self):
        top = tk.Frame(self.tab_ventas, bg=BG, pady=8, padx=8)
        top.pack(fill="x")
        self.lbl_ventas_hoy = tk.Label(top, text="", bg=BG, fg=ACCENT, font=("TkDefaultFont", 11, "bold"))
        self.lbl_ventas_hoy.pack(side="left")
        tk.Button(top, text="+ Venta", bg=ACCENT, fg="#1c1917", relief="flat",
                  command=self.abrir_registrar_venta).pack(side="right")

        cols = ("fecha", "codigo", "nombre", "cant", "precio", "total")
        self.tree_ventas = ttk.Treeview(self.tab_ventas, columns=cols, show="headings")
        encabezados = {"fecha": "Fecha", "codigo": "Código", "nombre": "Nombre", "cant": "Cant.", "precio": "Precio unit.", "total": "Total"}
        anchos = {"fecha": 90, "codigo": 80, "nombre": 240, "cant": 60, "precio": 100, "total": 100}
        for c in cols:
            self.tree_ventas.heading(c, text=encabezados[c])
            self.tree_ventas.column(c, width=anchos[c], anchor="w")
        self.tree_ventas.pack(fill="both", expand=True, padx=8, pady=8)

    def refrescar_ventas(self):
        for row in self.tree_ventas.get_children():
            self.tree_ventas.delete(row)
        filas = self.con.execute("SELECT * FROM ventas ORDER BY fecha DESC LIMIT 100").fetchall()
        for f in filas:
            self.tree_ventas.insert("", "end", values=(
                f["fecha"][:10], f["codigo"], f["nombre"], f["cantidad"], money(f["precio_unitario"]), money(f["total"]),
            ))

        hoy = date.today().isoformat()
        n_hoy = self.con.execute("SELECT COUNT(*) FROM ventas WHERE fecha LIKE ?", (f"{hoy}%",)).fetchone()[0]
        ingresos_hoy = self.con.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha LIKE ?", (f"{hoy}%",)).fetchone()[0]
        self.lbl_ventas_hoy.config(text=f"Hoy: {n_hoy} venta(s) · {money(ingresos_hoy)}")

    def abrir_registrar_venta(self):
        DialogoVenta(self, self.con, self.refrescar_todo)

    # ---------------- Resumen ----------------

    def construir_tab_resumen(self):
        frame = tk.Frame(self.tab_resumen, bg=BG, padx=8, pady=8)
        frame.pack(fill="both", expand=True)

        cards = tk.Frame(frame, bg=BG)
        cards.pack(fill="x", pady=(0, 12))
        self.lbl_ingresos_totales = self._crear_card(cards, "Ingresos totales")
        self.lbl_valor_inv = self._crear_card(cards, "Valor del inventario")

        tk.Label(frame, text="⚠ Para reponer", bg=BG, fg=DANGER, anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x")
        self.lista_bajo = tk.Listbox(frame, bg=SURFACE, fg=DANGER, relief="flat", height=6)
        self.lista_bajo.pack(fill="x", pady=(4, 12))

        tk.Label(frame, text="📈 Más vendidos", bg=BG, fg=ACCENT, anchor="w", font=("TkDefaultFont", 10, "bold")).pack(fill="x")
        self.lista_top = tk.Listbox(frame, bg=SURFACE, fg=TEXT, relief="flat", height=6)
        self.lista_top.pack(fill="x", pady=(4, 0))

    def _crear_card(self, parent, titulo):
        card = tk.Frame(parent, bg=SURFACE, padx=14, pady=10)
        card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(card, text=titulo, bg=SURFACE, fg=MUTED, anchor="w").pack(fill="x")
        valor = tk.Label(card, text="$0.00", bg=SURFACE, fg=ACCENT, font=("TkDefaultFont", 16, "bold"), anchor="w")
        valor.pack(fill="x")
        return valor

    def refrescar_resumen(self):
        ingresos_totales = self.con.execute("SELECT COALESCE(SUM(total),0) FROM ventas").fetchone()[0]
        valor_inv = self.con.execute("SELECT COALESCE(SUM(cant*precio),0) FROM items").fetchone()[0]
        self.lbl_ingresos_totales.config(text=money(ingresos_totales))
        self.lbl_valor_inv.config(text=money(valor_inv))

        self.lista_bajo.delete(0, tk.END)
        stock_bajo = self.con.execute("SELECT * FROM items WHERE cant <= cant_min ORDER BY codigo").fetchall()
        if not stock_bajo:
            self.lista_bajo.insert(tk.END, "Todo en orden — nada por debajo del mínimo.")
        for f in stock_bajo:
            self.lista_bajo.insert(tk.END, f"{f['codigo']} · {f['nombre']} — stock {f['cant']} / mín {f['cant_min']}")

        self.lista_top.delete(0, tk.END)
        ranking = self.con.execute("""
            SELECT codigo, nombre, SUM(cantidad) AS total_cant, SUM(total) AS total_ingreso
            FROM ventas GROUP BY item_id ORDER BY total_cant DESC LIMIT 5
        """).fetchall()
        if not ranking:
            self.lista_top.insert(tk.END, "Todavía no hay ventas registradas.")
        for f in ranking:
            self.lista_top.insert(tk.END, f"{f['codigo']} · {f['nombre']} — {f['total_cant']} un. · {money(f['total_ingreso'])}")

    # ---------------- General ----------------

    def refrescar_todo(self):
        self.refrescar_inventario()
        self.refrescar_ventas()
        self.refrescar_resumen()


if __name__ == "__main__":
    inicializar_db()
    app = App()
    app.mainloop()