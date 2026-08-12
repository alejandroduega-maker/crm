# CRM de Telefonía — aplicación web

Cartera de clientes por comercial, centralizada desde un panel de administrador.
Permanencias, penalizaciones, avisos automáticos e historial completo de cambios.

---

## Arrancar en 3 pasos

```bash
cd crm_web
pip install -r requirements.txt
python seed.py --ejemplo        # crea el administrador y datos de muestra
python run.py                   # abre http://localhost:8000
```

Si arrancas sin haber creado ningún usuario, `run.py` te avisa y te dice qué hacer
en lugar de dejarte una pantalla de error.

`seed.py` imprime las contraseñas **una sola vez**. Apúntalas: no se pueden recuperar,
solo se puede generar una nueva desde el panel de administrador.

Sin datos de muestra: `python seed.py` (solo crea el usuario `admin`).
Importando tu Excel: `python seed.py --excel ../CRM_Telefonia.xlsx`

---

## Qué hace

**Para el comercial**
- Panel con sus indicadores y gráficos: cartera, líneas, facturación, penalización expuesta.
- Cartera filtrable por aviso, estado, operador y prioridad, con buscador libre.
- Ficha de cliente con todo lo calculado y su historial de cambios.
- Lista de vencimientos ordenada por urgencia: su lista de llamadas.
- Exportación a Excel de su cartera.

**Para el administrador** — todo lo anterior de todas las carteras, más:
- Crear usuarios con contraseña temporal y obligación de cambiarla al entrar.
- Activar, desactivar, cambiar de rol o regenerar contraseña.
- Historial de cambios de toda la aplicación, con el antes y el después de cada campo.
- Papelera: nada se borra de verdad, todo se puede restaurar.
- Importar clientes desde el Excel y ajustar los umbrales de aviso.

---

## Cómo se calcula

| Campo | Fórmula |
|---|---|
| Cuota mensual | nº de líneas × cuota por línea |
| Fin de permanencia | fecha de alta + meses de permanencia |
| Penalización pendiente | penalización total × (meses restantes ÷ meses de permanencia) |
| Valor del contrato | cuota mensual × meses de permanencia |
| Prioridad | urgencia del vencimiento + facturación + incidencias de pago |

Idéntico al Excel: la penalización baja sola cada mes y llega a 0 € el día que vence.

**Avisos** (umbrales configurables en *Parámetros*):
rojo ≤ 30 días · naranja ≤ 60 · amarillo ≤ 90 · azul = ya sin permanencia · verde = con margen.

---

## Copias de seguridad

Cada vez que arrancas con `python run.py` se guarda una copia de la base de datos en
`data/copias/` (se conservan las 15 últimas). Para recuperar una:

1. Para el servidor (`Ctrl+C`).
2. Copia el archivo que quieras de `data/copias/` encima de `data/crm.db`.
3. Vuelve a arrancar.

Toda la base de datos es el archivo `data/crm.db`. Si lo copias a otro sitio, te llevas
usuarios, clientes e historial completos.

---

## Seguridad

- Contraseñas cifradas con bcrypt. Nadie —tampoco el administrador— puede consultarlas.
- Sesión en cookie firmada (HttpOnly, SameSite=Lax) con caducidad de 12 horas.
- Protección CSRF en todos los formularios.
- Cada comercial solo accede a su cartera, comprobado en el servidor, no solo escondido.
- Borrado lógico: los datos permanecen y quedan restaurables.
- Todo movimiento queda registrado con usuario, fecha e IP.

**Antes de ponerlo en producción**, define estas dos variables de entorno:

```bash
export CRM_SECRETO="una-cadena-larga-y-aleatoria"   # firma las sesiones
export CRM_BD="/ruta/persistente/crm.db"            # base de datos
```

Sirve siempre por HTTPS. Y ten en cuenta que guardas datos personales de clientes
(CIF, teléfonos, emails): eso es RGPD — registro de actividades de tratamiento,
contrato de encargado con el hosting y política de conservación.

---

## Desplegar

Netlify **no** sirve para esto: sus funciones solo ejecutan Node.js. Opciones que sí:

| Dónde | Cómo |
|---|---|
| **Render** (recomendado) | Build `pip install -r requirements.txt`, arranque `gunicorn wsgi:app`. Añade un disco persistente para `data/`. |
| **Railway / Fly.io** | Igual que Render. |
| **Tu propio servidor** | `gunicorn wsgi:app --bind 0.0.0.0:8000` detrás de Nginx con certificado. |
| **PythonAnywhere** | Apunta la app WSGI a `wsgi.py`. |

Con SQLite, **haz copia del archivo `data/crm.db`**: es toda tu base de datos.
Si crecéis, se migra a PostgreSQL sin tocar las pantallas.

---

## Estructura

```
crm_web/
├── run.py              arranque local
├── wsgi.py             arranque en producción
├── seed.py             crea el administrador e importa datos
├── pruebas.py          56 pruebas de punta a punta
├── requirements.txt
├── data/crm.db         la base de datos (se crea sola)
└── app/
    ├── framework.py    enrutado, peticiones, sesiones firmadas
    ├── db.py           esquema y registro de auditoría
    ├── negocio.py      permanencias, penalizaciones, avisos, prioridad
    ├── auth.py         contraseñas y permisos
    ├── main.py         todas las pantallas
    ├── templates/      HTML
    └── static/         CSS y JS
```

Para comprobar que todo sigue funcionando tras cualquier cambio:

```bash
python pruebas.py
```

56 comprobaciones sobre una base de datos temporal propia —login, permisos, cálculos,
papelera, historial, importación y exportación— sin tocar tus datos reales.
