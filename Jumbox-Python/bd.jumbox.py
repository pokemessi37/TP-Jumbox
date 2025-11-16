import sqlite3

conn = sqlite3.connect('jumbox.db')
cursor = conn.cursor()


cursor.execute('''
CREATE TABLE IF NOT EXISTS categoria (
  id_categoria INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS cliente (
  id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  direccion TEXT NOT NULL,
  telefono INTEGER NOT NULL UNIQUE,
  contrasena TEXT,
  tipo TEXT DEFAULT 'usuario'
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS sucursal (
  id_sucursal INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_cliente INTEGER)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS producto (
  id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  precio REAL NOT NULL,
  stock INTEGER NOT NULL,
  fk_categoria INTEGER NOT NULL, imagen BLOB,
  FOREIGN KEY (fk_categoria) REFERENCES categoria(id_categoria)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS carrito (
  id_carrito INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_cliente INTEGER NOT NULL,
  FOREIGN KEY (fk_cliente) REFERENCES cliente(id_cliente)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS "pedido" (
  id_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL,
  estado TEXT NOT NULL,
  fk_cliente INTEGER NOT NULL,
  fk_sucursal INTEGER,
  FOREIGN KEY (fk_cliente) REFERENCES cliente(id_cliente)
    ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY (fk_sucursal) REFERENCES cliente(id_cliente)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS "pedido_reposicion" (
  id_pedido_reposicion INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL,
  fk_sucursal INTEGER NOT NULL,
  FOREIGN KEY (fk_sucursal) REFERENCES cliente(id_cliente)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)

''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS "detalles_pedido" (
  id_detalles_pedido INTEGER PRIMARY KEY AUTOINCREMENT,
  cantidad INTEGER NOT NULL,
  fk_producto INTEGER NOT NULL,
  fk_pedido INTEGER NOT NULL,
  FOREIGN KEY (fk_producto) REFERENCES producto(id_producto)
    ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY (fk_pedido) REFERENCES pedido(id_pedido)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS "detalle_pedido_reposicion" (
  id_detalle_pedido_reposicion INTEGER PRIMARY KEY AUTOINCREMENT,
  cantidad INTEGER NOT NULL,
  fk_pedido_reposicion INTEGER NOT NULL,
  fk_producto INTEGER NOT NULL,
  FOREIGN KEY (fk_pedido_reposicion) REFERENCES pedido_reposicion(id_pedido_reposicion)
    ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY (fk_producto) REFERENCES producto(id_producto)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS producto_carrito (
  id_producto_carrito INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_producto INTEGER NOT NULL,
  fk_carrito INTEGER NOT NULL,
  cantidad INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (fk_producto) REFERENCES producto(id_producto)
    ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY (fk_carrito) REFERENCES carrito(id_carrito)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS "almacen_sucursal" (
  id_almacen_sucursal INTEGER PRIMARY KEY AUTOINCREMENT,
  fk_sucursal INTEGER NOT NULL,
  fk_producto INTEGER NOT NULL,
  cantidad INTEGER NOT NULL DEFAULT 0,
  UNIQUE (fk_sucursal, fk_producto),
  FOREIGN KEY (fk_sucursal) REFERENCES cliente(id_cliente)
    ON DELETE NO ACTION ON UPDATE NO ACTION,
  FOREIGN KEY (fk_producto) REFERENCES producto(id_producto)
    ON DELETE NO ACTION ON UPDATE NO ACTION
)
''')


conn.commit()
conn.close()