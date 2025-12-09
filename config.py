# config.py
import os

DB_CONFIG = {
    "host": os.getenv("mysql.railway.internal"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("root"),
    "password": os.getenv("kAUENhRhQnNOhCduDBvJILnwKZEpnePL"),
    "database": os.getenv("railway"),
}
