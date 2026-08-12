#!/usr/bin/env python3
"""Prepara la base de datos: crea el administrador y, si quieres, datos de ejemplo.

    python seed.py                      -> solo el administrador
    python seed.py --ejemplo            -> administrador + 2 comerciales + clientes de muestra
    python seed.py --excel ruta.xlsx    -> importa los clientes de un Excel
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db  # noqa: E402
from app.auth import crear_usuario, password_temporal  # noqa: E402


def asegurar_usuario(con, usuario, nombre, rol, password):
    fila = con.execute("SELECT id FROM usuarios WHERE usuario=?", (usuario,)).fetchone()
    if fila:
        return fila[0], None
    uid = crear_usuario(con, {"usuario": usuario, "nombre": nombre, "rol": rol}, password)
    return uid, password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejemplo", action="store_true", help="crea comerciales y clientes de muestra")
    parser.add_argument("--excel", help="ruta a un CRM_Telefonia.xlsx para importar")
    args = parser.parse_args()

    db.inicializar()
    con = db.conectar()
    credenciales = []

    pw_admin = os.environ.get("CRM_ADMIN_PASSWORD") or password_temporal()
    admin_id, generada = asegurar_usuario(con, "admin", "Administrador", "admin", pw_admin)
    if generada:
        credenciales.append(("admin", generada))

    if args.ejemplo:
        for usuario, nombre in [("alejandro", "Alejandro Duega"), ("comercial2", "Marta Iglesias")]:
            pw = password_temporal()
            uid, generada = asegurar_usuario(con, usuario, nombre, "comercial", pw)
            if generada:
                credenciales.append((usuario, generada))
            if usuario == "alejandro":
                comercial_id = uid
        hoy = date.today()
        muestras = [
            ("Talleres Ruiz S.L.", "B12345678", "Marcos Ruiz", "611 223 344", "admin@ruiz.es",
             "Movistar", "Fibra + Móvil", 6, 18.50, hoy - timedelta(days=683), 24, 450, "Activo"),
            ("Bar El Rincón", "12345678Z", "Pepe Solís", "633 445 566", "",
             "Orange", "Móvil", 2, 12.90, hoy - timedelta(days=709), 24, 150, "Activo"),
            ("Peluquería Vera", "87654321X", "Vera Gil", "666 778 899", "vera@pelu.es",
             "Yoigo", "Móvil", 2, 11.00, hoy - timedelta(days=390), 12, 90, "Activo"),
            ("Gestoría Navarro", "B34567890", "Ana Navarro", "644 556 677", "gestoria@navarro.es",
             "Movistar", "Centralita", 12, 15.75, hoy - timedelta(days=415), 36, 1200, "Activo"),
            ("Hotel Costa Brava", "B67890123", "Marc Puig", "699 001 122", "recepcion@hcb.es",
             "Vodafone", "Centralita", 18, 14.50, hoy - timedelta(days=252), 36, 1800, "Activo"),
        ]
        campos = list(db.CAMPOS_CLIENTE)
        for m in muestras:
            if con.execute("SELECT 1 FROM clientes WHERE nombre=?", (m[0],)).fetchone():
                continue
            datos = dict(zip(["nombre", "cif", "persona", "telefono", "email", "operador", "producto",
                              "num_lineas", "cuota_linea", "fecha_alta", "permanencia_meses",
                              "penalizacion_total", "estado"], m))
            datos["fecha_alta"] = datos["fecha_alta"].isoformat()
            datos.update(proxima_accion=None, observaciones="", comercial_id=comercial_id)
            con.execute(f"INSERT INTO clientes ({','.join(campos)}, creado_en, creado_por, actualizado_en) "
                        f"VALUES ({','.join('?' * len(campos))},?,?,?)",
                        [datos[c] for c in campos] + [db.ahora(), admin_id, db.ahora()])

    if args.excel:
        from app.main import importar_excel
        with open(args.excel, "rb") as fh:
            insertados, saltados = importar_excel(con, fh.read(), admin_id,
                                                  {"id": admin_id, "nombre": "Administrador"})
        print(f"  Importados {insertados} clientes ({saltados} saltados por duplicado).")

    con.commit()
    con.close()

    print("\n  Base de datos lista:", db.RUTA_BD)
    if credenciales:
        print("\n  CREDENCIALES — apúntalas ahora, no se vuelven a mostrar:")
        for usuario, pw in credenciales:
            print(f"    {usuario:<14} {pw}")
        print("\n  Todas obligan a cambiar la contraseña en el primer acceso.\n")
    else:
        print("  (Los usuarios ya existían, no se ha generado ninguna contraseña nueva.)\n")


if __name__ == "__main__":
    main()
