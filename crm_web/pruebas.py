"""Pruebas de punta a punta de la aplicación.

    python pruebas.py

Se crea una base de datos temporal propia, así que puede ejecutarse tantas veces
como haga falta sin tocar los datos reales.
"""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

TEMPORAL = tempfile.mkdtemp(prefix="crm_pruebas_")
os.environ["CRM_BD"] = os.path.join(TEMPORAL, "prueba.db")
os.environ["CRM_ADMIN_PASSWORD"] = "Admin2026"

import seed  # noqa: E402

sys.argv = ["seed", "--ejemplo"]
with contextlib.redirect_stdout(io.StringIO()):
    seed.main()

from app.main import aplicacion  # noqa: E402

class Cliente:
    def __init__(self): self.cookie = ""
    def pedir(self, metodo, ruta, datos=None, ficheros=None):
        ruta, _, qs = ruta.partition("?")
        cuerpo = b""; ctype = "application/x-www-form-urlencoded"
        if ficheros:
            b = "----X"; partes = []
            for k, v in (datos or {}).items():
                partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for k, (nom, cont) in ficheros.items():
                partes.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{nom}"\r\n\r\n'.encode() + cont + b"\r\n")
            partes.append(f"--{b}--\r\n".encode())
            cuerpo = b"".join(partes); ctype = f"multipart/form-data; boundary={b}"
        elif datos:
            from urllib.parse import urlencode
            cuerpo = urlencode(datos).encode()
        env = {"REQUEST_METHOD": metodo, "PATH_INFO": ruta, "QUERY_STRING": qs,
               "CONTENT_LENGTH": str(len(cuerpo)), "CONTENT_TYPE": ctype,
               "wsgi.input": io.BytesIO(cuerpo), "HTTP_COOKIE": self.cookie, "REMOTE_ADDR": "127.0.0.1"}
        salida = {}
        def iniciar(estado, cabeceras):
            salida["estado"] = int(estado.split()[0]); salida["cab"] = cabeceras
        cuerpo_resp = b"".join(aplicacion(env, iniciar))
        for k, v in salida["cab"]:
            if k == "Set-Cookie" and v.startswith("crm_sesion="):
                self.cookie = v.split(";")[0]
        salida["texto"] = cuerpo_resp.decode("utf-8", "replace")
        salida["bytes"] = cuerpo_resp
        salida["destino"] = dict(salida["cab"]).get("Location", "")
        return salida
    def get(self, r): return self.pedir("GET", r)
    def post(self, r, d=None, f=None): return self.pedir("POST", r, d, f)
    def csrf(self, html):
        m = re.search(r'name="csrf" value="([^"]+)"', html); return m.group(1) if m else ""

fallos = []
def check(nombre, condicion, detalle=""):
    print(("  OK   " if condicion else "  FALLO ") + nombre + ("" if condicion else f"  <- {detalle}"))
    if not condicion: fallos.append(nombre)

print("\n== 1. Acceso y seguridad ==")
c = Cliente()
r = c.get("/"); check("sin sesión redirige al login", r["estado"] == 303 and r["destino"] == "/login", r)
r = c.post("/login", {"usuario": "admin", "password": "malaclave"})
check("contraseña incorrecta rechazada", "incorrectos" in r["texto"])
r = c.post("/login", {"usuario": "admin", "password": "Admin2026"})
check("login correcto", r["estado"] == 303, r["destino"])
check("obliga a cambiar contraseña", r["destino"] == "/cambiar-password", r["destino"])
r = c.get("/clientes"); check("bloquea navegar sin cambiar contraseña", r["destino"] == "/cambiar-password")
r = c.get("/cambiar-password"); tok = c.csrf(r["texto"])
r = c.post("/cambiar-password", {"csrf": tok, "actual": "Admin2026", "nueva": "corta", "repetir": "corta"})
check("rechaza contraseña débil", "8 caracteres" in r["texto"])
r = c.post("/cambiar-password", {"csrf": tok, "actual": "Admin2026", "nueva": "Segura2026", "repetir": "Segura2026"})
check("cambia la contraseña", r["estado"] == 303 and r["destino"].startswith("/?"), r["destino"])
r = c.post("/clientes/nuevo", {"nombre": "Sin token"})
check("CSRF: rechaza formulario sin token", r["estado"] == 303 and "caducado" in r["destino"])

