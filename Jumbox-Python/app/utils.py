import sqlite3
from flask import session, redirect, url_for, flash, current_app

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_conn():
    """Conexión SQLite con row_factory y FK on."""
    conn = sqlite3.connect(current_app.config["DB_NAME"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def require_login_redirect():
    """Si no hay sesión, redirige a /login."""
    if 'id_cliente' not in session:
        flash("Necesitás iniciar sesión.", "error")
        return redirect(url_for('auth.login'))
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