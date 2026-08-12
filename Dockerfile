FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y forzar salida sin buffer para logs claros
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar ciertos paquetes si hiciera falta
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar primero el requirements y descargar las dependencias (aprovechando caché de Docker)
COPY crm_web/requirements.txt /app/crm_web/requirements.txt
RUN pip install --no-cache-dir -r crm_web/requirements.txt

# Copiar el código fuente completo
COPY . /app/

# Crear el directorio de datos para SQLite y caché de BORME
RUN mkdir -p /app/crm_web/data /app/cache_borme

# Exponer el puerto por defecto
EXPOSE 8000

# Variables de entorno por defecto
ENV PORT=8000
ENV CRM_BD="/app/crm_web/data/crm.db"

# Iniciar la aplicación desde la carpeta crm_web para que wsgi:app se resuelva correctamente
WORKDIR /app/crm_web
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT}"]
