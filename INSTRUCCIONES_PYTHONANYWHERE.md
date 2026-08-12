# Guía de Despliegue Gratis en PythonAnywhere

PythonAnywhere es un servicio excelente que permite alojar aplicaciones Python gratis de forma permanente. A diferencia de Render, **los archivos del plan gratuito no se borran**, por lo que tu base de datos SQLite estará 100% a salvo de forma gratuita.

Sigue estos pasos detallados para desplegar tu CRM:

---

## Paso 1: Crear una cuenta gratuita
1. Ve a [PythonAnywhere](https://www.pythonanywhere.com/) y haz clic en **Sign up** (Registrarse).
2. Elige una cuenta **"Create a Beginner account"** (gratuita).
3. Tu nombre de usuario determinará la URL de tu aplicación (por ejemplo, si tu usuario es `comercialXYZ`, tu CRM estará en `https://comercialXYZ.pythonanywhere.com`).

---

## Paso 2: Descargar el código
1. Una vez dentro de tu panel de control, ve a la pestaña **Consoles** (Consolas) y abre una consola de tipo **Bash**.
2. Clona tu repositorio de GitHub ejecutando este comando:
   ```bash
   git clone https://github.com/alejandroduega-maker/crm.git
   ```
3. Espera a que termine de descargarse y luego cierra la pestaña de la consola.

---

## Paso 3: Instalar las dependencias y sembrar la base de datos
1. Vuelve a abrir una consola **Bash** en PythonAnywhere.
2. Instala las dependencias necesarias en tu espacio ejecutando:
   ```bash
   pip install --user -r crm/crm_web/requirements.txt
   ```
3. Entra a la carpeta del proyecto y ejecuta la siembra inicial para crear el administrador:
   ```bash
   cd crm/crm_web
   python seed.py --ejemplo
   ```
   *(Nota: Si prefieres no tener datos de prueba y empezar con el CRM vacío, ejecuta `python seed.py` en su lugar).*
4. **IMPORTANTE:** Copia la contraseña temporal de administrador (`admin`) que imprimirá la pantalla. La necesitarás para el primer inicio de sesión.
5. Puedes cerrar la consola.

---

## Paso 4: Configurar la Aplicación Web
1. En el panel superior de PythonAnywhere, ve a la pestaña **Web**.
2. Haz clic en el botón **Add a new web app** (Añadir nueva aplicación web).
3. Avanza en el asistente:
   - Haz clic en **Next**.
   - Selecciona **Manual Configuration** (¡Importante! NO selecciones Flask ni Django).
   - Selecciona **Python 3.10** o **Python 3.11** (las dos versiones funcionan perfectamente).
   - Haz clic en **Next** para finalizar.

---

## Paso 5: Configurar el archivo WSGI y las variables
1. En la pestaña **Web**, busca la sección llamada **Code** y haz clic en el enlace al archivo **"WSGI configuration file"** (tendrá una ruta similar a `/var/www/tu-usuario_pythonanywhere_com_wsgi.py`).
2. Se abrirá un editor web. **Borra todo su contenido** y pega las siguientes líneas:

```python
import sys
import os

# Define las variables de entorno de seguridad del CRM
os.environ["CRM_BD"] = "/home/TU_USUARIO/crm/crm_web/data/crm.db"
os.environ["CRM_SECRETO"] = "cambia-esto-por-una-clave-larga-y-aleatoria"

# Configura la ruta del proyecto en el sistema
path = '/home/TU_USUARIO/crm/crm_web'
if path not in sys.path:
    sys.path.insert(0, path)

# Importa la aplicación del CRM
from wsgi import app as application
```

3. **¡IMPORTANTE!** Reemplaza `TU_USUARIO` en el código (líneas 5 y 9) por tu nombre de usuario real de PythonAnywhere (fíjate en que esté en minúsculas).
4. Haz clic en el botón verde **Save** (Guardar) arriba a la derecha.

---

## Paso 6: Recargar y Probar
1. Vuelve a la pestaña **Web** del panel de control de PythonAnywhere.
2. Haz clic en el gran botón verde **Reload** (Recargar) que está arriba del todo.
3. ¡Listo! Haz clic en el enlace de tu sitio web (ej: `https://tu-usuario.pythonanywhere.com`) para entrar al CRM.
4. Inicia sesión con el usuario `admin` y la contraseña temporal que copiaste en el Paso 3.
