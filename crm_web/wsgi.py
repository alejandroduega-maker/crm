"""Punto de entrada para servidores de producción (gunicorn, waitress...).

    gunicorn wsgi:app --bind 0.0.0.0:8000
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.main import aplicacion as app  # noqa: E402,F401
