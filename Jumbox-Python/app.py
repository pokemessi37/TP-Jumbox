import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import base64
from flask_bcrypt import Bcrypt

from dotenv import load_dotenv
import os

# Cargar las variables desde .env
load_dotenv()

from datetime import date
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


# ===============================================
# CREDENCIALES DE PRUEBA
# ===============================================
# telefono admin: 12345678
# contraseña admin: Admin1234

# telefono usuario1: 87654321
# contraseña usuario1: Usuario1234

# telefono sucursal1: 09876543
# contraseña sucursal1: Sucursal1111

# telefono sucursal2: 98765432
# contraseña sucursal2: Sucursal2222

# telefono sucursal3: 76543210
# contraseña sucursal3: Sucursal3333

# ===============================================
# CONFIGURACIÓN DE LA APP
# ===============================================
load_dotenv()
app = Flask(__name__)
app.secret_key = 'clave_secreta_super_segura'
#app.secret_key = os.environ.get("FLASK_SECRET_KEY")
bcrypt = Bcrypt(app)
DB_NAME = "jumbox.db"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:5000/auth/callback"
flow = Flow.from_client_config(
    client_config={
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    },
    scopes=[
        "openid",
        #"https://www.googleapis.com/auth/user.phonenumbers.read",
        "https://www.googleapis.com/auth/userinfo.profile"
        ],
    redirect_uri=REDIRECT_URI
)

