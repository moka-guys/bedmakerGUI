from flask import Blueprint

bed_generator_bp = Blueprint('bed_generator', __name__)

from app.bed_generator import routes