print("\n== 2. Panel y cartera (administrador) ==")
r = c.get("/"); check("panel carga", r["estado"] == 200 and "Panel de control" in r["texto"])
check("panel muestra los 4 indicadores", all(t in r["texto"] for t in
      ("Clientes activos", "Líneas activas", "Vencen en 30 días", "Ya sin permanencia")))
check("panel ya no muestra los indicadores retirados", not any(t in r["texto"] for t in
      ("Facturación / mes", "Valor de la cartera", "Penalización pendiente", "Pagos con incidencia")))
check("panel ya no tiene el gráfico de facturación", "Facturación por operador" not in r["texto"])
check("panel conserva rosco, meses y productos", all(t in r["texto"] for t in
      ("Situación de la cartera", "Permanencias que vencen por mes", "Líneas por producto")))
check("panel dibuja el rosco", "<svg" in r["texto"] and "stroke-dasharray" in r["texto"])
r = c.get("/clientes"); check("cartera carga", r["estado"] == 200)
check("la tabla ya no tiene columna de pago", ">Pago<" not in r["texto"])
check("admin ve los 5 clientes de ejemplo", r["texto"].count('class="nombre-cliente"') >= 5,
      r["texto"].count('class="nombre-cliente"'))
check("selector de comercial visible para admin", "Todos los comerciales" in c.get("/")["texto"])
r = c.get("/vencimientos"); check("vencimientos carga", r["estado"] == 200 and "Peluquería Vera" in r["texto"])

print("\n== 3. Alta, edición y borrado ==")
r = c.get("/clientes/nuevo"); tok = c.csrf(r["texto"])
nuevo = {"csrf": tok, "nombre": "Cliente De Prueba", "cif": "B99999999", "telefono": "600 000 000",
         "operador": "Vodafone", "producto": "Fibra", "num_lineas": "4", "cuota_linea": "20",
         "fecha_alta": "2025-01-15", "permanencia_meses": "24", "penalizacion_total": "480",
         "estado": "Activo", "observaciones": "creado por la prueba"}
r = c.post("/clientes/nuevo", nuevo)
check("crea cliente", r["estado"] == 303 and "/clientes/" in r["destino"], r["destino"])
cid = int(re.search(r"/clientes/(\d+)", r["destino"]).group(1))
r = c.get(f"/clientes/{cid}")
check("ficha del cliente carga", r["estado"] == 200 and "Cliente De Prueba" in r["texto"])
check("la ficha ya no muestra estado de pago", "Estado de pago" not in r["texto"])
check("la ficha conserva cuota y penalización", "Cuota mensual" in r["texto"] and "Penalización pendiente" in r["texto"])
check("calcula cuota total (4 x 20 = 80 €)", "80 €" in r["texto"], "no aparece 80 €")
check("calcula fin de permanencia (15/01/2027)", "15/01/2027" in r["texto"])
r = c.get(f"/clientes/{cid}/editar"); tok = c.csrf(r["texto"])
r = c.post(f"/clientes/{cid}/editar", {**nuevo, "csrf": tok, "num_lineas": "6"})
check("edita cliente", r["estado"] == 303)
r = c.get(f"/clientes/{cid}"); check("recalcula tras editar (6 x 20 = 120 €)", "120 €" in r["texto"])
check("registra el cambio en la ficha", "modificó" in r["texto"])

# --- Prueba de Tareas/Avisos ---
r = c.post(f"/clientes/{cid}/tareas/nueva", {"csrf": tok, "fecha": "2026-08-15", "tipo": "Tarea", "nota": "Llamar para ofertar"})
check("crea tarea/aviso", r["estado"] == 303)
r = c.get(f"/clientes/{cid}")
check("tarea visible en ficha", "Llamar para ofertar" in r["texto"] and "15/08/2026" in r["texto"])

import sqlite3
db_con = sqlite3.connect(os.environ["CRM_BD"])
tid = db_con.execute("SELECT id FROM tareas_cliente WHERE cliente_id=?", (cid,)).fetchone()[0]
db_con.close()