# ===============================================
# FUNCIONES AUXILIARES - BASE DE DATOS
# ===============================================
def get_conn():
    """Conexión SQLite con row_factory y FK on."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def require_login_redirect():
    """Si no hay sesión, redirige a /login."""
    if 'id_cliente' not in session:
        flash("Necesitás iniciar sesión.", "error")
        return redirect(url_for('login'))
    return None

def ensure_carrito_abierto(conn, id_cliente: int):
    """Obtiene o crea el carrito del cliente."""
    car = conn.execute(
        "SELECT * FROM carrito WHERE fk_cliente=? LIMIT 1",
        (id_cliente,)
    ).fetchone()
    if car:
        return car
    cur = conn.execute("INSERT INTO carrito(fk_cliente) VALUES (?)", (id_cliente,))
    return conn.execute("SELECT * FROM carrito WHERE id_carrito=?", (cur.lastrowid,)).fetchone()

def leer_items(conn, id_carrito: int):
    """Items del carrito + datos de producto."""
    rows = conn.execute("""
        SELECT
            pc.fk_producto              AS producto_id,
            p.nombre                    AS nombre,
            p.precio                    AS precio,
            pc.cantidad                 AS cantidad,
            (p.precio * pc.cantidad)    AS subtotal
        FROM producto_carrito pc
        JOIN producto p ON p.id_producto = pc.fk_producto
        WHERE pc.fk_carrito = ?
        ORDER BY p.nombre
    """, (id_carrito,)).fetchall()
    total = sum(r['subtotal'] for r in rows) if rows else 0.0
    return rows, total

def listar_sucursales(conn):
    """Lista todas las sucursales (clientes tipo 'sucursal')."""
    return conn.execute("""
        SELECT id_cliente AS id, 
            nombre AS nombre,
            direccion AS direccion
        FROM cliente
        WHERE tipo = 'sucursal'
        ORDER BY id_cliente
    """).fetchall()

def listar_categorias(conn):
    """Lista todas las categorías disponibles."""
    try:
        return [r['nombre'] for r in conn.execute("SELECT nombre FROM categoria ORDER BY nombre").fetchall()]
    except sqlite3.Error:
        return []

def get_productos_sucursal(conn, cliente_sucursal_id: int):
    """Obtiene todos los productos con su stock en una sucursal específica."""
    return conn.execute("""
        SELECT 
            p.id_producto AS id,
            p.nombre,
            p.precio,
            COALESCE(a.cantidad, 0) AS stock_sucursal,
            c.nombre AS categoria
        FROM producto p
        LEFT JOIN almacen_sucursal a 
            ON a.fk_producto = p.id_producto 
            AND a.fk_sucursal = ?
        JOIN categoria c ON c.id_categoria = p.fk_categoria
        ORDER BY p.nombre
    """, (cliente_sucursal_id,)).fetchall()

# ===============================================
# RUTAS PRINCIPALES
# ===============================================
@app.route('/')
def home():
    categoria_filtro = request.args.get('categoria', None)
    conn = get_conn()

    # Obtener sucursales para el selector
    sucursales = listar_sucursales(conn)
    
    # Sucursal seleccionada (de sesión o primera disponible)
    if 'cliente_sucursal_id' not in session and sucursales:
        session['cliente_sucursal_id'] = sucursales[0]['id']
    
    cliente_sucursal_id = session.get('cliente_sucursal_id')

    categorias = conn.execute("SELECT nombre FROM categoria ORDER BY nombre").fetchall()
    categorias_lista = [c['nombre'] for c in categorias]

    # Consultar productos con stock de la sucursal seleccionada
    if categoria_filtro:
        productos = conn.execute("""
            SELECT
                p.id_producto AS id,
                p.nombre,
                p.precio,
                COALESCE(a.cantidad, 0) AS stock,
                p.imagen,
                p.fk_categoria,
                c.nombre AS categoria_nombre
            FROM producto p
            JOIN categoria c ON p.fk_categoria = c.id_categoria
            LEFT JOIN almacen_sucursal a 
                ON a.fk_producto = p.id_producto 
                AND a.fk_sucursal = ?
            WHERE c.nombre = ?
            ORDER BY p.id_producto DESC
        """, (cliente_sucursal_id, categoria_filtro)).fetchall()
    else:
        productos = conn.execute("""
            SELECT
                p.id_producto AS id,
                p.nombre,
                p.precio,
                COALESCE(a.cantidad, 0) AS stock,
                p.imagen,
                p.fk_categoria,
                c.nombre AS categoria_nombre
            FROM producto p
            JOIN categoria c ON p.fk_categoria = c.id_categoria
            LEFT JOIN almacen_sucursal a 
                ON a.fk_producto = p.id_producto 
                AND a.fk_sucursal = ?
            ORDER BY p.id_producto DESC
        """, (cliente_sucursal_id,)).fetchall()

    productos_con_imagen = []
    for p in productos:
        producto_dict = dict(p)
        if producto_dict['imagen']:
            producto_dict['imagen_base64'] = base64.b64encode(producto_dict['imagen']).decode('utf-8')
        else:
            producto_dict['imagen_base64'] = None
        productos_con_imagen.append(producto_dict)

    conn.close()

    return render_template('index.html',
                        productos=productos_con_imagen,
                        categorias=categorias_lista,
                        categoria_actual=categoria_filtro,
                        sucursales=sucursales,
                        cliente_sucursal_id=cliente_sucursal_id)

@app.route('/cambiar-sucursal', methods=['POST'])
def cambiar_sucursal():
    """Cambiar la sucursal seleccionada en el index."""
    cliente_sucursal_id = request.form.get('cliente_sucursal_id', type=int)
    if not cliente_sucursal_id:
        flash("Selecciona una sucursal válida.", "error")
    else:
        session['cliente_sucursal_id'] = cliente_sucursal_id
        flash("Sucursal cambiada correctamente.", "success")
    return redirect(url_for('home'))

@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(405)
def pagina_no_encontrada2(e):
    return render_template('404.html'), 405

# ===============================================
# AUTENTICACIÓN
# ===============================================
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        tel = request.form['tel']
        direccion = request.form['direccion']
        contra = request.form['contra']
        confirmar = request.form['confirmar']

        if contra != confirmar:
            flash('Las contraseñas no coinciden', 'error')
            return render_template('registro.html', nombre=nombre, tel=tel, direccion=direccion)

        hash_contra = bcrypt.generate_password_hash(contra).decode('utf-8')

        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cliente (nombre, direccion, telefono, contrasena, tipo)
                VALUES (?, ?, ?, ?, 'usuario')
            """, (nombre, direccion, tel, hash_contra))
            conn.commit()
            conn.close()

            flash("Registro exitoso", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("El telefono ya está registrado", "error")
            return redirect(url_for('registro'))

    return render_template('registro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        tel = request.form['tel']
        contra = request.form['contra']

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id_cliente, nombre, contrasena, tipo
            FROM cliente
            WHERE telefono = ?
        """, (tel,))
        cliente = cursor.fetchone()
        conn.close()

        if cliente and bcrypt.check_password_hash(cliente[2], contra):
            session['id_cliente'] = cliente[0]
            session['nombre'] = cliente[1]
            session['tipo'] = cliente[3]
            
            flash("Inicio de sesión exitoso", "success")
            
            # Redirigir según tipo de usuario
            if cliente[3] == 'sucursal':
                return redirect(url_for('sucursal.panel_sucursal'))
            elif cliente[3] == 'admin':
                return redirect(url_for('admin.admin'))
            else:
                return redirect(url_for('home'))

        flash("Credenciales incorrectas", "error")
        return render_template('login.html', tel=tel)

    return render_template('login.html')

@app.route("/logingoogle")
def logingoogle():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/auth/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    request_session = google_requests.Request()

    id_info = id_token.verify_oauth2_token(
        credentials._id_token,
        request_session,
        os.environ.get("GOOGLE_CLIENT_ID")
    )

    phone_number = id_info.get("phone_number")
    nombre_google = id_info.get("name", "Usuario Google")

    if not phone_number:
        session["google_temp_id"] = id_info.get("sub")
        session["nombre_google"] = nombre_google
        return redirect(url_for("pedir_telefono"))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cliente WHERE telefono = ?", (phone_number,))
    cliente = cursor.fetchone()

    if not cliente:
        cursor.execute(
            "INSERT INTO cliente (nombre, direccion, telefono, contrasena, tipo) VALUES (?, ?, ?, ?, ?)",
            (nombre_google, "", phone_number, "", "usuario")
        )
        conn.commit()
        cursor.execute("SELECT * FROM cliente WHERE telefono = ?", (phone_number,))
        cliente = cursor.fetchone()

    conn.close()

    session["id_cliente"] = cliente[0]
    session["nombre"] = cliente[1]
    session["tipo"] = cliente[3]

    flash("Inicio de sesión exitoso", "success")
    return redirect(url_for("home"))


@app.route("/pedir-telefono", methods=["GET", "POST"])
def pedir_telefono():
    if request.method == "POST":
        telefono = request.form["telefono"]
        google_id = session.get("google_temp_id")
        nombre_google = session.get("nombre_google", "Usuario Google")

        if not google_id:
            flash("Error: sesión de Google no válida.", "error")
            return redirect(url_for("login"))

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Verificamos si el teléfono ya existe
        cursor.execute("SELECT * FROM cliente WHERE telefono = ?", (telefono,))
        cliente = cursor.fetchone()

        if cliente:
            # Si ya existe, verificamos si el nombre coincide
            nombre_existente = cliente[1]
            if nombre_existente != nombre_google:
                conn.close()
                flash("El número de teléfono ya está asociado a otra cuenta. Las credenciales no coinciden.", "error")
                return redirect(url_for("login"))
        else:
            # Si no existe, creamos el usuario nuevo
            cursor.execute(
                "INSERT INTO cliente (nombre, direccion, telefono, contrasena, tipo) VALUES (?, ?, ?, ?, ?)",
                (nombre_google, "", telefono, "", "usuario")
            )
            conn.commit()
            cursor.execute("SELECT * FROM cliente WHERE telefono = ?", (telefono,))
            cliente = cursor.fetchone()

        conn.close()

        # Guardamos sesión
        session["id_cliente"] = cliente[0]
        session["nombre"] = cliente[1]
        session["tipo"] = cliente[3]


        flash("Inicio de sesión exitoso", "success")
        return redirect(url_for("home"))

    return render_template("pedir_telefono.html")

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('home'))

# ===============================================
# CARRITO
# ===============================================
@app.get('/carrito')
def carrito():
    resp = require_login_redirect()
    if resp:
        return resp

    id_cliente = session['id_cliente']
    cliente = {"id_cliente": id_cliente, "nombre": session.get('nombre', 'Usuario')}

    with get_conn() as conn:
        sucursales = listar_sucursales(conn)
        if not sucursales:
            flash("No hay sucursales cargadas.", "error")
            return redirect(url_for('home'))

        if 'cliente_sucursal_id' not in session:
            session['cliente_sucursal_id'] = sucursales[0]['id']
        
        sucursal_actual = next((s for s in sucursales if s['id'] == session['cliente_sucursal_id']), sucursales[0])

        car = ensure_carrito_abierto(conn, id_cliente)
        items, total = leer_items(conn, car['id_carrito'])
        categorias = listar_categorias(conn)

    return render_template(
        'vista_carrito.html',
        cliente=cliente,
        categorias=categorias,
        sucursales=sucursales,
        sucursal_actual=sucursal_actual,
        items=items,
        total=total,
        metodos_pago=['EFECTIVO', 'TARJETA']
    )

@app.post('/carrito/items/update')
def carrito_actualizar_item():
    resp = require_login_redirect()
    if resp:
        return resp

    id_cliente  = session['id_cliente']
    producto_id = request.form.get('producto_id', type=int)
    cantidad    = request.form.get('cantidad', type=int)

    if not producto_id or not cantidad or cantidad < 1:
        flash("Cantidad inválida.", "error")
        return redirect(url_for('carrito'))

    with get_conn() as conn:
        car = ensure_carrito_abierto(conn, id_cliente)

        ex = conn.execute("""
            SELECT id_producto_carrito
            FROM producto_carrito
            WHERE fk_carrito=? AND fk_producto=?
        """, (car['id_carrito'], producto_id)).fetchone()

        if ex:
            conn.execute("""
                UPDATE producto_carrito
                SET cantidad=?
                WHERE id_producto_carrito=?
            """, (cantidad, ex['id_producto_carrito']))
        else:
            conn.execute("""
                INSERT INTO producto_carrito(fk_producto, fk_carrito, cantidad)
                VALUES (?,?,?)
            """, (producto_id, car['id_carrito'], cantidad))

    flash("Carrito actualizado.", "success")
    return redirect(url_for('carrito'))

@app.post('/carrito/items/remove')
def carrito_eliminar_item():
    resp = require_login_redirect()
    if resp:
        return resp

    id_cliente  = session['id_cliente']
    producto_id = request.form.get('producto_id', type=int)
    if not producto_id:
        flash("Producto inválido.", "error")
        return redirect(url_for('carrito'))

    with get_conn() as conn:
        car = ensure_carrito_abierto(conn, id_cliente)
        conn.execute("""
            DELETE FROM producto_carrito
            WHERE fk_carrito=? AND fk_producto=?
        """, (car['id_carrito'], producto_id))

    flash("Producto eliminado.", "success")
    return redirect(url_for('carrito'))

@app.post('/carrito/checkout')
def carrito_checkout():
    resp = require_login_redirect()
    if resp:
        return resp

    metodo_pago = request.form.get('metodo_pago')

    if metodo_pago not in ('EFECTIVO', 'TARJETA'):
        flash("Seleccioná un método de pago válido.", "error")
        return redirect(url_for('carrito'))

    id_cliente = session['id_cliente']
    cliente_sucursal_id = session.get('cliente_sucursal_id')

    with get_conn() as conn:
        car = ensure_carrito_abierto(conn, id_cliente)

        items = conn.execute("""
            SELECT pc.fk_producto AS producto_id, pc.cantidad, 
                p.precio, 
                COALESCE(a.cantidad, 0) AS stock_sucursal
            FROM producto_carrito pc
            JOIN producto p ON p.id_producto = pc.fk_producto
            LEFT JOIN almacen_sucursal a 
                ON a.fk_producto = pc.fk_producto 
                AND a.fk_sucursal = ?
            WHERE pc.fk_carrito=?
        """, (cliente_sucursal_id, car['id_carrito'])).fetchall()

        if not items:
            flash("Tu carrito está vacío.", "error")
            return redirect(url_for('carrito'))

        # Validar stock de la sucursal
        for it in items:
            if it['stock_sucursal'] < it['cantidad']:
                flash(f"Stock insuficiente en la sucursal para uno o más productos.", "error")
                return redirect(url_for('carrito'))

        # Crear pedido
        cursor = conn.execute("""
            INSERT INTO pedido (fecha, estado, fk_cliente, fk_sucursal)
            VALUES (?, 'pendiente', ?, ?)
        """, (date.today().isoformat(), id_cliente, cliente_sucursal_id))
        
        pedido_id = cursor.lastrowid

        # Agregar detalles y descontar stock
        for it in items:
            conn.execute("""
                INSERT INTO detalles_pedido (cantidad, fk_producto, fk_pedido)
                VALUES (?, ?, ?)
            """, (it['cantidad'], it['producto_id'], pedido_id))
            
            # Descontar del almacén de la sucursal
            conn.execute("""
                UPDATE almacen_sucursal
                SET cantidad = cantidad - ?
                WHERE fk_sucursal = ? AND fk_producto = ?
            """, (it['cantidad'], cliente_sucursal_id, it['producto_id']))

        # Vaciar carrito
        conn.execute("DELETE FROM producto_carrito WHERE fk_carrito=?", (car['id_carrito'],))

    flash("¡Compra confirmada!", "success")
    return redirect(url_for('home'))

# ===============================================
# PANEL SUCURSAL
# ===============================================
@app.get('/panel-sucursal')
def panel_sucursal():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    return render_template('panel_sucursal.html')

@app.route('/sucursal/almacen')
def sucursal_almacen():
    """Ver el almacén de la sucursal con stock de productos."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    cliente_sucursal_id = session.get('id_cliente')
    
    with get_conn() as conn:
        sucursal = conn.execute("""
            SELECT nombre AS nombre, direccion AS direccion 
            FROM cliente 
            WHERE id_cliente = ?
        """, (cliente_sucursal_id,)).fetchone()
        
        productos = get_productos_sucursal(conn, cliente_sucursal_id)
    
    return render_template('sucursal_almacen.html', 
                         sucursal=sucursal, 
                         productos=productos)

@app.route('/sucursal/pedir-stock', methods=['GET', 'POST'])
def sucursal_pedir_stock():
    """Formulario para pedir reposición de stock."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    cliente_sucursal_id = session.get('id_cliente')
    
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        cantidad = request.form.get('cantidad', type=int)
        
        if not producto_id or not cantidad or cantidad < 1:
            flash("Datos inválidos.", "error")
            return redirect(url_for('sucursal_pedir_stock'))
        
        with get_conn() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO pedido_reposicion (fecha, fk_sucursal)
                    VALUES (?, ?)
                """, (date.today().isoformat(), cliente_sucursal_id))
                
                pedido_id = cursor.lastrowid
                
                conn.execute("""
                    INSERT INTO detalle_pedido_reposicion 
                    (cantidad, fk_pedido_reposicion, fk_producto)
                    VALUES (?, ?, ?)
                """, (cantidad, pedido_id, producto_id))
                
                conn.commit()
                flash("Solicitud de stock enviada correctamente.", "success")
                return redirect(url_for('sucursal_pedir_stock'))
                
            except Exception as e:
                conn.rollback()
                flash(f"Error al crear solicitud: {e}", "error")
    
    # GET - Obtener datos para el formulario
    with get_conn() as conn:
        # Obtener nombre de la sucursal
        sucursal = conn.execute("""
            SELECT nombre FROM cliente WHERE id_cliente = ?
        """, (cliente_sucursal_id,)).fetchone()
        
        sucursal_nombre = sucursal['nombre'] if sucursal else "Sucursal"
        
        # Obtener productos con su stock actual en esta sucursal
        productos = conn.execute("""
            SELECT 
                p.id_producto,
                p.nombre,
                COALESCE(a.cantidad, 0) AS stock_actual
            FROM producto p
            LEFT JOIN almacen_sucursal a 
                ON a.fk_producto = p.id_producto 
                AND a.fk_sucursal = ?
            ORDER BY p.nombre
        """, (cliente_sucursal_id,)).fetchall()
    
    return render_template('sucursal_pedir_stock.html', 
                        productos=productos,
                        sucursal_nombre=sucursal_nombre)

@app.get('/sucursal/pedidos-clientes')
def sucursal_pedidos_clientes():
    """Muestra los pedidos realizados por clientes."""
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))

    cliente_sucursal_id = session.get('id_cliente')

    with get_conn() as conn:
        pedidos = conn.execute("""
            SELECT
                ped.id_pedido,
                ped.fecha,
                ped.estado,
                cli.nombre AS cliente_nombre,
                p.nombre AS producto_nombre,
                dp.cantidad
            FROM pedido ped
            JOIN cliente cli ON cli.id_cliente = ped.fk_cliente
            JOIN detalles_pedido dp ON dp.fk_pedido = ped.id_pedido
            JOIN producto p ON p.id_producto = dp.fk_producto
            WHERE ped.fk_sucursal = ?
            ORDER BY ped.id_pedido DESC
        """, (cliente_sucursal_id,)).fetchall()

    return render_template('sucursal_pedidos_clientes.html', pedidos=pedidos)

