"""Autenticación, contraseñas y permisos."""
from __future__ import annotations

import re
import secrets
import string

import bcrypt

from . import db
from .framework import redirect


def cifrar(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode()


def comprobar(password: str, hash_guardado: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_guardado.encode())
    except Exception:
        return False


def password_temporal(longitud: int = 10) -> str:
    """Contraseña temporal legible: sin caracteres que se confundan (l, O, 0)
    y con al menos dos letras y dos números garantizados, para que siempre
    supere validar_password()."""
    letras = string.ascii_letters.replace("l", "").replace("O", "")
    digitos = string.digits.replace("0", "")
    caracteres = [secrets.choice(letras), secrets.choice(letras),
                  secrets.choice(digitos), secrets.choice(digitos)]
    alfabeto = letras + digitos
    caracteres += [secrets.choice(alfabeto) for _ in range(max(0, longitud - 4))]
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)


def validar_password(password: str) -> str | None:
    """Devuelve el mensaje de error, o None si es válida."""
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "La contraseña debe combinar letras y números."
    return None


def usuario_por_credenciales(con, usuario: str, password: str):
    fila = con.execute(
        "SELECT * FROM usuarios WHERE usuario = ? COLLATE NOCASE", (usuario.strip(),)
    ).fetchone()
    if not fila or not fila["activo"]:
        return None
    if not comprobar(password, fila["password_hash"]):
        return None
    return dict(fila)


def usuario_actual(con, sesion: dict):
    uid = sesion.get("uid")
    if not uid:
        return None
    fila = con.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)).fetchone()
    return dict(fila) if fila else None


# --------------------------------------------------------------- decoradores
def requiere_login(funcion):
    def envoltorio(peticion, **kwargs):
        if not peticion.usuario:
            return redirect("/login")
        if peticion.usuario["cambiar_password"] and peticion.path != "/cambiar-password":
            return redirect("/cambiar-password")
        return funcion(peticion, **kwargs)
    envoltorio.__name__ = funcion.__name__
    return envoltorio


def requiere_admin(funcion):
    def envoltorio(peticion, **kwargs):
        if not peticion.usuario:
            return redirect("/login")
        if peticion.usuario["rol"] != "admin":
            return redirect("/", "No tienes permiso para entrar ahí.", "error")
        return funcion(peticion, **kwargs)
    envoltorio.__name__ = funcion.__name__
    return envoltorio


def puede_ver_cliente(usuario, cliente) -> bool:
    return usuario["rol"] == "admin" or cliente["comercial_id"] == usuario["id"]


def crear_usuario(con, datos: dict, password: str, autor=None, ip="-"):
    con.execute(
        """INSERT INTO usuarios (usuario, nombre, email, rol, password_hash, activo,
                                 cambiar_password, creado_en)
           VALUES (?,?,?,?,?,?,1,?)""",
        (datos["usuario"].strip(), datos["nombre"].strip(), datos.get("email", "").strip(),
         datos.get("rol", "comercial"), cifrar(password), 1 if datos.get("activo", 1) else 0,
         db.ahora()),
    )
    nuevo_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.registrar(con, autor, "crear_usuario", "usuario", nuevo_id, datos["nombre"],
                 {"usuario": datos["usuario"], "rol": datos.get("rol", "comercial")}, ip)
    return nuevo_id
