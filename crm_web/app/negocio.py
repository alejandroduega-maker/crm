"""Reglas de negocio del CRM de telefonía.

Todo el cálculo de permanencias, penalizaciones, avisos y prioridad vive aquí,
y replica exactamente lo que hace el Excel.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


def r2(valor: float, decimales: int = 2) -> float:
    """Redondeo comercial (0,5 sube), igual que Excel."""
    cuant = Decimal(10) ** -decimales
    return float(Decimal(str(valor)).quantize(cuant, rounding=ROUND_HALF_UP))

ESTADOS = ["Activo", "En trámite", "Portabilidad", "Renovación", "Baja", "Perdido"]
OPERADORES = ["Movistar", "Vodafone", "Orange", "Yoigo", "MasMovil", "Digi",
              "Pepephone", "Finetwork", "Otro"]
PRODUCTOS = ["Móvil", "Fibra", "Fibra + Móvil", "Fijo", "Centralita", "Convergente", "Otro"]

# Clave de aviso -> (etiqueta corta, color css)
AVISOS = {
    "urgente": ("Urgente", "rojo"),
    "aviso": ("Aviso", "naranja"),
    "proximo": ("Próximo", "amarillo"),
    "sin_permanencia": ("Sin permanencia", "azul"),
    "ok": ("Con margen", "verde"),
    "baja": ("Baja", "gris"),
}


def a_fecha(valor):
    if not valor:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    valor = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


def sumar_meses(inicio: date, meses: int) -> date:
    """Equivalente a EDATE de Excel."""
    total = inicio.month - 1 + int(meses)
    anio = inicio.year + total // 12
    mes = total % 12 + 1
    dia = min(inicio.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def calcular(cliente: dict, hoy: date | None = None, umbrales=(30, 60, 90)) -> dict:
    """Añade al diccionario del cliente todos los campos derivados."""
    hoy = hoy or date.today()
    rojo, naranja, amarillo = umbrales
    c = dict(cliente)

    lineas = int(c.get("num_lineas") or 0)
    cuota_linea = float(c.get("cuota_linea") or 0)
    permanencia = int(c.get("permanencia_meses") or 0)
    penal_total = float(c.get("penalizacion_total") or 0)
    alta = a_fecha(c.get("fecha_alta"))

    c["cuota_total"] = r2(lineas * cuota_linea)

    if alta and permanencia > 0:
        fin = sumar_meses(alta, permanencia)
        dias = (fin - hoy).days
        meses_rest = max(0.0, r2(dias / 30.44, 1))
        c["fin_permanencia"] = fin
        c["dias_restantes"] = dias
        c["meses_restantes"] = meses_rest
        c["penalizacion_pendiente"] = r2(max(0.0, penal_total * meses_rest / permanencia))
    else:
        c["fin_permanencia"] = None
        c["dias_restantes"] = None
        c["meses_restantes"] = None
        c["penalizacion_pendiente"] = None

    # ---- aviso
    if c.get("estado") == "Baja":
        clave = "baja"
    elif c["dias_restantes"] is None:
        clave = None
    elif c["dias_restantes"] < 0:
        clave = "sin_permanencia"
    elif c["dias_restantes"] <= rojo:
        clave = "urgente"
    elif c["dias_restantes"] <= naranja:
        clave = "aviso"
    elif c["dias_restantes"] <= amarillo:
        clave = "proximo"
    else:
        clave = "ok"
    c["aviso"] = clave
    if clave in ("urgente", "aviso", "proximo"):
        c["aviso_texto"] = f"{AVISOS[clave][0]} · {c['dias_restantes']} d"
    elif clave:
        c["aviso_texto"] = AVISOS[clave][0]
    else:
        c["aviso_texto"] = "—"
    c["aviso_color"] = AVISOS[clave][1] if clave else "gris"

    # ---- puntuación de prioridad (0-100)
    if clave in (None, "baja"):
        c["puntuacion"] = None
        c["prioridad"] = None
    else:
        dias = c["dias_restantes"]
        if dias < 0:
            puntos = 40
        elif dias <= rojo:
            puntos = 50
        elif dias <= naranja:
            puntos = 30
        elif dias <= amarillo:
            puntos = 20
        else:
            puntos = 5
        puntos += min(50, c["cuota_total"] / 6)
        c["puntuacion"] = r2(puntos, 1)
        c["prioridad"] = "ALTA" if puntos >= 60 else ("MEDIA" if puntos >= 35 else "BAJA")
    return c


def resumen(clientes: list[dict]) -> dict:
    """Indicadores agregados para el panel."""
    activos = [c for c in clientes if c.get("estado") == "Activo"]
    n_act = len(activos)
    lineas = sum(int(c.get("num_lineas") or 0) for c in activos)
    facturacion = sum(c["cuota_total"] for c in activos)
    cuenta = lambda k: sum(1 for c in clientes if c.get("aviso") == k)
    return {
        "clientes_total": len(clientes),
        "clientes_activos": n_act,
        "bajas": sum(1 for c in clientes if c.get("estado") == "Baja"),
        "lineas": lineas,
        "facturacion_mes": r2(facturacion),
        "facturacion_anio": r2(facturacion * 12),
        "media_lineas": r2(lineas / n_act, 1) if n_act else 0,
        "cuota_media_cliente": r2(facturacion / n_act) if n_act else 0,
        "cuota_media_linea": r2(facturacion / lineas) if lineas else 0,
        "penalizacion_pendiente": r2(sum(c["penalizacion_pendiente"] or 0 for c in activos)),
        "urgentes": cuenta("urgente"),
        "avisos": cuenta("aviso"),
        "proximos": cuenta("proximo"),
        "sin_permanencia": cuenta("sin_permanencia"),
        "con_margen": cuenta("ok"),
        "lineas_sin_permanencia": sum(int(c.get("num_lineas") or 0) for c in clientes
                                      if c.get("aviso") == "sin_permanencia"),
        "facturacion_en_riesgo": r2(sum(c["cuota_total"] for c in clientes
                                        if c.get("aviso") == "sin_permanencia")),
        "prioridad_alta": sum(1 for c in clientes if c.get("prioridad") == "ALTA"),
    }


def vencimientos_por_mes(clientes: list[dict], hoy: date | None = None, meses=12):
    hoy = hoy or date.today()
    etiquetas_mes = ["ene", "feb", "mar", "abr", "may", "jun",
                     "jul", "ago", "sep", "oct", "nov", "dic"]
    salida = []
    for k in range(meses):
        ref = sumar_meses(date(hoy.year, hoy.month, 1), k)
        n = sum(1 for c in clientes
                if c.get("estado") == "Activo" and c.get("fin_permanencia")
                and c["fin_permanencia"].year == ref.year and c["fin_permanencia"].month == ref.month)
        salida.append({"etiqueta": f"{etiquetas_mes[ref.month - 1]} {str(ref.year)[2:]}", "valor": n})
    return salida


def agrupar(clientes: list[dict], campo: str, valor_de=None):
    valor_de = valor_de or (lambda c: 1)
    acumulado: dict[str, float] = {}
    for c in clientes:
        if c.get("estado") != "Activo":
            continue
        clave = c.get(campo) or "—"
        acumulado[clave] = acumulado.get(clave, 0) + valor_de(c)
    return sorted(({"etiqueta": k, "valor": r2(v)} for k, v in acumulado.items()),
                  key=lambda x: -x["valor"])