@app.post('/sucursal/pedidos-clientes/enviar/<int:id_pedido>')
def sucursal_enviar_pedido(id_pedido):
    """Marca el pedido como enviado."""
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))

    with get_conn() as conn:
        try:
            conn.execute("""
                UPDATE pedido
                SET estado = 'enviado'
                WHERE id_pedido = ?
            """, (id_pedido,))

            conn.commit()
            flash(f"Pedido #{id_pedido} marcado como enviado.", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Error al actualizar el pedido: {e}", "error")

    return redirect(url_for('sucursal_pedidos_clientes'))

# ===============================================
# PANEL ADMIN
# ===============================================
@app.route('/administracion')
def admin():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    return render_template('admin.html')

@app.route('/admin/solicitudes')
def admin_solicitudes():
    """Ver todas las solicitudes de reposición."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    with get_conn() as conn:
        solicitudes = conn.execute("""
            SELECT 
                pr.id_pedido_reposicion AS id,
                pr.fecha,
                c.nombre AS sucursal,
                p.nombre AS producto,
                dpr.cantidad,
                pr.fk_sucursal AS sucursal_id,
                dpr.fk_producto AS producto_id
            FROM pedido_reposicion pr
            JOIN cliente c ON c.id_cliente = pr.fk_sucursal
            JOIN detalle_pedido_reposicion dpr 
                ON dpr.fk_pedido_reposicion = pr.id_pedido_reposicion
            JOIN producto p ON p.id_producto = dpr.fk_producto
            ORDER BY pr.id_pedido_reposicion DESC
        """).fetchall()
    
    return render_template('admin_solicitudes.html', solicitudes=solicitudes)

@app.route('/admin/solicitudes/aprobar/<int:solicitud_id>', methods=['POST'])
def admin_aprobar_solicitud(solicitud_id):
    """Aprobar una solicitud y transferir stock a la sucursal."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    with get_conn() as conn:
        try:
            solicitud = conn.execute("""
                SELECT 
                    pr.fk_sucursal,
                    dpr.fk_producto,
                    dpr.cantidad
                FROM pedido_reposicion pr
                JOIN detalle_pedido_reposicion dpr 
                    ON dpr.fk_pedido_reposicion = pr.id_pedido_reposicion
                WHERE pr.id_pedido_reposicion = ?
            """, (solicitud_id,)).fetchone()
            
            if not solicitud:
                flash("Solicitud no encontrada.", "error")
                return redirect(url_for('admin_solicitudes'))
            
            cliente_sucursal_id = solicitud['fk_sucursal']
            producto_id = solicitud['fk_producto']
            cantidad = solicitud['cantidad']
            
            stock_global = conn.execute("""
                SELECT stock FROM producto WHERE id_producto = ?
            """, (producto_id,)).fetchone()
            
            if not stock_global or stock_global['stock'] < cantidad:
                flash("No hay suficiente stock en el deposito.", "error")
                return redirect(url_for('admin_solicitudes'))
            
            # Restar del stock global
            conn.execute("""
                UPDATE producto 
                SET stock = stock - ? 
                WHERE id_producto = ?
            """, (cantidad, producto_id))
            
            # Sumar al almacén de la sucursal
            conn.execute("""
                INSERT INTO almacen_sucursal (fk_sucursal, fk_producto, cantidad)
                VALUES (?, ?, ?)
                ON CONFLICT(fk_sucursal, fk_producto) 
                DO UPDATE SET cantidad = cantidad + ?
            """, (cliente_sucursal_id, producto_id, cantidad, cantidad))
            
            # Eliminar la solicitud
            conn.execute("""
                DELETE FROM detalle_pedido_reposicion 
                WHERE fk_pedido_reposicion = ?
            """, (solicitud_id,))
            
            conn.execute("""
                DELETE FROM pedido_reposicion 
                WHERE id_pedido_reposicion = ?
            """, (solicitud_id,))
            
            conn.commit()
            flash("Productos enviados correctamente", "success")
            
        except Exception as e:
            conn.rollback()
            flash(f"Error al aprobar solicitud: {e}", "error")
    
    return redirect(url_for('admin_solicitudes'))

@app.route('/admin/solicitudes/rechazar/<int:solicitud_id>', methods=['POST'])
def admin_rechazar_solicitud(solicitud_id):
    """Rechazar y eliminar una solicitud."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    with get_conn() as conn:
        try:
            conn.execute("""
                DELETE FROM detalle_pedido_reposicion 
                WHERE fk_pedido_reposicion = ?
            """, (solicitud_id,))
            
            conn.execute("""
                DELETE FROM pedido_reposicion 
                WHERE id_pedido_reposicion = ?
            """, (solicitud_id,))
            
            conn.commit()
            flash("Solicitud rechazada.", "success")
            
        except Exception as e:
            conn.rollback()
            flash(f"Error al rechazar solicitud: {e}", "error")
    
    return redirect(url_for('admin_solicitudes'))

@app.route('/admin/estadisticas')
def admin_estadisticas():
    """Ver estadísticas de ventas por sucursal y totales."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    with get_conn() as conn:
        # Estadísticas por sucursal
        estadisticas_sucursales = conn.execute("""
            SELECT 
                c.nombre AS sucursal,
                COUNT(DISTINCT p.id_pedido) AS total_pedidos,
                SUM(dp.cantidad) AS productos_vendidos,
                SUM(dp.cantidad * pr.precio) AS total_ventas
            FROM pedido p
            JOIN cliente c ON c.id_cliente = p.fk_sucursal
            JOIN detalles_pedido dp ON dp.fk_pedido = p.id_pedido
            JOIN producto pr ON pr.id_producto = dp.fk_producto
            WHERE c.tipo = 'sucursal'
            GROUP BY c.id_cliente, c.nombre
            ORDER BY total_ventas DESC
        """).fetchall()
        
        # Estadísticas totales
        estadisticas_totales = conn.execute("""
            SELECT 
                COUNT(DISTINCT p.id_pedido) AS total_pedidos,
                SUM(dp.cantidad) AS productos_vendidos,
                SUM(dp.cantidad * pr.precio) AS total_ventas
            FROM pedido p
            JOIN detalles_pedido dp ON dp.fk_pedido = p.id_pedido
            JOIN producto pr ON pr.id_producto = dp.fk_producto
        """).fetchone()
        
        # Productos más vendidos
        productos_mas_vendidos = conn.execute("""
            SELECT 
                pr.nombre AS producto,
                SUM(dp.cantidad) AS cantidad_vendida,
                SUM(dp.cantidad * pr.precio) AS ingresos
            FROM detalles_pedido dp
            JOIN producto pr ON pr.id_producto = dp.fk_producto
            GROUP BY pr.id_producto, pr.nombre
            ORDER BY cantidad_vendida DESC
            LIMIT 5
        """).fetchall()
    
    return render_template('admin_estadisticas.html', 
                        estadisticas_sucursales=estadisticas_sucursales,
                        estadisticas_totales=estadisticas_totales,
                        productos_mas_vendidos=productos_mas_vendidos)


# ===============================================
# GESTIÓN DE PRODUCTOS (ADMIN)
# ===============================================
@app.route('/crear-producto', methods=['GET', 'POST'])
def crear_producto():
    resp = require_login_redirect()
    if resp:
        return resp

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        precio = request.form.get('precio')
        stock = request.form.get('stock')
        categoria = request.form.get('categoria')

        if not nombre or not precio or not stock or not categoria:
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('crear_producto'))

        try:
            precio = float(precio)
            stock = int(stock)
        except ValueError:
            flash('Precio y stock deben ser números válidos', 'error')
            return redirect(url_for('crear_producto'))

        imagen_data = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    imagen_data = file.read()
                else:
                    flash('Formato de imagen no permitido', 'error')
                    return redirect(url_for('crear_producto'))

        with get_conn() as conn:
            cat_row = conn.execute("SELECT id_categoria FROM categoria WHERE nombre = ?", (categoria,)).fetchone()
            if not cat_row:
                flash('Categoría no válida', 'error')
                return redirect(url_for('crear_producto'))

            fk_categoria = cat_row['id_categoria']

            conn.execute("""
                INSERT INTO producto (nombre, precio, stock, fk_categoria, imagen)
                VALUES (?, ?, ?, ?, ?)
            """, (nombre, precio, stock, fk_categoria, imagen_data))
            conn.commit()

        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('home'))

    with get_conn() as conn:
        categorias = listar_categorias(conn)

    return render_template('crear_producto.html', categorias=categorias)

