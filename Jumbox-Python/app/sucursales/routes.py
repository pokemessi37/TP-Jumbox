from flask import Blueprint


main = Blueprint("main", __name__)


# ===============================================
# PANEL SUCURSAL
# ===============================================
@main.get('/panel-sucursal')
def panel_sucursal():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('home'))
    return render_template('panel_sucursal.html')

@main.route('/sucursal/almacen')
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

@main.route('/sucursal/pedir-stock', methods=['GET', 'POST'])
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

@main.get('/sucursal/pedidos-clientes')
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

@main.post('/sucursal/pedidos-clientes/enviar/<int:id_pedido>')
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
