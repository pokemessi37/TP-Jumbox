from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import base64
from app.utils import get_conn, listar_sucursales, listar_categorias

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    categoria_filtro = request.args.get('categoria', None)
    conn = get_conn()

    sucursales = listar_sucursales(conn)
    
    if 'cliente_sucursal_id' not in session and sucursales:
        session['cliente_sucursal_id'] = sucursales[0]['id']
    
    cliente_sucursal_id = session.get('cliente_sucursal_id')

    categorias = conn.execute("SELECT nombre FROM categoria ORDER BY nombre").fetchall()
    categorias_lista = [c['nombre'] for c in categorias]

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

@main_bp.route('/cambiar-sucursal', methods=['POST'])
def cambiar_sucursal():
    cliente_sucursal_id = request.form.get('cliente_sucursal_id', type=int)
    if not cliente_sucursal_id:
        flash("Selecciona una sucursal válida.", "error")
    else:
        session['cliente_sucursal_id'] = cliente_sucursal_id
        flash("Sucursal cambiada correctamente.", "success")
    return redirect(url_for('main.home'))

@main_bp.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404

@main_bp.errorhandler(405)
def pagina_no_encontrada2(e):
    return render_template('404.html'), 405