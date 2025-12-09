from flask import (
    Flask, abort, g, render_template, request,
    redirect, url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
from functools import wraps
from config import DB_CONFIG
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Config correo (por si lo usas después)
app.config["MAIL_SERVER"]   = "smtp.gmail.com"
app.config["MAIL_PORT"]     = 587
app.config["MAIL_USE_TLS"]  = True
app.config["MAIL_USERNAME"] = "global.english.mail@gmail.com"
app.config["MAIL_PASSWORD"] = "mhqjeinxyyfquhvf"
app.config["MAIL_FROM"]     = "global.english.mail@gmail.com"


# ---------------------------------------------------------
#           CONEXIÓN A BD
# ---------------------------------------------------------

def get_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
        )
        return conn
    except Error as e:
        print(f"Error al conectar a MySQL: {e}")
        return None


def query_one(sql, params=None):
    conn = get_connection()
    if conn is None:
        print("query_one: sin conexión a BD")
        return None
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def query_all(sql, params=None):
    conn = get_connection()
    if conn is None:
        print("query_all: sin conexión a BD")
        return []
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def execute_query(sql, params=None):
    """Ejecuta INSERT/UPDATE/DELETE y devuelve el lastrowid (si aplica)."""
    conn = get_connection()
    if conn is None:
        return None
    cur = conn.cursor()
    cur.execute(sql, params or ())
    conn.commit()
    last_id = cur.lastrowid
    cur.close()
    conn.close()
    return last_id

def get_current_user():
    """Devuelve el usuario logueado (fila de la tabla usuarios) o None."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    if g.get("tenant"):
        return query_one(
            "SELECT * FROM usuarios WHERE id = %s AND tenant_id = %s",
            (user_id, g.tenant["id"])
        )
    else:
        return query_one(
            "SELECT * FROM usuarios WHERE id = %s",
            (user_id,)
        )




# ---------------------------------------------------------
#           DECORADORES
# ---------------------------------------------------------

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if session.get("rol") not in roles:
                flash("No tienes permiso para acceder a esta sección.", "danger")
                # Si hay tenant en la URL, lo mandamos a su dashboard
                if g.get("tenant"):
                    return redirect(url_for("dashboard", tenant_slug=g.tenant["slug"]))
                return redirect(url_for("login"))

            return f(*args, **kwargs)
        return wrapper
    return decorator


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        user_tenant_id = session.get("tenant_id")
        if g.get("tenant") and user_tenant_id != g.tenant["id"]:
            abort(403)  # usuario quiere entrar al tenant equivocado

        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------
#           MULTITENANT: CARGAR TENANT DESDE URL
# ---------------------------------------------------------

@app.url_value_preprocessor
def pull_tenant_slug(endpoint, values):
    """
    Carga g.tenant sólo en rutas que tienen <tenant_slug> en la URL,
    por ejemplo /<tenant_slug>/dashboard
    """
    g.tenant = None

    if not values:
        return

    tenant_slug = values.get("tenant_slug")
    if tenant_slug:
        tenant = query_one(
            "SELECT * FROM tenants WHERE slug = %s",
            (tenant_slug,)
        )
        if tenant is None:
            abort(404)  # tenant no existe
        g.tenant = tenant


# ---------------------------------------------------------
#           RUTAS GLOBALES (MISMO LINK PARA TODOS)
# ---------------------------------------------------------

@app.route("/")
def index():
    # Siempre redirigimos al login global
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Login global (mismo link para todas las empresas).
    1. Usuario entra a /login
    2. Pon email + password
    3. Buscamos en usuarios JOIN tenants
    4. Según su tenant, redirigimos a /<slug>/dashboard
    """
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # Buscamos al usuario y al tenant asociado
        user = query_one(
            """
            SELECT u.*, t.slug, t.nombre_empresa
            FROM usuarios u
            JOIN tenants t ON u.tenant_id = t.id
            WHERE u.email = %s
            """,
            (email,)
        )
        print("LOGIN /login -> user:", user)

        if user and check_password_hash(user["password_hash"], password):
            # Guardamos info básica en sesión
            session["user_id"] = user["id"]
            session["tenant_id"] = user["tenant_id"]
            # Si tu tabla usuarios tiene campo rol, lo usamos; si no, queda None
            session["rol"] = user.get("rol") if isinstance(user, dict) and "rol" in user else None

            # Redirigimos al dashboard de su empresa
            return redirect(url_for("dashboard", tenant_slug=user["slug"]))
        else:
            error = "Credenciales incorrectas"

        if request.method == "POST":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            print("EMAIL RECIBIDO FORM:", repr(email))


    # GET o POST con error → mostramos login
    return render_template("login.html", error=error)


