#!/bin/sh

# Initialize the database if migrations directory doesn't exist
if [ ! -d "migrations" ]; then
    echo "Initializing database..."
    flask db init
fi

# Check if there are any pending migrations
if flask db current > /dev/null 2>&1; then
    if flask db check > /dev/null 2>&1; then
        echo "No pending migrations."
    else
        echo "Running database migrations..."
        flask db migrate
        flask db upgrade
    fi
else
    echo "Running first migration..."
    flask db migrate
    flask db upgrade
fi

# Start the application
exec gunicorn -b 0.0.0.0:5000 run:app