@app.route('/editar-productos')
def listar_productos_para_editar():
    resp = require_login_redirect()
    if resp:
        return resp
    
    with get_conn() as conn:
        productos = conn.execute("SELECT id_producto, nombre, precio, stock FROM producto").fetchall()
    return render_template('listar_productos.html', productos=productos)

@app.route('/editar-producto/<int:id_producto>', methods=['GET', 'POST'])
def editar_producto(id_producto):
    resp = require_login_redirect()
    if resp:
        return resp

    with get_conn() as conn:
        categorias = listar_categorias(conn)
        
        producto = conn.execute("""
            SELECT p.id_producto, p.nombre, p.precio, p.stock, c.nombre AS categoria
            FROM producto p
            JOIN categoria c ON p.fk_categoria = c.id_categoria
            WHERE p.id_producto = ?
        """, (id_producto,)).fetchone()

        if not producto:
            flash('Producto no encontrado', 'error')
            return redirect(url_for('home'))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        precio = request.form.get('precio')
        stock = request.form.get('stock')
        categoria = request.form.get('categoria')

        if not nombre or not precio or not stock or not categoria:
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('editar_producto', id_producto=id_producto))

        try:
            precio = float(precio)
            stock = int(stock)
        except ValueError:
            flash('Precio y stock deben ser números válidos', 'error')
            return redirect(url_for('editar_producto', id_producto=id_producto))

        imagen_data = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    imagen_data = file.read()
                else:
                    flash('Formato de imagen no permitido', 'error')
                    return redirect(url_for('editar_producto', id_producto=id_producto))

        with get_conn() as conn:
            cat_row = conn.execute("SELECT id_categoria FROM categoria WHERE nombre = ?", (categoria,)).fetchone()
            if not cat_row:
                flash('Categoría no válida', 'error')
                return redirect(url_for('editar_producto', id_producto=id_producto))

            fk_categoria = cat_row['id_categoria']

            if imagen_data:
                conn.execute("""
                    UPDATE producto
                    SET nombre = ?, precio = ?, stock = ?, fk_categoria = ?, imagen = ?
                    WHERE id_producto = ?
                """, (nombre, precio, stock, fk_categoria, imagen_data, id_producto))
            else:
                conn.execute("""
                    UPDATE producto
                    SET nombre = ?, precio = ?, stock = ?, fk_categoria = ?
                    WHERE id_producto = ?
                """, (nombre, precio, stock, fk_categoria, id_producto))

            conn.commit()

        flash('Producto actualizado correctamente', 'success')
        return redirect(url_for('home'))

    return render_template('editar_producto.html', categorias=categorias, producto=producto)

