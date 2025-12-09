# config.py
import os

DB_CONFIG = {
    # Si Railway define variables DB_*, se usarán.
    # Si NO existen (local), se usarán los valores por defecto de tu captura.
    "host": os.getenv("DB_HOST", "mysql.railway.internal"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "kAUENhRhQnNOhCduDBvJILnwKZEpnePL"),
    "database": os.getenv("DB_NAME", "railway"),
}
