#!/usr/bin/env python3
"""
borme_leads.py
==============

Genera una base de datos de empresas espanolas a partir del BORME
(Boletin Oficial del Registro Mercantil), fuente oficial, publica y gratuita.

Para cada empresa extrae:
    denominacion, tipo de acto, objeto social, domicilio, municipio,
    provincia, capital social y administradores

Y ANADE UNA ESTIMACION del numero de lineas moviles que podria tener.

  ###################################################################
  #  AVISO IMPORTANTE SOBRE LAS LINEAS ESTIMADAS                    #
  #                                                                 #
  #  NO existe ninguna base de datos, gratuita ni de pago, con las  #
  #  lineas que una empresa tiene contratadas. Ese dato lo tiene    #
  #  su operador y es confidencial.                                 #
  #                                                                 #
  #  Las columnas lineas_min / lineas_estimadas / lineas_max son    #
  #  una HEURISTICA basada en sector y tramo de capital social.     #
  #  Sirven para PRIORIZAR a quien llamas primero.                  #
  #  NO son un dato y no deben presentarse como tal a un cliente.   #
  ###################################################################

Fuente: https://www.boe.es/datosabiertos/api/api.php
Licencia de reutilizacion del BOE:
    https://www.boe.es/informacion/aviso_legal/index.php#reutilizacion

Uso:
    python borme_leads.py --desde 2026-07-01 --hasta 2026-07-31
    python borme_leads.py --ayer --solo-constituciones
    python borme_leads.py --desde 2026-07-01 --provincia MADRID BARCELONA
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Iterator, Optional

try:
    import requests
except ImportError:
    sys.exit("Falta 'requests'. Instala con: pip install -r requirements_borme.txt")


API_SUMARIO = "https://www.boe.es/datosabiertos/api/borme/sumario/{fecha}"

# Cortesia con un servicio publico: pausa entre peticiones.
PAUSA_SEGUNDOS = 0.4

CABECERAS = {
    "Accept": "application/json",
    "User-Agent": "borme-leads/1.0 (script de prospeccion B2B; datos abiertos BOE)",
}


# ---------------------------------------------------------------------------
# Sectores y ratio de lineas moviles por empleado
# ---------------------------------------------------------------------------
#
# El ratio es cuantas lineas moviles suele haber por empleado en ese sector.
# Un comercial o un instalador lleva movil de empresa casi siempre (~1,0+).
# En hosteleria o retail solo lo lleva el encargado (~0,2).
#
# Estos valores son ordenes de magnitud del sector telco B2B, no cifras
# oficiales. Ajustalos con tu propia experiencia de conversion.

SECTORES = [
    # (clave, ratio, [palabras que lo identifican en el objeto social])
    ("construccion", 1.10, [
        "construccion", "edificios", "obra", "reforma", "albanileria",
        "instalaciones electricas", "fontaneria", "climatizacion",
        "aire acondicionado", "carpinteria", "pintura", "encofrado",
        "rehabilitacion", "promocion inmobiliaria", "demolicion",
        "instalacion", "montaje",
    ]),
    ("transporte_logistica", 1.20, [
        "transporte", "mensajeria", "paqueteria", "logistica",
        "mudanzas", "flota", "taxi", "vtc", "alquiler de automoviles",
        "vehiculos de motor", "grua", "almacenamiento",
    ]),
    ("comercio_mayorista", 0.75, [
        "comercio al por mayor", "mayorista", "distribucion",
        "intermediarios del comercio", "importacion", "exportacion",
    ]),
    ("servicios_profesionales", 0.85, [
        "consultoria", "asesoramiento", "ingenieria", "arquitectura",
        "abogados", "juridico", "gestoria", "asesoria", "auditoria",
        "contabilidad", "servicios tecnicos", "formacion", "publicidad",
        "marketing", "agencia", "diseno", "arquitectura tecnica",
    ]),
    ("tecnologia", 0.90, [
        "informatica", "software", "telecomunicaciones", "programacion",
        "desarrollo de aplicaciones", "sistemas informaticos", "datos",
        "paginas web", "ciberseguridad", "tecnologias",
    ]),
    ("sanidad_servicios", 0.55, [
        "clinica", "sanitaria", "medica", "dental", "fisioterapia",
        "veterinaria", "farmacia", "optica", "residencia",
        "servicios sociales", "asistencia",
    ]),
    ("industria", 0.45, [
        "fabricacion", "fabrica", "produccion", "manufactura",
        "elaboracion", "procesado", "envasado", "textil", "calzado",
        "metalurgia", "taller",
    ]),
    ("inmobiliario", 0.70, [
        "inmobiliaria", "arrendamiento", "alquiler de bienes",
        "compraventa de bienes inmuebles", "gestion de inmuebles",
        "patrimonio",
    ]),
    ("agricultura", 0.55, [
        "agricola", "cultivo", "ganaderia", "explotacion agraria",
        "pesca", "forestal", "jardineria", "viveros",
    ]),
    ("hosteleria_retail", 0.22, [
        "hosteleria", "restaurante", "bar", "cafeteria", "catering",
        "hotel", "alojamiento", "turistico", "comercio al por menor",
        "establecimientos especializados", "tienda", "supermercado",
        "peluqueria", "estetica", "gimnasio",
    ]),
    ("limpieza_seguridad", 0.60, [
        # Frases largas primero: pesan mas y desempatan bien frente a
        # 'edificios', que tambien aparece en construccion.
        "limpieza de edificios", "actividades de limpieza",
        "servicios de limpieza", "limpieza general de edificios",
        "seguridad privada", "vigilancia y seguridad",
        "recogida de residuos", "gestion de residuos",
        "limpieza", "seguridad", "vigilancia", "mantenimiento",
        "conserjeria", "residuos",
    ]),
]

SECTOR_POR_DEFECTO = ("otros", 0.55)


# Tramos de capital social -> plantilla estimada (min, tipica, max).
# Basado en que la inmensa mayoria de SL nuevas se constituyen con el
# minimo legal y son microempresas de 1-3 personas.
TRAMOS_CAPITAL = [
    #  hasta,      min, tipica, max
    (3_500,          1,    2,     4),
    (10_000,         1,    3,     6),
    (25_000,         2,    5,    10),
    (60_000,         4,   10,    25),
    (150_000,        8,   20,    50),
    (500_000,       15,   40,   120),
    (float("inf"),  30,   90,   400),
]


# Formas societarias: si la denominacion NO acaba en una de estas,
# puede tratarse de una persona fisica (empresario individual).
FORMAS_SOCIETARIAS = [
    "SL", "S L", "S.L.", "SLU", "S L U", "SLP", "S L P", "SLNE",
    "SA", "S A", "S.A.", "SAU", "S A U", "SAL", "SLL",
    "SCP", "SC", "COOP", "COOPERATIVA", "SDAD", "SOCIEDAD LIMITADA",
    "SOCIEDAD ANONIMA", "SOCIEDAD CIVIL", "AIE", "UTE", "SICAV",
    "LIMITED", "LTD", "GMBH", "BV", "SUCURSAL EN ESPANA", "SRL",
    "SOCIEDAD DE RESPONSABILIDAD LIMITADA", "SOCIEDAD COOPERATIVA",
]


# Tipos de acto que nos interesan como senal comercial
ACTOS_INTERES = {
    "Constitución":            "empresa nueva, sin operador previo",
    "Ampliación de capital":   "crecimiento, probable aumento de plantilla",
    "Nombramientos":           "cambio en direccion, ventana de decision",
    "Cambio de domicilio social": "mudanza, replantea servicios",
    "Reapertura hoja registral":  "reactivacion de actividad",
}

ACTOS_DESCARTE = {
    "Disolución", "Extinción", "Situación concursal",
    "Declaración de concurso", "Liquidación",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def sin_tildes(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def normalizar(texto: str) -> str:
    return sin_tildes(texto or "").lower()


def a_numero(texto: str) -> Optional[float]:
    """Convierte '3.000,00' (formato espanol) a 3000.0"""
    if not texto:
        return None
    limpio = texto.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------

@dataclass
class Empresa:
    fecha_borme: str = ""
    provincia: str = ""
    id_documento: str = ""
    num_acto: str = ""
    denominacion: str = ""

    actos: str = ""
    es_constitucion: bool = False
    es_descarte: bool = False
    senal_comercial: str = ""

    objeto_social: str = ""
    domicilio: str = ""
    municipio: str = ""
    capital_eur: Optional[float] = None
    capital_resultante_eur: Optional[float] = None
    inicio_operaciones: str = ""

    administradores: str = ""
    num_administradores: int = 0

    sector: str = ""
    ratio_lineas: float = 0.0
    empleados_min: int = 0
    empleados_est: int = 0
    empleados_max: int = 0

    lineas_min: int = 0
    lineas_estimadas: int = 0
    lineas_max: int = 0
    confianza: str = ""

    posible_persona_fisica: bool = False
    prioridad: int = 0


# ---------------------------------------------------------------------------
# Cliente de la API
# ---------------------------------------------------------------------------

class ErrorRed(Exception):
    """Fallo de red o del servidor. NO significa que no haya BORME ese dia."""


class ClienteBORME:
    def __init__(self, cache_dir: str = "cache_borme", pausa: float = PAUSA_SEGUNDOS):
        self.cache_dir = cache_dir
        self.pausa = pausa
        self.sesion = requests.Session()
        self.sesion.headers.update(CABECERAS)
        os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, clave: str) -> str:
        seguro = re.sub(r"[^A-Za-z0-9_.-]", "_", clave)
        return os.path.join(self.cache_dir, seguro)

    def _get(self, url: str, clave_cache: str, accept: str) -> Optional[str]:
        ruta = self._cache_path(clave_cache)
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as fh:
                return fh.read()

        time.sleep(self.pausa)
        try:
            resp = self.sesion.get(url, headers={"Accept": accept}, timeout=30)
        except requests.RequestException as exc:
            raise ErrorRed(f"no se pudo conectar con boe.es: {exc}") from exc

        if resp.status_code == 404:
            # 404 SI significa que no hay documento ese dia (festivo, etc).
            # Solo este caso se cachea como vacio.
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write("")
            return None

        if resp.status_code != 200:
            raise ErrorRed(f"HTTP {resp.status_code} en {url}")

        resp.encoding = resp.encoding or "utf-8"
        texto = resp.text
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(texto)
        return texto

    def sumario(self, dia: date) -> list[dict]:
        """
        Devuelve los items de la SECCION A (Empresarios. Actos inscritos),
        uno por provincia.
        """
        fecha = dia.strftime("%Y%m%d")
        crudo = self._get(
            API_SUMARIO.format(fecha=fecha),
            f"sumario_{fecha}.json",
            "application/json",
        )
        if not crudo:
            return []

        try:
            import json
            datos = json.loads(crudo)
        except ValueError:
            return []

        if str(datos.get("status", {}).get("code")) != "200":
            return []

        sumario = datos.get("data", {}).get("sumario", {})
        diarios = sumario.get("diario", [])
        if isinstance(diarios, dict):
            diarios = [diarios]

        items: list[dict] = []
        for diario in diarios:
            secciones = diario.get("seccion", [])
            if isinstance(secciones, dict):
                secciones = [secciones]
            for seccion in secciones:
                if seccion.get("codigo") != "A":
                    continue
                lista = seccion.get("item", [])
                if isinstance(lista, dict):
                    lista = [lista]
                for it in lista:
                    items.append({
                        "identificador": it.get("identificador", ""),
                        "provincia": it.get("titulo", ""),
                        "url_xml": it.get("url_xml", ""),
                    })
        return items

    def documento(self, item: dict) -> list[str]:
        """Descarga un documento de seccion A y devuelve sus parrafos."""
        crudo = self._get(
            item["url_xml"],
            f"doc_{item['identificador']}.xml",
            "application/xml",
        )
        if not crudo:
            return []

        try:
            raiz = ET.fromstring(crudo)
        except ET.ParseError:
            return []

        parrafos: list[str] = []
        for trozo in raiz.itertext():
            limpio = " ".join(trozo.split())
            if limpio:
                parrafos.append(limpio)
        return parrafos


# ---------------------------------------------------------------------------
# Parser de actos
# ---------------------------------------------------------------------------

# Cabecera de acto: "241607 - HYDROGINEERING SL."
# Ojo: el nombre puede llevar puntos (JM.ISTA SL, M.J. O'NEILL ...),
# por eso NO cortamos en el primer punto: el parrafo entero es la cabecera.
RE_CABECERA = re.compile(r"^(\d{4,8})\s*-\s*(.+?)\.?$")

RE_CAPITAL = re.compile(r"Capital:\s*([\d.,]+)\s*Euros", re.IGNORECASE)
RE_CAPITAL_RESULT = re.compile(
    r"Resultante Suscrito:\s*([\d.,]+)\s*Euros", re.IGNORECASE)
RE_INICIO = re.compile(
    r"Comienzo de operaciones:\s*([\d]{1,2}\.[\d]{1,2}\.[\d]{2,4})", re.IGNORECASE)

_SIGUIENTES = (
    r"Domicilio:|Capital:|Nombramientos\.|Ceses/Dimisiones\.|"
    r"Datos registrales\.|Declaración de unipersonalidad\.|"
    r"Socio único:|Otros conceptos:|Revocaciones\.|Reelecciones\.|$"
)

RE_OBJETO = re.compile(
    r"Objeto social:\s*(.+?)(?=\s(?:" + _SIGUIENTES + r"))",
    re.IGNORECASE | re.DOTALL)

RE_DOMICILIO = re.compile(
    r"Domicilio:\s*(.+?)(?=\s(?:" + _SIGUIENTES + r"))",
    re.IGNORECASE | re.DOTALL)

# El municipio va entre parentesis al final del domicilio. Admitimos
# puntuacion final, porque el domicilio suele venir cerrado con punto.
RE_MUNICIPIO = re.compile(r"\(([^()]+)\)\s*\.?\s*$")

RE_CARGOS = re.compile(
    r"(Adm\.\s*Unico|Adm\.\s*Solid\.|Adm\.\s*Mancom\.|Consejero|"
    r"Con\.Delegado|Apoderado|Liquidador|Socio único|Auditor)\s*:\s*([^.]+)",
    re.IGNORECASE)

# Tipos de acto que aparecen literalmente al principio de una frase
RE_ACTOS = re.compile(
    r"(Constitución|Ampliación de capital|Reducción de capital|"
    r"Nombramientos|Ceses/Dimisiones|Revocaciones|Reelecciones|"
    r"Cambio de denominación social|Cambio de domicilio social|"
    r"Ampliacion del objeto social|Modificación de objeto social|"
    r"Disolución|Extinción|Situación concursal|Reapertura hoja registral|"
    r"Declaración de unipersonalidad|Pérdida del caracter de unipersonalidad|"
    r"Fusión por absorción|Transformación de sociedad)",
    re.IGNORECASE)


def parsear_documento(parrafos: list[str], provincia: str,
                      id_doc: str, fecha: str) -> list[Empresa]:
    empresas: list[Empresa] = []
    actual: Optional[Empresa] = None
    cuerpo: list[str] = []

    def cerrar() -> None:
        if actual is not None:
            _rellenar(actual, " ".join(cuerpo))
            empresas.append(actual)

    for parrafo in parrafos:
        m = RE_CABECERA.match(parrafo)
        # Una cabecera es corta, empieza por numero seguido de guion y
        # nunca contiene el pie "Datos registrales" que cierra los cuerpos.
        if m and len(parrafo) < 250 and "Datos registrales" not in parrafo:
            cerrar()
            actual = Empresa(
                fecha_borme=fecha,
                provincia=provincia,
                id_documento=id_doc,
                num_acto=m.group(1),
                denominacion=m.group(2).strip(),
            )
            cuerpo = []
        elif actual is not None:
            cuerpo.append(parrafo)

    cerrar()
    return empresas


def _rellenar(emp: Empresa, texto: str) -> None:
    # --- Actos ---
    actos = []
    for m in RE_ACTOS.finditer(texto):
        nombre = m.group(1)
        nombre = nombre[0].upper() + nombre[1:]
        if nombre not in actos:
            actos.append(nombre)
    emp.actos = "; ".join(actos)
    emp.es_constitucion = any(normalizar(a).startswith("constitucion")
                              for a in actos)
    emp.es_descarte = any(
        normalizar(a) in {normalizar(d) for d in ACTOS_DESCARTE}
        for a in actos
    )

    for acto in actos:
        for clave, senal in ACTOS_INTERES.items():
            if normalizar(acto) == normalizar(clave):
                emp.senal_comercial = senal
                break
        if emp.senal_comercial:
            break

    # --- Campos ---
    m = RE_OBJETO.search(texto)
    if m:
        emp.objeto_social = " ".join(m.group(1).split())[:600]

    m = RE_DOMICILIO.search(texto)
    if m:
        emp.domicilio = " ".join(m.group(1).split()).strip(" .")[:300]
        mm = RE_MUNICIPIO.search(emp.domicilio)
        if mm:
            emp.municipio = mm.group(1).strip()

    m = RE_CAPITAL.search(texto)
    if m:
        emp.capital_eur = a_numero(m.group(1))

    m = RE_CAPITAL_RESULT.search(texto)
    if m:
        emp.capital_resultante_eur = a_numero(m.group(1))

    m = RE_INICIO.search(texto)
    if m:
        emp.inicio_operaciones = m.group(1)

    # --- Administradores ---
    # Deduplicamos POR PERSONA: es habitual que el mismo individuo aparezca
    # como socio unico y como administrador unico. Son una linea, no dos.
    # Los auditores se excluyen: son externos, no llevan movil de la empresa.
    personas: list[str] = []
    vistos: set[str] = set()

    for m in RE_CARGOS.finditer(texto):
        cargo = " ".join(m.group(1).split())
        if normalizar(cargo).startswith("auditor"):
            continue
        for nombre in m.group(2).split(";"):
            nombre = nombre.strip(" .,")
            if not nombre or len(nombre) <= 2:
                continue
            clave = normalizar(nombre)
            if clave in vistos:
                continue
            vistos.add(clave)
            personas.append(f"{cargo}: {nombre}")

    emp.administradores = " | ".join(personas[:12])
    emp.num_administradores = len(personas)

    # --- Persona fisica? ---
    emp.posible_persona_fisica = _es_posible_persona_fisica(emp.denominacion)


def _es_posible_persona_fisica(denominacion: str) -> bool:
    d = normalizar(denominacion).replace(".", " ")
    d = " ".join(d.split())
    for forma in FORMAS_SOCIETARIAS:
        f = normalizar(forma).replace(".", " ")
        f = " ".join(f.split())
        if d.endswith(" " + f) or d == f or f in d.split():
            return False
    return True


# ---------------------------------------------------------------------------
# Clasificacion de sector y estimacion de lineas
# ---------------------------------------------------------------------------

def clasificar_sector(objeto: str) -> tuple[str, float]:
    """
    Puntua cada sector por  (veces que aparece la palabra) x (su longitud).

    Ponderar por longitud evita que palabras genericas cortas ganen a
    terminos especificos. Ejemplo real: un objeto social de
    "telecomunicaciones por cable / inalambricas / por satelite +
    instalaciones electricas" debe clasificarse como tecnologia, no como
    construccion solo porque 'instalacion' aparezca dentro de
    'instalaciones'.
    """
    if not objeto:
        return SECTOR_POR_DEFECTO

    texto = normalizar(objeto)
    mejor = None
    mejor_puntos = 0.0

    for clave, ratio, palabras in SECTORES:
        puntos = sum(texto.count(p) * len(p) for p in palabras)
        if puntos > mejor_puntos:
            mejor_puntos = puntos
            mejor = (clave, ratio)

    return mejor if mejor else SECTOR_POR_DEFECTO


def estimar_plantilla(capital: Optional[float]) -> tuple[int, int, int]:
    if capital is None:
        return (1, 3, 8)          # sin dato: banda ancha
    for tope, mn, tip, mx in TRAMOS_CAPITAL:
        if capital < tope:
            return (mn, tip, mx)
    return (30, 90, 400)


def estimar_lineas(emp: Empresa) -> None:
    sector, ratio = clasificar_sector(emp.objeto_social)
    emp.sector = sector
    emp.ratio_lineas = ratio

    capital = emp.capital_resultante_eur or emp.capital_eur
    mn, tip, mx = estimar_plantilla(capital)
    emp.empleados_min, emp.empleados_est, emp.empleados_max = mn, tip, mx

    # Suelo duro: cada administrador lleva movil casi con total seguridad.
    suelo = max(1, emp.num_administradores)

    emp.lineas_min = max(suelo, round(mn * ratio))
    emp.lineas_estimadas = max(suelo, round(tip * ratio))
    emp.lineas_max = max(emp.lineas_estimadas, round(mx * ratio))

    # Confianza: depende de cuanta informacion real tenemos
    if capital is None:
        emp.confianza = "baja (sin capital)"
    elif not emp.objeto_social:
        emp.confianza = "baja (sin objeto social)"
    elif sector == "otros":
        emp.confianza = "media (sector no identificado)"
    elif capital <= 3_500:
        emp.confianza = "media (capital minimo: micro)"
    else:
        emp.confianza = "media-alta"


def calcular_prioridad(emp: Empresa) -> None:
    """0-100. Solo para ordenar la lista de llamadas."""
    if emp.es_descarte or emp.posible_persona_fisica:
        emp.prioridad = 0
        return

    p = 0
    if emp.es_constitucion:
        p += 40                                  # sin operador previo
    if "Ampliación de capital" in emp.actos:
        p += 20
    if "Cambio de domicilio social" in emp.actos:
        p += 10

    p += min(30, emp.lineas_estimadas * 3)       # volumen potencial

    if emp.ratio_lineas >= 1.0:
        p += 10                                  # sector movil-intensivo
    elif emp.ratio_lineas <= 0.3:
        p -= 10

    emp.prioridad = max(0, min(100, p))


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

CAMPOS = list(Empresa.__dataclass_fields__.keys())


def guardar_sqlite(ruta: str, empresas: list[Empresa]) -> int:
    con = sqlite3.connect(ruta)
    cols = ", ".join(f"{c} TEXT" for c in CAMPOS)
    con.execute(f"CREATE TABLE IF NOT EXISTS empresas ({cols}, "
                f"PRIMARY KEY (id_documento, num_acto))")
    nuevas = 0
    for emp in empresas:
        d = asdict(emp)
        marcas = ",".join("?" * len(CAMPOS))
        cur = con.execute(
            f"INSERT OR IGNORE INTO empresas ({','.join(CAMPOS)}) VALUES ({marcas})",
            [str(d[c]) if d[c] is not None else "" for c in CAMPOS],
        )
        nuevas += cur.rowcount
    con.commit()
    con.close()
    return nuevas


def guardar_csv(ruta: str, empresas: list[Empresa]) -> None:
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        for emp in empresas:
            w.writerow(asdict(emp))


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------

def rango_fechas(desde: date, hasta: date) -> Iterator[date]:
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:        # el BORME no se publica sab/dom
            yield dia
        dia += timedelta(days=1)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Genera base de datos de empresas desde el BORME "
                    "(datos abiertos oficiales del BOE) con estimacion "
                    "de lineas moviles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Constituciones de todo julio en toda Espana
  python borme_leads.py --desde 2026-07-01 --hasta 2026-07-31 --solo-constituciones

  # Solo el ultimo dia habil publicado
  python borme_leads.py --ayer

  # Filtrar provincias
  python borme_leads.py --desde 2026-07-01 --provincia MADRID BARCELONA

AVISO: las columnas de lineas son una ESTIMACION heuristica por sector y
capital social, no un dato real. Sirven para priorizar llamadas.
        """,
    )
    ap.add_argument("--desde", help="Fecha inicial AAAA-MM-DD")
    ap.add_argument("--hasta", help="Fecha final AAAA-MM-DD (por defecto: hoy)")
    ap.add_argument("--ayer", action="store_true",
                    help="Solo el dia habil anterior")
    ap.add_argument("--provincia", nargs="*",
                    help="Filtrar por provincia (como aparece en el BORME)")
    ap.add_argument("--solo-constituciones", action="store_true",
                    help="Quedarse solo con empresas de nueva creacion")
    ap.add_argument("--incluir-descartes", action="store_true",
                    help="Incluir disoluciones, extinciones y concursos")
    ap.add_argument("--incluir-personas-fisicas", action="store_true",
                    help="Incluir posibles empresarios individuales "
                         "(ojo: su tratamiento con fines de marketing "
                         "NO se ampara en interes legitimo)")
    ap.add_argument("--min-lineas", type=int, default=0,
                    help="Descartar empresas con menos lineas estimadas")
    ap.add_argument("--csv", default="empresas_borme.csv")
    ap.add_argument("--db", default="empresas_borme.sqlite")
    ap.add_argument("--cache", default="cache_borme")

    args = ap.parse_args(argv)

    if args.ayer:
        hasta = date.today() - timedelta(days=1)
        while hasta.weekday() >= 5:
            hasta -= timedelta(days=1)
        desde = hasta
    else:
        if not args.desde:
            ap.error("Indica --desde AAAA-MM-DD o usa --ayer")
        desde = date.fromisoformat(args.desde)
        hasta = date.fromisoformat(args.hasta) if args.hasta else date.today()

    if desde > hasta:
        ap.error("--desde es posterior a --hasta")

    filtro_prov = {normalizar(p) for p in args.provincia} if args.provincia else None

    cliente = ClienteBORME(cache_dir=args.cache)
    todas: list[Empresa] = []
    dias = list(rango_fechas(desde, hasta))

    print(f"BORME: del {desde} al {hasta}  ({len(dias)} dias habiles)")
    print(f"Cache: {args.cache}/  (los dias ya descargados no se repiten)")
    print()

    fallos_red = 0

    for i, dia in enumerate(dias, 1):
        try:
            items = cliente.sumario(dia)
        except ErrorRed as exc:
            fallos_red += 1
            print(f"[{i}/{len(dias)}] {dia}  ERROR DE RED: {exc}")
            continue

        if not items:
            print(f"[{i}/{len(dias)}] {dia}  sin publicacion (festivo)")
            continue

        if filtro_prov:
            items = [it for it in items
                     if normalizar(it["provincia"]) in filtro_prov]

        del_dia = 0
        for it in items:
            try:
                parrafos = cliente.documento(it)
            except ErrorRed as exc:
                fallos_red += 1
                print(f"    ! {it['identificador']}: {exc}")
                continue
            if not parrafos:
                continue
            empresas = parsear_documento(
                parrafos, it["provincia"], it["identificador"],
                dia.isoformat(),
            )
            todas.extend(empresas)
            del_dia += len(empresas)

        print(f"[{i}/{len(dias)}] {dia}  {len(items):>2} provincias  "
              f"{del_dia:>5} actos")

    if fallos_red:
        print()
        print(f"AVISO: {fallos_red} descargas fallaron por red. Los datos estan")
        print("INCOMPLETOS. Vuelve a lanzar el mismo comando: la cache conserva")
        print("lo ya descargado y solo se reintentara lo que falta.")

    print()
    print(f"Actos leidos: {len(todas)}")

    # --- Enriquecer ---
    for emp in todas:
        estimar_lineas(emp)
        calcular_prioridad(emp)

    # --- Filtrar ---
    filtradas = todas
    if not args.incluir_descartes:
        filtradas = [e for e in filtradas if not e.es_descarte]
    if not args.incluir_personas_fisicas:
        filtradas = [e for e in filtradas if not e.posible_persona_fisica]
    if args.solo_constituciones:
        filtradas = [e for e in filtradas if e.es_constitucion]
    if args.min_lineas:
        filtradas = [e for e in filtradas if e.lineas_estimadas >= args.min_lineas]

    filtradas.sort(key=lambda e: (-e.prioridad, -e.lineas_estimadas))

    if not filtradas:
        print("No queda ninguna empresa tras aplicar los filtros.")
        return 0

    guardar_csv(args.csv, filtradas)
    nuevas = guardar_sqlite(args.db, filtradas)

    _resumen(todas, filtradas, nuevas, args)
    return 0