# ===============================================
# PRODUCTOS (VISTA GENERAL)
# ===============================================

@app.post('/productos/editar')
def productos_editar():
    flash("Editar producto: pendiente de implementar", "error")
    return redirect(url_for('productos'))

@app.post('/productos/<int:prod_id>/activar')
def productos_activar(prod_id):
    flash(f"Activar producto {prod_id}: pendiente", "error")
    return redirect(url_for('productos'))

@app.post('/productos/<int:prod_id>/desactivar')
def productos_desactivar(prod_id):
    flash(f"Desactivar producto {prod_id}: pendiente", "error")
    return redirect(url_for('productos'))


# ===============================================
# COMPRAS DEL CLIENTE
# ===============================================
@app.route('/mis-compras')
def mis_compras():
    """Ver historial de compras del cliente."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'usuario':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    id_cliente = session['id_cliente']
    
    with get_conn() as conn:
        # Obtener datos del cliente
        cliente = conn.execute("""
            SELECT nombre, direccion, telefono
            FROM cliente
            WHERE id_cliente = ?
        """, (id_cliente,)).fetchone()
        
        # Obtener todos los pedidos del cliente con sus productos
        pedidos = conn.execute("""
            SELECT 
                p.id_pedido,
                p.fecha,
                p.estado,
                s.nombre AS sucursal,
                GROUP_CONCAT(prod.nombre || '|' || dp.cantidad || '|' || prod.precio, '###') AS productos_info,
                SUM(dp.cantidad * prod.precio) AS total
            FROM pedido p
            LEFT JOIN cliente s ON s.id_cliente = p.fk_sucursal
            JOIN detalles_pedido dp ON dp.fk_pedido = p.id_pedido
            JOIN producto prod ON prod.id_producto = dp.fk_producto
            WHERE p.fk_cliente = ?
            GROUP BY p.id_pedido
            ORDER BY p.id_pedido DESC
        """, (id_cliente,)).fetchall()
        
        # Procesar los productos de cada pedido
        pedidos_procesados = []
        for pedido in pedidos:
            productos_raw = pedido['productos_info'].split('###') if pedido['productos_info'] else []
            productos = []
            for prod_info in productos_raw:
                partes = prod_info.split('|')
                if len(partes) == 3:
                    productos.append({
                        'nombre': partes[0],
                        'cantidad': int(partes[1]),
                        'precio': float(partes[2]),
                        'subtotal': int(partes[1]) * float(partes[2])
                    })
            
            pedidos_procesados.append({
                'id_pedido': pedido['id_pedido'],
                'fecha': pedido['fecha'],
                'estado': pedido['estado'],
                'sucursal': pedido['sucursal'],
                'total': pedido['total'],
                'productos': productos
            })
    
    return render_template('compras_cliente.html', 
                         cliente=cliente,
                         pedidos=pedidos_procesados)

@app.route('/actualizar-direccion', methods=['POST'])
def actualizar_direccion():
    """Actualizar la dirección del cliente."""
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'usuario':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    
    id_cliente = session['id_cliente']
    nueva_direccion = request.form.get('direccion', '').strip()
    
    if not nueva_direccion:
        flash("La dirección no puede estar vacía.", "error")
        return redirect(url_for('mis_compras'))
    
    with get_conn() as conn:
        try:
            conn.execute("""
                UPDATE cliente
                SET direccion = ?
                WHERE id_cliente = ?
            """, (nueva_direccion, id_cliente))
            conn.commit()
            flash("Dirección actualizada correctamente.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error al actualizar dirección: {e}", "error")
    
    return redirect(url_for('mis_compras'))




# ===============================================
# MAIN
# ===============================================
if __name__ == '__main__':
    app.run(debug=True)