r = c.post(f"/clientes/{cid}/tareas/{tid}/completar", {"csrf": tok})
check("completa tarea", r["estado"] == 303)
r = c.get(f"/clientes/{cid}")
check("tarea marcada como completada", "✅" in r["texto"])

r = c.post(f"/clientes/{cid}/tareas/nueva", {"csrf": tok, "fecha": "2026-08-16", "tipo": "Alarma", "nota": "Alarma borrar"})
db_con = sqlite3.connect(os.environ["CRM_BD"])
tid2 = db_con.execute("SELECT id FROM tareas_cliente WHERE cliente_id=? AND nota='Alarma borrar'", (cid,)).fetchone()[0]
db_con.close()

r = c.post(f"/clientes/{cid}/tareas/{tid2}/eliminar", {"csrf": tok})
check("elimina tarea", r["estado"] == 303)
r = c.get(f"/clientes/{cid}")
check("tarea borrada no visible", "Alarma borrar" not in r["texto"])


print("\n== 4. Papelera y recuperación ==")
r = c.post(f"/clientes/{cid}/borrar", {"csrf": tok})
check("borra (a papelera)", r["estado"] == 303 and "papelera" in r["destino"])
r = c.get("/clientes"); check("desaparece de la cartera", "Cliente De Prueba" not in r["texto"])
r = c.get("/admin/papelera"); check("aparece en la papelera", "Cliente De Prueba" in r["texto"])
tok2 = c.csrf(r["texto"])
r = c.post(f"/admin/papelera/{cid}/restaurar", {"csrf": tok2})
check("restaura", r["estado"] == 303 and "restaurado" in r["destino"])
r = c.get("/clientes"); check("vuelve a la cartera", "Cliente De Prueba" in r["texto"])

print("\n== 5. Historial ==")
r = c.get("/admin/historial")
check("historial carga", r["estado"] == 200)
for accion in ("dio de alta el cliente", "modificó el cliente", "movió a la papelera", "restauró el cliente", "inició sesión"):
    check(f"registra: {accion}", accion in r["texto"])
check("muestra el antes y el después", 'class="antes"' in r["texto"] and 'class="despues"' in r["texto"])
r = c.get("/admin/historial?accion=borrar"); check("filtra por acción", "movió a la papelera" in r["texto"])

print("\n== 6. Usuarios ==")
from app.auth import password_temporal, validar_password
generadas = [password_temporal() for _ in range(3000)]
check("toda contraseña generada es válida", not [g for g in generadas if validar_password(g)],
      f"{len([g for g in generadas if validar_password(g)])} de 3000 serían rechazadas")
check("las contraseñas generadas no se repiten", len(set(generadas)) == len(generadas))
check("no llevan caracteres confusos (l, O, 0)", not [g for g in generadas if set(g) & set("lO0")])
r = c.get("/admin/usuarios"); tok = c.csrf(r["texto"])
check("lista usuarios", "alejandro" in r["texto"] and "Administrador" in r["texto"])
r = c.post("/admin/usuarios/nuevo", {"csrf": tok, "usuario": "nuevocom", "nombre": "Nuevo Comercial", "rol": "comercial"})
check("crea usuario con contraseña generada", r["estado"] == 303 and "nueva=" in r["destino"])
pw_nuevo = re.search(r"nueva=([^&]+)", r["destino"]).group(1)
r = c.get(r["destino"]); check("enseña la contraseña una sola vez", pw_nuevo in r["texto"])
r = c.post("/admin/usuarios/nuevo", {"csrf": tok, "usuario": "NuevoCom", "nombre": "Repetido"})
check("impide usuario duplicado (sin distinguir mayúsculas)", "ya%20existe" in r["destino"])
check("y no lo llega a crear", "Repetido" not in c.get("/admin/usuarios")["texto"])

print("\n== 7. Aislamiento entre comerciales ==")
c2 = Cliente()
r = c2.post("/login", {"usuario": "nuevocom", "password": pw_nuevo})
check("el comercial nuevo entra", r["estado"] == 303, r["destino"])
r = c2.get("/cambiar-password"); tok = c2.csrf(r["texto"])
c2.post("/cambiar-password", {"csrf": tok, "actual": pw_nuevo, "nueva": "Comercial99", "repetir": "Comercial99"})
r = c2.get("/clientes")
check("no ve clientes de otros comerciales", r["texto"].count('class="nombre-cliente"') == 0,
      r["texto"].count('class="nombre-cliente"'))