# ---------------------------------------------------------
#           RUTAS MULTITENANT (DESPUÉS DEL LOGIN)
# ---------------------------------------------------------

from datetime import date  # ya lo tienes arriba, pero por si acaso

@app.route("/<tenant_slug>/dashboard")
@login_required
def dashboard(tenant_slug):
    tenant_id = g.tenant["id"]

    # --- Ventas del mes ---
    hoy = date.today()
    primer_dia = date(hoy.year, hoy.month, 1)

    row_ventas_mes = query_one(
        """
        SELECT COALESCE(SUM(total), 0) AS total
        FROM facturas
        WHERE tenant_id = %s
          AND fecha >= %s
          AND estado IN ('pendiente', 'pagada')
        """,
        (tenant_id, primer_dia)
    )
    ventas_mes = row_ventas_mes["total"] if row_ventas_mes else 0

    # --- Clientes activos (todos) ---
    row_clientes = query_one(
        "SELECT COUNT(*) AS c FROM clientes WHERE tenant_id = %s",
        (tenant_id,)
    )
    clientes_activos = row_clientes["c"] if row_clientes else 0

    # --- Productos activos ---
    row_productos = query_one(
        "SELECT COUNT(*) AS c FROM productos WHERE tenant_id = %s AND estado = 'activo'",
        (tenant_id,)
    )
    productos_activos = row_productos["c"] if row_productos else 0

    # --- Facturas pendientes ---
    row_pendientes = query_one(
        """
        SELECT COUNT(*) AS c
        FROM facturas
        WHERE tenant_id = %s AND estado = 'pendiente'
        """,
        (tenant_id,)
    )
    facturas_pendientes = row_pendientes["c"] if row_pendientes else 0

    # --- Ventas recientes (tabla) ---
    ventas_recientes = query_all(
        """
        SELECT
            f.id,
            f.fecha,
            f.numero,
            f.total,
            f.estado,
            c.nombre AS cliente
        FROM facturas f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.tenant_id = %s
        ORDER BY f.fecha DESC
        LIMIT 10
        """,
        (tenant_id,)
    )

    return render_template(
        "dashboard.html",
        tenant=g.tenant,
        ventas_mes=ventas_mes,
        clientes_activos=clientes_activos,
        productos_activos=productos_activos,
        facturas_pendientes=facturas_pendientes,
        ventas_recientes=ventas_recientes,
    )


@app.route("/<tenant_slug>/productos")
@login_required
def productos_list(tenant_slug):
    productos = query_all(
        "SELECT * FROM productos WHERE tenant_id = %s ORDER BY nombre",
        (g.tenant["id"],)
    )
    return render_template("productos_list.html", tenant=g.tenant, productos=productos)


@app.route("/<tenant_slug>/clientes")
@login_required
def clientes_list(tenant_slug):
    q = request.args.get("q", "").strip()
    tenant_id = g.tenant["id"]

    sql = "SELECT * FROM clientes WHERE tenant_id = %s"
    params = [tenant_id]

    # Si hay texto de búsqueda, filtrar SOLO por documento o email
    if q:
        sql += " AND (documento LIKE %s OR email LIKE %s)"
        like = f"%{q}%"
        params.extend([like, like])

    sql += " ORDER BY nombre ASC"

    clientes = query_all(sql, params)

    return render_template("clientes_list.html", tenant=g.tenant, clientes=clientes)


# ---------- CLIENTES: NUEVO / EDITAR ----------

