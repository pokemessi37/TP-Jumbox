from flask import Blueprint


main = Blueprint("main", __name__)


# ===============================================
# CARRITO
# ===============================================
@main.get('/carrito')
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

@main.post('/carrito/items/update')
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

@main.post('/carrito/items/remove')
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

@main.post('/carrito/checkout')
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
# COMPRAS DEL CLIENTE
# ===============================================
@main.route('/mis-compras')
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

@main.route('/actualizar-direccion', methods=['POST'])
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