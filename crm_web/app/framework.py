"""Mini framework WSGI sin dependencias externas.

Contiene lo justo para esta aplicación: enrutado, peticiones, respuestas,
sesiones firmadas con cookie y protección CSRF.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import time
import urllib.parse
from http.cookies import SimpleCookie

STATUS = {
    200: "200 OK", 302: "302 Found", 303: "303 See Other", 400: "400 Bad Request",
    401: "401 Unauthorized", 403: "403 Forbidden", 404: "404 Not Found",
    405: "405 Method Not Allowed", 500: "500 Internal Server Error",
}


# --------------------------------------------------------------------- sesión
class SessionCookie:
    """Cookie firmada con HMAC. El contenido es legible pero no manipulable."""

    def __init__(self, secret: str, name: str = "crm_sesion", max_age: int = 60 * 60 * 12):
        self.secret = secret.encode()
        self.name = name
        self.max_age = max_age

    def dump(self, data: dict) -> str:
        raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        firma = hmac.new(self.secret, raw.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{raw}.{firma}"

    def load(self, valor: str | None) -> dict:
        if not valor or "." not in valor:
            return {}
        raw, firma = valor.rsplit(".", 1)
        esperada = hmac.new(self.secret, raw.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(firma, esperada):
            return {}
        try:
            data = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        except Exception:
            return {}
        if data.get("_exp", 0) < time.time():
            return {}
        return data


# ------------------------------------------------------------------- petición
def _parse_multipart(body: bytes, boundary: bytes):
    """Devuelve (campos, ficheros). Suficiente para subir un xlsx."""
    campos, ficheros = {}, {}
    sep = b"--" + boundary
    for parte in body.split(sep):
        parte = parte.strip(b"\r\n")
        if not parte or parte == b"--":
            continue
        if b"\r\n\r\n" not in parte:
            continue
        cabecera, contenido = parte.split(b"\r\n\r\n", 1)
        contenido = contenido.rstrip(b"\r\n")
        cab = cabecera.decode("utf-8", "replace")
        nombre = re.search(r'name="([^"]*)"', cab)
        if not nombre:
            continue
        nombre = nombre.group(1)
        fichero = re.search(r'filename="([^"]*)"', cab)
        if fichero:
            if fichero.group(1):
                ficheros[nombre] = (fichero.group(1), contenido)
        else:
            campos[nombre] = contenido.decode("utf-8", "replace")
    return campos, ficheros


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO", "/") or "/"
        self.query = {k: v[0] for k, v in urllib.parse.parse_qs(environ.get("QUERY_STRING", "")).items()}
        self.form: dict[str, str] = {}
        self.files: dict[str, tuple[str, bytes]] = {}
        self.session: dict = {}
        self.usuario = None
        self._leer_cuerpo()

    def _leer_cuerpo(self):
        if self.method not in ("POST", "PUT", "PATCH"):
            return
        try:
            longitud = int(self.environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            longitud = 0
        if longitud <= 0:
            return
        body = self.environ["wsgi.input"].read(longitud)
        tipo = self.environ.get("CONTENT_TYPE", "")
        if tipo.startswith("multipart/form-data"):
            m = re.search(r"boundary=(.+)", tipo)
            if m:
                self.form, self.files = _parse_multipart(body, m.group(1).strip('"').encode())
        else:
            parsed = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
            self.form = {k: v[0] for k, v in parsed.items()}

    @property
    def cookies(self):
        c = SimpleCookie()
        c.load(self.environ.get("HTTP_COOKIE", ""))
        return {k: v.value for k, v in c.items()}

    @property
    def ip(self):
        return (self.environ.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                or self.environ.get("REMOTE_ADDR", "") or "-")

    def get(self, campo, por_defecto=""):
        return (self.form.get(campo) or self.query.get(campo) or por_defecto).strip()


# ------------------------------------------------------------------ respuesta
class Response:
    def __init__(self, cuerpo=b"", estado=200, content_type="text/html; charset=utf-8", cabeceras=None):
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode("utf-8")
        self.cuerpo = cuerpo
        self.estado = estado
        self.cabeceras = [("Content-Type", content_type)] + list(cabeceras or [])

    def cookie(self, nombre, valor, max_age=None, borrar=False):
        partes = [f"{nombre}={valor}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if borrar:
            partes.append("Max-Age=0")
        elif max_age:
            partes.append(f"Max-Age={max_age}")
        self.cabeceras.append(("Set-Cookie", "; ".join(partes)))
        return self


def redirect(destino, mensaje=None, tipo="ok"):
    if mensaje:
        sep = "&" if "?" in destino else "?"
        destino = f"{destino}{sep}aviso={urllib.parse.quote(mensaje)}&t={tipo}"
    return Response(b"", 303, cabeceras=[("Location", destino)])


def json_response(datos, estado=200):
    return Response(json.dumps(datos, ensure_ascii=False, default=str), estado, "application/json; charset=utf-8")


# ------------------------------------------------------------------- enrutado
class Router:
    def __init__(self):
        self.rutas = []

    def add(self, metodos, patron, funcion):
        def convertir(m):
            tipo, nombre = m.group(1), m.group(2)
            return f"(?P<{nombre}>" + (r"\d+" if tipo == "int" else r"[^/]+") + ")"

        regex = re.sub(r"<(?:(int):)?(\w+)>", convertir, patron)
        self.rutas.append((set(metodos), re.compile(f"^{regex}$"), funcion))

    def route(self, patron, metodos=("GET",)):
        def deco(f):
            self.add(metodos, patron, f)
            return f
        return deco

    def resolver(self, metodo, path):
        permitidos = set()
        for metodos, regex, funcion in self.rutas:
            m = regex.match(path)
            if m:
                if metodo in metodos:
                    return funcion, {k: int(v) if v.isdigit() else v for k, v in m.groupdict().items()}
                permitidos |= metodos
        return (None, permitidos)


# --------------------------------------------------------------- estáticos
def servir_estatico(base, path):
    rel = path[len("/static/"):]
    destino = os.path.normpath(os.path.join(base, rel))
    if not destino.startswith(os.path.normpath(base)) or not os.path.isfile(destino):
        return Response("No encontrado", 404, "text/plain; charset=utf-8")
    tipo = mimetypes.guess_type(destino)[0] or "application/octet-stream"
    with open(destino, "rb") as fh:
        return Response(fh.read(), 200, tipo, [("Cache-Control", "public, max-age=3600")])


def token_csrf():
    return secrets.token_urlsafe(24)
