# config.py
import os

DB_CONFIG = {
    # En Railway leerá DB_HOST, DB_PORT, etc.
    # En tu PC, si no existen variables, usará los valores por defecto.
    "host": os.getenv("mysql.railway.internal", "127.0.0.1"),
    "port": int(os.getenv("3306", 3306)),
    "user": os.getenv("root", "root"),
    "password": os.getenv("kAUENhRhQnNOhCduDBvJILnwKZEpnePL", "Pedrinche@2020"),
    "database": os.getenv("railway", "catalogo_selles"),
}
