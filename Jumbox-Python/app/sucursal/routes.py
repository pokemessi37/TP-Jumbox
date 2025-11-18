from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import date
from app.utils import (get_conn, require_login_redirect, get_productos_sucursal)

sucursal_bp = Blueprint('sucursal', __name__, template_folder='../../templates/sucursal')

@sucursal_bp.get('/panel-sucursal')
def panel_sucursal():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    return render_template('panel_sucursal.html')

@sucursal_bp.route('/sucursal/almacen')
def sucursal_almacen():
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    
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

@sucursal_bp.route('/sucursal/pedir-stock', methods=['GET', 'POST'])
def sucursal_pedir_stock():
    resp = require_login_redirect()
    if resp:
        return resp
    
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))
    
    cliente_sucursal_id = session.get('id_cliente')
    
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        cantidad = request.form.get('cantidad', type=int)
        
        if not producto_id or not cantidad or cantidad < 1:
            flash("Datos inválidos.", "error")
            return redirect(url_for('sucursal.sucursal_pedir_stock'))
        
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
                return redirect(url_for('sucursal.sucursal_pedir_stock'))
                
            except Exception as e:
                conn.rollback()
                flash(f"Error al crear solicitud: {e}", "error")
    
    with get_conn() as conn:
        sucursal = conn.execute("""
            SELECT nombre FROM cliente WHERE id_cliente = ?
        """, (cliente_sucursal_id,)).fetchone()
        
        sucursal_nombre = sucursal['nombre'] if sucursal else "Sucursal"
        
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

@sucursal_bp.get('/sucursal/pedidos-clientes')
def sucursal_pedidos_clientes():
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))

    cliente_sucursal_id = session.get('id_cliente')

    with get_conn() as conn:
        # Agrupar pedidos completos, no por producto
        pedidos = conn.execute("""
            SELECT
                ped.id_pedido,
                ped.fecha,
                ped.estado,
                cli.nombre AS cliente_nombre,
                cli.telefono AS cliente_telefono,
                cli.direccion AS cliente_direccion,
                GROUP_CONCAT(p.nombre || '|' || dp.cantidad, '###') AS productos_detalle,
                SUM(dp.cantidad * p.precio) AS total
            FROM pedido ped
            JOIN cliente cli ON cli.id_cliente = ped.fk_cliente
            JOIN detalles_pedido dp ON dp.fk_pedido = ped.id_pedido
            JOIN producto p ON p.id_producto = dp.fk_producto
            WHERE ped.fk_sucursal = ?
            GROUP BY ped.id_pedido
            ORDER BY ped.id_pedido DESC
        """, (cliente_sucursal_id,)).fetchall()
        
        # Procesar los productos de cada pedido
        pedidos_procesados = []
        for pedido in pedidos:
            productos = []
            if pedido['productos_detalle']:
                for prod_info in pedido['productos_detalle'].split('###'):
                    partes = prod_info.split('|')
                    if len(partes) == 2:
                        productos.append({
                            'nombre': partes[0],
                            'cantidad': int(partes[1])
                        })
            
            pedidos_procesados.append({
                'id_pedido': pedido['id_pedido'],
                'fecha': pedido['fecha'],
                'estado': pedido['estado'],
                'cliente_nombre': pedido['cliente_nombre'],
                'cliente_telefono': pedido['cliente_telefono'],
                'cliente_direccion': pedido['cliente_direccion'],
                'productos': productos,
                'total': pedido['total']
            })

    return render_template('sucursal/sucursal_pedidos_clientes.html', pedidos=pedidos_procesados)

@sucursal_bp.post('/sucursal/pedidos-clientes/enviar/<int:id_pedido>')
def sucursal_enviar_pedido(id_pedido):
    resp = require_login_redirect()
    if resp:
        return resp
    if session.get('tipo') != 'sucursal':
        flash("No autorizado.", "error")
        return redirect(url_for('main.home'))

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

    return redirect(url_for('sucursal.sucursal_pedidos_clientes'))