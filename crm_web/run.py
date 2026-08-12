#!/usr/bin/env python3
"""Arranca la aplicación en local: python run.py  →  http://localhost:8000"""
import os
import shutil
import sys
import webbrowser
from datetime import datetime
from wsgiref.simple_server import make_server, WSGIRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db  # noqa: E402
from app.main import aplicacion  # noqa: E402

COPIAS_A_GUARDAR = 15


class Silencioso(WSGIRequestHandler):
    def log_message(self, formato, *args):
        if args and "GET /static" not in str(args[0]):
            sys.stderr.write("  %s\n" % (formato % args))


def copia_de_seguridad():
    """Guarda una copia de la base de datos cada vez que se arranca."""
    if not os.path.isfile(db.RUTA_BD) or os.path.getsize(db.RUTA_BD) == 0:
        return
    carpeta = os.path.join(os.path.dirname(db.RUTA_BD), "copias")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"crm-{datetime.now():%Y%m%d-%H%M%S}.db")
    shutil.copy2(db.RUTA_BD, destino)
    copias = sorted(f for f in os.listdir(carpeta) if f.endswith(".db"))
    for vieja in copias[:-COPIAS_A_GUARDAR]:
        os.remove(os.path.join(carpeta, vieja))
    print(f"  Copia de seguridad guardada en data/copias/ ({len(copias[-COPIAS_A_GUARDAR:])} disponibles)")


if __name__ == "__main__":
    db.inicializar()

    if not db.hay_usuarios():
        print("\n  No hay ningún usuario en la base de datos.\n")
        print("  Créalos antes de arrancar:\n")
        print("      python seed.py              solo el administrador")
        print("      python seed.py --ejemplo    administrador + datos de muestra\n")
        carpeta = os.path.join(os.path.dirname(db.RUTA_BD), "copias")
        if os.path.isdir(carpeta) and os.listdir(carpeta):
            print("  Tienes copias de seguridad en data/copias/. Para recuperar una,")
            print("  copia el archivo que quieras encima de data/crm.db.\n")
        sys.exit(1)

    copia_de_seguridad()
    puerto = int(os.environ.get("PORT", 8000))
    print(f"\n  CRM Telefonía en marcha  →  http://localhost:{puerto}\n  (Ctrl+C para parar)\n")
    if os.environ.get("CRM_ABRIR", "1") == "1":
        try:
            webbrowser.open(f"http://localhost:{puerto}")
        except Exception:
            pass
    make_server("0.0.0.0", puerto, aplicacion, handler_class=Silencioso).serve_forever()
