from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from app.auth import routes

# Import Flask-Login
from flask_login import LoginManager

# Create LoginManager instance
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# User loader function
@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))
