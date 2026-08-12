# Instrucciones de Despliegue en la Nube

Este documento te guía paso a paso para subir el **CRM de Telefonía** a producción (Render) y que se pueda acceder de forma segura desde cualquier lugar y en cualquier dispositivo, así como utilizar la funcionalidad de Docker.

---

## 1. Despliegue en Render (Recomendado)

Render permite desplegar aplicaciones web conectándose directamente a tu cuenta de GitHub. Hemos configurado el archivo [render.yaml](file:///c:/Users/aleja/Desktop/new%20crm/render.yaml) para automatizar todo el proceso en el plan **Free** (gratuito) y añadir un **disco persistente de 1 GB** para que tu base de datos SQLite no se borre cuando se reinicie el servidor.

### Paso 1.1: Subir el proyecto a GitHub
Si aún no has subido el proyecto a un repositorio de GitHub:

1. Ve a [GitHub](https://github.com/) y crea un repositorio vacío (público o privado) llamado `new-crm`.
2. Ejecuta los siguientes comandos desde la carpeta raíz del proyecto (`new crm`) en tu terminal local para subir los archivos:
   ```bash
   git add .
   git commit -m "feat: integración de leads del BORME y configuración de despliegue"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO_DE_GITHUB/new-crm.git
   git push -u origin main
   ```
   *(Nota: Reemplaza `TU_USUARIO_DE_GITHUB` por tu usuario real).*

### Paso 1.2: Desplegar en Render
1. Inicia sesión en tu panel de [Render](https://dashboard.render.com/).
2. Haz clic en el botón **New** (Nuevo) en la esquina superior derecha y selecciona **Blueprint**.
3. Conecta tu repositorio de GitHub `new-crm`.
4. Render leerá el archivo `render.yaml` y configurará:
   - El servicio web con Python 3.11.8.
   - El volumen persistente de 1 GB montado en `/data`.
   - Generará una clave secreta segura (`CRM_SECRETO`) de manera automática.
5. Haz clic en **Approve** (Aprobar) o **Apply** para iniciar el despliegue.

¡Listo! Cuando termine de compilar (2-3 minutos), Render te proporcionará una URL pública (ejemplo: `https://crm-telefonia.onrender.com`) desde la cual cualquier comercial o administrador podrá acceder.

### Paso 1.3: Poblar la Base de Datos Inicial en Producción
La base de datos se inicializa automáticamente vacía. Para crear el primer usuario administrador o cargar datos de prueba:

1. Ve al panel del servicio web en Render.
2. En el menú lateral izquierdo, haz clic en **Shell** para abrir una terminal interactiva del servidor web.
3. Ejecuta el comando de siembra según prefieras:
   - **Solo crear administrador:**
     ```bash
     python seed.py
     ```
   - **Crear administrador y datos de muestra:**
     ```bash
     python seed.py --ejemplo
     ```
4. **IMPORTANTE:** Apunta la contraseña temporal que imprima la consola, ya que solo se muestra una vez. La usarás para iniciar sesión por primera vez y el sistema te obligará a cambiarla inmediatamente.

---

## 2. Despliegue con Docker / Servidor Propio (Alternativo)

Si prefieres usar un servidor propio (VPS) con Docker y Docker Compose, hemos preparado un [Dockerfile](file:///c:/Users/aleja/Desktop/new%20crm/Dockerfile) y un [docker-compose.yml](file:///c:/Users/aleja/Desktop/new%20crm/docker-compose.yml).

### Ejecutar localmente o en un VPS con Docker:
1. Asegúrate de tener instalado [Docker](https://www.docker.com/) y Docker Compose.
2. Inicia la aplicación en segundo plano con el siguiente comando:
   ```bash
   docker-compose up -d --build
   ```
3. La aplicación estará accesible en `http://localhost:8000`.
4. Las bases de datos se guardarán persistentemente en la carpeta `crm_web/data` de tu máquina y la caché del BORME en `cache_borme`.
5. Si necesitas correr la siembra de base de datos dentro del contenedor:
   ```bash
   docker exec -it crm_telefonia python seed.py --ejemplo
   ```

---

## 3. Características Añadidas

- **Leads del BORME en la Web:** Ahora hay una sección dedicada llamada **Leads del BORME** dentro del menú de administración. Permite descargar leads por fecha, filtrar por provincia y mínimo de líneas estimadas, e importarlos directamente a la base de datos asignados a cualquier comercial en un solo clic.
- **Auditoría:** Todas las descargas e importaciones de leads del BORME se registran en la sección **Historial** de forma automática indicando la fecha, el usuario que lo hizo, y la cantidad de prospectos importados.
- **Seguridad Git:** El archivo `.gitignore` está configurado para evitar subir archivos accidentales como las bases de datos de prueba o la caché pesada del BORME.
