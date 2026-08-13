"""Acceso a la base de datos (SQLite) y registro de auditoría."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

RUTA_BD = os.environ.get(
    "CRM_BD",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "crm.db"),
)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario         TEXT UNIQUE NOT NULL,
    nombre          TEXT NOT NULL,
    email           TEXT,
    rol             TEXT NOT NULL DEFAULT 'comercial',
    password_hash   TEXT NOT NULL,
    activo          INTEGER NOT NULL DEFAULT 1,
    cambiar_password INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL,
    ultimo_acceso   TEXT
);

CREATE TABLE IF NOT EXISTS clientes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    comercial_id        INTEGER NOT NULL REFERENCES usuarios(id),
    nombre              TEXT NOT NULL,
    cif                 TEXT,
    persona             TEXT,
    telefono            TEXT,
    email               TEXT,
    operador            TEXT,
    producto            TEXT,
    num_lineas          INTEGER DEFAULT 0,
    cuota_linea         REAL DEFAULT 0,
    fecha_alta          TEXT,
    permanencia_meses   INTEGER DEFAULT 0,
    penalizacion_total  REAL DEFAULT 0,
    estado              TEXT DEFAULT 'Activo',
    estado_pago         TEXT DEFAULT 'Pagado',
    proxima_accion      TEXT,
    observaciones       TEXT,
    borrado             INTEGER NOT NULL DEFAULT 0,
    borrado_en          TEXT,
    borrado_por         INTEGER,
    creado_en           TEXT NOT NULL,
    creado_por          INTEGER,
    actualizado_en      TEXT
);
CREATE INDEX IF NOT EXISTS idx_clientes_comercial ON clientes(comercial_id, borrado);

CREATE TABLE IF NOT EXISTS auditoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    momento         TEXT NOT NULL,
    usuario_id      INTEGER,
    usuario_nombre  TEXT,
    accion          TEXT NOT NULL,
    entidad         TEXT,
    entidad_id      INTEGER,
    entidad_nombre  TEXT,
    cambios         TEXT,
    ip              TEXT
);
CREATE INDEX IF NOT EXISTS idx_auditoria_momento ON auditoria(momento DESC);
CREATE INDEX IF NOT EXISTS idx_auditoria_entidad ON auditoria(entidad, entidad_id);

CREATE TABLE IF NOT EXISTS ajustes (
    clave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tareas_cliente (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id   INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    fecha        TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    nota         TEXT NOT NULL,
    completada   INTEGER DEFAULT 0,
    creado_en    TEXT NOT NULL,
    creado_por   INTEGER REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS idx_tareas_cliente ON tareas_cliente(cliente_id);
"""

AJUSTES_POR_DEFECTO = {
    "aviso_rojo": "30",
    "aviso_naranja": "60",
    "aviso_amarillo": "90",
    "nombre_empresa": "Mi empresa de telefonía",
}

CAMPOS_CLIENTE = [
    "nombre", "cif", "persona", "telefono", "email", "operador", "producto",
    "num_lineas", "cuota_linea", "fecha_alta", "permanencia_meses",
    "penalizacion_total", "estado", "proxima_accion",
    "observaciones", "comercial_id",
]

ETIQUETAS = {
    "nombre": "Cliente", "cif": "CIF/NIF", "persona": "Persona de contacto",
    "telefono": "Teléfono", "email": "Email", "operador": "Operador",
    "producto": "Producto", "num_lineas": "Nº de líneas", "cuota_linea": "Cuota por línea",
    "fecha_alta": "Fecha de alta", "permanencia_meses": "Permanencia (meses)",
    "penalizacion_total": "Penalización total", "estado": "Estado",
    "proxima_accion": "Próxima acción",
    "observaciones": "Observaciones", "comercial_id": "Comercial asignado",
}


def conectar():
    """Abre la base de datos y se asegura de que el esquema existe.

    La comprobación es barata y evita que la aplicación se caiga si el archivo
    de base de datos desaparece o se mueve con el servidor en marcha.
    """
    os.makedirs(os.path.dirname(RUTA_BD), exist_ok=True)
    con = sqlite3.connect(RUTA_BD)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='usuarios'").fetchone()
    if not existe:
        _crear_esquema(con)
    else:
        # En caso de actualización, nos aseguramos de que existe la tabla de tareas
        existe_tareas = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tareas_cliente'").fetchone()
        if not existe_tareas:
            con.executescript(ESQUEMA)
            con.commit()
    return con


def _crear_esquema(con):
    con.executescript(ESQUEMA)
    for clave, valor in AJUSTES_POR_DEFECTO.items():
        con.execute("INSERT OR IGNORE INTO ajustes (clave, valor) VALUES (?,?)", (clave, valor))
    con.commit()


def inicializar():
    con = conectar()
    _crear_esquema(con)
    con.close()


def hay_usuarios():
    con = conectar()
    n = con.execute("SELECT COUNT(*) FROM usuarios WHERE activo=1").fetchone()[0]
    con.close()
    return n > 0


def ahora():
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------- ajustes
def leer_ajustes(con):
    return {f["clave"]: f["valor"] for f in con.execute("SELECT clave, valor FROM ajustes")}


def umbrales(con):
    a = leer_ajustes(con)
    return (int(a.get("aviso_rojo", 30)), int(a.get("aviso_naranja", 60)), int(a.get("aviso_amarillo", 90)))


# ----------------------------------------------------------------- auditoría
def registrar(con, usuario, accion, entidad=None, entidad_id=None, entidad_nombre=None,
              cambios=None, ip="-"):
    con.execute(
        """INSERT INTO auditoria (momento, usuario_id, usuario_nombre, accion, entidad,
                                  entidad_id, entidad_nombre, cambios, ip)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (ahora(),
         usuario["id"] if usuario else None,
         usuario["nombre"] if usuario else "sistema",
         accion, entidad, entidad_id, entidad_nombre,
         json.dumps(cambios, ensure_ascii=False, default=str) if cambios else None,
         ip),
    )


def diferencias(antes: dict | None, despues: dict | None, campos=None):
    """Devuelve solo los campos que han cambiado, con su valor anterior y nuevo."""
    campos = campos or CAMPOS_CLIENTE
    cambios = {}
    for campo in campos:
        v1 = (antes or {}).get(campo)
        v2 = (despues or {}).get(campo)
        if str(v1 or "") != str(v2 or ""):
            cambios[campo] = {"antes": v1, "despues": v2}
    return cambios