@app.route("/<tenant_slug>/clientes/nuevo", methods=["GET", "POST"])
@login_required
def clientes_nuevo(tenant_slug):
    if request.method == "POST":
        nombre     = request.form.get("nombre")
        documento  = request.form.get("documento") or None
        email      = request.form.get("email") or None
        telefono   = request.form.get("telefono") or None
        direccion  = request.form.get("direccion") or None
        ciudad     = request.form.get("ciudad") or None

        execute_query(
            """
            INSERT INTO clientes (tenant_id, nombre, documento, email, telefono, direccion, ciudad)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (g.tenant["id"], nombre, documento, email, telefono, direccion, ciudad)
        )
        flash("Cliente creado correctamente.", "success")
        return redirect(url_for("clientes_list", tenant_slug=g.tenant["slug"]))

    # GET
    return render_template("clientes_form.html", tenant=g.tenant)


@app.route("/<tenant_slug>/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
def clientes_editar(tenant_slug, cliente_id):
    cliente = query_one(
        "SELECT * FROM clientes WHERE id = %s AND tenant_id = %s",
        (cliente_id, g.tenant["id"])
    )
    if not cliente:
        abort(404)

    if request.method == "POST":
        nombre     = request.form.get("nombre")
        documento  = request.form.get("documento") or None
        email      = request.form.get("email") or None
        telefono   = request.form.get("telefono") or None
        direccion  = request.form.get("direccion") or None
        ciudad     = request.form.get("ciudad") or None

        execute_query(
            """
            UPDATE clientes
            SET nombre=%s, documento=%s, email=%s, telefono=%s, direccion=%s, ciudad=%s
            WHERE id=%s AND tenant_id=%s
            """,
            (nombre, documento, email, telefono, direccion, ciudad, cliente_id, g.tenant["id"])
        )
        flash("Cliente actualizado.", "success")
        return redirect(url_for("clientes_list", tenant_slug=g.tenant["slug"]))

    # GET
    return render_template("clientes_form.html", tenant=g.tenant, cliente=cliente)

# ---------- USUARIOS: NUEVO / EDITAR ----------

@app.route("/<tenant_slug>/usuarios/nuevo", methods=["GET", "POST"])
@login_required
def usuarios_nuevo(tenant_slug):
    if request.method == "POST":
        nombre   = request.form.get("nombre")
        seg_nom  = request.form.get("seg_nom") or ""
        apel     = request.form.get("apel")
        seg_apel = request.form.get("seg_apel") or ""
        email    = request.form.get("email")
        rol      = request.form.get("rol", "vendedor")
        activo   = 1 if request.form.get("activo") == "1" else 0

        password  = request.form.get("password")
        password2 = request.form.get("password2")

        if password != password2:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("usuarios_form.html", tenant=g.tenant)

        password_hash = generate_password_hash(password)

        execute_query(
            """
            INSERT INTO usuarios
            (nombre, seg_nom, apel, seg_apel, tenant_id, email, password_hash, rol, activo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (nombre, seg_nom, apel, seg_apel, g.tenant["id"], email, password_hash, rol, activo)
        )
        flash("Usuario creado correctamente.", "success")
        return redirect(url_for("usuarios_list", tenant_slug=g.tenant["slug"]))

    return render_template("usuarios_form.html", tenant=g.tenant)


@app.route("/<tenant_slug>/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
def usuarios_editar(tenant_slug, usuario_id):
    usuario = query_one(
        "SELECT * FROM usuarios WHERE id=%s AND tenant_id=%s",
        (usuario_id, g.tenant["id"])
    )
    if not usuario:
        abort(404)

    if request.method == "POST":
        nombre   = request.form.get("nombre")
        seg_nom  = request.form.get("seg_nom") or None
        apel     = request.form.get("apel")
        seg_apel = request.form.get("seg_apel") or None
        email    = request.form.get("email")
        rol      = request.form.get("rol", "vendedor")
        activo   = 1 if request.form.get("activo") == "1" else 0

        password  = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        # Actualiza siempre datos básicos
        execute_query(
            """
            UPDATE usuarios
            SET nombre=%s, seg_nom=%s, apel=%s, seg_apel=%s,
                email=%s, rol=%s, activo=%s
            WHERE id=%s AND tenant_id=%s
            """,
            (nombre, seg_nom, apel, seg_apel, email, rol, activo, usuario_id, g.tenant["id"])
        )

        # Si escribió nueva contraseña
        if password or password2:
            if password != password2:
                flash("Las contraseñas no coinciden.", "danger")
                return render_template("usuarios_form.html", tenant=g.tenant, usuario=usuario)
            password_hash = generate_password_hash(password)
            execute_query(
                "UPDATE usuarios SET password_hash=%s WHERE id=%s AND tenant_id=%s",
                (password_hash, usuario_id, g.tenant["id"])
            )

        flash("Usuario actualizado.", "success")
        return redirect(url_for("usuarios_list", tenant_slug=g.tenant["slug"]))

    return render_template("usuarios_form.html", tenant=g.tenant, usuario=usuario)



@app.route("/<tenant_slug>/facturas")
@login_required
def facturas_list(tenant_slug):
    facturas = query_all(
        """
        SELECT f.*, c.nombre AS cliente_nombre
        FROM facturas f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.tenant_id = %s
        ORDER BY f.fecha DESC
        """,
        (g.tenant["id"],)
    )
    return render_template("facturas_list.html", tenant=g.tenant, facturas=facturas)


@app.route("/<tenant_slug>/reportes")
@login_required
def reportes_list(tenant_slug):
    reportes = query_all(
        "SELECT * FROM reportes WHERE tenant_id = %s ORDER BY creado_en DESC",
        (g.tenant["id"],)
    )
    return render_template("reportes_list.html", tenant=g.tenant, reportes=reportes)


@app.route("/<tenant_slug>/usuarios")
@login_required
def usuarios_list(tenant_slug):
    usuarios = query_all(
        "SELECT * FROM usuarios WHERE tenant_id = %s ORDER BY nombre",
        (g.tenant["id"],)
    )
    return render_template("usuarios_list.html", tenant=g.tenant, usuarios=usuarios)


@app.route("/<tenant_slug>/configuracion", methods=["GET", "POST"])
@login_required
def config_empresa(tenant_slug):
    if not g.tenant:
        abort(404)

    tenant_id = g.tenant["id"]

    if request.method == "POST":
        nombre_empresa = request.form.get("nombre_empresa")
        direccion      = request.form.get("direccion") or None
        telefono       = request.form.get("telefono") or None
        moneda         = request.form.get("moneda") or None
        logo_url       = request.form.get("logo_url") or None

        execute_query(
            """
            UPDATE tenants
            SET nombre_empresa = %s,
                direccion      = %s,
                telefono       = %s,
                moneda         = %s,
                logo_url       = %s
            WHERE id = %s
            """,
            (nombre_empresa, direccion, telefono, moneda, logo_url, tenant_id)
        )

        flash("Datos de la empresa actualizados correctamente.", "success")
        # Recargar tenant desde la BD para que muestre los datos modificados
        nuevo_tenant = query_one("SELECT * FROM tenants WHERE id = %s", (tenant_id,))
        g.tenant = nuevo_tenant

        return redirect(url_for("config_empresa", tenant_slug=g.tenant["slug"]))

    # GET: mostrar el formulario con los datos actuales
    return render_template("config_empresa.html", tenant=g.tenant)






# ---------- PRODUCTOS: NUEVO / EDITAR ----------

@app.route("/<tenant_slug>/productos/nuevo", methods=["GET", "POST"])
@login_required
def productos_nuevo(tenant_slug):
    if request.method == "POST":
        codigo      = request.form.get("codigo")
        nombre      = request.form.get("nombre")
        descripcion = request.form.get("descripcion") or None
        precio      = request.form.get("precio") or 0
        stock       = request.form.get("stock") or 0
        estado      = request.form.get("estado", "activo")

        execute_query(
            """
            INSERT INTO productos
            (tenant_id, codigo, nombre, descripcion, precio, stock, estado)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (g.tenant["id"], codigo, nombre, descripcion, precio, stock, estado)
        )
        flash("Producto creado correctamente.", "success")
        return redirect(url_for("productos_list", tenant_slug=g.tenant["slug"]))

    return render_template("productos_form.html", tenant=g.tenant)


@app.route("/<tenant_slug>/productos/<int:producto_id>/editar", methods=["GET", "POST"])
@login_required
def productos_editar(tenant_slug, producto_id):
    producto = query_one(
        "SELECT * FROM productos WHERE id=%s AND tenant_id=%s",
        (producto_id, g.tenant["id"])
    )
    if not producto:
        abort(404)

    if request.method == "POST":
        codigo      = request.form.get("codigo")
        nombre      = request.form.get("nombre")
        descripcion = request.form.get("descripcion") or None
        precio      = request.form.get("precio") or 0
        stock       = request.form.get("stock") or 0
        estado      = request.form.get("estado", "activo")

        execute_query(
            """
            UPDATE productos
            SET codigo=%s, nombre=%s, descripcion=%s, precio=%s, stock=%s, estado=%s
            WHERE id=%s AND tenant_id=%s
            """,
            (codigo, nombre, descripcion, precio, stock, estado, producto_id, g.tenant["id"])
        )
        flash("Producto actualizado.", "success")
        return redirect(url_for("productos_list", tenant_slug=g.tenant["slug"]))

    return render_template("productos_form.html", tenant=g.tenant, producto=producto)

# ---------- PRODUCTOS: AJUSTE / AUMENTAR STOCK ----------

@app.route("/<tenant_slug>/productos/<int:producto_id>/stock", methods=["GET", "POST"])
@login_required
def productos_stock(tenant_slug, producto_id):
    producto = query_one(
        "SELECT * FROM productos WHERE id=%s AND tenant_id=%s",
        (producto_id, g.tenant["id"])
    )
    if not producto:
        abort(404)

    if request.method == "POST":
        try:
            cantidad = int(request.form.get("cantidad") or 0)
        except ValueError:
            cantidad = 0

        if cantidad <= 0:
            flash("La cantidad debe ser mayor que cero.", "danger")
            return render_template("productos_stock.html", tenant=g.tenant, producto=producto)

        # Aumentar stock actual
        execute_query(
            """
            UPDATE productos
            SET stock = stock + %s
            WHERE id=%s AND tenant_id=%s
            """,
            (cantidad, producto_id, g.tenant["id"])
        )
        flash(f"Stock actualizado (+{cantidad}).", "success")
        return redirect(url_for("productos_list", tenant_slug=g.tenant["slug"]))

    # GET: mostrar formulario
    return render_template("productos_stock.html", tenant=g.tenant, producto=producto)


# ---------- FACTURAS: NUEVA / VER (simple) ----------

@app.route("/<tenant_slug>/facturas/nueva", methods=["GET", "POST"])
@login_required
def facturas_nueva(tenant_slug):
    # Productos activos del tenant
    productos = query_all(
        "SELECT * FROM productos WHERE tenant_id = %s AND estado = 'activo'",
        (g.tenant["id"],)
    )

    # Clientes del tenant
    clientes = query_all(
        "SELECT * FROM clientes WHERE tenant_id = %s",
        (g.tenant["id"],)
    )

    if request.method == "POST":
        cliente_id = request.form.get("cliente_id")

        if not cliente_id:
            flash("Debes seleccionar un cliente.", "danger")
            return redirect(url_for("facturas_nueva", tenant_slug=g.tenant["slug"]))

        # Fecha AUTOMÁTICA
        fecha = datetime.now()

        # Crear factura con número correlativo por tenant
        factura_id = execute_query(
            """
            INSERT INTO facturas (tenant_id, cliente_id, numero, fecha, total, estado)
            VALUES (
                %s,
                %s,
                (SELECT IFNULL(MAX(f2.numero), 0) + 1 FROM facturas f2 WHERE f2.tenant_id = %s),
                %s,
                0,
                'pendiente'
            )
            """,
            (g.tenant["id"], cliente_id, g.tenant["id"], fecha)
        )

        total_factura = 0

        # Recorrer los productos enviados en el formulario
        for key, value in request.form.items():
            if not key.startswith("producto_"):
                continue

            producto_id = key.split("_", 1)[1]

            try:
                cantidad = int(value or 0)
            except ValueError:
                cantidad = 0

            if cantidad <= 0:
                continue

            prod = query_one(
                "SELECT id, precio, stock FROM productos WHERE id = %s AND tenant_id = %s",
                (producto_id, g.tenant["id"])
            )

            if not prod:
                continue

            subtotal = prod["precio"] * cantidad
            total_factura += subtotal

            # INSERT en factura_detalle (NO factura_items)
            execute_query(
                """
                INSERT INTO factura_detalle (factura_id, producto_id, cantidad, precio_unit, subtotal)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (factura_id, producto_id, cantidad, prod["precio"], subtotal)
            )

            # Opcional: actualizar stock del producto
            execute_query(
                """
                UPDATE productos
                SET stock = stock - %s
                WHERE id = %s AND tenant_id = %s
                """,
                (cantidad, producto_id, g.tenant["id"])
            )

        # Actualizar total en la factura
        execute_query(
            "UPDATE facturas SET total = %s WHERE id = %s",
            (total_factura, factura_id)
        )

        flash("Factura creada correctamente.", "success")
        return redirect(url_for("facturas_ver", tenant_slug=g.tenant["slug"], factura_id=factura_id))

    # GET
    return render_template(
        "facturas_form.html",
        tenant=g.tenant,
        productos=productos,
        clientes=clientes
    )





@app.route("/<tenant_slug>/facturas/<int:factura_id>")
@login_required
def facturas_ver(tenant_slug, factura_id):
    # Cabecera de factura + datos de cliente
    factura = query_one(
        """
        SELECT f.*, 
               c.nombre        AS cliente_nombre,
               c.documento     AS cliente_documento,
               c.email         AS cliente_email
        FROM facturas f
        LEFT JOIN clientes c ON c.id = f.cliente_id
        WHERE f.id = %s AND f.tenant_id = %s
        """,
        (factura_id, g.tenant["id"])
    )

    if not factura:
        abort(404)

    # Detalle de productos (desde factura_detalle)
    detalles = query_all(
        """
        SELECT d.*, 
               p.nombre AS producto_nombre
        FROM factura_detalle d
        JOIN productos p ON p.id = d.producto_id
        WHERE d.factura_id = %s
        """,
        (factura_id,)
    )

    # Fecha ya formateada para mostrar bonita en el template
    fecha_str = ""
    if factura.get("fecha"):
        try:
            fecha_str = factura["fecha"].strftime("%d/%m/%Y %H:%M")
        except Exception:
            fecha_str = str(factura["fecha"])

    return render_template(
        "factura_ver.html",
        tenant=g.tenant,
        factura=factura,
        detalles=detalles,
        fecha_str=fecha_str
    )


@app.route("/<tenant_slug>/facturas/<int:factura_id>/pagada", methods=["POST"])
@login_required
def facturas_marcar_pagada(tenant_slug, factura_id):
    # Verificar que la factura exista y pertenezca al tenant actual
    factura = query_one(
        "SELECT * FROM facturas WHERE id = %s AND tenant_id = %s",
        (factura_id, g.tenant["id"])
    )

    if not factura:
        abort(404)

    # Marcar como pagada
    execute_query(
        "UPDATE facturas SET estado = 'pagada' WHERE id = %s AND tenant_id = %s",
        (factura_id, g.tenant["id"])
    )

    flash("La factura ha sido marcada como pagada.", "success")
    return redirect(url_for("facturas_ver",
                            tenant_slug=g.tenant["slug"],
                            factura_id=factura_id))



# ---------- REPORTES: NUEVO / VER (simple) ----------

@app.route("/<tenant_slug>/reportes/nuevo", methods=["GET", "POST"])
@login_required
def reportes_nuevo(tenant_slug):
    # TODO: implementar creación de reportes
    flash("Pantalla de creación de reportes aún no implementada.", "info")
    return redirect(url_for("reportes_list", tenant_slug=g.tenant["slug"]))


@app.route("/<tenant_slug>/reportes/<int:reporte_id>")
@login_required
def reportes_ver(tenant_slug, reporte_id):
    reporte = query_one(
        "SELECT * FROM reportes WHERE id=%s AND tenant_id=%s",
        (reporte_id, g.tenant["id"])
    )
    if not reporte:
        abort(404)

    # Por ahora solo mostramos datos básicos del reporte
    return render_template(
        "reportes_detalle.html",  # si no existe, puedes crear una plantilla sencilla
        tenant=g.tenant,
        reporte=reporte
    )

@app.route("/<tenant_slug>/perfil", methods=["GET", "POST"])
@login_required
def perfil_usuario(tenant_slug):
    if not g.tenant:
        abort(404)

    # Cargar datos del usuario logueado
    user = query_one(
        "SELECT * FROM usuarios WHERE id = %s AND tenant_id = %s",
        (session.get("user_id"), g.tenant["id"])
    )
    if not user:
        abort(404)

    if request.method == "POST":
        nombre   = request.form.get("nombre", "").strip()
        seg_nom  = request.form.get("seg_nom", "").strip()
        apel     = request.form.get("apel", "").strip()
        seg_apel = request.form.get("seg_apel", "").strip()
        email    = request.form.get("email", "").strip()

        # Actualizar en BD
        execute_query(
            """
            UPDATE usuarios
               SET nombre=%s,
                   seg_nom=%s,
                   apel=%s,
                   seg_apel=%s,
                   email=%s
             WHERE id=%s AND tenant_id=%s
            """,
            (nombre, seg_nom, apel, seg_apel, email, user["id"], g.tenant["id"])
        )

        # Refrescar datos del usuario y nombre en sesión
        user = query_one(
            "SELECT * FROM usuarios WHERE id = %s AND tenant_id = %s",
            (session.get("user_id"), g.tenant["id"])
        )
        session["user_name"] = f"{user['nombre']} {user['apel']}"
        flash("Perfil actualizado correctamente.", "success")

    return render_template("perfil.html", tenant=g.tenant, user=user)


    if request.method == "POST":
        nombre    = request.form.get("nombre") or ""
        seg_nom   = request.form.get("seg_nom") or ""
        apel      = request.form.get("apel") or ""
        seg_apel  = request.form.get("seg_apel") or ""
        email     = request.form.get("email") or ""

        execute_query(
            """
            UPDATE usuarios
            SET nombre = %s,
                seg_nom = %s,
                apel = %s,
                seg_apel = %s,
                email = %s
            WHERE id = %s AND tenant_id = %s
            """,
            (nombre, seg_nom, apel, seg_apel, email, user["id"], g.tenant["id"])
        )

        session["user_name"] = f"{nombre} {apel}".strip()
        flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for("perfil_usuario", tenant_slug=g.tenant["slug"]))

    return render_template("perfil.html", tenant=g.tenant, user=user)


@app.route("/<tenant_slug>/cuenta/configuracion", methods=["GET", "POST"])
@login_required
def cuenta_config(tenant_slug):
    user = get_current_user()
    if not user:
        abort(404)

    if request.method == "POST":
        actual    = request.form.get("password_actual") or ""
        nueva     = request.form.get("password_nueva") or ""
        confirmar = request.form.get("password_confirmar") or ""

        if not check_password_hash(user["password_hash"], actual):
            flash("La contraseña actual no es correcta.", "danger")
            return redirect(url_for("cuenta_config", tenant_slug=g.tenant["slug"]))

        if len(nueva) < 4:
            flash("La nueva contraseña debe tener al menos 4 caracteres.", "warning")
            return redirect(url_for("cuenta_config", tenant_slug=g.tenant["slug"]))

        if nueva != confirmar:
            flash("La confirmación no coincide con la nueva contraseña.", "warning")
            return redirect(url_for("cuenta_config", tenant_slug=g.tenant["slug"]))

        nuevo_hash = generate_password_hash(nueva)

        execute_query(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s AND tenant_id = %s",
            (nuevo_hash, user["id"], g.tenant["id"])
        )

        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("cuenta_config", tenant_slug=g.tenant["slug"]))

    return render_template("cuenta_config.html", tenant=g.tenant, user=user)



@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión correctamente.", "info")
    return redirect(url_for("login"))   # tu login principal está en /login





if __name__ == "__main__":
    print(app.url_map)   # para ver todas las rutas
    app.run(debug=True)
