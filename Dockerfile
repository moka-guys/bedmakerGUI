# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . .

# Make entrypoint.sh executable
RUN chmod +x /app/entrypoint.sh

# Create a non-root user and switch to it
RUN useradd -m myuser
RUN chown -R myuser:myuser /app
USER myuser

# Run entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]