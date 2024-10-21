import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

class Config:
    SECRET_KEY = os.environ.get('BED_GENERATOR_FLASK_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TYPE = 'filesystem'
    DRAFT_BED_FILES_DIR = os.environ.get('DRAFT_BED_FILES_DIR') or \
        os.path.join(os.path.abspath(os.path.dirname(__file__)), 'draft_bedfiles')

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test_transcript.db'
    DRAFT_BED_FILES_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'test_draft_bedfiles')