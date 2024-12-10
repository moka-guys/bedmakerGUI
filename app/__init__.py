import os
from flask import Flask
from flask_bootstrap import Bootstrap
from flask_session import Session
from config import Config
from .extensions import db, login_manager, migrate
import logging
from logging.handlers import RotatingFileHandler

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    Bootstrap(app)
    Session(app)
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'

    # Register blueprints
    from app.bed_generator import bed_generator_bp
    from app.bed_manager import bed_manager_bp
    from app.auth import auth_bp

    app.register_blueprint(bed_generator_bp, url_prefix='/bed_generator')
    app.register_blueprint(bed_manager_bp, url_prefix='/bed_manager')
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # Set up logging
    if not app.debug and not app.testing:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler('logs/bed_generator.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('BED Generator startup')

    @app.context_processor
    def inject_version():
        return dict(app_version=app.config['VERSION'])

    return app

from app import models

@login_manager.user_loader
def load_user(user_id):
    return models.User.query.get(int(user_id))
