from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.utils import (get_conn, require_login_redirect, listar_categorias, allowed_file)

admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')

@admin_bp.route('/administracion')
def admin():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    return render_template('admin.html')

@admin_bp.route('/admin/solicitudes')
def admin_solicitudes():
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    
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

@admin_bp.route('/admin/solicitudes/aprobar/<int:solicitud_id>', methods=['POST'])
def admin_aprobar_solicitud(solicitud_id):
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    
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
                return redirect(url_for('admin.admin_solicitudes'))
            
            cliente_sucursal_id = solicitud['fk_sucursal']
            producto_id = solicitud['fk_producto']
            cantidad = solicitud['cantidad']
            
            stock_global = conn.execute("""
                SELECT stock FROM producto WHERE id_producto = ?
            """, (producto_id,)).fetchone()
            
            if not stock_global or stock_global['stock'] < cantidad:
                flash("No hay suficiente stock en el deposito.", "error")
                return redirect(url_for('admin.admin_solicitudes'))
            
            conn.execute("""
                UPDATE producto 
                SET stock = stock - ? 
                WHERE id_producto = ?
            """, (cantidad, producto_id))
            
            conn.execute("""
                INSERT INTO almacen_sucursal (fk_sucursal, fk_producto, cantidad)
                VALUES (?, ?, ?)
                ON CONFLICT(fk_sucursal, fk_producto) 
                DO UPDATE SET cantidad = cantidad + ?
            """, (cliente_sucursal_id, producto_id, cantidad, cantidad))
            
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
    
    return redirect(url_for('admin.admin_solicitudes'))

@admin_bp.route('/admin/estadisticas')
def admin_estadisticas():
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'admin':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    
    with get_conn() as conn:
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
        
        estadisticas_totales = conn.execute("""
            SELECT 
                COUNT(DISTINCT p.id_pedido) AS total_pedidos,
                SUM(dp.cantidad) AS productos_vendidos,
                SUM(dp.cantidad * pr.precio) AS total_ventas
            FROM pedido p
            JOIN detalles_pedido dp ON dp.fk_pedido = p.id_pedido
            JOIN producto pr ON pr.id_producto = dp.fk_producto
        """).fetchone()
        
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

@admin_bp.route('/crear-producto', methods=['GET', 'POST'])
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
            return redirect(url_for('admin.crear_producto'))

        try:
            precio = float(precio)
            stock = int(stock)
        except ValueError:
            flash('Precio y stock deben ser números válidos', 'error')
            return redirect(url_for('admin.crear_producto'))

        imagen_data = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    imagen_data = file.read()
                else:
                    flash('Formato de imagen no permitido', 'error')
                    return redirect(url_for('admin.crear_producto'))

        with get_conn() as conn:
            cat_row = conn.execute("SELECT id_categoria FROM categoria WHERE nombre = ?", (categoria,)).fetchone()
            if not cat_row:
                flash('Categoría no válida', 'error')
                return redirect(url_for('admin.crear_producto'))

            fk_categoria = cat_row['id_categoria']

            conn.execute("""
                INSERT INTO producto (nombre, precio, stock, fk_categoria, imagen)
                VALUES (?, ?, ?, ?, ?)
            """, (nombre, precio, stock, fk_categoria, imagen_data))
            conn.commit()

        flash('Producto creado exitosamente', 'success')
        return redirect(url_for('main.home'))

    with get_conn() as conn:
        categorias = listar_categorias(conn)

    return render_template('crear_producto.html', categorias=categorias)

@admin_bp.route('/editar-productos')
def listar_productos_para_editar():
    resp = require_login_redirect()
    if resp:
        return resp
    
    with get_conn() as conn:
        productos = conn.execute("SELECT id_producto, nombre, precio, stock FROM producto").fetchall()
    return render_template('listar_productos.html', productos=productos)

@admin_bp.route('/editar-producto/<int:id_producto>', methods=['GET', 'POST'])
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
            return redirect(url_for('main.home'))

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        precio = request.form.get('precio')
        stock = request.form.get('stock')
        categoria = request.form.get('categoria')

        if not nombre or not precio or not stock or not categoria:
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('admin.editar_producto', id_producto=id_producto))

        try:
            precio = float(precio)
            stock = int(stock)
        except ValueError:
            flash('Precio y stock deben ser números válidos', 'error')
            return redirect(url_for('admin.editar_producto', id_producto=id_producto))

        imagen_data = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                if allowed_file(file.filename):
                    imagen_data = file.read()
                else:
                    flash('Formato de imagen no permitido', 'error')
                    return redirect(url_for('admin.editar_producto', id_producto=id_producto))

        with get_conn() as conn:
            cat_row = conn.execute("SELECT id_categoria FROM categoria WHERE nombre = ?", (categoria,)).fetchone()
            if not cat_row:
                flash('Categoría no válida', 'error')
                return redirect(url_for('admin.editar_producto', id_producto=id_producto))

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
        return redirect(url_for('main.home'))

    return render_template('editar_producto.html', categorias=categorias, producto=producto)

@admin_bp.post('/productos/editar')
def productos_editar():
    flash("Editar producto: pendiente de implementar", "error")
    return redirect(url_for('admin.productos'))