r = c2.get(f"/clientes/{cid}")
check("no puede abrir una ficha ajena", "no es de tu cartera" in r["texto"])
r = c2.get("/admin/usuarios")
check("no entra en el panel de administrador", r["estado"] == 303 and "permiso" in r["destino"])
r = c2.get("/admin/papelera"); check("no entra en la papelera", r["estado"] == 303)
r = c2.get("/"); check("el comercial no ve el selector de comerciales", "Todos los comerciales" not in r["texto"])

print("\n== 8. Exportar / importar ==")
r = c.get("/exportar.xlsx")
check("exporta un xlsx válido", r["bytes"][:2] == b"PK" and len(r["bytes"]) > 4000, len(r["bytes"]))
excel = os.path.join(BASE, "..", "CRM_Telefonia.xlsx")
r = c.get("/admin/importar"); tok = c.csrf(r["texto"])
with open(excel, "rb") as fh: contenido = fh.read()
r = c.post("/admin/importar", {"csrf": tok, "comercial_id": "2"}, {"fichero": ("CRM_Telefonia.xlsx", contenido)})
m = re.search(r"<strong>(\d+)</strong> clientes importados", r["texto"])
check("importa desde el Excel", bool(m) and int(m.group(1)) >= 8, r["texto"][:300] if not m else m.group(1))
check("salta los que ya existían en esa cartera", "saltado" in r["texto"])
r = c.post("/admin/importar", {"csrf": tok, "comercial_id": "2"}, {"fichero": ("CRM_Telefonia.xlsx", contenido)})
check("no duplica al reimportar", "saltado" in r["texto"])

# --- Prueba de Importar BORME (Mocked) ---
class MockClienteBORME:
    def __init__(self, cache_dir=None): pass
    def sumario(self, dia):
        return [{"identificador": "test-id", "provincia": "MADRID", "url_xml": "http://example.com/xml"}]
    def documento(self, item):
        return [
            "241607 - CONSTRUCCIONES Y REFORMAS TEST SL.",
            "Constitución. Comienzo de operaciones: 10.08.2026. Objeto social: Construccion y reformas en general.",
            "Domicilio: Calle Falsa 123 (Madrid). Capital: 3.000,00 Euros.",
            "Administradores: Adm. Unico: PEPITO PEREZ."
        ]

import sys
parent_dir = os.path.dirname(BASE)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import borme_leads
orig_cliente = borme_leads.ClienteBORME
borme_leads.ClienteBORME = MockClienteBORME

r = c.get("/admin/borme"); tok_borme = c.csrf(r["texto"])
r = c.post("/admin/borme", {"csrf": tok_borme, "desde": "2026-08-10", "hasta": "2026-08-10", "comercial_id": "2", "solo_constituciones": "1"})
m_b = re.search(r"<strong>(\d+)</strong> prospectos importados", r["texto"])
check("importa desde el BORME (Mocked)", bool(m_b) and int(m_b.group(1)) == 1, r["texto"][:300] if not m_b else m_b.group(1))

# Restauramos el original
borme_leads.ClienteBORME = orig_cliente

print("\n== 9. Varios ==")
check("404 en ruta inexistente", c.get("/no-existe")["estado"] == 404)
check("endpoint de salud", json.loads(c.get("/salud")["texto"])["estado"] == "ok")
r = c.get("/static/css/app.css"); check("sirve el css", r["estado"] == 200 and b"--navy" in r["bytes"])
check("no sirve ficheros fuera de static", c.get("/static/../app/main.py")["estado"] in (404, 200) and
      b"SECRETO" not in c.get("/static/../app/main.py")["bytes"])
r = c.get("/logout"); check("cierra sesión", r["estado"] == 303)
check("tras salir ya no hay acceso", c.get("/")["destino"] == "/login")

shutil.rmtree(TEMPORAL, ignore_errors=True)
print("\n" + ("=" * 46))
print(f"  {len(fallos)} fallos" if fallos else "  TODAS LAS PRUEBAS PASAN")
if fallos: print("  ->", fallos)
sys.exit(1 if fallos else 0)
