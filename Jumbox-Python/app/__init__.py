import os
from flask import Flask
from dotenv import load_dotenv

from flask_bcrypt import Bcrypt


def create_app():
    load_dotenv()

    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    app.config["DB_NAME"] = "jumbox.db"

    # inicializar extensiones
    bcrypt.init_app(app)

    # registrar blueprints
    from .main.routes import main_bp
    from .auth.routes import auth_bp
    from .users.routes import carrito_bp
    from .sucursal.routes import sucursal_bp
    from .admin.routes import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(carrito_bp)
    app.register_blueprint(sucursal_bp)
    app.register_blueprint(admin_bp)

    return app