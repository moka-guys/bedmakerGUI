from app import create_app, db
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

app = create_app()
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for static files

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
    app.secret_key = os.getenv('SECRET_KEY')  # Load secret key from environment
