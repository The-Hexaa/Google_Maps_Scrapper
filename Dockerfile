# Use the official Python image as a base with version 3.11.4
FROM python:3.11.4

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install system dependencies for Playwright, psycopg2, Node.js, and other required tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg curl libxshmfence1 \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libx11-xcb1 libcups2 \
    libdbus-glib-1-2 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libpq-dev gcc \
    libgtk-3-0 libx11-xcb1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install psycopg2
RUN pip install psycopg2

# Install Node.js and npm
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install project dependencies without caching
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its dependencies
# RUN npm install -g playwright && \
    # playwright install --with-deps chromium firefox webkit
# Install Playwright using pip
# RUN pip install playwright

# Install Playwright browsers with dependencies   --with-deps chromium firefox webkit
RUN playwright install --with-deps chromium

# Create a non-root user for running the application in production
# RUN useradd -ms /bin/bash appuser && chown -R appuser:appuser /app

# Switch to the non-root user
USER root

# Set environment variables for Flask
ENV FLASK_APP=main.py
ENV FLASK_ENV=production

# Run Flask-Migrate commands to apply database migrations
# RUN flask db upgrade  # Ensure migrations are applied

# Expose the port Flask runs on
EXPOSE 5000

# Run the Flask application
CMD ["python", "main.py"]
