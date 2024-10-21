from flask import Blueprint

bed_manager_bp = Blueprint('bed_manager', __name__)

from app.bed_manager import routes
