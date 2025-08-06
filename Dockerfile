FROM python:3.11-slim

# Install system dependencies including Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create auth directory
RUN mkdir -p auth

# Copy application code
COPY . .

# Expose port (Railway will inject the actual PORT)
EXPOSE $PORT

# Start the application using Railway's PORT environment variable
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port $PORT"] 