def _resumen(todas, filtradas, nuevas, args) -> None:
    constituciones = sum(1 for e in filtradas if e.es_constitucion)
    fisicas = sum(1 for e in todas if e.posible_persona_fisica)
    descartes = sum(1 for e in todas if e.es_descarte)
    lineas_tot = sum(e.lineas_estimadas for e in filtradas)

    print()
    print("=" * 64)
    print("  RESUMEN")
    print("=" * 64)
    print(f"  Actos leidos del BORME ............ {len(todas)}")
    print(f"  Excluidos: disolucion/concurso .... {descartes}")
    print(f"  Excluidos: posibles pers. fisicas . {fisicas}")
    print(f"  En el fichero final ............... {len(filtradas)}")
    print(f"     de las cuales constituciones ... {constituciones}")
    print(f"  Nuevas en la base de datos ........ {nuevas}")
    print()
    print(f"  Suma de lineas ESTIMADAS .......... {lineas_tot}")
    print("  (estimacion heuristica, NO dato real)")

    print()
    print("  Top sectores:")
    conteo: dict[str, int] = {}
    for e in filtradas:
        conteo[e.sector] = conteo.get(e.sector, 0) + 1
    for sector, n in sorted(conteo.items(), key=lambda x: -x[1])[:6]:
        print(f"    {sector:<26} {n:>5}")

    print()
    print("  Top 5 por prioridad:")
    for e in filtradas[:5]:
        nombre = e.denominacion[:36]
        print(f"    [{e.prioridad:>3}] {nombre:<38} "
              f"~{e.lineas_estimadas} lineas  {e.municipio[:16]}")

    print("=" * 64)
    print(f"\nCSV: {args.csv}\nBD : {args.db}")
    print("\nRecuerda: lineas_estimadas es una heuristica para priorizar "
          "llamadas.\nNo la presentes como dato al cliente.")


if __name__ == "__main__":
    raise SystemExit(main())
