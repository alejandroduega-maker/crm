# Base de datos de empresas desde el BORME

Genera un CSV de empresas españolas a partir del **Boletín Oficial del Registro
Mercantil**, con una estimación del número de líneas móviles que podrían tener.

Fuente oficial, pública y gratuita. Sin API keys, sin cuentas, sin límites.

## Instalación

```
pip install -r requirements_borme.txt
```

## Uso

```bash
# Constituciones nuevas de todo julio, toda España
python borme_leads.py --desde 2026-07-01 --hasta 2026-07-31 --solo-constituciones

# Solo el último día hábil
python borme_leads.py --ayer

# Filtrar provincias y volumen mínimo
python borme_leads.py --desde 2026-07-01 --provincia MADRID BARCELONA --min-lineas 5
```

Genera `empresas_borme.csv` y `empresas_borme.sqlite`, ordenados por prioridad.

## Lo que extrae de cada empresa

Denominación, tipo de acto, objeto social, domicilio, municipio, provincia,
capital social, administradores y fecha de inicio de operaciones.

## Sobre las columnas de líneas — léelo

**No existe ninguna base de datos, ni gratuita ni de pago, con las líneas que una
empresa tiene contratadas.** Ese dato lo tiene su operador y es confidencial.

`lineas_min`, `lineas_estimadas` y `lineas_max` son una **heurística**: sector
deducido del objeto social × plantilla estimada por tramo de capital social, con
el número de administradores como suelo mínimo.

Sirven para **ordenar a quién llamas primero**. No son un dato y no deben
presentarse como cifra a un cliente. La columna `confianza` te dice cuánto fiarte
de cada fila.

Si necesitas la plantilla real, está en las cuentas anuales depositadas en el
Registro Mercantil (~8-15 € por empresa) o en eInforma/Axesor por suscripción.

## Por qué las constituciones nuevas son el mejor filón

Una empresa recién constituida no tiene operador al que desbancar ni permanencia
que romper. El BORME las publica el día que se inscriben, gratis. `--solo-constituciones`
te deja solo esas.

Las **ampliaciones de capital** y los **cambios de domicilio** son la segunda mejor
señal: crecimiento y mudanza, ambos momentos en que se replantean los servicios.

## Filtros de seguridad activos por defecto

| Filtro | Qué excluye | Por qué |
|---|---|---|
| Descartes | Disoluciones, extinciones, concursos | No son clientes |
| Personas físicas | Denominaciones sin forma societaria (SL, SA, SLP...) | El art. 19 LOPDGDD **no** ampara el marketing a empresarios individuales; ahí hace falta consentimiento |

Puedes desactivarlos con `--incluir-descartes` y `--incluir-personas-fisicas`,
pero piénsate el segundo. La AEPD ha sancionado por eso.

La detección de personas físicas es heurística por la denominación: revisa las
dudosas antes de meterlas en una campaña.

## Marco legal

- **Datos de la empresa** (razón social, domicilio, objeto): persona jurídica, no
  son datos personales. Libre uso.
- **Contacto de empleados**: el [art. 19 LOPDGDD](https://www.iberley.es/legislacion/articulo-19-ley-organica-proteccion-datos-personales-garantia-derechos-digitales-lopdgdd)
  presume interés legítimo para relacionarte con la empresa.
- **Autónomos y empresarios individuales**: necesitan consentimiento.
- **Reutilización del BORME**: permitida bajo las
  [condiciones del BOE](https://www.boe.es/informacion/aviso_legal/index.php#reutilizacion).

No soy tu asesor legal: si vas a montar campañas a volumen, que lo revise quien te
lleve el cumplimiento.

## Detalles técnicos

- API oficial: `GET /datosabiertos/api/borme/sumario/{AAAAMMDD}` con cabecera `Accept`
  ([spec v2.0, mayo 2026](https://www.boe.es/datosabiertos/documentos/APIsumarioBORME.pdf))
- Solo lee la **Sección A** (Empresarios, actos inscritos)
- Caché en disco: los días ya descargados no se repiten. Puedes cortar y reanudar.
- Pausa de 0,4 s entre peticiones por cortesía con un servicio público. No la quites.
- La base SQLite tiene clave primaria `(id_documento, num_acto)`: relanzar el mismo
  rango no duplica filas.
- El BORME solo se publica de lunes a viernes no festivos. Los festivos se detectan
  por 404 y se saltan.

## Qué está verificado y qué no

**Verificado** contra el documento real `BORME-A-2024-102-03` (Alicante): el parser
extrae correctamente 9 actos con sus capitales, domicilios, municipios y
administradores, incluidos nombres con puntos interiores (`JM.ISTA SL`,
`M.J. O'NEILL (INSURANCES) LIMITED SUCURSAL EN ESPAÑA`). También verificados el
clasificador de sector, la deduplicación de administradores, la exclusión de
concursos y personas físicas, la idempotencia y el parseo del JSON según la
especificación oficial.

**No verificado**: la llamada HTTP en vivo a boe.es, porque el entorno donde se
desarrolló tiene ese dominio bloqueado. El código sigue la especificación oficial
publicada, pero la primera ejecución real es tuya. Si algo falla en el parseo del
sumario, pásame la salida y lo ajusto.
