# config.py
import os

DB_CONFIG = {
    # En Railway usará las variables MYSQLHOST, etc.
    # En tu PC usará los valores por defecto (localhost).
    "host": os.getenv("MYSQLHOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQLPORT", 3306)),
    "user": os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("MYSQLPASSWORD", "Pedrinche@2020"),
    "database": os.getenv("MYSQLDATABASE", "catalogo_selles"),
}
