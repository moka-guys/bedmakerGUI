#!/bin/sh

# Initialize the database
flask db init

# Run database migrations
flask db migrate
flask db upgrade

# Start the application
exec gunicorn -b 0.0.0.0:5000 run:app