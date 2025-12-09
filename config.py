# config.py
import os

DB_CONFIG = {
    # En Railway leerá DB_HOST, DB_PORT, etc.
    # En tu PC, si no existen variables, usará los valores por defecto.
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "Pedrinche@2020"),
    "database": os.getenv("DB_NAME", "catalogo_selles"),
}
