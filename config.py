import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

class Config:
    # Require SECRET_KEY to be set in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY and os.environ.get('FLASK_ENV') == 'production':
        raise ValueError("SECRET_KEY must be set in production")
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:////' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TYPE = 'filesystem'
    DRAFT_BED_FILES_DIR = os.environ.get('DRAFT_BED_FILES_DIR') or \
        os.path.join(os.path.abspath(os.path.dirname(__file__)), 'draft_bedfiles')

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/test_app.db'
    DRAFT_BED_FILES_DIR = '/app/test_draft_bedfiles'